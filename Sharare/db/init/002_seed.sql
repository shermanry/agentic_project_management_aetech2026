-- Seed: a slice of the NYC facade survey (Sharare/docs/use-case/facade-inspection.md,
-- Ryan/usecase-facade-survey.md) plus the start of Ryan's Slack intake story (use-cases-and-decisions.md §1.1).
-- After boot:
--   SELECT ref, input_ref, cited_version_no, newer_version_no FROM stale_decisions;
--     -> D-014 stale (forecast changed), D-011 stale (airspace approval moved FAA -> DHS)
--   SELECT ref, statement FROM decision_proposals;          -> Jev's proposal to move to Fri 20 Nov
--   SELECT ref, title, status FROM nodes WHERE status = 'candidate';   -> "Drone 4A needs maintenance" from Slack
--   SELECT * FROM lineage((SELECT version_id FROM decision_current WHERE ref = 'D-014'), 3);

INSERT INTO users (id, name, kind) VALUES
    ('u_dev',      'Dev K. (pilot)',            'human'),
    ('u_mara',     'Mara S. (project lead)',    'human'),
    ('u_mary',     'Mary (equipment owner)',    'human'),
    ('u_alice',    'Alice (field tech)',        'human'),
    ('u_client',   'Client rep',                'human'),
    ('agent_jev',  'Jev',                       'agent'),
    ('agent_loop', 'Analysis loop',             'agent'),
    ('svc_worker', 'Capture worker',            'service');

INSERT INTO projects (id, name, description, pack, settings) VALUES
    ('p_facade', 'NYC facade survey', 'Drone facade inspection and repair estimate, Manhattan', 'nyc-facade-survey',
     '{"limits": {"max_gust_mph": 20, "max_rain_pct": 30, "min_visibility_mi": 3}}');

INSERT INTO project_members (project_id, user_id, view_level, can_review) VALUES
    ('p_facade', 'u_dev',    'advanced', true),
    ('p_facade', 'u_mara',   'medium',   true),
    ('p_facade', 'u_mary',   'medium',   true),
    ('p_facade', 'u_alice',  'medium',   false),
    ('p_facade', 'u_client', 'basic',    false);

-- rules seeded in the facade survey pack (Ryan/agent-architecture.md §3)
INSERT INTO rules (id, pack, applies_to, when_expr, then_actions, why, written_by, status) VALUES
    ('rule_031', 'nyc-facade-survey', '{"type": "decision", "tags": ["permit-date"]}',
     'state == ''awaiting_inputs'' and days_until(deadline) <= sum(lead_time_days of missing inputs) + 3',
     '[{"action": "raise_attention", "level": "red", "for": ["pm", "pilot"]}, {"action": "nudge_owners_of", "target": "missing_inputs", "via": "messenger_nanny"}]',
     'On past facade jobs the permit date slipped because inputs arrived after the 30-day cutoff', 'agent_loop', 'active'),
    ('rule_040', 'nyc-facade-survey', '{"type": "decision"}',
     'any cited input has a newer version',
     '[{"action": "raise_attention", "level": "red", "for": ["pilot", "pm"]}, {"action": "run_specialist", "agent": "scheduler"}]',
     'A decision resting on an outdated forecast or rule should be re-checked', 'u_mara', 'active');

DO $$
DECLARE
    n_weather bigint; n_rule bigint; n_pkg bigint; n_crew bigint; n_auth bigint; n_window bigint; n_flight bigint;
    n_drone bigint; n_maint bigint; n_d014 bigint; n_d011 bigint;
    w1 bigint; w2 bigint; r1 bigint; r2 bigint; pkg1 bigint; crew1 bigint; auth1 bigint; win1 bigint; maint1 bigint;
    d014_1 bigint; d014_2 bigint; d014_3 bigint; d011_1 bigint;
    run_win bigint; run_sched bigint; ev_w2 bigint; ev_slack bigint;
BEGIN
    -- ------------------------------------------------ shared registry entity (G5, A3)
    INSERT INTO nodes (project_id, type, ref, title, state, owner_id, data, created_by)
        VALUES (NULL, 'entity', 'DRONE-4A', 'Drone 4A', 'active', 'u_mary',
                '{"kind": "drone", "registration": "FA3XK4A9", "model": "M30T"}', 'u_mary') RETURNING id INTO n_drone;
    INSERT INTO entity_aliases VALUES (n_drone, 'drone 4a'), (n_drone, 'drone 4-a'), (n_drone, '4a');

    -- ------------------------------------------------ project nodes
    INSERT INTO nodes (project_id, type, ref, title, state, importance, created_by, tags)
        VALUES ('p_facade', 'data_feed', 'W-01', 'Site forecast (NWS, hourly)', 'changed', 0.9, 'svc_worker', '{weather}') RETURNING id INTO n_weather;
    INSERT INTO nodes (project_id, type, ref, title, state, importance, created_by, tags)
        VALUES ('p_facade', 'constraint', 'R-01', 'Airspace approval for Manhattan drone flights', 'changed', 0.8, 'u_mara', '{permit}') RETURNING id INTO n_rule;
    INSERT INTO nodes (project_id, type, ref, title, state, owner_id, phase, importance, created_by, tags)
        VALUES ('p_facade', 'deliverable', 'DOC-07', 'NYPD permit package', 'delivered', 'u_mara', 'permitting', 0.7, 'u_mara', '{permit}') RETURNING id INTO n_pkg;
    INSERT INTO nodes (project_id, type, ref, title, state, importance, created_by, tags)
        VALUES ('p_facade', 'constraint', 'C-03', 'Crew availability: Dev K.', 'active', 0.5, 'u_dev', '{schedule}') RETURNING id INTO n_crew;
    INSERT INTO nodes (project_id, type, ref, title, state, valid_from, valid_to, importance, created_by, tags)
        VALUES ('p_facade', 'event', 'E-09', 'Flight authorization window', 'scheduled',
                '2026-11-18 07:00-05', '2026-11-22 17:00-05', 0.9, 'u_mara', '{permit,schedule}') RETURNING id INTO n_auth;
    INSERT INTO nodes (project_id, type, ref, title, state, importance, created_by, tags)
        VALUES ('p_facade', 'analysis', 'A-01', 'Flight window (wind, rain, visibility)', 'stale', 0.8, 'agent_jev', '{weather,schedule}') RETURNING id INTO n_window;
    INSERT INTO nodes (project_id, type, ref, title, state, due, phase, owner_id, importance, created_by, tags, data)
        VALUES ('p_facade', 'event', 'F-01', 'North facade test flight', 'scheduled', '2026-11-19 08:00-05', 'flight', 'u_dev', 0.9,
                'u_dev', '{flight}', jsonb_build_object('equipment', jsonb_build_array('DRONE-4A'))) RETURNING id INTO n_flight;

    INSERT INTO sources (node_id, connector, refresh_policy, cron, change_threshold, capture_instruction)
        VALUES (n_weather, 'http:nws', 'periodic', '0 6 * * *', '{"gust_mph": 5, "rain_pct": 15}',
                'Hourly wind, gusts, rain probability and visibility for the site, 07:00-17:00, next 5 days. Hourly polling inside 72 h of a flight.');

    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_rule, 1, 'Drone flights in Class B airspace over Manhattan need FAA LAANC authorization; NYPD issues the take-off permit.',
                'u_mara', '2026-10-20 09:00Z', 'h_r1') RETURNING id INTO r1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_crew, 1, 'Dev K. is free 18-22 Nov; booked on another project from 23 Nov.',
                'u_dev', '2026-10-21 15:00Z', 'h_c1') RETURNING id INTO crew1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash, raw_uri)
        VALUES (n_pkg, 1, 'Permit package: flight plans, elevations, pilot/observer positions, drone registration FA3XK4A9, insurance, owner letter, community notice.',
                'u_mara', '2026-10-25 12:00Z', 'h_p1', 'data/raw/h_p1') RETURNING id INTO pkg1;
    INSERT INTO node_versions (node_id, version_no, parent_version_id, content_text, created_by, valid_at, content_hash)
        VALUES (n_rule, 2, r1, 'During the FIFA security period airspace approval moved from the FAA to DHS. NYPD needs DHS airspace approval before issuing the take-off permit.',
                'u_mara', '2026-11-10 10:00Z', 'h_r2') RETURNING id INTO r2;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_weather, 1, 'Thu 19 Nov 08:00-11:00: gusts 14 mph, rain 10%, visibility 10 mi. 18, 20-22 Nov: gusts 24-31 mph.',
                'svc_worker', '2026-11-12 06:00Z', 'h_w1') RETURNING id INTO w1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_auth, 1, 'Flight authorized 18-22 Nov 2026, 07:00-17:00. Named crew: Dev K. (pilot), visual observer. Aircraft: FA3XK4A9.',
                'u_mara', '2026-11-13 14:00Z', 'h_a1') RETURNING id INTO auth1;

    INSERT INTO runs (project_id, kind, name, actor_id, input_version_ids, status, finished_at)
        VALUES ('p_facade', 'analysis', 'flight_window', 'agent_jev', ARRAY[w1, auth1], 'succeeded', '2026-11-13 14:05Z')
        RETURNING id INTO run_win;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, produced_by_run_id)
        VALUES (n_window, 1, 'Only 1 of 5 authorized days meets limits: Thu 19 Nov 08:00-11:00.',
                'agent_jev', '2026-11-13 14:05Z', run_win) RETURNING id INTO win1;

    -- forecast refresh: Thursday turns bad
    INSERT INTO node_versions (node_id, version_no, parent_version_id, content_text, created_by, valid_at, content_hash)
        VALUES (n_weather, 2, w1, 'Thu 19 Nov 08:00-11:00: gusts 27 mph, rain 60%. Fri 20 Nov 08:00-12:00: gusts 15 mph, rain 15%.',
                'svc_worker', '2026-11-14 06:00Z', 'h_w2') RETURNING id INTO w2;
    INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload)
        VALUES ('p_facade', 'svc_worker', 'version.created', 'node_version', w2, jsonb_build_object('node', 'W-01', 'version_no', 2))
        RETURNING id INTO ev_w2;

    -- ------------------------------------------------ D-011: submit the permit package (stale after the rule change)
    INSERT INTO nodes (project_id, type, ref, title, state, owner_id, phase, created_by, tags)
        VALUES ('p_facade', 'decision', 'D-011', 'Submit NYPD permit package', 'decided', 'u_mara', 'permitting', 'u_mara', '{permit}') RETURNING id INTO n_d011;
    INSERT INTO node_versions (node_id, version_no, created_by, valid_at)
        VALUES (n_d011, 1, 'u_mara', '2026-10-26 10:00Z') RETURNING id INTO d011_1;
    INSERT INTO decision_versions (node_version_id, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d011_1, 'decided', 'created', 'Submit the permit package to NYPD with FAA LAANC authorization.',
                'Package complete; LAANC is the current airspace process.', 'manual', 'u_mara', '2026-10-26 10:00Z');
    INSERT INTO decision_inputs VALUES
        (d011_1, pkg1, 0.9, 'The package being submitted', 'u_mara'),
        (d011_1, r1,   0.8, 'Defines which airspace approval to attach', 'u_mara');

    -- ------------------------------------------------ D-014: north facade flight date
    INSERT INTO nodes (project_id, type, ref, title, state, owner_id, phase, created_by, tags)
        VALUES ('p_facade', 'decision', 'D-014', 'North facade flight date', 'decided', 'u_dev', 'flight', 'u_dev', '{permit-date,schedule}') RETURNING id INTO n_d014;

    -- v1: date picked 30 days out, before any forecast exists; needs the forecast
    INSERT INTO node_versions (node_id, version_no, created_by, valid_at)
        VALUES (n_d014, 1, 'u_dev', '2026-10-21 16:00Z') RETURNING id INTO d014_1;
    INSERT INTO decision_versions (node_version_id, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d014_1, 'decided', 'created', 'Request permit for 18-22 Nov; plan to fly the north facade on 19 Nov.',
                'NYPD needs the date 30 days ahead; weather unknown until 2-3 days before.', 'manual', 'u_dev', '2026-10-21 16:00Z');
    INSERT INTO decision_inputs VALUES
        (d014_1, r1,    0.6, 'Permit lead time drives the date choice', 'u_dev'),
        (d014_1, crew1, 0.5, 'Pilot available 18-22 Nov only', 'u_dev');
    INSERT INTO decision_needs (decision_version_id, input_node_id, description, condition, expected_by, resolved_by_version_id, resolved_at)
        VALUES (d014_1, n_weather, 'Forecast covering 19 Nov 08:00-11:00',
                '{"date": "2026-11-19", "max_gust_mph": 20, "max_rain_pct": 30}', '2026-11-16 00:00Z', w1, '2026-11-12 06:05Z');

    -- v2: forecast + authorization arrived, confirmed as test flight
    INSERT INTO node_versions (node_id, version_no, parent_version_id, created_by, valid_at)
        VALUES (n_d014, 2, d014_1, 'u_dev', '2026-11-13 15:00Z') RETURNING id INTO d014_2;
    INSERT INTO decision_versions (node_version_id, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d014_2, 'decided', 'edited', 'Fly the north facade on Thu 19 Nov 08:00-11:00 as a test flight; apply for more days.',
                'Only 1 of 5 authorized days fits the limits.', 'manual', 'u_dev', '2026-11-13 15:00Z');
    INSERT INTO decision_inputs VALUES
        (d014_2, w1,    0.9, 'Forecast shows 19 Nov is the only day under the gust limit', 'agent_jev'),
        (d014_2, win1,  0.8, 'Flight window analysis', 'agent_jev'),
        (d014_2, auth1, 0.8, 'Authorized days 18-22 Nov', 'u_dev'),
        (d014_2, crew1, 0.4, 'Pilot is available', 'u_dev');

    -- v3: proposal from the scheduler specialist, triggered by rule_040 after the forecast refresh
    INSERT INTO runs (project_id, kind, name, actor_id, model, status, tokens_in, tokens_out, finished_at)
        VALUES ('p_facade', 'agent', 'scheduler', 'agent_jev', 'jev', 'succeeded', 4200, 380, '2026-11-14 06:02Z')
        RETURNING id INTO run_sched;
    INSERT INTO run_steps (run_id, step_no, type, name, args) VALUES
        (run_sched, 1, 'tool', 'list_stale', '{}'),
        (run_sched, 2, 'tool', 'lineage', jsonb_build_object('decision_version', d014_2, 'level', 'medium')),
        (run_sched, 3, 'tool', 'get_version', jsonb_build_object('id', w2)),
        (run_sched, 4, 'model', 'jev', NULL);
    INSERT INTO run_reads VALUES (run_sched, d014_2), (run_sched, w1), (run_sched, w2), (run_sched, auth1), (run_sched, crew1);

    INSERT INTO node_versions (node_id, version_no, parent_version_id, created_by, valid_at, produced_by_run_id)
        VALUES (n_d014, 3, d014_2, 'agent_jev', '2026-11-14 06:02Z', run_sched) RETURNING id INTO d014_3;
    INSERT INTO decision_versions (node_version_id, status, change_kind, statement, rationale, origin, author_id, rule_id, decided_at)
        VALUES (d014_3, 'proposed', 'proposed',
                'Move the north facade test flight from Thu 19 Nov to Fri 20 Nov 08:00-12:00.',
                'New forecast puts Thursday gusts at 27 mph (limit 20). Friday is inside the authorization and Dev K. is still available.',
                'agent', 'agent_jev', 'rule_040', '2026-11-14 06:02Z');
    INSERT INTO decision_inputs VALUES
        (d014_3, w2,     0.95, 'Thursday now above gust limit; Friday under', 'agent_jev'),
        (d014_3, d014_2, 0.7,  'The decision this would replace', 'agent_jev'),
        (d014_3, auth1,  0.8,  '20 Nov is inside the authorized window', 'agent_jev'),
        (d014_3, crew1,  0.5,  'Pilot available through 22 Nov', 'agent_jev');
    INSERT INTO events (project_id, actor_id, rule_id, verb, object_type, object_id, payload, chain_depth)
        VALUES ('p_facade', 'agent_jev', 'rule_040', 'decision.proposed', 'decision_version', d014_3,
                jsonb_build_object('ref', 'D-014', 'version_no', 3), 1);

    INSERT INTO attention_items (project_id, event_id, rule_id, type, touches, matched_by, reason, suggested_action, scores, levels)
        VALUES ('p_facade', ev_w2, 'rule_040', 'decision', ARRAY[n_d014, n_weather, n_flight], '{lineage:stale,json:date}',
                'D-014 rests on forecast v1; v2 puts Thursday gusts at 27 mph (limit 20)',
                'Approve moving the test flight to Fri 20 Nov',
                '{"urgency": 0.9, "impact": 0.8, "confidence": 0.9}',
                '{"pilot": "flashing_red", "pm": "red", "client": "status_line"}');

    -- ------------------------------------------------ Slack intake: candidate blocker (Ryan's use case 1.1, step before Mary confirms)
    INSERT INTO nodes (project_id, type, ref, title, status, state, owner_id, created_by, tags, placed, data)
        VALUES ('p_facade', 'blocker', 'B-05', 'Drone 4A needs maintenance', 'candidate', 'open', 'u_mary', 'agent_jev', '{equipment}', false,
                '{"source": "slack", "permalink": "https://example.slack.com/archives/C0FACADE/p1731600000", "posted_by": "u_alice"}')
        RETURNING id INTO n_maint;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at)
        VALUES (n_maint, 1, 'Alice in #facade-survey: "drone 4a needs maintenance"', 'agent_jev', '2026-11-14 15:20Z') RETURNING id INTO maint1;
    INSERT INTO mentions VALUES (maint1, 'equipment', 'drone 4a', n_drone);
    INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload)
        VALUES ('p_facade', 'agent_jev', 'candidate.created', 'node', n_maint,
                jsonb_build_object('asked', 'u_mary', 'via', 'slack_dm')) RETURNING id INTO ev_slack;

    -- ------------------------------------------------ canvas edges (G3)
    INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by) VALUES
        ('p_facade', n_weather, n_d014, 'evidence_for', 'metadata', 1.0, 'Cited by D-014', 'accepted', 'svc_worker'),
        ('p_facade', n_flight,  n_d014, 'depends_on',   'user',     1.0, 'Flight date is set by D-014', 'accepted', 'u_dev'),
        ('p_facade', n_auth,    n_flight, 'evidence_for', 'metadata', 1.0, 'Authorization window', 'accepted', 'u_mara'),
        ('p_facade', n_maint,   n_drone, 'about',       'agent',    0.95, 'Mentions "drone 4a"', 'proposed', 'agent_jev'),
        ('p_facade', n_maint,   n_flight, 'blocks',     'rule',     0.9, 'F-01 uses Drone 4A', 'proposed', 'agent_jev');
    INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by, created_by_run_id)
        VALUES ('p_facade', n_rule, n_pkg, 'about', 'agent', 0.78,
                'Airspace rule changed after the package was submitted; package cites LAANC', 'proposed', 'agent_jev', run_sched);
END $$;

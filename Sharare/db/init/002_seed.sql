-- Seed: a slice of the NYC facade inspection use case (docs/use-case/facade-inspection.md).
-- After boot:
--   SELECT ref, input_ref, cited_version_no, newer_version_no FROM stale_decisions;
--     -> D-014 is stale (forecast changed), D-011 is stale (airspace rule moved FAA -> DHS)
--   SELECT * FROM lineage((SELECT version_id FROM decision_head WHERE ref = 'D-014'), 3);

INSERT INTO users (id, name, kind) VALUES
    ('u_dev',     'Dev K. (pilot)',          'human'),
    ('u_mara',    'Mara S. (project lead)',  'human'),
    ('u_client',  'Client rep',              'human'),
    ('agent_jev', 'Jev',                     'agent'),
    ('svc_worker','Capture worker',          'service');

INSERT INTO projects (id, name, description, settings) VALUES
    ('p_facade', 'NYC facade inspection', 'Drone facade inspection and repair estimate, Manhattan',
     '{"limits": {"max_gust_mph": 20, "max_rain_pct": 30, "min_visibility_mi": 3}}');

INSERT INTO project_members (project_id, user_id, view_level, can_review) VALUES
    ('p_facade', 'u_dev',    'advanced', true),
    ('p_facade', 'u_mara',   'medium',   true),
    ('p_facade', 'u_client', 'basic',    false);

DO $$
DECLARE
    n_weather bigint; n_rule bigint; n_pkg bigint; n_team bigint; n_auth bigint; n_window bigint;
    n_d014 bigint; n_d011 bigint; n_s021 bigint;
    w1 bigint; w2 bigint; r1 bigint; r2 bigint; pkg1 bigint; team1 bigint; auth1 bigint; win1 bigint;
    d014_1 bigint; d014_2 bigint; d011_1 bigint; s021_1 bigint;
    run_win bigint; run_s021 bigint;
BEGIN
    -- ------------------------------------------------ evidence nodes
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'weather', 'W-01', 'Site forecast (NWS, hourly)', 'svc_worker', 0.9) RETURNING id INTO n_weather;
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'regulation', 'R-01', 'Airspace approval for Manhattan drone flights', 'u_mara', 0.8) RETURNING id INTO n_rule;
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'document', 'DOC-07', 'NYPD permit package', 'u_mara', 0.7) RETURNING id INTO n_pkg;
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'message', 'M-03', 'Team availability: Dev K.', 'u_dev', 0.5) RETURNING id INTO n_team;
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'document', 'DOC-09', 'Flight authorization, 18-22 Nov', 'u_mara', 0.9) RETURNING id INTO n_auth;
    INSERT INTO nodes (project_id, kind, ref, title, created_by, importance)
        VALUES ('p_facade', 'analysis', 'A-01', 'Flight window (wind, rain, visibility)', 'agent_jev', 0.8) RETURNING id INTO n_window;

    INSERT INTO sources (node_id, connector, refresh_policy, cron, change_threshold, capture_instruction)
        VALUES (n_weather, 'http:nws', 'periodic', '0 * * * *', '{"gust_mph": 5, "rain_pct": 15}',
                'Hourly wind, gusts, rain probability and visibility for the site, 07:00-17:00, next 5 days.');

    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_rule, 1, 'Drone flights in Class B airspace over Manhattan need FAA LAANC authorization; NYPD issues the take-off permit.',
                'u_mara', '2026-10-20 09:00Z', 'h_r1') RETURNING id INTO r1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_team, 1, 'Dev K. is free 18-22 Nov; booked on another project from 23 Nov.',
                'u_dev', '2026-10-21 15:00Z', 'h_t1') RETURNING id INTO team1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash, raw_uri)
        VALUES (n_pkg, 1, 'Permit package: flight plans, elevations, pilot/observer positions, insurance, owner letter, community notice.',
                'u_mara', '2026-10-25 12:00Z', 'h_p1', 'data/raw/h_p1') RETURNING id INTO pkg1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_rule, 2, 'During the FIFA security period airspace approval moved from the FAA to DHS. NYPD needs DHS airspace approval before issuing the take-off permit.',
                'u_mara', '2026-11-10 10:00Z', 'h_r2') RETURNING id INTO r2;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_weather, 1, 'Thu 19 Nov 08:00-11:00: gusts 14 mph, rain 10%, visibility 10 mi. Other days 18, 20-22 Nov: gusts 24-31 mph.',
                'svc_worker', '2026-11-12 06:00Z', 'h_w1') RETURNING id INTO w1;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, content_hash)
        VALUES (n_auth, 1, 'Flight authorized 18-22 Nov 2026, 07:00-17:00. Named crew: Dev K. (pilot), visual observer.',
                'u_mara', '2026-11-13 14:00Z', 'h_a1') RETURNING id INTO auth1;

    -- analysis run: flight window from forecast v1 + authorization
    INSERT INTO runs (project_id, kind, name, actor_id, input_version_ids, status, finished_at)
        VALUES ('p_facade', 'analysis', 'flight_window', 'agent_jev', ARRAY[w1, auth1], 'succeeded', '2026-11-13 14:05Z')
        RETURNING id INTO run_win;
    INSERT INTO node_versions (node_id, version_no, content_text, created_by, valid_at, produced_by_run_id)
        VALUES (n_window, 1, 'Only 1 of 5 authorized days meets limits: Thu 19 Nov 08:00-11:00.',
                'agent_jev', '2026-11-13 14:05Z', run_win) RETURNING id INTO win1;

    -- forecast refresh: Thursday turns bad (this is what makes D-014 stale)
    INSERT INTO node_versions (node_id, version_no, parent_version_id, content_text, created_by, valid_at, content_hash)
        VALUES (n_weather, 2, w1, 'Thu 19 Nov 08:00-11:00: gusts 27 mph, rain 60%. Fri 20 Nov 08:00-12:00: gusts 15 mph, rain 15%.',
                'svc_worker', '2026-11-14 06:00Z', 'h_w2') RETURNING id INTO w2;

    -- ------------------------------------------------ D-011: submit the permit package (stale after the rule change)
    INSERT INTO nodes (project_id, kind, ref, title, created_by)
        VALUES ('p_facade', 'decision', 'D-011', 'Submit NYPD permit package', 'u_mara') RETURNING id INTO n_d011;
    INSERT INTO node_versions (node_id, version_no, created_by, valid_at)
        VALUES (n_d011, 1, 'u_mara', '2026-10-26 10:00Z') RETURNING id INTO d011_1;
    INSERT INTO decision_versions (node_version_id, kind, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d011_1, 'decision', 'active', 'created', 'Submit the permit package to NYPD with FAA LAANC authorization.',
                'Package complete; LAANC is the current airspace process.', 'manual', 'u_mara', '2026-10-26 10:00Z');
    INSERT INTO decision_inputs VALUES
        (d011_1, pkg1, 0.9, 'The package being submitted', 'u_mara'),
        (d011_1, r1,   0.8, 'Defines which airspace approval to attach', 'u_mara');

    -- ------------------------------------------------ D-014: north facade flight date (two versions)
    INSERT INTO nodes (project_id, kind, ref, title, created_by)
        VALUES ('p_facade', 'decision', 'D-014', 'North facade flight date', 'u_dev') RETURNING id INTO n_d014;

    -- v1: date picked 30 days out, before any forecast exists
    INSERT INTO node_versions (node_id, version_no, created_by, valid_at)
        VALUES (n_d014, 1, 'u_dev', '2026-10-21 16:00Z') RETURNING id INTO d014_1;
    INSERT INTO decision_versions (node_version_id, kind, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d014_1, 'decision', 'active', 'created', 'Request permit for 18-22 Nov; plan to fly the north facade on 19 Nov.',
                'NYPD needs the date 30 days ahead; weather unknown until 2-3 days before.', 'manual', 'u_dev', '2026-10-21 16:00Z');
    INSERT INTO decision_inputs VALUES
        (d014_1, r1,    0.6, 'Permit lead time drives the date choice', 'u_dev'),
        (d014_1, team1, 0.5, 'Pilot available 18-22 Nov only', 'u_dev');
    INSERT INTO decision_awaits (decision_version_id, source_node_id, description, condition, expected_by, resolved_by_version_id, resolved_at)
        VALUES (d014_1, n_weather, 'Forecast covering 19 Nov 08:00-11:00',
                '{"date": "2026-11-19", "max_gust_mph": 20, "max_rain_pct": 30}', '2026-11-16 00:00Z', w1, '2026-11-12 06:05Z');

    -- v2: forecast + authorization arrived, confirmed as test flight
    INSERT INTO node_versions (node_id, version_no, parent_version_id, created_by, valid_at)
        VALUES (n_d014, 2, d014_1, 'u_dev', '2026-11-13 15:00Z') RETURNING id INTO d014_2;
    INSERT INTO decision_versions (node_version_id, kind, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (d014_2, 'decision', 'active', 'edited', 'Fly the north facade on Thu 19 Nov 08:00-11:00 as a test flight; apply for more days.',
                'Only 1 of 5 authorized days fits the limits.', 'manual', 'u_dev', '2026-11-13 15:00Z');
    INSERT INTO decision_inputs VALUES
        (d014_2, w1,    0.9, 'Forecast shows 19 Nov is the only day under the gust limit', 'agent_jev'),
        (d014_2, win1,  0.8, 'Flight window analysis', 'agent_jev'),
        (d014_2, auth1, 0.8, 'Authorized days 18-22 Nov', 'u_dev'),
        (d014_2, team1, 0.4, 'Pilot is available', 'u_dev');

    -- ------------------------------------------------ S-021: agent suggestion after the forecast refresh
    INSERT INTO runs (project_id, kind, name, actor_id, model, status, tokens_in, tokens_out, finished_at)
        VALUES ('p_facade', 'agent', 'decision_agent', 'agent_jev', 'jev', 'succeeded', 4200, 380, '2026-11-14 06:02Z')
        RETURNING id INTO run_s021;
    INSERT INTO run_steps (run_id, step_no, type, name, args) VALUES
        (run_s021, 1, 'tool', 'list_stale', '{}'),
        (run_s021, 2, 'tool', 'lineage', jsonb_build_object('decision_version', d014_2, 'level', 'medium')),
        (run_s021, 3, 'tool', 'get_version', jsonb_build_object('id', w2)),
        (run_s021, 4, 'model', 'jev', NULL);
    INSERT INTO run_reads VALUES (run_s021, d014_2), (run_s021, w1), (run_s021, w2), (run_s021, auth1), (run_s021, team1);

    INSERT INTO nodes (project_id, kind, ref, title, created_by, placed)
        VALUES ('p_facade', 'suggestion', 'S-021', 'Move test flight to Fri 20 Nov', 'agent_jev', false) RETURNING id INTO n_s021;
    INSERT INTO node_versions (node_id, version_no, created_by, valid_at, produced_by_run_id)
        VALUES (n_s021, 1, 'agent_jev', '2026-11-14 06:02Z', run_s021) RETURNING id INTO s021_1;
    INSERT INTO decision_versions (node_version_id, kind, status, change_kind, statement, rationale, origin, author_id, decided_at)
        VALUES (s021_1, 'suggestion', 'proposed', 'created',
                'Move the north facade test flight from Thu 19 Nov to Fri 20 Nov 08:00-12:00.',
                'New forecast puts Thursday gusts at 27 mph (limit 20). Friday is inside the authorization and Dev K. is still available.',
                'agent', 'agent_jev', '2026-11-14 06:02Z');
    INSERT INTO decision_inputs VALUES
        (s021_1, w2,     0.95, 'Thursday now above gust limit; Friday under', 'agent_jev'),
        (s021_1, d014_2, 0.7,  'The decision this would replace', 'agent_jev'),
        (s021_1, auth1,  0.8,  '20 Nov is inside the authorized window', 'agent_jev'),
        (s021_1, team1,  0.5,  'Pilot available through 22 Nov', 'agent_jev');

    -- ------------------------------------------------ canvas edges
    INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by, reviewed_by, reviewed_at)
        VALUES ('p_facade', n_weather, n_d014, 'constrains', 'metadata', 1.0, 'Cited by D-014', 'accepted', 'svc_worker', 'u_dev', '2026-11-13 15:00Z');
    INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by, created_by_run_id)
        VALUES ('p_facade', n_rule, n_pkg, 'constrains', 'agent', 0.78,
                'Airspace rule changed after the package was submitted; package cites LAANC', 'proposed', 'agent_jev', run_s021);
    INSERT INTO edges (project_id, from_node, to_node, type, origin, confidence, reason, status, created_by)
        VALUES ('p_facade', n_s021, n_d014, 'supersedes', 'agent', 0.9, 'Proposes replacing D-014 v2', 'proposed', 'agent_jev');

    -- ------------------------------------------------ activity
    INSERT INTO events (project_id, actor_id, verb, object_type, object_id, payload) VALUES
        ('p_facade', 'svc_worker', 'version.created', 'node_version', w2, jsonb_build_object('node', 'W-01', 'version_no', 2)),
        ('p_facade', 'svc_worker', 'decision.stale', 'decision_version', d014_2, jsonb_build_object('because', w2)),
        ('p_facade', 'agent_jev',  'suggestion.proposed', 'decision_version', s021_1, jsonb_build_object('ref', 'S-021'));
END $$;

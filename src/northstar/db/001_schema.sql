-- VENDORED COPY. Source: Sharare/db/init/001_schema.sql on branch sharare/decision-engine at commit d1d0b9d.
-- Do not edit here. Once that branch is merged to main, delete this file and mount Sharare/db/init instead.

-- Decision engine schema · draft 2026-11-14 · see ../../decision-engine.md
-- Postgres 16 + pgvector. Runs automatically on first boot of the db container.
--
-- Follows the backbone decisions in docs/use-cases-and-decisions.md §3:
--   R1/L1  every change is an event in one append-only Postgres log (events), worked by a worker
--   G1     Postgres, not a graph database          G2  fixed core node types with states + free `data`
--   G3     fixed edge vocabulary                    G4  candidate status on the node
--   G5     shared entities across projects          A3  entity registry with aliases
--   E2/E3  vectors per part + one card per node, in pgvector, model id stored per vector (api/embeddings.py)
--   R3     scenario label instead of branches       R5  agents in the same log, with the rule that triggered them
--   L2     JSON rules with a small condition language (docs/agent-architecture.md §3)
--   L5     one approval record whether approved in the app, in Slack or over MCP
-- Adds the lineage layer from Sharare/plan.md: versions, decision inputs with temperature, stale checks.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- people, agents, projects
CREATE TABLE users (
    id          text PRIMARY KEY,                       -- 'u_mary', 'agent_jev'
    name        text NOT NULL,
    kind        text NOT NULL DEFAULT 'human' CHECK (kind IN ('human', 'agent', 'service')),
    slack_id    text,                                   -- for intake confirmations and the messenger nanny
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    description text,
    pack        text,                                   -- use-case pack, e.g. 'nyc-facade-survey'
    settings    jsonb NOT NULL DEFAULT '{}',            -- flight limits, autonomy overrides
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    project_id  text NOT NULL REFERENCES projects,
    user_id     text NOT NULL REFERENCES users,
    view_level  text NOT NULL CHECK (view_level IN ('basic', 'medium', 'advanced')),   -- client / PM / pilot
    can_review  boolean NOT NULL DEFAULT false,         -- may approve suggestions, rules, candidates
    PRIMARY KEY (project_id, user_id)
);

-- ---------------------------------------------------------------- nodes (G2, G4, G5)
-- Ryan's core set, plus `analysis` and `observation` from Sharare/plan.md (to confirm with Ryan).
CREATE TABLE node_types (
    type    text PRIMARY KEY,
    family  text NOT NULL CHECK (family IN ('evidence', 'work', 'decision', 'computation', 'registry')),
    states  text[] NOT NULL                             -- allowed values of nodes.state; first is the initial state
);
INSERT INTO node_types (type, family, states) VALUES
    ('decision',    'decision',    '{awaiting_inputs,ready,decided,superseded}'),
    ('discovery',   'evidence',    '{new,triaged,absorbed,dismissed}'),
    ('event',       'work',        '{scheduled,imminent,happened,missed}'),
    ('data_feed',   'evidence',    '{healthy,changed,stale,failed}'),
    ('deliverable', 'work',        '{not_started,in_progress,in_review,delivered}'),
    ('blocker',     'work',        '{open,waiting,done}'),
    ('constraint',  'evidence',    '{active,changed,expired}'),
    ('document',    'evidence',    '{placed,floating}'),
    ('entity',      'registry',    '{active,retired}'),            -- drones, people, sites, permits; shared
    ('analysis',    'computation', '{current,stale,failed}'),
    ('observation', 'evidence',    '{new,confirmed,dismissed}');

CREATE TABLE nodes (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id     text REFERENCES projects,            -- NULL only for shared entities (G5)
    type           text NOT NULL REFERENCES node_types,
    ref            text,                                -- human handle: 'D-014', 'DRONE-4A'
    title          text NOT NULL,
    status         text NOT NULL DEFAULT 'confirmed' CHECK (status IN ('candidate', 'confirmed', 'dismissed')),   -- G4
    state          text NOT NULL,                       -- per-type state machine, checked by trigger below
    -- current working fields from docs/usecase-facade-survey.md §5 (every change is also an event)
    owner_id       text REFERENCES users,
    owner_external text,                                -- 'legal', 'property owner'
    due            timestamptz,
    lead_time_days int,
    valid_from     timestamptz,
    valid_to       timestamptz,
    phase          text,                                -- proposal | scope | site_visit | mobilization | permitting | flight | processing | delivery
    tags           text[] NOT NULL DEFAULT '{}',
    data           jsonb NOT NULL DEFAULT '{}',         -- free field (G2)
    placed         boolean NOT NULL DEFAULT true,       -- false = floating node on the canvas
    importance     real CHECK (importance BETWEEN 0 AND 1),
    created_by     text NOT NULL REFERENCES users,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (project_id IS NOT NULL OR type = 'entity'),
    UNIQUE (project_id, ref)
);
CREATE INDEX nodes_tags ON nodes USING gin (tags);

CREATE FUNCTION check_node_state() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM node_types t WHERE t.type = NEW.type AND NEW.state = ANY (t.states)) THEN
        RAISE EXCEPTION 'state % is not valid for node type %', NEW.state, NEW.type;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER nodes_state_check BEFORE INSERT OR UPDATE OF state, type ON nodes
    FOR EACH ROW EXECUTE FUNCTION check_node_state();

-- entity registry aliases (A3): "drone 4a" -> DRONE-4A
CREATE TABLE entity_aliases (
    entity_node_id bigint NOT NULL REFERENCES nodes,
    alias          text NOT NULL,                       -- stored lower-case
    PRIMARY KEY (entity_node_id, alias)
);
CREATE INDEX entity_aliases_lookup ON entity_aliases (alias);

-- ---------------------------------------------------------------- runs (agents, analyses, rules, imports)
CREATE TABLE runs (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id        text REFERENCES projects,
    kind              text NOT NULL CHECK (kind IN ('agent', 'analysis', 'analysis_loop', 'rule', 'capture', 'import')),
    name              text NOT NULL,                    -- specialist / skill / analysis def / rule id / connector
    actor_id          text NOT NULL REFERENCES users,
    model             text,
    params            jsonb NOT NULL DEFAULT '{}',
    input_version_ids bigint[] NOT NULL DEFAULT '{}',   -- analysis inputs (lineage walks through these)
    status            text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled')),
    error             text,
    tokens_in         int,
    tokens_out        int,
    cost_usd          numeric(10, 5),
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz
);

-- ---------------------------------------------------------------- versions (lineage layer, append-only)
CREATE TABLE node_versions (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id            bigint NOT NULL REFERENCES nodes,
    version_no         int NOT NULL,
    scenario           text NOT NULL DEFAULT 'main',    -- R3: scenario label, not real branches
    parent_version_id  bigint REFERENCES node_versions,
    content_text       text,
    summary            text,
    metadata           jsonb NOT NULL DEFAULT '{}',     -- adapter output (source, metadata, pointers) goes here
    raw_uri            text,
    content_hash       text,
    produced_by_run_id bigint REFERENCES runs,
    created_by         text NOT NULL REFERENCES users,
    valid_at           timestamptz NOT NULL,            -- when it was true in the world
    recorded_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (node_id, scenario, version_no)
);
CREATE INDEX node_versions_head ON node_versions (node_id, scenario, version_no DESC);
CREATE INDEX node_versions_run ON node_versions (produced_by_run_id);

-- embeddable parts (E2): one row per adapter part, plus role = 'card' for the node's summary+tags vector
CREATE TABLE chunks (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_version_id bigint NOT NULL REFERENCES node_versions,
    idx             int NOT NULL,
    modality        text NOT NULL CHECK (modality IN ('text', 'image', 'audio', 'video')),
    role            text NOT NULL DEFAULT 'body',       -- card | summary | body | page | view | keyframe | ...
    text            text NOT NULL,
    asset_uri       text,
    mime            text,
    pointer         jsonb NOT NULL DEFAULT '{}',        -- page / view / element_id / t (adapter contract)
    meta            jsonb NOT NULL DEFAULT '{}',
    embedding       vector(768),                        -- EMBEDDING_DIMENSIONS=768 (.env.example)
    embedding_model text,                               -- embeddings.model_id(); search within one model only
    embedded_at     timestamptz,
    UNIQUE (node_version_id, idx)
);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX chunks_model ON chunks (embedding_model);

-- names found in a version (rfi-012, level-6, 'drone 4a'), resolved to registry entities when possible
CREATE TABLE mentions (
    node_version_id bigint NOT NULL REFERENCES node_versions,
    kind            text NOT NULL,
    value           text NOT NULL,                      -- normalised
    entity_node_id  bigint REFERENCES nodes,            -- resolved registry entity, if any
    PRIMARY KEY (node_version_id, kind, value)
);
CREATE INDEX mentions_lookup ON mentions (kind, value);
CREATE INDEX mentions_entity ON mentions (entity_node_id);

-- ---------------------------------------------------------------- rules (L2) and approvals (L5)
CREATE TABLE rules (
    id          text PRIMARY KEY,                       -- 'rule_031'
    pack        text NOT NULL,
    applies_to  jsonb NOT NULL,                         -- {"type": "decision", "tags": ["permit-date"]}
    when_expr   text NOT NULL,                          -- small condition language
    then_actions jsonb NOT NULL,                        -- [{"action": "raise_attention", ...}]
    judgment    jsonb,                                  -- optional Jev step
    why         text NOT NULL,
    written_by  text NOT NULL REFERENCES users,         -- analysis loop agent or a person
    evidence    bigint[] NOT NULL DEFAULT '{}',         -- node_version ids that motivated it
    status      text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'dry_run', 'active', 'retired')),
    stats       jsonb NOT NULL DEFAULT '{"fired": 0, "acted_on": 0, "dismissed": 0}',
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE approvals (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id   text REFERENCES projects,
    subject_type text NOT NULL CHECK (subject_type IN ('candidate', 'decision_version', 'rule', 'edge', 'attention_item')),
    subject_id   text NOT NULL,
    verdict      text NOT NULL CHECK (verdict IN ('approved', 'dismissed', 'edited', 'already_known')),
    reason       text,
    by_user      text NOT NULL REFERENCES users,
    via          text NOT NULL CHECK (via IN ('app', 'slack', 'mcp')),
    at           timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- decisions (lineage layer)
-- A decision node's versions. A suggestion is a `proposed` version on the same decision node;
-- approving it writes the next version as `decided`. No separate suggestion node type is needed.
CREATE TABLE decision_versions (
    node_version_id bigint PRIMARY KEY REFERENCES node_versions,
    status          text NOT NULL CHECK (status IN ('awaiting_inputs', 'ready', 'proposed', 'decided',
                                                    'dismissed', 'superseded', 'revoked')),
    change_kind     text NOT NULL CHECK (change_kind IN ('created', 'inputs_changed', 'proposed', 'approved',
                                                         'dismissed', 'edited', 'superseded', 'revoked')),
    statement       text NOT NULL,
    rationale       text,                               -- R4: required on decisions, Jev may draft it
    origin          text NOT NULL CHECK (origin IN ('manual', 'agent', 'mcp', 'slack')),
    author_id       text NOT NULL REFERENCES users,
    rule_id         text REFERENCES rules,              -- R5: which rule triggered it, if any
    approval_id     bigint REFERENCES approvals,
    decided_at      timestamptz NOT NULL,
    CHECK (status NOT IN ('decided', 'dismissed', 'revoked') OR rationale IS NOT NULL)
);

CREATE TABLE decision_inputs (
    decision_version_id bigint NOT NULL REFERENCES decision_versions,
    input_version_id    bigint NOT NULL REFERENCES node_versions,
    temperature         real NOT NULL CHECK (temperature BETWEEN 0 AND 1),
    influence_reason    text,
    suggested_by        text NOT NULL REFERENCES users,
    PRIMARY KEY (decision_version_id, input_version_id),
    CHECK (decision_version_id <> input_version_id)
);
CREATE INDEX decision_inputs_input ON decision_inputs (input_version_id);

-- upstream inputs a decision needs (Ryan's `needs: [...]`); readiness = all resolved
CREATE TABLE decision_needs (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decision_version_id    bigint NOT NULL REFERENCES decision_versions,
    input_node_id          bigint NOT NULL REFERENCES nodes,
    description            text NOT NULL,               -- 'forecast covering 19 Nov 08:00-11:00'
    condition              jsonb,                       -- optional machine-checkable form
    expected_by            timestamptz,
    resolved_by_version_id bigint REFERENCES node_versions,
    resolved_at            timestamptz
);

-- ---------------------------------------------------------------- edges (G3)
CREATE TABLE edges (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id        text NOT NULL REFERENCES projects,
    from_node         bigint NOT NULL REFERENCES nodes,
    to_node           bigint NOT NULL REFERENCES nodes,
    type              text NOT NULL CHECK (type IN ('depends_on', 'blocks', 'evidence_for', 'about', 'supersedes',
                                                    'derived_from', 'similar_to',
                                                    'part_of', 'contains', 'marks_up')),   -- last three: converter links
    origin            text NOT NULL CHECK (origin IN ('adapter', 'metadata', 'embedding', 'agent', 'rule', 'user', 'mcp')),
    confidence        real CHECK (confidence BETWEEN 0 AND 1),
    reason            text,
    status            text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected')),
    created_by        text NOT NULL REFERENCES users,
    created_by_run_id bigint REFERENCES runs,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CHECK (from_node <> to_node)
);
CREATE UNIQUE INDEX edges_unique ON edges (from_node, to_node, type);

-- ---------------------------------------------------------------- attention engine and nanny (docs/usecase-facade-survey.md §5)
CREATE TABLE attention_items (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id       text NOT NULL REFERENCES projects,
    event_id         bigint,                            -- FK added after events
    rule_id          text REFERENCES rules,
    type             text NOT NULL CHECK (type IN ('deadline', 'blocker', 'decision', 'discovery', 'fyi')),
    touches          bigint[] NOT NULL DEFAULT '{}',    -- node ids
    matched_by       text[] NOT NULL DEFAULT '{}',      -- 'json:date', 'embedding:0.83', 'lineage:stale'
    reason           text NOT NULL,
    suggested_action text,
    scores           jsonb NOT NULL DEFAULT '{}',       -- urgency, impact, confidence
    levels           jsonb NOT NULL DEFAULT '{}',       -- {"pilot": "flashing_red", "pm": "red", "client": "status_line"}
    state            text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'snoozed', 'dismissed', 'done')),
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE nudges (
    attention_item_id bigint NOT NULL REFERENCES attention_items,
    step              int NOT NULL,
    to_user           text NOT NULL REFERENCES users,
    via               text NOT NULL,                    -- slack_dm | email | app
    at                timestamptz NOT NULL DEFAULT now(),
    response          text,
    PRIMARY KEY (attention_item_id, step)
);

CREATE TABLE commitments (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text NOT NULL REFERENCES projects,
    source      text,                                   -- Slack permalink
    owner_id    text REFERENCES users,
    text        text NOT NULL,                          -- "I'll send the flight plan tomorrow"
    due         timestamptz,
    relates_to  bigint[] NOT NULL DEFAULT '{}',
    state       text NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'done', 'lapsed'))
);

-- ---------------------------------------------------------------- sources and analyses (Sharare/plan.md §3, §7, §8)
CREATE TABLE sources (
    node_id             bigint PRIMARY KEY REFERENCES nodes,     -- usually a data_feed node
    connector           text NOT NULL,                  -- 'http:nws', 'mcp:slack', 'inbox', 'replay'
    config              jsonb NOT NULL DEFAULT '{}',
    refresh_policy      text NOT NULL CHECK (refresh_policy IN ('static', 'periodic', 'on_upload', 'stream')),
    cron                text,                           -- tightens near events (Ryan's data feed rule)
    change_threshold    jsonb NOT NULL DEFAULT '{}',
    capture_instruction text,
    capture_spec        jsonb,
    last_captured_at    timestamptz
);

CREATE TABLE readings (
    source_node_id bigint NOT NULL REFERENCES sources,
    ts             timestamptz NOT NULL,
    payload        jsonb NOT NULL,
    PRIMARY KEY (source_node_id, ts)
);

CREATE TABLE analysis_defs (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id       bigint NOT NULL REFERENCES nodes,
    version_no    int NOT NULL,
    mode          text NOT NULL CHECK (mode IN ('generated', 'registered', 'external')),
    code          text,
    ref           text,
    params_schema jsonb NOT NULL DEFAULT '{}',
    approved_by   text REFERENCES users,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (node_id, version_no)
);

-- ---------------------------------------------------------------- run steps and reads
CREATE TABLE run_steps (
    run_id     bigint NOT NULL REFERENCES runs,
    step_no    int NOT NULL,
    type       text NOT NULL CHECK (type IN ('model', 'tool')),
    name       text,
    args       jsonb,
    result     jsonb,
    tokens_in  int,
    tokens_out int,
    latency_ms int,
    at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, step_no)
);

-- every version a run saw through a tool: cited inputs must be a subset (decision-engine.md §6.4)
CREATE TABLE run_reads (
    run_id          bigint NOT NULL REFERENCES runs,
    node_version_id bigint NOT NULL REFERENCES node_versions,
    PRIMARY KEY (run_id, node_version_id)
);

-- ---------------------------------------------------------------- the event log (R1, R5, L1)
CREATE TABLE events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text REFERENCES projects,
    actor_id    text NOT NULL REFERENCES users,         -- person or agent (R5)
    rule_id     text REFERENCES rules,                  -- the rule that triggered it, if any (R5)
    verb        text NOT NULL,          -- node.created | node.updated | version.created | candidate.confirmed | decision.proposed | ...
    object_type text NOT NULL,
    object_id   bigint,
    payload     jsonb NOT NULL DEFAULT '{}',            -- before/after for node.updated, so the graph can be replayed
    scenario    text NOT NULL DEFAULT 'main',
    chain_depth int NOT NULL DEFAULT 0,                 -- agent->agent hops; worker stops at 3
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_project ON events (project_id, at DESC);
ALTER TABLE attention_items ADD FOREIGN KEY (event_id) REFERENCES events;

-- work queue for the worker (L1): same database, claimed with FOR UPDATE SKIP LOCKED
CREATE TABLE agent_tasks (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id       text REFERENCES projects,
    agent            text NOT NULL,
    trigger_event_id bigint REFERENCES events,
    payload          jsonb NOT NULL DEFAULT '{}',
    dedupe_key       text,                              -- e.g. 'decision:42' so one re-check per decision
    status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    attempts         int NOT NULL DEFAULT 0,
    not_before       timestamptz NOT NULL DEFAULT now(),
    locked_by        text,
    locked_at        timestamptz,
    run_id           bigint REFERENCES runs,
    created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX agent_tasks_dedupe ON agent_tasks (dedupe_key) WHERE status IN ('queued', 'running');
CREATE INDEX agent_tasks_ready ON agent_tasks (not_before) WHERE status = 'queued';

CREATE TABLE comments (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id    bigint NOT NULL REFERENCES nodes,
    user_id    text NOT NULL REFERENCES users,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- append-only enforcement
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: write a new version or event instead', TG_TABLE_NAME;
END $$;

CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER node_versions_append_only BEFORE UPDATE OR DELETE ON node_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER decision_versions_append_only BEFORE UPDATE OR DELETE ON decision_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER decision_inputs_append_only BEFORE UPDATE OR DELETE ON decision_inputs
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER approvals_append_only BEFORE UPDATE OR DELETE ON approvals
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- wake the worker and the live-update broadcaster (G6) on every event
CREATE FUNCTION notify_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('events', json_build_object('id', NEW.id, 'project', NEW.project_id, 'verb', NEW.verb)::text);
    RETURN NEW;
END $$;
CREATE TRIGGER events_notify AFTER INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION notify_event();

-- ---------------------------------------------------------------- views
CREATE VIEW node_head AS
SELECT DISTINCT ON (nv.node_id) nv.*
FROM node_versions nv
WHERE nv.scenario = 'main'
ORDER BY nv.node_id, nv.version_no DESC;

-- the decision as it currently stands: latest version that is not a pending or dismissed proposal
CREATE VIEW decision_current AS
SELECT DISTINCT ON (nv.node_id)
       n.project_id, n.ref, n.title, nv.node_id, nv.id AS version_id, nv.version_no, d.*
FROM node_versions nv
JOIN nodes n ON n.id = nv.node_id
JOIN decision_versions d ON d.node_version_id = nv.id
WHERE nv.scenario = 'main' AND d.status NOT IN ('proposed', 'dismissed')
ORDER BY nv.node_id, nv.version_no DESC;

-- proposals waiting for approval (shown as suggestions)
CREATE VIEW decision_proposals AS
SELECT n.project_id, n.ref, n.title, nv.node_id, nv.id AS version_id, nv.version_no, d.*
FROM node_versions nv
JOIN nodes n ON n.id = nv.node_id
JOIN decision_versions d ON d.node_version_id = nv.id
JOIN decision_current c ON c.node_id = nv.node_id
WHERE d.status = 'proposed' AND nv.version_no > c.version_no;

-- current decisions that cite an input which now has a newer version
CREATE VIEW stale_decisions AS
SELECT dc.project_id, dc.ref, dc.title, dc.version_id AS decision_version_id, dc.status,
       inp.ref AS input_ref, inp.title AS input_title,
       iv.id AS cited_version_id, iv.version_no AS cited_version_no,
       head.id AS newer_version_id, head.version_no AS newer_version_no,
       di.temperature, head.valid_at AS newer_valid_at
FROM decision_current dc
JOIN decision_inputs di ON di.decision_version_id = dc.version_id
JOIN node_versions iv   ON iv.id = di.input_version_id
JOIN node_head head     ON head.node_id = iv.node_id AND head.version_no > iv.version_no
JOIN nodes inp          ON inp.id = iv.node_id
WHERE dc.status IN ('decided', 'ready', 'awaiting_inputs');

-- decisions still waiting on upstream inputs
CREATE VIEW decisions_awaiting_inputs AS
SELECT dc.project_id, dc.ref, dc.title, dc.version_id AS decision_version_id,
       nd.description, nd.expected_by, src.title AS input_title, nd.id AS need_id
FROM decision_current dc
JOIN decision_needs nd ON nd.decision_version_id = dc.version_id
JOIN nodes src ON src.id = nd.input_node_id
WHERE nd.resolved_by_version_id IS NULL;

-- ---------------------------------------------------------------- lineage
-- Walk back from a decision version through cited inputs and analysis-run inputs.
-- simple = lineage(v, 1) top 3 by temperature; medium = lineage(v, 3, 0.3); advanced = lineage(v, 10).
CREATE FUNCTION lineage(root bigint, max_depth int DEFAULT 3, min_temp real DEFAULT 0)
RETURNS TABLE (version_id bigint, cited_by bigint, depth int, temperature real, via text)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE walk AS (
        SELECT root AS version_id, NULL::bigint AS cited_by, 0 AS depth, 1.0::real AS temperature, 'root'::text AS via
        UNION ALL
        SELECT nxt.version_id, w.version_id, w.depth + 1, nxt.temperature, nxt.via
        FROM walk w
        CROSS JOIN LATERAL (
            SELECT di.input_version_id AS version_id, di.temperature, 'decision_input'::text AS via
            FROM decision_inputs di
            WHERE di.decision_version_id = w.version_id AND di.temperature >= min_temp
            UNION ALL
            SELECT unnest(r.input_version_ids), 1.0::real, 'analysis_input'::text
            FROM node_versions nv
            JOIN runs r ON r.id = nv.produced_by_run_id
            WHERE nv.id = w.version_id
        ) nxt
        WHERE w.depth < max_depth
    )
    SELECT * FROM walk
$$;

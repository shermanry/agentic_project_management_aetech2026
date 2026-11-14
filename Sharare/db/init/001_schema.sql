-- Decision engine schema · draft 2026-11-14 · see ../../decision-engine.md
-- Postgres 16 + pgvector. Runs automatically on first boot of the db container.

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------- people, agents, projects
CREATE TABLE users (
    id          text PRIMARY KEY,                       -- 'u_mara', 'agent_jev'
    name        text NOT NULL,
    kind        text NOT NULL DEFAULT 'human' CHECK (kind IN ('human', 'agent', 'service')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id          text PRIMARY KEY,
    name        text NOT NULL,
    description text,
    settings    jsonb NOT NULL DEFAULT '{}',            -- flight limits, autonomy table overrides
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_members (
    project_id  text NOT NULL REFERENCES projects,
    user_id     text NOT NULL REFERENCES users,
    view_level  text NOT NULL CHECK (view_level IN ('basic', 'medium', 'advanced')),   -- client / PM / pilot
    can_review  boolean NOT NULL DEFAULT false,         -- may accept / dismiss suggestions
    PRIMARY KEY (project_id, user_id)
);

-- ---------------------------------------------------------------- nodes and versions
CREATE TABLE node_kinds (
    kind    text PRIMARY KEY,
    family  text NOT NULL CHECK (family IN ('evidence', 'computation', 'decision'))
);
INSERT INTO node_kinds (kind, family) VALUES
    ('source', 'evidence'), ('document', 'evidence'), ('model', 'evidence'), ('image', 'evidence'),
    ('video', 'evidence'), ('audio', 'evidence'), ('email', 'evidence'), ('message', 'evidence'),
    ('weather', 'evidence'), ('regulation', 'evidence'), ('rfi', 'evidence'), ('flight', 'evidence'),
    ('site', 'evidence'), ('observation', 'evidence'), ('log', 'evidence'),
    ('analysis', 'computation'),
    ('suggestion', 'decision'), ('decision', 'decision'), ('action_item', 'decision');

CREATE TABLE nodes (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id    text NOT NULL REFERENCES projects,
    kind          text NOT NULL REFERENCES node_kinds,
    ref           text,                                 -- human handle: 'D-014', 'F-03'
    title         text NOT NULL,
    -- mutable UI state (changes are logged in events, not versioned)
    placed        boolean NOT NULL DEFAULT true,        -- false = floating node
    importance    real CHECK (importance BETWEEN 0 AND 1),
    importance_by text REFERENCES users,                -- who set it last (agent or person override)
    created_by    text NOT NULL REFERENCES users,
    created_at    timestamptz NOT NULL DEFAULT now(),
    archived_at   timestamptz,
    UNIQUE (project_id, ref)
);

-- runs: one row per agent run, analysis run, capture or import (defined before node_versions)
CREATE TABLE runs (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id        text NOT NULL REFERENCES projects,
    kind              text NOT NULL CHECK (kind IN ('agent', 'analysis', 'capture', 'import')),
    name              text NOT NULL,                    -- agent spec name / analysis def / connector
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

CREATE TABLE node_versions (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id            bigint NOT NULL REFERENCES nodes,
    version_no         int NOT NULL,
    branch             text NOT NULL DEFAULT 'main',
    parent_version_id  bigint REFERENCES node_versions,
    content_text       text,                            -- extracted / relevant slice
    summary            text,
    metadata           jsonb NOT NULL DEFAULT '{}',     -- kind-specific; converter manifest goes here
    raw_uri            text,                            -- ./data/raw/<hash> or converter package dir
    content_hash       text,
    produced_by_run_id bigint REFERENCES runs,
    created_by         text NOT NULL REFERENCES users,
    valid_at           timestamptz NOT NULL,            -- when it was true in the world
    recorded_at        timestamptz NOT NULL DEFAULT now(),   -- when we stored it
    UNIQUE (node_id, branch, version_no)
);
CREATE INDEX node_versions_head ON node_versions (node_id, branch, version_no DESC);
CREATE INDEX node_versions_run ON node_versions (produced_by_run_id);

-- embeddable units (converter chunks.jsonl rows)
CREATE TABLE chunks (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_version_id bigint NOT NULL REFERENCES node_versions,
    idx             int NOT NULL,
    modality        text NOT NULL CHECK (modality IN ('text', 'image', 'audio', 'video')),
    role            text NOT NULL DEFAULT 'body',
    text            text NOT NULL,                      -- every chunk has text (converter rule)
    asset_uri       text,
    mime            text,
    locator         jsonb NOT NULL DEFAULT '{}',
    meta            jsonb NOT NULL DEFAULT '{}',
    embedding       vector(768),                        -- pinned dimension, see doc §4
    embedding_model text,
    embedded_at     timestamptz,
    UNIQUE (node_version_id, idx)
);
CREATE INDEX chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);

-- exact-match keys for linking (converter metadata.entities)
CREATE TABLE entities (
    node_version_id bigint NOT NULL REFERENCES node_versions,
    kind            text NOT NULL,                      -- rfi | level | elevation | grid | sheet | date | person | ...
    value           text NOT NULL,                      -- normalised: 'level-6', 'north-elevation'
    PRIMARY KEY (node_version_id, kind, value)
);
CREATE INDEX entities_lookup ON entities (kind, value);

CREATE TABLE tags (
    node_id   bigint NOT NULL REFERENCES nodes,
    tag       text NOT NULL,
    added_by  text NOT NULL REFERENCES users,
    added_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (node_id, tag)
);

-- ---------------------------------------------------------------- decisions
CREATE TABLE decision_versions (
    node_version_id bigint PRIMARY KEY REFERENCES node_versions,
    kind            text NOT NULL CHECK (kind IN ('suggestion', 'decision', 'action_item')),
    status          text NOT NULL CHECK (status IN ('proposed', 'accepted', 'dismissed', 'active', 'revoked',
                                                    'open', 'done', 'cancelled', 'superseded')),
    change_kind     text NOT NULL CHECK (change_kind IN ('created', 'edited', 'accepted', 'dismissed',
                                                         'superseded', 'completed', 'revoked')),
    statement       text NOT NULL,
    rationale       text,
    origin          text NOT NULL CHECK (origin IN ('manual', 'agent', 'mcp')),
    author_id       text NOT NULL REFERENCES users,
    decided_at      timestamptz NOT NULL,
    due_at          timestamptz,
    assignee_id     text REFERENCES users,
    CHECK (change_kind NOT IN ('accepted', 'dismissed', 'revoked') OR rationale IS NOT NULL),
    CHECK (kind <> 'suggestion'  OR status IN ('proposed', 'accepted', 'dismissed', 'superseded')),
    CHECK (kind <> 'decision'    OR status IN ('active', 'revoked', 'superseded')),
    CHECK (kind <> 'action_item' OR status IN ('open', 'done', 'cancelled'))
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

-- inputs a decision is still waiting on (permit date picked before the forecast exists)
CREATE TABLE decision_awaits (
    id                     bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    decision_version_id    bigint NOT NULL REFERENCES decision_versions,
    source_node_id         bigint NOT NULL REFERENCES nodes,
    description            text NOT NULL,               -- 'forecast covering 19 Nov 08:00-11:00'
    condition              jsonb,                       -- optional machine-checkable form (open question 2)
    expected_by            timestamptz,
    resolved_by_version_id bigint REFERENCES node_versions,
    resolved_at            timestamptz
);

-- ---------------------------------------------------------------- canvas edges (node level, mutable status)
CREATE TABLE edges (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id        text NOT NULL REFERENCES projects,
    from_node         bigint NOT NULL REFERENCES nodes,
    to_node           bigint NOT NULL REFERENCES nodes,
    type              text NOT NULL,     -- constrains | supports | supersedes | answers | derived_from | similar_to
                                         -- | part_of | contains | marks_up | refers_to (converter)
    origin            text NOT NULL CHECK (origin IN ('converter', 'metadata', 'embedding', 'agent', 'user', 'mcp')),
    confidence        real CHECK (confidence BETWEEN 0 AND 1),
    reason            text,
    status            text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'accepted', 'rejected')),
    created_by        text NOT NULL REFERENCES users,
    created_by_run_id bigint REFERENCES runs,
    created_at        timestamptz NOT NULL DEFAULT now(),
    reviewed_by       text REFERENCES users,
    reviewed_at       timestamptz,
    CHECK (from_node <> to_node)
);
CREATE UNIQUE INDEX edges_unique ON edges (from_node, to_node, type);

-- ---------------------------------------------------------------- sources and analyses (plan.md §3, §7, §8)
CREATE TABLE sources (
    node_id          bigint PRIMARY KEY REFERENCES nodes,
    connector        text NOT NULL,                     -- 'http:nws', 'mcp:slack', 'inbox', 'replay'
    config           jsonb NOT NULL DEFAULT '{}',
    refresh_policy   text NOT NULL CHECK (refresh_policy IN ('static', 'periodic', 'on_upload', 'stream')),
    cron             text,
    change_threshold jsonb NOT NULL DEFAULT '{}',
    capture_instruction text,                           -- plain language
    capture_spec     jsonb,                             -- compiled by the LLM, approved by a person
    last_captured_at timestamptz
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
    approved_by   text REFERENCES users,                -- required before a generated script runs
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (node_id, version_no)
);

-- ---------------------------------------------------------------- agent runs, steps, reads
CREATE TABLE run_steps (
    run_id     bigint NOT NULL REFERENCES runs,
    step_no    int NOT NULL,
    type       text NOT NULL CHECK (type IN ('model', 'tool')),
    name       text,                                    -- tool name, or model id
    args       jsonb,
    result     jsonb,                                   -- truncated / digested for large results
    tokens_in  int,
    tokens_out int,
    latency_ms int,
    at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, step_no)
);

-- every version a run saw through a tool: citations must be a subset (doc §6.4)
CREATE TABLE run_reads (
    run_id          bigint NOT NULL REFERENCES runs,
    node_version_id bigint NOT NULL REFERENCES node_versions,
    PRIMARY KEY (run_id, node_version_id)
);

-- ---------------------------------------------------------------- events, queue, collaboration
CREATE TABLE events (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id  text NOT NULL REFERENCES projects,
    actor_id    text NOT NULL REFERENCES users,
    verb        text NOT NULL,          -- version.created | decision.logged | decision.stale | edge.reviewed | ...
    object_type text NOT NULL,
    object_id   bigint,
    payload     jsonb NOT NULL DEFAULT '{}',
    chain_depth int NOT NULL DEFAULT 0, -- agent->agent hops; dispatcher stops at 3
    at          timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_project ON events (project_id, at DESC);

CREATE TABLE agent_tasks (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id       text NOT NULL REFERENCES projects,
    agent            text NOT NULL,
    trigger_event_id bigint REFERENCES events,
    payload          jsonb NOT NULL DEFAULT '{}',
    dedupe_key       text,
    status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed', 'skipped')),
    attempts         int NOT NULL DEFAULT 0,
    not_before       timestamptz NOT NULL DEFAULT now(),
    locked_by        text,
    locked_at        timestamptz,
    run_id           bigint REFERENCES runs,
    created_at       timestamptz NOT NULL DEFAULT now()
);
-- one queued/running task per dedupe key
CREATE UNIQUE INDEX agent_tasks_dedupe ON agent_tasks (dedupe_key) WHERE status IN ('queued', 'running');
CREATE INDEX agent_tasks_ready ON agent_tasks (not_before) WHERE status = 'queued';

CREATE TABLE comments (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    node_id    bigint NOT NULL REFERENCES nodes,
    user_id    text NOT NULL REFERENCES users,
    body       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE canvas_snapshots (
    project_id text NOT NULL REFERENCES projects,
    yjs_state  bytea NOT NULL,
    saved_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (project_id, saved_at)
);

-- ---------------------------------------------------------------- append-only enforcement
CREATE FUNCTION forbid_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: write a new version instead', TG_TABLE_NAME;
END $$;

CREATE TRIGGER node_versions_append_only BEFORE UPDATE OR DELETE ON node_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER decision_versions_append_only BEFORE UPDATE OR DELETE ON decision_versions
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();
CREATE TRIGGER decision_inputs_append_only BEFORE UPDATE OR DELETE ON decision_inputs
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- wake the worker and the websocket broadcaster on every event
CREATE FUNCTION notify_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('events', json_build_object('id', NEW.id, 'project', NEW.project_id, 'verb', NEW.verb)::text);
    RETURN NEW;
END $$;

CREATE TRIGGER events_notify AFTER INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION notify_event();

-- ---------------------------------------------------------------- views
-- latest version of every node on main
CREATE VIEW node_head AS
SELECT DISTINCT ON (nv.node_id) nv.*
FROM node_versions nv
WHERE nv.branch = 'main'
ORDER BY nv.node_id, nv.version_no DESC;

-- latest version of every decision-family node, with its decision fields
CREATE VIEW decision_head AS
SELECT n.project_id, n.ref, n.title, h.node_id, h.id AS version_id, h.version_no, d.*
FROM node_head h
JOIN nodes n ON n.id = h.node_id
JOIN decision_versions d ON d.node_version_id = h.id;

-- current decisions/suggestions that cite an input which now has a newer version
CREATE VIEW stale_decisions AS
SELECT dh.project_id, dh.ref, dh.title, dh.version_id AS decision_version_id, dh.status,
       inp_node.ref AS input_ref, inp_node.title AS input_title,
       iv.id AS cited_version_id, iv.version_no AS cited_version_no,
       head.id AS newer_version_id, head.version_no AS newer_version_no,
       di.temperature, head.valid_at AS newer_valid_at
FROM decision_head dh
JOIN decision_inputs di ON di.decision_version_id = dh.version_id
JOIN node_versions iv   ON iv.id = di.input_version_id
JOIN node_head head     ON head.node_id = iv.node_id AND head.version_no > iv.version_no
JOIN nodes inp_node     ON inp_node.id = iv.node_id
WHERE dh.status IN ('active', 'proposed', 'accepted', 'open');

-- decisions still waiting on an input
CREATE VIEW awaiting_decisions AS
SELECT dh.project_id, dh.ref, dh.title, dh.version_id AS decision_version_id,
       a.description, a.expected_by, src.title AS source_title, a.id AS await_id
FROM decision_head dh
JOIN decision_awaits a ON a.decision_version_id = dh.version_id
JOIN nodes src ON src.id = a.source_node_id
WHERE a.resolved_by_version_id IS NULL;

-- ---------------------------------------------------------------- lineage
-- Walk back from a decision version through cited inputs and analysis-run inputs.
-- Simple = lineage(v, 1, 0.0) top 3 by temperature; medium = lineage(v, 3, 0.3); advanced = lineage(v, 10, 0).
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

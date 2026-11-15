-- North star intake: things users have added that are being processed or are waiting for review.
-- The graph of record lives in the shared schema (001_schema.sql). A proposal only becomes a node,
-- edges, an approval and an event when a person approves it.
CREATE TABLE IF NOT EXISTS intake_items (
    id         text PRIMARY KEY,
    project_id text NOT NULL REFERENCES projects,
    status     text NOT NULL CHECK (status IN ('processing', 'refining', 'ready', 'approved', 'dismissed', 'failed')),
    label      text NOT NULL,
    author     text,
    source     jsonb NOT NULL DEFAULT '{}',
    proposal   jsonb,
    timings    jsonb,
    error      text,
    node_id    bigint REFERENCES nodes,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- Keyword search over every chunk (node cards and document passages). Idempotent: run at every startup.
-- Meaning search already has an HNSW index on chunks.embedding (001_schema.sql).
CREATE INDEX IF NOT EXISTS chunks_fts ON chunks USING gin (to_tsvector('english', text));
CREATE INDEX IF NOT EXISTS edges_from ON edges (from_node);
CREATE INDEX IF NOT EXISTS edges_to ON edges (to_node);

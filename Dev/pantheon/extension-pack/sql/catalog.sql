-- Fixture-side DDL for the extension pack: the ingest catalog and web
-- registry live in the same Postgres the connectors already reach.
-- Run alongside the prototype's seed scripts.

CREATE TABLE IF NOT EXISTS ingest_catalog (
    id              bigserial PRIMARY KEY,
    sha256          text NOT NULL UNIQUE,
    requester       text NOT NULL,
    kind            text NOT NULL CHECK (kind IN ('table', 'document', 'image', 'data')),
    media_type      text NOT NULL,
    source_filename text NOT NULL,
    summary         text NOT NULL,
    detail          jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at      timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS web_registry (
    name         text PRIMARY KEY,
    url          text NOT NULL,
    purpose      text NOT NULL,
    requester    text NOT NULL,
    status       text NOT NULL CHECK (status IN ('ok', 'failed', 'retired')),
    sha256       text,
    media_type   text,
    blob_key     text,
    detail       jsonb NOT NULL DEFAULT '{}'::jsonb,
    fetched_at   timestamptz,
    last_checked timestamptz,
    live         boolean,
    last_error   text
);

-- Example grants (shape per spec §8: user, resource, verbs, per-connector
-- scope). Align table/column names with the prototype's grants table.
--
-- Catalog visibility is per-requester for uploads: the row filter scopes a
-- user to their own ingested files, so "the file I uploaded" can never
-- surface another user's upload in a report.
--
-- INSERT INTO grants (user_id, resource, verbs, scope) VALUES
--   ('alice', 'catalog_db', '{query}',
--    'requester = current_user_id OR kind = ''data'''),          -- row filter
--   ('alice', 'blob_store', '{get,put}', 'ingest/'),             -- key prefix
--   ('alice', 'web', '{request}',
--    'https://api.frankfurter.dev/,https://raw.githubusercontent.com/');  -- URL allowlist

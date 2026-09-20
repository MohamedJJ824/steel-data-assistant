#!/bin/bash
# Roles and privileges. Defence in depth, layer 1: the agent's SQL runs as a
# role that is physically incapable of writing or of reading rag/app.
#
# This is a .sh rather than the .sql the plan names, because role passwords come
# from the environment and psql cannot read env vars from a plain .sql file.
# Recorded in DECISIONS.md.
set -euo pipefail

: "${ASSISTANT_RO_PASSWORD:?ASSISTANT_RO_PASSWORD must be set}"
: "${APP_RW_PASSWORD:?APP_RW_PASSWORD must be set}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
-- ---------------------------------------------------------- assistant_ro ----
-- Used by the sql_query tool only. SELECT on schema plant, nothing else.
CREATE ROLE assistant_ro LOGIN PASSWORD '${ASSISTANT_RO_PASSWORD}';

REVOKE ALL ON DATABASE ${POSTGRES_DB} FROM PUBLIC;
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO assistant_ro;

-- PUBLIC gets USAGE on the public schema by default; take it back everywhere.
REVOKE ALL ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA plant, rag, app FROM PUBLIC;

GRANT USAGE ON SCHEMA plant TO assistant_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA plant TO assistant_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA plant GRANT SELECT ON TABLES TO assistant_ro;

-- No route into rag or app, now or later.
REVOKE ALL ON SCHEMA rag, app FROM assistant_ro;

-- A runaway generated query cannot tie up a connection.
ALTER ROLE assistant_ro SET statement_timeout = '5s';
ALTER ROLE assistant_ro SET default_transaction_read_only = on;
ALTER ROLE assistant_ro SET search_path = plant;

-- ---------------------------------------------------------------- app_rw ----
-- Used by the API: reads the retrieval corpus, writes feedback and the log.
CREATE ROLE app_rw LOGIN PASSWORD '${APP_RW_PASSWORD}';

GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO app_rw;
GRANT USAGE ON SCHEMA plant, rag, app TO app_rw;

-- The pgvector extension installs its types into public. Revoking public
-- above left app_rw unable to resolve the 'vector' type, so every dense
-- search failed with 'type vector does not exist'. public holds no tables
-- (CREATE was revoked), so USAGE here only exposes the type namespace.
GRANT USAGE ON SCHEMA public TO app_rw;

GRANT SELECT ON ALL TABLES IN SCHEMA plant TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO app_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA rag, app TO app_rw;

ALTER DEFAULT PRIVILEGES IN SCHEMA plant GRANT SELECT ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag, app
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA rag, app
  GRANT USAGE, SELECT ON SEQUENCES TO app_rw;

ALTER ROLE app_rw SET statement_timeout = '30s';
EOSQL

echo "roles: assistant_ro (read-only, plant only) and app_rw created"

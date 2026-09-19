-- Schemas and extensions.
-- Runs once, as superuser, on first container start (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Business data. The only schema the agent's read-only role may touch.
CREATE SCHEMA IF NOT EXISTS plant;

-- Retrieval corpus: chunks, embeddings, full-text vectors.
CREATE SCHEMA IF NOT EXISTS rag;

-- Application state: feedback, request log.
CREATE SCHEMA IF NOT EXISTS app;

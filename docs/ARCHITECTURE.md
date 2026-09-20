# Architecture

## What this system does

A user asks a question in French or English. The agent decides which of three
tools can answer it, runs them, and writes an answer that cites its evidence:
the SQL it executed and the rows that came back, the document sections it read,
or the exact file and line range it quoted.

## Components

```
                 ┌───────────────────────────┐
  User (FR/EN) → │  Streamlit UI  (ui/)      │
                 └────────────┬──────────────┘
                              │ HTTP (X-API-Key)
                 ┌────────────▼──────────────┐
                 │  FastAPI  (src/api/)      │  /v1/ask, /v1/feedback, /health
                 └────────────┬──────────────┘
                              │
                 ┌────────────▼──────────────┐
                 │  LangGraph agent          │  router or tool_calling
                 │  (src/agent/)             │  + answer synthesis
                 │                           │  + number-grounding check
                 └───┬──────────┬─────────┬──┘
                     │          │         │
          ┌──────────▼──┐ ┌─────▼─────┐ ┌─▼───────────┐
          │ sql_query   │ │search_docs│ │ search_code │
          │ text-to-SQL │ │ hybrid RAG│ │ hybrid RAG  │
          │ + sql_guard │ │ + rerank  │ │ over AST    │
          └──────┬──────┘ └─────┬─────┘ └──────┬──────┘
                 │              │              │
          ┌──────▼──────────────▼──────────────▼──────┐
          │ Postgres 16 + pgvector                     │
          │  schema plant  : business tables (RO role) │
          │  schema rag    : chunks + embeddings + tsv │
          │  schema app    : feedback, request log     │
          └────────────────────────────────────────────┘
```

**One database, three schemas.** Business data, vectors and application state
live in the same Postgres instance. Fewer moving parts is closer to what an
industrial IT department will accept, and it keeps the SQL surface honest.

## Data flow for one question

1. **Language detection** — marker-based, no model call. A French question gets
   a French answer.
2. **Routing** — one LLM call classifies into `sql | docs | code | multi |
   out_of_scope`. In `tool_calling` mode the model chooses tools itself, capped
   at five calls with repeated identical calls suppressed.
3. **Tool execution** — whichever tools the category implies.
4. **Synthesis** — one LLM call writes the answer from the tool outputs only.
5. **Grounding check** — every number in the answer is looked for in the tool
   outputs, handling French formatting (`959 636,7` against `959636.7`).
6. **Logging** — trace id, tools used, latency. Never the returned rows.

## The SQL path in detail

1. **Schema context**, cached per process, built from the live database:
   columns, types, keys, the bilingual `COMMENT ON` text, and three real rows
   per table. The sample rows matter — without them the model generated
   `load_type = 'maximum load'` when the stored value is `Maximum_Load`, which
   returns zero rows and looks like a legitimate empty result.
2. **Few-shot examples** — `none`, `static` (all ten) or `dynamic` (the four
   nearest by embedding). Verified not to overlap the evaluation set.
3. **Generation** at temperature 0 with a JSON schema constraining the output.
4. **Guard** — see below.
5. **Execution** as `assistant_ro` in a read-only transaction.
6. **Self-correction** — on rejection the model receives its own query and the
   error, up to `sql.max_retries` times. Disabled in configuration C0 so the
   evaluation can measure what it is worth.

## Retrieval

Two branches, fused with Reciprocal Rank Fusion (k = 60):

- **Dense** — cosine distance over a pgvector HNSW index, using
  `intfloat/multilingual-e5-base` (768 dimensions) with the asymmetric
  `query:` / `passage:` prefixes that model requires.
- **Keyword** — PostgreSQL full-text ranking, `french` configuration for
  documents and `simple` for code, where stemming would break identifiers.

Two details are load-bearing and were both found by measurement:

- The tsquery's `&` operators are rewritten to `|`. `websearch_to_tsquery`
  joins terms with AND, so a natural-language question matched **zero** chunks
  and hybrid mode was silently identical to dense.
- The tsvector weights the heading (`title > section`) at `A` above the body at
  `B`. Without it, twenty near-identical maintenance reports flooded the
  keyword branch and displaced the one procedure a question was about.

Chunking keeps provenance: documents split on headings and keep the heading
path; Python splits on the AST with exact line ranges, verified by a test that
slices the file by each range and compares it to the chunk.

## Security

Read-only access is enforced at two independent layers, so neither is
load-bearing alone.

**Layer 1 — the database role.** Generated SQL runs as `assistant_ro`, which
holds `SELECT` on schema `plant` and nothing else, with a 5-second
`statement_timeout`. The role can unset its own `default_transaction_read_only`
flag, so the grants are tested in isolation: with that flag off and no
engine-level read-only option, every write still fails with `permission denied`.

**Layer 2 — the AST guard.** Every generated statement is parsed with `sqlglot`
before it executes. It must be exactly one statement, rooted in a `SELECT`,
reading only whitelisted schemas. Writes are rejected anywhere, including inside
nested CTEs — Postgres permits `WITH x AS (DELETE ... RETURNING ...)`, which a
root-only check would miss. Blocked functions and any `pg_*` administrative
function are rejected, as are `SELECT ... INTO` and locking clauses. A `LIMIT`
is injected unless the query is a bare aggregate.

Validation walks the parse tree rather than matching text, because a string
blocklist is defeated by case, by `/**/` comments and by quoting — all three
are in the test suite.

The guard also blocks `pg_catalog` and `information_schema`, which Postgres
exposes to every role and which no grant can practically revoke.

**Other measures.** Retrieved documents and code are rendered between explicit
`--- SOURCE ---` markers and the synthesis prompt states they are data, never
instructions. The API requires an `X-API-Key` header. Source endpoints resolve
paths and confirm they stayed inside the corpus directory. With the local
model, no data leaves the machine. Row contents are never logged.

## Known limitations

- **A single static API key.** Real deployment needs SSO and per-table access
  control; the read-only role is plant-wide, not per-user.
- **The judge is the model under test.** On 8 GB of RAM only one model can be
  resident, so `judge_model` is the same model that produced the answers. It
  grades its own work, which inflates the judge-based scores. The deterministic
  metrics — SQL execution accuracy, routing, refusal, number grounding — should
  carry the weight of any conclusion.
- **Synthetic corpus.** The measurements are real; the plant they describe is
  not. See `DATA_CARD.md`.
- **Small models.** Defaults are sized for an 8 GB laptop. Larger models are a
  configuration change, and `EVAL_REPORT.md` states which models produced its
  numbers.

## What production would need

SSO and per-user authorisation. Access control at the row and table level
rather than one shared read-only role. Monitoring on answer latency, refusal
rate and grounding, with alerting when grounding drops. A human feedback loop
that actually feeds back — the `app.feedback` table exists but nothing consumes
it yet. And a substantially larger evaluation set with more than one annotator.

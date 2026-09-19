# Steel Plant Data Assistant

A GenAI agent that answers questions about a steel plant by choosing between
three tools — **text-to-SQL** over a Postgres database, **RAG** over a French
document corpus, and **semantic search** over a legacy analytics codebase — and
shows its evidence for every answer: the SQL it ran and the rows it got back,
the document sections it cited, or the exact file and line range.

Questions can be asked in French or English; the answer comes back in the
language it was asked in.

> **Status: milestone 1 of 7 complete.** The database, both public datasets and
> the synthetic layer are in place and tested. The corpora, tools, agent, API,
> UI and evaluation are not built yet. Every number in this README that is
> marked `TBD` will be filled in from an actual evaluation run — never
> estimated.

---

## Why this exists

Built to match the Generative AI internship posting at ArcelorMittal France,
which asks for RAG and LLM agents over text, tabular data and source code; SQL
connectors into enterprise data; proofs of concept made industrialisable; and
user testing, documentation and training material. Each of those is a
deliverable here.

---

## Architecture

```
                 ┌───────────────────────────┐
  User (FR/EN) → │  Streamlit UI  (ui/)      │
                 └────────────┬──────────────┘
                              │ HTTP (X-API-Key)
                 ┌────────────▼──────────────┐
                 │  FastAPI  (src/api/)      │  → /v1/ask, /v1/feedback, /health
                 └────────────┬──────────────┘
                              │
                 ┌────────────▼──────────────┐
                 │  LangGraph agent          │  planner loop, max 5 tool calls
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

One Postgres instance holds the business data, the vectors and the application
tables. Fewer moving parts is closer to what an industrial IT department will
actually accept, and it keeps the SQL surface honest.

---

## Quickstart

Requires Docker and Python 3.11.

```bash
cp .env.example .env     # then edit the passwords
make setup               # create the venv, install the project
make up                  # start Postgres with pgvector
make seed-data           # download both UCI datasets, load them, add the synthetic layer
make test                # unit tests
```

`make seed` runs the full pipeline including the corpus index (available from
milestone 2).

Running the local LLM on macOS: Docker has no Metal access, so Ollama runs
natively on the host. `brew install ollama && brew services start ollama`, then
`ollama pull qwen3:4b`. Containers reach it at `http://host.docker.internal:11434`.

---

## Data

Two public UCI datasets, plus a clearly labelled synthetic layer that links
them. Every fabricated column is itemised in [docs/DATA_CARD.md](docs/DATA_CARD.md).

| Table | Rows | Provenance |
|---|---|---|
| `plant.energy_readings` | 35,040 | Real — UCI 851, one row per 15 min of 2018 |
| `plant.plate_inspections` | 1,941 | Real measurements — UCI 198; line and timestamp synthetic |
| `plant.maintenance_events` | 300 | Synthetic |
| `plant.fault_types` | 7 | Codes real, labels and severity synthetic |
| `plant.production_lines` | 3 | Synthetic |
| `plant.shifts` | 3 | Synthetic |

No real company data of any kind is used.

---

## Security

The agent's database access is read-only at two independent layers, so neither
one alone is load-bearing:

1. **Role.** Generated SQL runs as `assistant_ro`, which holds `SELECT` on
   schema `plant` and nothing else. It has no grants on `rag` or `app`, and a
   5-second `statement_timeout`. The role can unset its own
   `default_transaction_read_only` flag — the grants still refuse every write,
   and there is a test that proves it.
2. **Guard.** Every generated statement is parsed with `sqlglot` before it
   executes: exactly one statement, root must be `SELECT`, tables restricted to
   a `plant` whitelist, admin functions blocked, `LIMIT` injected when absent.
   This also blocks `pg_catalog` and `information_schema`, which Postgres
   exposes to every role and which no grant can practically revoke.

Retrieved documents and code are treated as data, never as instructions. With
the local model, no data leaves the machine. Row contents are never logged.

---

## Results

`TBD` — five pipeline configurations (C0 baseline through C4 tool-calling) will
be evaluated on roughly 60 questions, tracked in MLflow, and reported in
`docs/EVAL_REPORT.md`. No number will appear here that did not come from a run.

---

## Documentation

| Document | |
|---|---|
| [docs/DATA_CARD.md](docs/DATA_CARD.md) | Sources, licences, row counts, every synthetic column |
| [DECISIONS.md](DECISIONS.md) | One entry per non-trivial choice and per deviation from the plan |
| `docs/ARCHITECTURE.md` | Milestone 6 |
| `docs/EVAL_REPORT.md` | Milestone 5, generated |
| `docs/USER_GUIDE_FR.md` | Milestone 7 |
| `docs/USER_TEST_PROTOCOL_FR.md` | Milestone 7 |
| `docs/TRAINING_SESSION_FR.md` | Milestone 7 |

---

## Limitations

- The document corpus and the cross-table links are synthetic. The measurements
  are real; the plant they describe is not.
- The evaluation set is small (~60 questions) and single-annotator.
- The default models are sized for an 8 GB laptop. Larger models are a config
  change, and the report states which models produced its numbers.

---

## Licence

Code under MIT. The UCI datasets keep their own licences; see the data card.

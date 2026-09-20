# Steel Plant Data Assistant

A GenAI agent that answers questions about a steel plant by choosing between
three tools — **text-to-SQL** over a Postgres database, **RAG** over a French
document corpus, and **semantic search** over a legacy analytics codebase — and
shows its evidence for every answer: the SQL it ran and the rows it got back,
the document sections it cited, or the exact file and line range.

Questions can be asked in French or English; the answer comes back in the
language it was asked in. Everything runs locally — no data leaves the machine.

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

One Postgres instance holds the business data, the vectors and the application
tables. Fewer moving parts is closer to what an industrial IT department will
actually accept, and it keeps the SQL surface honest.

Full detail in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Quickstart

Requires Docker and Python 3.11.

```bash
cp .env.example .env        # then edit the passwords
make setup                  # virtualenv + dependencies
make seed                   # database up, UCI data loaded, corpus indexed
make up-all                 # api, ui and mlflow
```

The UI is then at <http://localhost:8501>, the API at <http://localhost:8000>,
MLflow at <http://localhost:5000>.

**Local model.** On macOS, Docker has no Metal access, so Ollama runs natively
on the host and containers reach it at `host.docker.internal`:

```bash
brew install ollama && brew services start ollama
ollama pull qwen2.5:3b-instruct
```

On Linux with a GPU, `docker compose --profile local-llm up` runs Ollama as a
service instead. Any OpenAI-compatible endpoint works by setting
`SDA_LLM__BACKEND=openai_compatible` and `SDA_LLM__BASE_URL`.

Run `make help` for every target.

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

Plus 40 French documents and 12 legacy analytics source files, indexed into 234
chunks. **No real company data of any kind is used.**

---

## Security

The agent's database access is read-only at two independent layers, so neither
one alone is load-bearing:

1. **Role.** Generated SQL runs as `assistant_ro`, which holds `SELECT` on
   schema `plant` and nothing else, with a 5-second `statement_timeout`. The
   role can unset its own `default_transaction_read_only` flag — the grants
   still refuse every write, and there is a test that proves exactly that by
   turning the flag off first.
2. **Guard.** Every generated statement is parsed with `sqlglot` before it
   executes: exactly one statement, root must be `SELECT`, tables restricted to
   a `plant` whitelist, admin functions blocked, `LIMIT` injected when absent.
   Writes are rejected anywhere, including inside nested CTEs — Postgres allows
   `WITH x AS (DELETE ... RETURNING ...)`, which a root-only check would miss.
   The guard also blocks `pg_catalog` and `information_schema`, which Postgres
   exposes to every role and which no grant can practically revoke.

Validation walks the parse tree rather than matching text, because a string
blocklist is defeated by case, by `/**/` comments and by quoting — all three
are in the test suite, which has 69 cases for the guard alone.

Retrieved documents and code are treated as data, never as instructions. Row
contents are never logged.

---

## Evaluation

Five pipeline configurations over 60 questions (18 sql, 12 docs, 10 code, 12
multi, 8 unanswerable; half French, half English), tracked in MLflow.

| Config | Agent | Few-shot | Retries | Retrieval | Rerank |
|---|---|---|---|---|---|
| C0 baseline | router | none | 0 | dense | off |
| C1 | router | static | 2 | dense | off |
| C2 | router | static | 2 | hybrid | off |
| C3 | router | dynamic | 2 | hybrid | on |
| C4 | tool_calling | dynamic | 2 | hybrid | on |

Metrics: SQL execution accuracy and valid rate, routing accuracy, retrieval
recall@5, faithfulness and answer correctness (LLM judge), refusal accuracy,
false refusal rate, number grounding, and latency.

**Results: see [docs/EVAL_REPORT.md](docs/EVAL_REPORT.md)**, generated by
`make report` from actual runs. No number appears there that did not come from
a run.

Gold SQL is executed and stored before any evaluation, and a leakage check
rejects any question that overlaps a few-shot example by normalised text or by
embedding similarity above 0.90. That check caught five real overlaps, which is
why the few-shot file no longer contains the examples it started with.

---

## Documentation

| Document | |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, security, limitations |
| [docs/DATA_CARD.md](docs/DATA_CARD.md) | Sources, licences, row counts, every synthetic column |
| [docs/EVAL_REPORT.md](docs/EVAL_REPORT.md) | Generated from real runs |
| [docs/USER_GUIDE_FR.md](docs/USER_GUIDE_FR.md) | Guide utilisateur (français) |
| [docs/USER_TEST_PROTOCOL_FR.md](docs/USER_TEST_PROTOCOL_FR.md) | Protocole de test utilisateur |
| [docs/TRAINING_SESSION_FR.md](docs/TRAINING_SESSION_FR.md) | Session de prise en main de 30 minutes |
| [DECISIONS.md](DECISIONS.md) | One entry per non-trivial choice and per deviation from the plan |

`DECISIONS.md` is the most useful file for anyone reviewing this work. It
records what the plan expected, what reality turned out to be, and what changed
as a result — including two occasions where a conclusion recorded earlier had
to be corrected by measurement.

---

## Limitations

- **The judge is the model under test.** Only one model fits in 8 GB, so the
  judge is the same model that produced the answers. It grades its own work.
  The deterministic metrics carry the weight of any conclusion.
- **The document corpus and the cross-table links are synthetic.** The
  measurements are real; the plant they describe is not.
- **The evaluation set is small** (60 questions) and single-annotator.
- **A single static API key.** Enough for a proof of concept, not for
  production.
- **Small models.** Defaults are sized for an 8 GB laptop; larger models are a
  configuration change.

## What production would need

SSO and per-user authorisation. Access control at the row and table level
rather than one shared read-only role. Monitoring on latency, refusal rate and
grounding, with alerting when grounding drops. A human feedback loop that
actually feeds back — `app.feedback` exists but nothing consumes it yet. And a
substantially larger evaluation set with more than one annotator.

---

## Licence

Code under MIT. The UCI datasets keep their own licences; see the data card.

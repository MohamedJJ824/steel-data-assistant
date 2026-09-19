# Decision log

One entry per non-trivial choice or per deviation from `LLM Project Plan.md`.
Format: date, decision, reason, alternatives considered.

---

## 2026-09-19 — Repository root keeps the existing folder name

**Decision.** The working folder stays `Steel Plant Data Assistant/`; the GitHub repository is named `steel-data-assistant` as specified in plan section 5.

**Reason.** The folder already existed with the plan inside it. Renaming a user's directory is not worth the churn; the remote name is what people see.

**Alternatives.** Rename the local folder to match — rejected as needless.

---

## 2026-09-19 — Fault column is spelled `K_Scratch`, not `K_Scatch`

**Decision.** Use `K_Scratch` everywhere. Plan section 6.2 says the source spelling is `K_Scatch` ("sic, keep source spelling in the raw layer"); that is not what the source actually contains.

**Reason.** Verified at runtime against UCI id=198 via `ucimlrepo`. The seven target columns are exactly `Pastry, Z_Scratch, K_Scratch, Stains, Dirtiness, Bumps, Other_Faults`. The misspelling `K_Scatch` appears in some secondary copies of this dataset (notably the Kaggle mirror) but not in the UCI API payload we load from. Plan rule 2 says follow reality.

**Alternatives.** Preserve `K_Scatch` in a raw layer anyway — rejected, it would mean inventing a spelling the loader never sees.

---

## 2026-09-19 — Energy dataset: interval labels are end-of-interval, so file order is not chronological

**Decision.** Parse `date` with explicit format `%d/%m/%Y %H:%M` (day-first) and treat the timestamp as the **end** of each 15-minute interval. Sort by timestamp after loading rather than trusting file order.

**Reason.** Verified at runtime: field 1 reaches 31 while field 2 caps at 12, so day-first is confirmed. The parsed series spans `2018-01-01 00:00:00` to `2018-12-31 23:45:00` but is **not monotonically increasing** in file order — each day's block runs `00:15 … 23:45` and then a `00:00` row that closes the day out. Letting pandas infer the format, or assuming file order is chronological, both produce silently wrong data.

**Alternatives.** `dayfirst=True` inference — rejected, slower and not guaranteed stable across pandas versions.

---

## 2026-09-19 — Loader must handle a UTF-8 BOM and supply its own CA bundle

**Decision.** `scripts/download_data.py` reads the UCI CSV with `encoding="utf-8-sig"` and sets `SSL_CERT_FILE` from `certifi` before any network call.

**Reason.** Both verified at runtime. The raw response starts with `\xef\xbb\xbf`, which turns the first column name into `﻿date` under plain `utf-8`. Separately, the python.org 3.11.6 framework build on this machine ships without a usable CA store, so `ucimlrepo` fails with `CERTIFICATE_VERIFY_FAILED` and reports it misleadingly as `DatasetNotFoundError`. System `curl` reaches the same URL fine, which is what isolated it to Python's cert store.

**Alternatives.** Run macOS's `Install Certificates.command` — rejected, fixes this machine but not a fresh clone. Pinning `certifi` makes the repo portable.

---

## 2026-09-19 — Small local models instead of the plan's defaults

**Decision.** Default to a ~4B instruct model on Ollama and `intfloat/multilingual-e5-base` (768 dimensions) for embeddings, with the reranker off by default. `bge-m3` (1024 dim), `bge-reranker-v2-m3` and 7-8B models stay reachable through config.

**Reason.** Build machine is an Apple M2 with 8 GB RAM and 17 GB free disk. The plan's defaults come to roughly 10-12 GB of model weights, which does not leave room for Postgres, images and caches. Plan section 13 already anticipates both swaps.

**Consequence.** `rag.chunks.embedding` is `VECTOR(768)`, not 1024. The dimension is read from config so switching models is a re-index, not a code change. Evaluation numbers will reflect the smaller models — the report must say so.

**Alternatives.** Hosted OpenAI-compatible endpoint — offered and declined in favour of staying local.

---

## 2026-09-19 — Peak-load alert threshold sourced from the data

**Decision.** The energy policy document's numeric alert threshold is the 95th percentile of `usage_kwh`, **99.04 kWh**, rounded to **99 kWh** in prose.

**Reason.** Plan section 6.6 asks for a threshold derived from the data so a question can require both SQL and a document. Computed at sanity-check time over all 35,040 rows.

**Alternatives.** A round invented number — rejected by plan rule 1.

---

## 2026-09-19 — Reference tables are seeded by the loader, not the synthetic generator

**Decision.** `scripts/load_db.py` seeds `plant.production_lines`, `plant.shifts` and `plant.fault_types`. `scripts/generate_synthetic_tables.py` then does the enrichment: assigning `line_id` / `inspected_at` to plates, and building `plant.maintenance_events`. Plan section 6.3 puts all four in the generator.

**Reason.** `plate_inspections.fault_code` and `line_id` carry foreign keys to `fault_types` and `production_lines`, so those parents have to exist before any real row can be inserted. Running the generator first would invert the Makefile's `download → load → synthetic` order.

**Consequence.** `plate_inspections.inspected_at` is nullable in the DDL: real rows land first, the synthetic timestamp is written in the second pass. Everything seeded here is still listed as synthetic in `docs/DATA_CARD.md`.

**Alternatives.** Drop the foreign keys — rejected, they are load-bearing for the text-to-SQL joins. Merge both scripts — rejected, the plan's split keeps real and synthetic provenance visible.

---

## 2026-09-19 — Role creation is a shell script, not `04_roles.sql`

**Decision.** `docker/db/init/04_roles.sh` instead of the `04_roles.sql` named in plan section 5.

**Reason.** Role passwords come from the environment, and a plain `.sql` file run by the Postgres entrypoint cannot read env vars. The entrypoint executes `.sh` files in the same alphabetical pass, so ordering is unaffected.

**Alternatives.** Hard-code the passwords in the SQL — rejected by plan rule 6.

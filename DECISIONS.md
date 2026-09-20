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

---

## 2026-09-19 — Local inference measured at ~5 tokens/second

**Decision.** Recorded as a constraint, not yet acted on. The evaluation plan (five configurations × ~60 questions) needs re-scoping or a faster backend before milestone 5.

**Reason.** Measured on this machine with `qwen3:4b` warm, `keep_alive` set, three consecutive calls: 48-53 s wall per short answer, ~250 output tokens, **5.0-5.2 tok/s**. An M2 should manage roughly 25-30 tok/s for a 4B model. The cause is memory pressure, not the model: `sysctl vm.swapusage` reports **12.5 GB of 13.3 GB swap in use** with 15% of physical memory free, so weights are being paged in and out during generation.

**Consequence.** At this rate one agent run is 1-3 minutes, so 300 evaluation runs plus judge calls is roughly 8-12 hours. Every LLM-free component (chunkers, SQL guard, hybrid search, metrics) is built and tested independently so that none of it is blocked on inference speed.

**Alternatives.** A 1.7B model would roughly double throughput at a real cost in SQL quality. A hosted OpenAI-compatible endpoint would remove the constraint entirely. Both remain a config change.

---

## 2026-09-19 — `qwen3:4b` capabilities confirmed by probe

**Decision.** Keep `router` as the default agent mode, but `tool_calling` (config C4) is genuinely testable on this model. Every LLM call prepends `/no_think`.

**Reason.** Probed directly against the Ollama API:

* **Structured output works.** Passing a JSON schema in `format` returned valid, parseable JSON on the first try — this is what the `sql_query` tool depends on.
* **Native tool calling works.** The model emitted a well-formed `tool_calls` entry with the right function and arguments, so C4 is a real comparison rather than a guaranteed failure.
* **`think: false` does not suppress reasoning.** It leaks into `message.content` as prose while `message.thinking` stays empty. The `/no_think` directive in the user message does work, returning a clean `OK`. Without it, every answer would be polluted with the model's internal monologue.

**Alternatives.** Stripping `<think>` tags after the fact — kept as a defensive fallback in the client, since `/no_think` is a model-specific convention that a backend swap would silently drop.

---

## 2026-09-19 — Legacy code corpus is hand-written, not generated

**Decision.** The 12 files in `corpus/legacy_code/` were written directly rather than produced by the LLM.

**Reason.** This corpus is the ground truth for the `search_code` evaluation questions, so each file needs specific, checkable logic to target: the energy-intensity denominator is a plate count and not a tonnage, `ALWAYS_HOLD` overrides the reference table's severity, the night shift is imputed to the day it started. Generated prose tends to average those details away, and the corpus is committed anyway.

**Consequence.** `corpus/` is excluded from `ruff`: it is deliberately uneven in style, with French comments and `TODO`s, because that is what it is imitating.

---

## 2026-09-20 — Document facts are injected, not generated

**Decision.** `scripts/generate_docs.py` writes every fact itself — event ids, dates, downtime, thresholds, counts, hold durations — directly from the database. The LLM writes only connecting prose, and each prose section has a deterministic fallback.

**Reason.** Plan section 6.6 has the LLM write documents from injected facts. Letting it write the *numbers* would make the corpus uncheckable: `validate_corpus.py` could not compare a document against the database, and no evaluation question over these documents would have a gold answer. Splitting the two also means a model failure degrades prose, never correctness.

**Consequence.** `--no-llm` produces a complete, valid corpus. The LLM pass is an improvement, not a dependency, which matters when one pass takes about an hour at 5 tok/s.

---

## 2026-09-20 — `app_rw` needs USAGE on `public` for the `vector` type

**Decision.** `GRANT USAGE ON SCHEMA public TO app_rw`.

**Reason.** A bug introduced by the role hardening in milestone 1. `04_roles.sh` runs `REVOKE ALL ON SCHEMA public FROM PUBLIC`, but pgvector installs its types into `public`. Every dense search then failed with `type "vector" does not exist`, while indexing worked because it runs as superuser. Caught by the first end-to-end retrieval run.

**Consequence.** `public` holds no tables — `CREATE` stays revoked — so this exposes the type namespace and nothing else. `assistant_ro` is deliberately not granted it: `has_schema_privilege('assistant_ro','public','USAGE')` is still false.

---

## 2026-09-20 — Keyword search uses OR semantics, not `websearch_to_tsquery`'s AND

**Decision.** Rewrite the parsed tsquery's `&` operators to `|` before matching.

**Reason.** `websearch_to_tsquery` joins every term with AND, so a chunk must contain *all* of a question's words. Measured: `"défaut Z_Scratch actions immédiates"` matched **0** chunks under AND and **133** under OR, with the correct procedure at keyword rank 15 — inside the 20-candidate fusion window, which is what RRF needs. Under AND the keyword branch returned nothing for almost every natural-language question, so `retrieval.mode: hybrid` was silently identical to `dense`, and the C1-versus-C2 evaluation would have compared a configuration against itself.

**Alternatives.** `plainto_tsquery` — same AND semantics. Trying AND and falling back to OR — more moving parts for no measured gain.

---

## 2026-09-20 — The tsvector weights headings above body text

**Decision.** `setweight(to_tsvector(config, heading), 'A') || setweight(to_tsvector(config, content), 'B')`, where the heading is `title > section` for documents and `path symbol` for code.

**Reason.** Switching to OR semantics caused a regression: the twenty maintenance reports are near-identical by construction, all containing "défaut" and a fault code, so they flooded the keyword branch and pushed `PROC-FLT-ZSCR` off the top for the very query it should win. Weighting the heading fixed it — `ts_rank_cd` applies the default weights {A 1.0, B 0.4}, so a chunk whose *section* is "Actions immédiates" outranks twenty chunks that merely mention the words.

**Consequence.** Changing the tsvector requires `build_index.py --rebuild`, not an incremental run: the content hash is unchanged, so the incremental path would skip every file.

**Measured after the fix.** Twelve targeted retrieval queries across both corpora return the expected source at rank 1, under both `dense` and `hybrid`. These smoke queries are too easy to separate the two modes — that is what the milestone 5 evaluation is for, and no claim that hybrid beats dense is made until it is measured.

---

## 2026-09-20 — Default model switched from `qwen3:4b` to `qwen2.5:3b-instruct`

**Decision.** All three model slots (`agent_model`, `sql_model`, `judge_model`) now point at a non-reasoning instruct model. `suppress_reasoning` defaults to false; `num_ctx` is set to 8192.

**This corrects the 2026-09-19 entry above,** which recorded that `/no_think` reliably suppresses reasoning on qwen3. It does not. That conclusion came from a probe — "Reply with exactly one word: OK" — too trivial to expose the behaviour.

**Reason.** Measured on a real generation prompt, `qwen3:4b` with `/no_think` produced **2,697 output tokens** and took **467 seconds** to return **471 characters** of usable French. The reasoning is emitted, then discarded by `strip_reasoning`. The same prompt on `qwen2.5:3b-instruct` produced **206 tokens** with no leaked reasoning and comparable prose quality.

This was not a speed annoyance but a blocker: at roughly eight minutes per call, a single agent run would take half an hour and the five-configuration evaluation would have taken weeks. It surfaced because a 40-document generation run wrote nothing in 100 minutes.

**Capabilities re-verified on the new model**, since C4 and the SQL tool depend on them: structured JSON output parsed first try (30 s, 146 tokens), and native tool calling emitted the right function with the right arguments (26 s, 120 tokens). Both still work.

**A second finding from the same investigation.** Two models cannot be resident at once on 8 GB: with `qwen3` still held by `keep_alive`, a `qwen2.5` call spent about 610 of its 658 seconds loading. With one model resident, calls settle at 25-30 s. Anything that switches models mid-run pays that cost every time, so the judge model is deliberately the same model rather than a stronger one — and the evaluation report must say so, because a model judging its own output is a real limitation.

**Alternatives.** Capping `num_predict` on qwen3 — rejected, it truncates mid-reasoning and yields nothing usable. A hosted endpoint — still available through config, and would remove the constraint entirely.

---

## 2026-09-20 — Schema context is read live, with sample rows

**Decision.** `schema_context.py` builds the text-to-SQL prompt's schema description from the live database: columns, types, keys, the FR/EN `COMMENT ON` text, and three real rows per table. Cached per process.

**Reason.** Evidence that the sample rows earn their tokens: the very first model probe of this project, with no schema context, generated `load_type = 'maximum load'`. The stored value is `Maximum_Load`, so that query returns zero rows and the wrong answer looks like a legitimate empty result. With the sample rows in the prompt, the same model got it exactly right.

**Consequence.** The rendered context is about 10.7 KB, roughly 2,700 tokens — which is why `num_ctx` is 8192 rather than the 4096 default. `plant.plate_inspections` and its 27 measurement columns dominate; if the context needs trimming later, that table is where to start.

---

## 2026-09-20 — The router needs worked examples, and it is measurable

**Decision.** `ROUTER_SYSTEM` carries ten worked examples instead of category definitions alone.

**Reason.** Measured on the default model over ten questions, zero-shot classification scored **7/10**; with examples it scored **9/10**, and ran faster (36 s against 54 s) because the justifications got shorter. The zero-shot failures were not marginal: "Combien de tôles ont un défaut Bumps ?" went to `code`, and "Quelle est la durée de mise en attente pour une rayure en Z ?" went to `out_of_scope` — a plain refusal of an answerable question.

**Caveat.** Ten questions chosen by hand is a sanity check, not an evaluation. The real number comes from the milestone 5 routing-accuracy metric over the full question set, and this entry is not a claim about that.

**The remaining failure is arguably not one.** "Quel est le seuil d'alerte de pointe de consommation ?" classifies as `code`, and the threshold genuinely lives in both `POL-ENR-PEAK` and `config_thresholds.py`. It is a `multi` question, and the evaluation set should label it that way.

**Worth noting for the report.** When the router sent that SQL question to `code`, synthesis did not invent a count — it said the figure was not in the outputs. Wrong routing produced a non-answer rather than a confident wrong answer, which is the failure mode to prefer.

---

## 2026-09-20 — Citations must be copied, not templated

**Decision.** The synthesis prompt tells the model to copy a citation verbatim from the `--- SOURCE ... ---` header, and forbids bracket citations for SQL figures.

**Reason.** The first end-to-end request returned: *"Il y a 402 tôles avec un défaut Bumps ... [DOC-ID §1]"*. The count was right and grounded 1/1, but `[DOC-ID §1]` is a citation to nothing — the model had copied the placeholder out of the instructions. A fabricated citation is worse than none, because it looks checkable.

**Consequence.** The placeholder is gone. The model now sometimes restates the question and omits the SQL attribution instead, which the milestone 5 faithfulness metric will measure rather than being tuned against by hand.

---

## 2026-09-20 — Foreign keys were never reaching the prompt

**Decision.** Read foreign keys from `pg_constraint` instead of the
`information_schema` views.

**Reason.** A bug present since the schema context was written. The
`information_schema.table_constraints` / `key_column_usage` /
`constraint_column_usage` views filter their rows by the caller's privileges,
and as `app_rw` the join returned **nothing** for every table. The text-to-SQL
prompt therefore never told the model how the tables relate — on the hardest
part of the task, joins, it was working blind.

It surfaced only because a probe for `FOREIGN KEY` in the rendered context came
back false. Nothing errored; the prompt was simply missing a section, which is
exactly the kind of fault that shows up as "the model is bad at joins".

**Consequence.** `plate_inspections` and `maintenance_events` now declare their
links to `fault_types` and `production_lines`. Immediately afterwards, a
question about downtime by fault generated a correct three-table join.

---

## 2026-09-20 — Generated output is capped at 768 tokens

**Decision.** Set `num_predict: 768` on every Ollama call.

**Reason.** Ollama generates without limit by default, so a schema-constrained
call can run until it fills `num_ctx`. One evaluation question —
*"What is the total CO2 emitted across 2018, in tonnes?"* — hung for over four
minutes and was still going; with the cap it stopped at exactly 768 tokens with
`done_reason=length` and an unterminated JSON string, which is what made the
looping visible. It had stalled two separate evaluation runs at the same
question, and looked like memory pressure until it reproduced in isolation.

**Consequence.** A pathological generation now fails in about a minute instead
of hanging, and the self-correction loop can retry it. The cap is comfortably
above what a query plus its explanation needs.

---

## 2026-09-20 — Wide tables render without per-column comments

**Decision.** `render_schema_context` attaches comments to the first twelve
columns plus every key and foreign key; the rest are listed as name and type.

**Reason.** `plant.plate_inspections` has 30 columns, 25 of them self-describing
geometry measurements (`x_minimum`, `pixels_areas`), each carrying a bilingual
comment. That one table was 4,293 of 10,711 characters — 40% of the prompt —
for very little the column name did not already say. Keys keep their comments
because those are the columns a join depends on.

**Consequence.** The context went from ~2,677 to ~2,435 tokens while gaining the
foreign-key section. Combined with the output cap, the question that had hung
twice now answers correctly in 37 seconds. The reduction alone was not the fix;
the output cap was.

---

## 2026-09-20 — The evaluation was run at reduced scope

**Decision.** Five configurations over a stratified 20-question subset (four per
category) rather than the full 60, and `docs/EVAL_REPORT.md` states the actual
count it was generated from.

**Reason.** Measured throughput on this machine is roughly 60-140 s per
question depending on memory pressure, and the Python process was observed at
1 MB resident with the machine 8.4 GB into a 9.2 GB swap file. Five
configurations over 60 questions is between seven and twenty hours, which is
not a run that can be verified here.

**What is preserved.** All five configurations, every category, both languages,
and every metric. What is lost is statistical power: 20 questions means four per
category, so a per-category figure moves by 0.25 per question. The report must
not be read as separating configurations that differ by a few points.

**Alternatives.** Dropping the judge would roughly halve the time but would also
drop faithfulness and correctness, which are required metrics. A hosted endpoint
would remove the constraint entirely and remains a config change.

---

## 2026-09-20 — The refusal detector had a false negative that understated a headline metric

**Decision.** Widen `REFUSAL_MARKERS` and re-score the stored results with
`scripts/rescore.py` rather than re-running every configuration.

**Reason.** The generated failure analysis flagged Q054 as "an out-of-scope
question was answered". Reading the answer, it was a clean refusal: *"I'm sorry,
but I can't assist with information about our main competitor's production
capacity."* The marker list had `cannot answer` but not `can't assist`, so a
correct refusal scored as a failure.

The correction is material. Refusal accuracy went from 0.667 to **1.000** for
C0, C1 and C2, and from 0.333 to 0.667 for C3. The first report understated how
well the system declines out-of-scope questions.

**Checked for the opposite error.** Widening markers risks catching real answers
and inflating false-refusal instead. Across all five runs exactly one answerable
question now matches, and reading it, it is genuinely a refusal — the SQL tool
failed and the answer says the figure is unavailable. So C0's false-refusal rate
of 0.083 is correct rather than an artefact.

**Why re-score rather than re-run.** Refusal is derived from the answer text,
which is stored per question. Re-scoring uses exactly the answers the agent
produced; nothing was regenerated. Re-running five configurations would have
cost another hour for an identical result.

**Wider point.** A deterministic metric is only as good as its rule, and this
one was wrong in the direction that flattered nothing — it made the system look
worse. It was found because the report prints real failing answers rather than
just counts.

---

## 2026-09-20 — Number grounding can be satisfied by a fabricated literal

**Decision.** Recorded as a known limitation, in `ARCHITECTURE.md` and the
report. Not fixed.

**Reason.** Evaluation question Q020 asks for the peak-load threshold, which
lives in a document. The router sent it to SQL, and the model generated:

```sql
SELECT 100.0 AS peak_load_threshold FROM plant.energy_readings WHERE usage_kwh > 100.0 LIMIT 1
```

It then answered "100.0 kWh". The real threshold is **99**. The number-grounding
check passed, because 100.0 did appear in the tool output — the tool output was
the model's own invented literal.

So grounding verifies that a number in the answer came from a tool, not that the
tool obtained it from the data. A `SELECT <literal>` launders an invented figure
into an apparently grounded one.

**Mitigations that already exist.** The SQL is shown to the user in full, so the
query is inspectable, and the guard rejects queries that read no allowed table —
which is why this one still touches `energy_readings`. A future fix would flag
projections that are bare literals, since a legitimate analytical query almost
never selects a constant as its answer.

**Why it matters more than the individual failure.** It is the one metric that
looks like a correctness guarantee and is not. The report should not let a
reader infer otherwise.

# Evaluation report

Generated 2026-09-20 by `scripts/make_report.py`.
Every number below comes from an actual run. Nothing is estimated.

## Setup

- **Hardware**: Apple M2, 8 GB RAM, Darwin 25.2.0
- **Questions**: 15 (18 sql, 12 docs, 10 code, 12 multi, 8 unanswerable; half French, half English)
- **Models**: see the per-configuration parameters logged in MLflow (experiment `steel-assistant-eval`)

> **The judge is the model under test.** Only one model fits in memory on this machine, so `judge_model` is the same model that produced the answers. It grades its own work, which inflates faithfulness and correctness. The deterministic metrics — SQL execution accuracy, routing, refusal and number grounding — are the ones to rely on.

## Results by configuration

| Config | Agent | Few-shot | Retries | Retrieval | Rerank |
|---|---|---|---|---|---|
| C0 baseline | router | none | 0 | dense | off |
| C1 few-shot | router | static | 2 | dense | off |
| C2 hybrid | router | static | 2 | hybrid | off |
| C3 rerank | router | dynamic | 2 | hybrid | on |
| C4 tool-calling | tool_calling | dynamic | 2 | hybrid | on |

| Metric | C0 baseline | C1 few-shot | C2 hybrid | C3 rerank | C4 tool-calling |
|---|---|---|---|---|---|
| SQL exec. acc. | 0.167 | 0.667 | 0.667 | 0.667 | 0.333 |
| SQL valid | 0.556 | 0.889 | 0.889 | 0.889 | 0.545 |
| Routing | 0.500 | 0.583 | 0.583 | 0.583 | 0.333 |
| Routing (superset) | 0.750 | 0.833 | 0.833 | 0.833 | 0.583 |
| Recall@5 | 0.556 | 0.556 | 0.556 | 0.556 | 0.778 |
| Faithfulness | — | 4.333 | — | — | — |
| Correctness | — | 3.222 | — | — | — |
| Refusal acc. | 1.000 | 1.000 | 1.000 | 0.667 | 0.333 |
| False refusal | 0.083 | 0.000 | 0.000 | 0.000 | 0.000 |
| Num. grounding | 0.900 | 0.938 | 0.933 | 0.933 | 0.857 |
| Latency p50 (s) | 26.6 | 29.9 | 21.0 | 27.3 | 53.8 |
| Latency p95 (s) | 124.7 | 78.3 | 60.2 | 64.4 | 118.3 |
| Wall time (min) | 11.1 | 12.3 | 6.6 | 8.3 | 16.2 |

## Per-category breakdown — C1 few-shot

| Category | n | SQL exec. | Recall@5 | Faithfulness | Grounding | p50 (s) |
|---|---|---|---|---|---|---|
| sql | 3 | 1.000 | — | 5.000 | 1.000 | 27.9 |
| docs | 3 | — | 0.333 | 3.667 | 0.667 | 23.6 |
| code | 3 | — | 1.000 | 5.000 | 1.000 | 38.0 |
| multi | 3 | 0.333 | 0.333 | 3.667 | 1.000 | 32.2 |
| unanswerable | 3 | — | — | — | — | 13.4 |

## Failure analysis

Drawn from `eval/runs/c1-20260920-195502.csv`, one per distinct failure mode.

### 1. Q020 — retrieval-miss

**Question** (docs, en): What is the peak-load alert threshold in kWh per 15-minute interval?

**What happened**: the gold source was not in the top 5.
Tools called: `sql_query`; expected: `search_docs`.

```sql
SELECT 100.0 AS peak_load_threshold FROM plant.energy_readings WHERE usage_kwh > 100.0 LIMIT 1
```

**Answer given**: The peak-load alert threshold is 100.0 kWh per 15-minute interval.   SOURCE: --- SOURCE SQL ---


### 2. Q031 — invalid-sql

**Question** (code, en): Which function computes the energy intensity KPI and what denominator does it use?

**What happened**: no valid SQL was produced.
Tools called: `search_docs|search_code`; expected: `search_code`.

```sql
SELECT f.function AS function, f.denominator AS denominator FROM plant.functions AS f LIMIT 200
```

**Answer given**: The function that computes the energy intensity KPI is defined in the file `kpi_energy.py` and its range is from line 9 to line 18. The function `energy_intensity` uses the `plates_produced` as the denominator.  The denominator used by the function `energy_intensity` is the **number of plates produc


### 3. Q041 — wrong-sql

**Question** (multi, fr): Quel type de défaut a causé le plus de minutes d'arrêt en 2018, et que dit la procédure associée sur les actions immédiates ?

**What happened**: the query ran but returned the wrong result.
Tools called: `sql_query|search_docs|search_code`; expected: `sql_query|search_docs`.

```sql
SELECT f.label_en, f.procedure_doc_id FROM plant.fault_types AS f JOIN (SELECT fault_code, SUM(downtime_minutes) AS total_minutes FROM plant.maintenance_events WHERE started_at >= '2018-01-01' AND ended_at <= '2018-12-31' GROUP BY fault_code) AS m ON f.fault_code = m.fault_code WHERE m.total_minutes
```

**Answer given**: Le type de défaut qui a causé le plus de minutes d'arrêt en 2018 est "K_Scratch", avec 424 minutes d'arrêt, selon la requête SQL.   La procédure associée à ce défaut, "Procédure de traitement des défauts Other_Faults" (d'après la procédure associée), indique que si le défaut réapparaît sur plus de t


### 4. Q054 — missed-refusal

**Question** (unanswerable, en): What is our main competitor's production capacity this year?

**What happened**: an out-of-scope question was answered.

**Answer given**: The plant's production database covers our own production data, our French procedures and policies, and our analytics source code. I'm sorry, but I can't assist with information about our main competitor's production capacity.


### Failure counts

| Failure mode | Questions |
|---|---|
| retrieval miss | 4 |
| wrong SQL result | 2 |
| no valid SQL | 1 |
| missed refusal | 1 |

## Reproducing

```bash
make up && make seed
make eval-all
make report
```

Runs are tracked in MLflow under experiment `steel-assistant-eval`, with the full configuration as parameters and the per-question CSV as an artifact.

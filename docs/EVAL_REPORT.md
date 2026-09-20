# Evaluation report

Generated 2026-09-20 by `scripts/make_report.py`.
Every number below comes from an actual run. Nothing is estimated.

## Setup

- **Hardware**: Apple M2, 8 GB RAM, Darwin 25.2.0
- **Questions**: 5 (18 sql, 12 docs, 10 code, 12 multi, 8 unanswerable; half French, half English)
- **Models**: see the per-configuration parameters logged in MLflow (experiment `steel-assistant-eval`)

> **The judge is the model under test.** Only one model fits in memory on this machine, so `judge_model` is the same model that produced the answers. It grades its own work, which inflates faithfulness and correctness. The deterministic metrics — SQL execution accuracy, routing, refusal and number grounding — are the ones to rely on.

## Results by configuration

| Config | Agent | Few-shot | Retries | Retrieval | Rerank |
|---|---|---|---|---|---|
| C0 baseline *(not run)* | router | none | 0 | dense | off |
| C1 few-shot | router | static | 2 | dense | off |
| C2 hybrid *(not run)* | router | static | 2 | hybrid | off |
| C3 rerank *(not run)* | router | dynamic | 2 | hybrid | on |
| C4 tool-calling *(not run)* | tool_calling | dynamic | 2 | hybrid | on |

| Metric | C1 few-shot |
|---|---|
| SQL exec. acc. | 0.500 |
| SQL valid | 0.667 |
| Routing | 0.500 |
| Routing (superset) | 1.000 |
| Recall@5 | 0.667 |
| Faithfulness | — |
| Correctness | — |
| Refusal acc. | 1.000 |
| False refusal | 0.000 |
| Num. grounding | 1.000 |
| Latency p50 (s) | 59.8 |
| Latency p95 (s) | 91.3 |
| Wall time (min) | 4.6 |

*Not yet run: C0 baseline, C2 hybrid, C3 rerank, C4 tool-calling.*

## Per-category breakdown — C1 few-shot

| Category | n | SQL exec. | Recall@5 | Faithfulness | Grounding | p50 (s) |
|---|---|---|---|---|---|---|
| sql | 1 | 1.000 | — | — | 1.000 | 59.8 |
| docs | 1 | — | 1.000 | — | 1.000 | 28.7 |
| code | 1 | — | 1.000 | — | 1.000 | 76.9 |
| multi | 1 | 0.000 | 0.000 | — | 1.000 | 94.9 |
| unanswerable | 1 | — | — | — | — | 18.0 |

## Failure analysis

Drawn from `eval/runs/c1-20260920-180107.csv`, one per distinct failure mode.

### 1. Q031 — invalid-sql

**Question** (code, en): Which function computes the energy intensity KPI and what denominator does it use?

**What happened**: no valid SQL was produced.
Tools called: `search_docs|search_code`; expected: `search_code`.

```sql
SELECT f AS function_name, d AS denominator
FROM (
  SELECT 'Energy intensity (kWh/m²)' AS f, 'usage_kwh' AS d
  UNION ALL
  SELECT 'Power factor (PF) intensity (PF/m²)', 'lagging_current_power_factor' AS d
) AS kpis
ORDER BY f
```

**Answer given**: The function that computes the energy intensity KPI is defined in the file `kpi_energy.py` and its location is `L9-L18`. The denominator used in this function is the **number of plates produced**.


### 2. Q041 — wrong-sql

**Question** (multi, fr): Quel type de défaut a causé le plus de minutes d'arrêt en 2018, et que dit la procédure associée sur les actions immédiates ?

**What happened**: the query ran but returned the wrong result.
Tools called: `sql_query|search_docs|search_code`; expected: `sql_query|search_docs`.

```sql
SELECT f.label_en, f.procedure_doc_id FROM plant.fault_types AS f JOIN plant.maintenance_events AS m ON f.fault_code = m.fault_code WHERE m.downtime_minutes > 120 GROUP BY f.label_en, f.procedure_doc_id ORDER BY SUM(m.downtime_minutes) DESC LIMIT 200
```

**Answer given**: Le type de défaut qui a causé le plus de minutes d'arrêt en 2018 est les rayures en K, comme indiqué par la procédure associée PROC-FLT-OTHR. Selon cette procédure, si le défaut réapparaît sur plus de trois tôles consécutives, il faut alerter le chef d'équipe qualité dans un délai de 60 minutes. Au-


### Failure counts

| Failure mode | Questions |
|---|---|
| no valid SQL | 1 |
| wrong SQL result | 1 |
| retrieval miss | 1 |

## Reproducing

```bash
make up && make seed
make eval-all
make report
```

Runs are tracked in MLflow under experiment `steel-assistant-eval`, with the full configuration as parameters and the per-question CSV as an artifact.

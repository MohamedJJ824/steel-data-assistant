"""MTTR et MTBF par ligne, à partir du journal de maintenance.

Définitions retenues (validées avec le service Maintenance en 2019):
  MTTR = somme des minutes d'arrêt / nombre d'interventions correctives
  MTBF = temps d'ouverture total / nombre d'interventions correctives

Les interventions préventives sont exclues des deux indicateurs: elles sont
planifiées et ne traduisent pas une défaillance.
"""

from collections import defaultdict


def mttr(events):
    """Temps moyen de réparation, en minutes.

    events: liste de dicts avec 'category' et 'downtime_minutes'.
    """
    corrective = [e for e in events if e["category"] == "corrective"]
    if not corrective:
        return None
    total = sum(e["downtime_minutes"] for e in corrective)
    return total / len(corrective)


def mtbf(events, operating_minutes):
    """Temps moyen entre défaillances, en minutes."""
    corrective = [e for e in events if e["category"] == "corrective"]
    if not corrective:
        return None
    return operating_minutes / len(corrective)


def by_line(events, operating_minutes_by_line):
    """MTTR et MTBF pour chaque ligne."""
    grouped = defaultdict(list)
    for event in events:
        grouped[event["line_id"]].append(event)

    out = {}
    for line_id, line_events in sorted(grouped.items()):
        operating = operating_minutes_by_line.get(line_id, 0)
        out[line_id] = {
            "mttr_minutes": mttr(line_events),
            "mtbf_minutes": mtbf(line_events, operating),
            "events": len(line_events),
            "downtime_minutes": sum(e["downtime_minutes"] for e in line_events),
        }
    return out


def top_faults_by_downtime(events, limit=5):
    """Défauts classés par minutes d'arrêt cumulées, du pire au meilleur."""
    totals = defaultdict(int)
    for event in events:
        if event.get("fault_code"):
            totals[event["fault_code"]] += event["downtime_minutes"]
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    return ranked[:limit]

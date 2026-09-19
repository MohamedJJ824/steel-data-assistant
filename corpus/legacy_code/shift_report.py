"""Agrégation par poste (3x8).

Le poste de nuit franchit minuit: les heures de 0h à 6h sont imputées au
poste commencé la veille à 22h. C'est la convention du service Production et
elle diffère de celle du système de paie, qui coupe à minuit.
"""

from collections import defaultdict

from utils_dates import shift_date, shift_of


def aggregate_energy_by_shift(readings):
    """Consommation par (date de poste, code de poste)."""
    buckets = defaultdict(lambda: {"kwh": 0.0, "co2": 0.0, "intervals": 0})
    for row in readings:
        key = (shift_date(row["ts"]), shift_of(row["ts"]))
        bucket = buckets[key]
        bucket["kwh"] += row["usage_kwh"]
        bucket["co2"] += row["co2_tco2"]
        bucket["intervals"] += 1
    return dict(buckets)


def aggregate_faults_by_shift(inspections):
    """Nombre de défauts par (date de poste, code de poste, type de défaut)."""
    buckets = defaultdict(int)
    for row in inspections:
        key = (shift_date(row["inspected_at"]), shift_of(row["inspected_at"]), row["fault_code"])
        buckets[key] += 1
    return dict(buckets)


def shift_totals(readings):
    """Totaux par code de poste sur toute la période."""
    totals = defaultdict(lambda: {"kwh": 0.0, "intervals": 0})
    for row in readings:
        code = shift_of(row["ts"])
        totals[code]["kwh"] += row["usage_kwh"]
        totals[code]["intervals"] += 1
    return dict(totals)


def busiest_shift(readings):
    """Code du poste qui consomme le plus sur la période."""
    totals = shift_totals(readings)
    if not totals:
        return None
    return max(totals.items(), key=lambda kv: kv[1]["kwh"])[0]

"""Indicateurs énergie: intensité énergétique et CO2 par kWh.

Utilisé pour le reporting mensuel envoyé au service Énergie.
"""

from config_thresholds import CO2_FACTOR_TONNES_PER_KWH, PEAK_LOAD_ALERT_KWH


def energy_intensity(total_kwh, plates_produced):
    """Intensité énergétique en kWh par tôle produite.

    Le dénominateur est le NOMBRE DE TÔLES produites sur la période, pas le
    tonnage: la comptabilité tonnage n'est pas fiable avant 2017 et on garde
    la même définition depuis pour que l'historique reste comparable.
    """
    if plates_produced <= 0:
        return None
    return total_kwh / plates_produced


def co2_per_kwh(total_co2_tonnes, total_kwh):
    """Ratio CO2/énergie en kg de CO2 par kWh.

    Le fichier source donne le CO2 en tonnes, on convertit en kg (x1000) parce
    que le service Énergie raisonne en kg.
    """
    if total_kwh <= 0:
        return None
    return (total_co2_tonnes * 1000.0) / total_kwh


def estimated_co2(total_kwh):
    """CO2 estimé à partir du facteur d'émission, quand la mesure manque."""
    return total_kwh * CO2_FACTOR_TONNES_PER_KWH


def peak_intervals(readings):
    """Liste des intervalles dépassant le seuil d'alerte de pointe.

    readings: itérable de dicts avec les clés 'ts' et 'usage_kwh'.
    """
    out = []
    for row in readings:
        if row["usage_kwh"] > PEAK_LOAD_ALERT_KWH:
            out.append((row["ts"], row["usage_kwh"]))
    return out


def monthly_summary(readings, plates_by_month):
    """Agrège les indicateurs par mois.

    Retourne un dict {mois: {kwh, co2_kg_per_kwh, intensity}}.
    """
    buckets = {}
    for row in readings:
        key = row["ts"].month
        bucket = buckets.setdefault(key, {"kwh": 0.0, "co2": 0.0})
        bucket["kwh"] += row["usage_kwh"]
        bucket["co2"] += row["co2_tco2"]

    summary = {}
    for month, bucket in sorted(buckets.items()):
        summary[month] = {
            "kwh": bucket["kwh"],
            "co2_kg_per_kwh": co2_per_kwh(bucket["co2"], bucket["kwh"]),
            "intensity": energy_intensity(bucket["kwh"], plates_by_month.get(month, 0)),
        }
    return summary

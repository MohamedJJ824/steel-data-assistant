"""Rapport sur le facteur de puissance.

Signale les intervalles où le facteur de puissance inductif descend sous le
seuil contractuel. Le fournisseur facture une pénalité en dessous de 90%, on
alerte à 92% pour garder une marge de réaction.
"""

from config_thresholds import POWER_FACTOR_MIN_PCT


def flag_poor_power_factor(readings):
    """Retourne les intervalles au facteur de puissance dégradé.

    On ne regarde que le facteur inductif (lagging): le capacitif n'est
    pénalisé par le contrat que la nuit et le cas ne s'est jamais présenté.
    """
    flagged = []
    for row in readings:
        if row["lagging_current_power_factor"] < POWER_FACTOR_MIN_PCT:
            flagged.append(
                {
                    "ts": row["ts"],
                    "power_factor": row["lagging_current_power_factor"],
                    "usage_kwh": row["usage_kwh"],
                    "reactive_kvarh": row["lagging_current_reactive_power_kvarh"],
                }
            )
    return flagged


def reactive_ratio(readings):
    """Rapport entre énergie réactive inductive et énergie active."""
    active = sum(r["usage_kwh"] for r in readings)
    reactive = sum(r["lagging_current_reactive_power_kvarh"] for r in readings)
    if active <= 0:
        return None
    return reactive / active


def worst_intervals(readings, limit=10):
    """Les pires intervalles, du facteur de puissance le plus bas au plus haut."""
    flagged = flag_poor_power_factor(readings)
    flagged.sort(key=lambda r: r["power_factor"])
    return flagged[:limit]


def penalty_exposure_hours(readings):
    """Nombre d'heures passées sous le seuil contractuel de 90%.

    Chaque intervalle vaut 15 minutes, donc 0,25 heure.
    """
    count = sum(1 for r in readings if r["lagging_current_power_factor"] < 90.0)
    return count * 0.25

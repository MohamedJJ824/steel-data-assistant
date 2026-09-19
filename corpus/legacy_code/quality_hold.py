"""Règles de mise en attente qualité.

Une tôle en attente ne part pas en expédition tant que le contrôle n'a pas
statué. La durée d'attente dépend de la gravité du défaut.
"""

from config_thresholds import CRITICAL_DEFECT_RATE_THRESHOLD, QUALITY_HOLD_HOURS

# Défauts qui déclenchent systématiquement une mise en attente, quelle que
# soit la gravité déclarée dans la table de référence.
ALWAYS_HOLD = ("Z_Scratch", "K_Scratch")


def hold_duration_hours(fault_code, severity):
    """Durée de mise en attente en heures pour un défaut donné.

    Les rayures en Z et en K sont toujours traitées au niveau de gravité 3,
    même si la table de référence les déclare plus bas: une rayure traversante
    peut provoquer une rupture au formage chez le client.
    """
    if fault_code in ALWAYS_HOLD:
        return QUALITY_HOLD_HOURS[3]
    return QUALITY_HOLD_HOURS.get(severity, QUALITY_HOLD_HOURS[1])


def should_hold(fault_code, severity):
    """Vrai si la tôle doit être mise en attente."""
    if fault_code in ALWAYS_HOLD:
        return True
    return severity >= 2


def batch_needs_manual_review(plates):
    """Vrai si le lot dépasse le taux de défauts critiques toléré.

    plates: liste de dicts avec 'fault_code' et 'severity'.
    """
    if not plates:
        return False
    critical = sum(1 for p in plates if p["severity"] >= 3 or p["fault_code"] in ALWAYS_HOLD)
    return (critical / len(plates)) > CRITICAL_DEFECT_RATE_THRESHOLD


def hold_summary(plates):
    """Répartition des tôles entre libérées et mises en attente."""
    held = []
    released = []
    for plate in plates:
        if should_hold(plate["fault_code"], plate["severity"]):
            held.append(plate)
        else:
            released.append(plate)
    return {
        "held": len(held),
        "released": len(released),
        "manual_review": batch_needs_manual_review(plates),
    }

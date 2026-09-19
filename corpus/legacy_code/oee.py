"""Calcul du TRS (OEE) par ligne et par période.

OEE = disponibilité x performance x qualité.

La disponibilité est calculée à partir de plant.maintenance_events: on retire
du temps d'ouverture la somme des minutes d'arrêt de la période.
"""

from config_thresholds import NOMINAL_THROUGHPUT_PLATES_PER_HOUR, SHIFT_DURATION_MINUTES


def availability(planned_minutes, downtime_minutes):
    """Disponibilité = (temps prévu - arrêts) / temps prévu."""
    if planned_minutes <= 0:
        return 0.0
    run_time = planned_minutes - downtime_minutes
    if run_time < 0:
        # Peut arriver si deux interventions se chevauchent dans le journal.
        # TODO(am): dédoublonner les plages d'arrêt qui se recouvrent.
        run_time = 0
    return run_time / planned_minutes


def performance(plates_produced, run_minutes):
    """Performance = cadence réelle / cadence nominale."""
    if run_minutes <= 0:
        return 0.0
    actual_rate = plates_produced / (run_minutes / 60.0)
    return min(actual_rate / NOMINAL_THROUGHPUT_PLATES_PER_HOUR, 1.0)


def quality(plates_produced, plates_rejected):
    """Qualité = tôles conformes / tôles produites."""
    if plates_produced <= 0:
        return 0.0
    return (plates_produced - plates_rejected) / plates_produced


def oee(planned_minutes, downtime_minutes, plates_produced, plates_rejected):
    """TRS global. Retourne un ratio entre 0 et 1."""
    avail = availability(planned_minutes, downtime_minutes)
    run_minutes = planned_minutes - downtime_minutes
    perf = performance(plates_produced, run_minutes)
    qual = quality(plates_produced, plates_rejected)
    return avail * perf * qual


def oee_for_shifts(n_shifts, downtime_minutes, plates_produced, plates_rejected):
    """TRS sur un nombre de postes donné."""
    planned = n_shifts * SHIFT_DURATION_MINUTES
    return oee(planned, downtime_minutes, plates_produced, plates_rejected)

"""Assemblage du rapport mensuel énergie + qualité.

Point d'entrée historique: python monthly_report.py 2018 3

Le script écrivait un fichier Excel, la partie export a été retirée lors de la
migration. Seule la logique d'agrégation est conservée.
"""

import sys

from downtime_analysis import by_line, top_faults_by_downtime
from kpi_energy import co2_per_kwh, energy_intensity, peak_intervals
from shift_report import shift_totals
from utils_dates import month_bounds


def build_report(readings, inspections, events, plates_produced):
    """Construit le dictionnaire du rapport mensuel."""
    total_kwh = sum(r["usage_kwh"] for r in readings)
    total_co2 = sum(r["co2_tco2"] for r in readings)

    return {
        "energy": {
            "total_kwh": total_kwh,
            "co2_kg_per_kwh": co2_per_kwh(total_co2, total_kwh),
            "intensity_kwh_per_plate": energy_intensity(total_kwh, plates_produced),
            "peak_intervals": len(peak_intervals(readings)),
        },
        "shifts": shift_totals(readings),
        "quality": {
            "inspections": len(inspections),
            "faults": _count_by_fault(inspections),
        },
        "maintenance": {
            "by_line": by_line(events, _operating_minutes(events)),
            "top_faults": top_faults_by_downtime(events),
        },
    }


def _count_by_fault(inspections):
    counts = {}
    for row in inspections:
        counts[row["fault_code"]] = counts.get(row["fault_code"], 0) + 1
    return counts


def _operating_minutes(events):
    # Approximation: 3 postes de 8h, 7j/7. Suffisant pour le MTBF mensuel.
    # TODO(jlm): utiliser le calendrier réel d'ouverture des lignes.
    lines = {e["line_id"] for e in events}
    return {line_id: 30 * 24 * 60 for line_id in lines}


def main(argv):
    """Point d'entrée historique. Les données sont chargées ailleurs."""
    if len(argv) != 3:
        print("usage: monthly_report.py <annee> <mois>")
        return 1
    year, month = int(argv[1]), int(argv[2])
    start, end = month_bounds(year, month)
    print("Periode: %s -> %s" % (start, end))
    print("Chargement des donnees non implemente dans cette copie.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

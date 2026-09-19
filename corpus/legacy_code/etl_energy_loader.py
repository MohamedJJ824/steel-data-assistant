"""Ancien chargeur du fichier énergie.

Conservé pour référence: c'est lui qui a produit l'historique 2018 avant la
reprise sous Postgres. Plusieurs pièges de parsing sont documentés ici.

ATTENTION: ne pas relancer sur la base de production.
"""

import csv

from utils_dates import parse_source_timestamp

# Le fichier livré par le fournisseur est encodé en UTF-8 AVEC BOM. Sans
# 'utf-8-sig' la première colonne s'appelle '﻿date' et tous les accès par
# nom échouent. Ça nous a coûté une journée en janvier 2019.
SOURCE_ENCODING = "utf-8-sig"

COLUMN_MAP = {
    "date": "ts",
    "Usage_kWh": "usage_kwh",
    "Lagging_Current_Reactive.Power_kVarh": "lagging_current_reactive_power_kvarh",
    "Leading_Current_Reactive_Power_kVarh": "leading_current_reactive_power_kvarh",
    "CO2(tCO2)": "co2_tco2",
    "Lagging_Current_Power_Factor": "lagging_current_power_factor",
    "Leading_Current_Power_Factor": "leading_current_power_factor",
    "NSM": "nsm",
    "WeekStatus": "week_status",
    "Day_of_week": "day_of_week",
    "Load_Type": "load_type",
}

FLOAT_COLUMNS = (
    "usage_kwh",
    "lagging_current_reactive_power_kvarh",
    "leading_current_reactive_power_kvarh",
    "co2_tco2",
    "lagging_current_power_factor",
    "leading_current_power_factor",
)


def read_rows(path):
    """Lit le CSV source et normalise les noms de colonnes.

    Le format de date est jour/mois/année. Laisser une bibliothèque deviner le
    format lit 03/01 comme le 3 janvier sur certaines lignes et le 1er mars sur
    d'autres, sans lever d'erreur. D'où le format explicite.
    """
    rows = []
    with open(path, encoding=SOURCE_ENCODING, newline="") as handle:
        reader = csv.DictReader(handle)
        for raw in reader:
            row = {}
            for source_name, target_name in COLUMN_MAP.items():
                row[target_name] = raw[source_name]
            row["ts"] = parse_source_timestamp(row["ts"])
            for column in FLOAT_COLUMNS:
                row[column] = float(row[column])
            row["nsm"] = int(row["nsm"])
            rows.append(row)
    return rows


def sort_chronologically(rows):
    """Trie par horodatage.

    Le fichier source n'est PAS dans l'ordre chronologique: chaque journée va
    de 00:15 à 23:45 puis se termine par une ligne 00:00 qui clôt la journée,
    parce que l'horodatage marque la fin de l'intervalle et non son début.
    """
    return sorted(rows, key=lambda r: r["ts"])


def check_completeness(rows):
    """Vérifie qu'il ne manque aucun intervalle de 15 minutes sur l'année."""
    expected = 365 * 24 * 4
    return {"expected": expected, "actual": len(rows), "complete": len(rows) == expected}

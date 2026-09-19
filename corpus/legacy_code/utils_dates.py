"""Utilitaires de dates communs aux rapports.

Attention: le fichier source d'énergie est en format jour/mois/année et
l'horodatage marque la FIN de l'intervalle de 15 minutes. Beaucoup de bugs
sont venus de là.
"""

from datetime import datetime, timedelta

SOURCE_DATE_FORMAT = "%d/%m/%Y %H:%M"

# Postes 3x8. Le poste de nuit franchit minuit, d'où le traitement à part.
SHIFT_BOUNDS = {
    "M": (6, 14),
    "A": (14, 22),
    "N": (22, 6),
}


def parse_source_timestamp(raw):
    """Parse un horodatage du fichier source (jour en premier)."""
    return datetime.strptime(raw, SOURCE_DATE_FORMAT)


def interval_start(ts):
    """Retourne le début de l'intervalle de 15 min qui se termine à ts."""
    return ts - timedelta(minutes=15)


def shift_of(ts):
    """Retourne le code du poste (M, A ou N) pour un horodatage donné."""
    hour = ts.hour
    for code, (start, end) in SHIFT_BOUNDS.items():
        if start < end:
            if start <= hour < end:
                return code
        # Poste de nuit: 22h-6h, il faut tester les deux moitiés.
        elif hour >= start or hour < end:
            return code
    raise ValueError("heure hors des bornes de poste: %s" % hour)


def shift_date(ts):
    """Date d'imputation du poste.

    Le poste de nuit commencé le 3 à 22h est imputé au 3, y compris pour les
    heures qui tombent après minuit.
    """
    if shift_of(ts) == "N" and ts.hour < 6:
        return (ts - timedelta(days=1)).date()
    return ts.date()


def month_bounds(year, month):
    """Retourne (début inclus, fin exclue) pour un mois donné."""
    start = datetime(year, month, 1)
    if month == 12:
        return start, datetime(year + 1, 1, 1)
    return start, datetime(year, month + 1, 1)

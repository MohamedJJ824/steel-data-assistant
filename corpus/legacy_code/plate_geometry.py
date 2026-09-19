"""Mesures dérivées de la géométrie des défauts.

Sert au pré-tri avant contrôle visuel: un défaut long et fin n'est pas traité
comme un défaut compact de même surface.
"""


def defect_width(row):
    """Largeur du défaut en pixels."""
    return row["x_maximum"] - row["x_minimum"]


def defect_height(row):
    """Hauteur du défaut en pixels."""
    return row["y_maximum"] - row["y_minimum"]


def aspect_ratio(row):
    """Rapport largeur/hauteur. Retourne None si la hauteur est nulle."""
    height = defect_height(row)
    if height == 0:
        return None
    return defect_width(row) / height


def bounding_box_area(row):
    """Surface du rectangle englobant, en pixels."""
    return defect_width(row) * defect_height(row)


def fill_ratio(row):
    """Part de la boîte englobante réellement occupée par le défaut."""
    box = bounding_box_area(row)
    if box == 0:
        return None
    return row["pixels_areas"] / box


def mean_luminosity(row):
    """Luminosité moyenne du défaut, 0 à 255."""
    if row["pixels_areas"] == 0:
        return None
    return row["sum_of_luminosity"] / row["pixels_areas"]


def is_elongated(row, threshold=4.0):
    """Vrai si le défaut est nettement plus long que large.

    Les rayures (Z_Scratch, K_Scratch) ressortent avec ce critère.
    """
    ratio = aspect_ratio(row)
    if ratio is None:
        return False
    return ratio >= threshold or ratio <= (1.0 / threshold)

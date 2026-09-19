"""Seuils et constantes partagés par les scripts d'analyse.

Historiquement ces valeurs étaient dupliquées dans chaque script. Regroupées
ici en 2019 après un écart constaté entre le rapport énergie et le rapport
qualité. Ne pas modifier sans accord du service Méthodes.
"""

# Facteur d'émission utilisé pour convertir l'énergie en CO2.
# Source: moyenne du mix électrique 2018 fournie par le fournisseur.
CO2_FACTOR_TONNES_PER_KWH = 0.000512

# Seuil d'alerte de pointe de consommation, en kWh sur un intervalle de 15 min.
# Correspond au 95e percentile de la consommation 2018.
PEAK_LOAD_ALERT_KWH = 99.0

# En dessous de ce facteur de puissance (en %), l'intervalle est signalé.
# Le contrat fournisseur pénalise en dessous de 90, on garde une marge.
POWER_FACTOR_MIN_PCT = 92.0

# Durée de mise en attente qualité, en heures, par niveau de gravité.
QUALITY_HOLD_HOURS = {1: 4, 2: 24, 3: 72}

# Un lot dépassant ce taux de défauts critiques part en revue manuelle.
CRITICAL_DEFECT_RATE_THRESHOLD = 0.08

# Durée théorique d'un poste, en minutes. Utilisé pour le calcul de l'OEE.
SHIFT_DURATION_MINUTES = 480

# Cadence nominale de la ligne, en tôles par heure.
NOMINAL_THROUGHPUT_PLATES_PER_HOUR = 42

# TODO(jlm): la cadence nominale diffère entre L1 et L3, il faudrait une valeur
# par ligne plutôt qu'une constante globale.

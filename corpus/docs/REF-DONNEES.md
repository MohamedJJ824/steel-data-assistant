---
doc_id: REF-DONNEES
title: Dictionnaire des données de production
doc_type: reference
version: 1.2
date: 2018-04-02
---
# Dictionnaire des données

## Mesures de consommation

| Champ | Description | Unité |
|---|---|---|
| `ts` | Horodatage de **fin** de l'intervalle | — |
| `usage_kwh` | Énergie active consommée sur l'intervalle | kWh |
| `co2_tco2` | Émissions de CO2 sur l'intervalle | tonnes |
| `lagging_current_power_factor` | Facteur de puissance inductif | % |
| `leading_current_power_factor` | Facteur de puissance capacitif | % |
| `nsm` | Secondes écoulées depuis minuit | s |
| `load_type` | Régime de charge | — |

## Inspections de tôles

| Champ | Description |
|---|---|
| `plate_id` | Identifiant de la tôle |
| `fault_code` | Défaut constaté, un seul par tôle |
| `steel_grade` | Nuance, `A300` ou `A400` |
| `line_id` | Ligne d'inspection |
| `inspected_at` | Date et heure de l'inspection |

## Journal de maintenance

| Champ | Description |
|---|---|
| `event_id` | Identifiant de l'intervention |
| `category` | `preventive` ou `corrective` |
| `fault_code` | Vide pour une intervention préventive |
| `downtime_minutes` | Durée d'arrêt |
| `report_doc_id` | Rapport associé, vide si aucun rapport |

## Pièges connus

Le fichier source de consommation est au format **jour/mois/année** et
son horodatage marque la **fin** de l'intervalle. Le fichier n'est donc
pas dans l'ordre chronologique : chaque journée va de 00:15 à 23:45 puis
se termine par une ligne à 00:00.

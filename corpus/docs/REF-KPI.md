---
doc_id: REF-KPI
title: Définition des indicateurs de performance
doc_type: reference
version: 2.1
date: 2018-01-15
---
# Définition des indicateurs

## Intensité énergétique

Énergie consommée rapportée à la production.

> intensité = énergie totale en kWh / **nombre de tôles produites**

Le dénominateur est le **nombre de tôles**, et non le tonnage. La
comptabilité tonnage n'étant pas fiable avant 2017, la définition a été
conservée telle quelle pour que l'historique reste comparable.

## CO2 par kWh

> ratio = (CO2 en tonnes × 1000) / énergie en kWh

Le résultat est exprimé en **kilogrammes de CO2 par kWh**. Le facteur
mille convertit les tonnes du fichier source en kilogrammes.

## TRS (OEE)

> TRS = disponibilité × performance × qualité

| Composante | Définition |
|---|---|
| Disponibilité | (temps prévu − arrêts) / temps prévu |
| Performance | cadence réelle / cadence nominale |
| Qualité | tôles conformes / tôles produites |

La disponibilité est calculée à partir du journal de maintenance. La
cadence nominale de référence est de **42 tôles par heure** et la durée
théorique d'un poste de **480 minutes**.

## MTTR et MTBF

> MTTR = minutes d'arrêt cumulées / nombre d'interventions correctives
>
> MTBF = temps d'ouverture / nombre d'interventions correctives

Les interventions **préventives sont exclues** des deux indicateurs :
planifiées, elles ne traduisent pas une défaillance.

## Seuil de pointe

Le seuil d'alerte de pointe est de **99 kWh** sur quinze minutes.

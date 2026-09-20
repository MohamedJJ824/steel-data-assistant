---
doc_id: POL-MNT-PREV
title: Politique de maintenance préventive
doc_type: policy
version: 1.4
date: 2018-02-01
---
# Politique de maintenance préventive

## Objet

La maintenance préventive vise à réduire le nombre d'interventions
correctives, qui sont les seules retenues dans le calcul du MTTR et du
MTBF.

## Règles de planification

1. Toute intervention préventive est planifiée hors période de production
   lorsque la charge le permet.
2. Une intervention préventive ne se voit jamais attribuer de code défaut :
   le champ correspondant reste vide au journal.
3. La durée cible d'une intervention préventive est de **45 minutes**.

## Consignation des arrêts

Tout arrêt supérieur à **15 minutes** est consigné avec son heure de
début, son heure de fin et sa durée. Les trois valeurs doivent rester
cohérentes entre elles.

## Rédaction d'un rapport

Un rapport écrit est exigé pour les interventions correctives les plus
longues. Les interventions courtes ne donnent pas lieu à rapport : leur
absence au corpus documentaire est normale et ne traduit pas un oubli.

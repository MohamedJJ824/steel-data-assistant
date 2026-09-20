---
doc_id: POL-DAT-ACC
title: Politique d'accès aux données de production
doc_type: policy
version: 1.1
date: 2018-05-20
---
# Politique d'accès aux données de production

## Principe de moindre privilège

Tout outil d'analyse accède à la base de production en **lecture seule**.
Aucun outil d'aide à la décision ne dispose de droits d'écriture sur les
tables métier.

## Deux couches indépendantes

1. Le rôle de base de données utilisé par les outils d'analyse ne dispose
   que du droit de lecture sur le schéma métier.
2. Toute requête générée automatiquement est analysée avant exécution :
   une seule instruction, de type lecture, sur les tables autorisées.

Aucune des deux couches n'est considérée comme suffisante seule.

## Délai d'exécution

Une requête d'analyse est interrompue au-delà de **5 secondes** afin
qu'une requête mal formée ne puisse pas immobiliser la base.

## Journalisation

Les requêtes sont journalisées avec leur identifiant de trace, leur durée
et leur statut. Le contenu des lignes retournées n'est jamais journalisé.

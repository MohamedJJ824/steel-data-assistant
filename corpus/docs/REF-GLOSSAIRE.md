---
doc_id: REF-GLOSSAIRE
title: Glossaire des termes de production et de qualité
doc_type: reference
version: 1.5
date: 2018-01-08
---
# Glossaire

                ## Termes de production

                **Intervalle** — Période de quinze minutes sur laquelle la consommation
                est mesurée. L'horodatage associé marque la **fin** de l'intervalle, pas
                son début.

                **Régime de charge** — Classement d'un intervalle en `Light_Load`,
                `Medium_Load` ou `Maximum_Load` selon la puissance appelée.

                **Poste** — Période de travail de huit heures. Le site fonctionne en 3x8.

                **Nuance d'acier** — `A300` ou `A400`, selon les caractéristiques
                mécaniques visées.

                ## Termes de qualité

                **Mise en attente qualité** — Immobilisation d'une tôle jusqu'à décision
                du contrôle. La durée dépend de la gravité du défaut.

                **Gravité** — Niveau de 1 à 3 attribué à un type de défaut. La gravité 3
                correspond aux défauts pouvant entraîner une rupture chez le client.

                **Revue manuelle de lot** — Examen déclenché lorsque le taux de défauts
                critiques d'un lot dépasse 8 %.

                ## Termes de maintenance

                **Maintenance préventive** — Intervention planifiée, sans code défaut associé.

                **Maintenance corrective** — Intervention déclenchée par un défaut constaté.
                Seules ces interventions entrent dans le calcul du MTTR et du MTBF.

                **Durée d'arrêt** — Nombre de minutes pendant lesquelles la ligne est à
                l'arrêt, cohérent avec les heures de début et de fin consignées.

                ## Tables de référence

                | Code | Libellé | Label EN | Gravité | Procédure |
                |---|---|---|---|---|
                | `Bumps` | Bosses | Bumps | 2 | `PROC-FLT-BUMP` |
| `Dirtiness` | Souillures | Dirtiness | 1 | `PROC-FLT-DIRT` |
| `K_Scratch` | Rayure en K | K-shaped scratch | 3 | `PROC-FLT-KSCR` |
| `Other_Faults` | Autres défauts | Other faults | 2 | `PROC-FLT-OTHR` |
| `Pastry` | Feuilletage | Pastry | 2 | `PROC-FLT-PAST` |
| `Stains` | Taches | Stains | 1 | `PROC-FLT-STAI` |
| `Z_Scratch` | Rayure en Z | Z-shaped scratch | 3 | `PROC-FLT-ZSCR` |

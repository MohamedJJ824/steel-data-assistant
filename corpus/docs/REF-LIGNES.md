---
doc_id: REF-LIGNES
title: Lignes de production et organisation des postes
doc_type: reference
version: 1.0
date: 2018-01-05
---
# Lignes de production et postes

                ## Lignes

                | Identifiant | Nom | Procédé | Mise en service |
                |---|---|---|---|
                | `L1` | Ligne de laminage à chaud | hot_rolling | 2005 |
| `L2` | Ligne de laminage à froid | cold_rolling | 2011 |
| `L3` | Ligne de finition et inspection | finishing | 2016 |

                ## Postes

                | Code | Libellé | Début | Fin |
                |---|---|---|---|
                | `A` | Poste d'après-midi | 14h | 22h |
| `M` | Poste du matin | 6h | 14h |
| `N` | Poste de nuit | 22h | 6h |

                ## Convention d'imputation du poste de nuit

                Le poste de nuit franchit minuit. Les heures comprises entre minuit et
                6h sont imputées à la **journée de début de poste**, c'est-à-dire la
                veille.

                Cette convention est celle du service Production. Elle **diffère de celle
                du système de paie**, qui coupe à minuit. Tout rapprochement entre les
                deux sources doit en tenir compte.

                ## Flux de production

                Le flux va du laminage à chaud vers le laminage à froid, puis vers la
                finition et l'inspection. Une tôle traverse les trois étapes dans cet
                ordre.

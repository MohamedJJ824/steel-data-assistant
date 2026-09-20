---
doc_id: REF-CONTACTS
title: Rôles et circuit d'escalade
doc_type: reference
version: 1.3
date: 2018-03-19
---
# Rôles et circuit d'escalade

                Les contacts sont désignés par leur **rôle**. Aucun nom de personne ne
                figure dans ce document.

                ## Escalade qualité par gravité

                | Gravité | Rôle alerté | Délai d'escalade |
                |---|---|---|
                | 1 | L'opérateur de contrôle qualité | 120 minutes |
| 2 | Le chef d'équipe qualité | 60 minutes |
| 3 | Le responsable qualité de site | 15 minutes |

                ## Fréquence de contrôle renforcé

                | Gravité | Fréquence |
                |---|---|
                | 1 | Une fois par poste |
                | 2 | Toutes les deux heures |
                | 3 | En continu jusqu'à la levée de la mise en attente |

                ## Autres circuits

                | Sujet | Rôle destinataire | Délai |
                |---|---|---|
                | Dépassement de pointe électrique | Service Énergie | 48 heures |
                | Facteur de puissance sous 92 % | Service Énergie | Fin de poste |
                | Arrêt de plus de 15 minutes | Service Maintenance | Immédiat |
                | Revue manuelle de lot | Responsable qualité de site | Avant expédition |

                ## Décision d'arrêt de ligne

                L'arrêt d'une ligne est demandé au **chef de poste**, seul habilité à le
                prononcer.

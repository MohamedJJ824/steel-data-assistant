# Protocole de test utilisateur

*Assistant Données Aciérie — version 0.1*

---

## 1. Objectif

Vérifier qu'un utilisateur métier, sans formation préalable autre que le guide
d'utilisation, peut :

1. obtenir une réponse exacte à une question relevant de son quotidien ;
2. **retrouver et vérifier la source** de cette réponse ;
3. **détecter une réponse douteuse** plutôt que l'accepter telle quelle.

Le troisième point est le plus important. Un assistant dont les réponses ne
sont pas vérifiables est plus dangereux qu'utile en contexte industriel. Le
test mesure donc autant la vigilance des utilisateurs que la justesse de
l'outil.

## 2. Profils de testeurs

Trois profils fictifs, deux testeurs par profil, soit **six participants**.

| Profil | Contexte | Ce qu'il cherche à valider |
|---|---|---|
| **Technicien de maintenance** | Consulte les historiques d'arrêt, rédige des rapports | Retrouve-t-il une intervention et sa procédure ? |
| **Ingénieur énergie** | Suit la consommation et les pointes | Obtient-il un chiffre agrégé exact et exportable ? |
| **Analyste qualité** | Suit les défauts par ligne et les mises en attente | Croise-t-il un chiffre et une règle documentaire ? |

Aucun participant ne doit avoir contribué au développement.

## 3. Déroulement

**Durée : 45 minutes par participant.**

| Étape | Durée | Contenu |
|---|---|---|
| Accueil | 5 min | Objectif du test. Préciser : **c'est l'outil qui est testé, pas le participant** |
| Lecture | 5 min | Guide d'utilisation, seul |
| Tâches | 25 min | Six tâches chronométrées, sans aide |
| Questionnaire | 5 min | SUS (10 questions) |
| Entretien | 5 min | Questions ouvertes |

**Consigne à l'observateur :** ne pas aider pendant les tâches. Noter les
hésitations, les relectures et les reformulations — ce sont les données utiles.
Demander au participant de **penser à voix haute**.

## 4. Les six tâches

Pour chaque tâche, noter : **durée**, **réussite** (oui / partielle / non),
**nombre de reformulations**, et si le participant a **ouvert les sources**.

### Tâche 1 — Question chiffrée simple *(cible : 2 min)*
> Combien de tôles présentent un défaut `K_Scratch` ?

*Réussite : le bon nombre, et le participant a ouvert « Requête SQL ».*

### Tâche 2 — Question documentaire *(cible : 2 min)*
> Combien de temps une tôle de gravité 3 doit-elle rester en attente qualité ?

*Réussite : la bonne durée, et le participant cite le document source.*

### Tâche 3 — Question combinée *(cible : 5 min)*
> Quel type de défaut a causé le plus de minutes d'arrêt, et que dit sa
> procédure sur les actions immédiates ?

*Réussite : les deux moitiés traitées. Noter si le participant a dû scinder la
question — c'est une limite connue et sa fréquence nous intéresse.*

### Tâche 4 — Export *(cible : 3 min)*
> Obtenez la consommation d'énergie du week-end et téléchargez le résultat.

*Réussite : fichier CSV téléchargé.*

### Tâche 5 — Détection d'une réponse douteuse *(cible : 5 min)*
> Posez une question de votre domaine, puis **dites-nous si vous feriez
> confiance à la réponse, et pourquoi**.

*C'est la tâche centrale. Noter précisément : le participant a-t-il ouvert les
sources de lui-même ? A-t-il remarqué l'indicateur « Chiffres vérifiés » ? Si
l'assistant s'est trompé, l'a-t-il vu ?*

### Tâche 6 — Hors périmètre *(cible : 2 min)*
> Demandez le prix actuel de la tonne d'acier.

*Réussite : l'assistant refuse, et le participant juge ce refus approprié
plutôt que le prenant pour une panne.*

## 5. Questionnaire SUS

Échelle de 1 (pas du tout d'accord) à 5 (tout à fait d'accord).

1. J'aimerais utiliser cet assistant régulièrement.
2. L'assistant est inutilement complexe.
3. L'assistant est facile à utiliser.
4. J'aurais besoin d'aide pour l'utiliser.
5. Les différentes fonctions sont bien intégrées.
6. L'assistant manque de cohérence.
7. La plupart des gens apprendraient à l'utiliser rapidement.
8. L'assistant est lourd à utiliser.
9. Je me sens en confiance en l'utilisant.
10. J'ai dû apprendre beaucoup de choses avant de pouvoir m'en servir.

*Score SUS = (somme des impairs − 5 + 25 − somme des pairs) × 2,5. Repère
usuel : au-dessus de 68 = au-dessus de la moyenne.*

**Trois questions complémentaires, propres à cet outil** (1 à 5) :

11. J'ai compris d'où venaient les réponses.
12. Je saurais repérer une réponse à laquelle ne pas me fier.
13. Le temps de réponse est acceptable pour mon usage.

La question 12 est celle à surveiller. Un score élevé au SUS avec un score
faible en 12 signale un outil agréable et dangereux.

## 6. Entretien de clôture

1. Qu'avez-vous trouvé le plus utile ?
2. Qu'est-ce qui vous a gêné ou surpris ?
3. Dans quel cas concret de votre travail l'utiliseriez-vous ?
4. Qu'est-ce qui vous empêcherait de l'utiliser ?
5. Une réponse vous a-t-elle semblé fausse ? Comment l'avez-vous su ?

## 7. Grille de synthèse

| | T1 | T2 | T3 | T4 | T5 | T6 |
|---|---|---|---|---|---|---|
| Taux de réussite | | | | | | |
| Durée médiane | | | | | | |
| Reformulations (moy.) | | | | | | |
| Sources ouvertes | | | | | | |

| Indicateur | Résultat | Seuil visé |
|---|---|---|
| Score SUS moyen | | ≥ 68 |
| Q11 — compréhension des sources | | ≥ 4 |
| **Q12 — détection d'une réponse douteuse** | | **≥ 4** |
| Q13 — temps de réponse | | ≥ 3 |
| Tâches réussies sans aide | | ≥ 80 % |
| Refus hors périmètre jugé approprié | | 6/6 |

## 8. Collecte

Les retours 👍/👎 laissés pendant le test sont enregistrés avec l'identifiant
de trace, ce qui permet de relire après coup la requête et les documents
exacts. **Demander aux participants de s'en servir pendant les tâches** : cela
alimente la grille sans effort de transcription.

## 9. Suites

- Toute tâche sous 80 % de réussite : analyser les traces correspondantes avant
  de conclure que le problème vient de l'interface.
- Q12 sous 4 : priorité absolue. Renforcer la visibilité des sources et de
  l'indicateur de vérification avant toute nouvelle fonctionnalité.
- Consigner les questions réellement posées : elles constituent la meilleure
  base pour étendre le jeu d'évaluation.

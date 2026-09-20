# Guide d'utilisation — Assistant Données Aciérie

*Deux pages. À lire avant la première utilisation.*

---

## À quoi sert l'assistant

L'assistant répond à vos questions sur trois sources :

| Source | Ce qu'elle contient | Exemple de question |
|---|---|---|
| **La base de production** | Consommation d'énergie, inspections de tôles, interventions de maintenance | *Combien de tôles ont un défaut Bumps ?* |
| **La documentation** | Procédures défauts, manuels de ligne, politiques, rapports d'intervention | *Quelle est la durée de mise en attente pour une rayure en Z ?* |
| **Le code d'analyse** | Les scripts qui calculent les indicateurs | *Quelle fonction calcule le MTTR ?* |

Vous pouvez poser vos questions **en français ou en anglais**. L'assistant
répond toujours dans la langue de la question.

---

## Comment poser une bonne question

**Soyez précis sur ce que vous cherchez.** L'assistant choisit ses outils à
partir de votre formulation.

| Plutôt que | Écrivez |
|---|---|
| « Les défauts » | « Combien de tôles ont un défaut K_Scratch ? » |
| « L'énergie » | « Quelle est la consommation totale d'énergie en mars 2018 ? » |
| « La procédure » | « Que dit la procédure Z_Scratch sur les actions immédiates ? » |
| « Le calcul » | « Quel dénominateur utilise le calcul d'intensité énergétique ? » |

**Nommez les choses par leur code** quand vous le connaissez : `Z_Scratch`,
`L2`, `POL-ENR-PEAK`. C'est plus fiable qu'une description.

**Une question à la fois.** Une question qui en contient trois donne souvent
une réponse qui n'en traite qu'une.

**Les questions combinées fonctionnent** et sont l'un des points forts de
l'outil : *« Quel défaut a causé le plus d'arrêts, et que dit la procédure
associée ? »* déclenche à la fois une requête et une recherche documentaire.

---

## Lire la réponse et ses sources

Sous chaque réponse, des panneaux dépliables montrent **d'où vient
l'information**. C'est la partie la plus importante de l'outil : une réponse
sans source vérifiée ne doit pas être utilisée telle quelle.

### « Requête SQL »

La requête exécutée et le tableau de résultats. **Vous pouvez la lire et la
vérifier.** Regardez en particulier :

- les **filtres** : la période et la ligne sont-elles celles que vous vouliez ?
- le **nombre de lignes** retournées ;
- le bouton **Télécharger en CSV** pour reprendre les données ailleurs.

### « Documents cités »

Chaque source apparaît sous la forme `PROC-FLT-ZSCR § Actions immédiates`,
c'est-à-dire l'identifiant du document et la section exacte. Dépliez pour voir
l'extrait, ou ouvrez le document complet.

### « Code cité »

Sous la forme `kpi_energy.py : lignes 9-18`. Les numéros de ligne sont exacts.

### L'indicateur « Chiffres vérifiés »

En haut de chaque réponse, par exemple **3/3**. L'assistant recherche chaque
chiffre de sa réponse dans les résultats de ses outils.

- **3/3** : tous les chiffres proviennent bien des sources.
- **2/3** : un chiffre n'a pas été retrouvé. Un avertissement s'affiche et
  indique lequel. **Vérifiez-le avant de l'utiliser.**

---

## Donner votre avis

Sous chaque réponse : 👍 ou 👎, avec un commentaire facultatif.

Ce retour est enregistré avec l'identifiant de la réponse, ce qui permet de
retrouver exactement la requête et les documents utilisés. **Un 👎 accompagné
d'une phrase expliquant ce qui n'allait pas vaut dix 👎 sans commentaire.**

---

## Limites connues

**L'assistant peut se tromper.** Les cas observés :

- **Mauvaise orientation** : une question chiffrée traitée comme une question
  documentaire. Symptôme : la réponse dit qu'elle n'a pas l'information alors
  que la base la contient. Reformulez en nommant explicitement ce que vous
  voulez compter.
- **Réponse incomplète sur une question combinée** : seule une partie est
  traitée. Posez les deux moitiés séparément.
- **Chiffre non vérifié** : signalé par l'indicateur. Ne l'utilisez pas sans
  contrôle.

**Ce que l'assistant ne sait pas faire :**

- répondre sur des sujets hors usine : prix du marché, météo, concurrents,
  effectifs. Il refuse, et c'est le comportement attendu ;
- prévoir l'avenir. Il ne dispose que de données historiques ;
- modifier quoi que ce soit. **Son accès à la base est en lecture seule**, à
  deux niveaux indépendants. Il ne peut rien écrire, ni par erreur ni sur
  demande.

**Les documents et une partie des données sont synthétiques** : ils ont été
produits pour ce démonstrateur. Les mesures d'énergie et d'inspection sont
réelles ; l'usine décrite ne l'est pas.

---

## Temps de réponse

Le modèle tourne **localement**, sans envoi de données à l'extérieur. Comptez
**30 secondes à 2 minutes** par question selon sa complexité. C'est le prix de
la confidentialité. Un message d'attente s'affiche pendant la recherche.

---

## En cas de problème

| Symptôme | Que faire |
|---|---|
| « API injoignable » dans le bandeau latéral | Prévenir l'équipe technique ; le service est arrêté |
| « Service dégradé » | La base ou le modèle est injoignable ; les réponses seront partielles |
| Réponse vide ou incohérente | Reformuler en nommant les codes explicitement |
| Chiffre qui semble faux | Ouvrir « Requête SQL » et vérifier les filtres, puis 👎 avec le détail |

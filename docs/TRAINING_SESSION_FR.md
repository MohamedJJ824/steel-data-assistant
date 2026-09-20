# Session de prise en main — 30 minutes

*Assistant Données Aciérie. Groupe de 4 à 8 personnes. Prévoir un poste par
binôme.*

---

## Objectif de la session

À la fin, chaque participant sait :

1. poser une question qui obtient une réponse exploitable ;
2. **retrouver la source** de cette réponse ;
3. **reconnaître une réponse à laquelle ne pas se fier**.

Le troisième point est l'objectif réel de la session. Un participant qui repart
en faisant confiance aveuglément aura moins bien appris qu'un participant
prudent qui pose moins de questions.

## Avant la session

- [ ] Service démarré et testé le matin même (`/health` au vert)
- [ ] Guide d'utilisation imprimé, un par participant
- [ ] Un poste par binôme, interface déjà ouverte
- [ ] **Avoir préparé une réponse fausse ou incomplète** pour l'exercice 3

---

## Déroulé

### 0-5 min — Ce que c'est, et ce que ce n'est pas

À dire explicitement :

> « L'assistant interroge trois sources : la base de production, la
> documentation, et le code d'analyse. Il tourne **sur nos machines** : aucune
> donnée ne sort. C'est aussi pourquoi il met 30 secondes à 2 minutes à
> répondre. »

Et immédiatement après :

> « Ce n'est pas un moteur de recherche et ce n'est pas un oracle. Il se trompe.
> Ce qu'il fait de mieux, c'est **montrer d'où vient sa réponse**. C'est ce que
> nous allons apprendre à lire. »

Préciser tout de suite, parce que la question vient toujours :

> « Il ne peut rien modifier. Son accès à la base est en lecture seule, à deux
> niveaux indépendants. Il ne peut pas écrire, ni par erreur ni si on le lui
> demande. »

### 5-12 min — Démonstration commentée

Trois questions, projetées, en commentant chaque étape.

**1. Une question chiffrée** — *« Combien de tôles ont un défaut Bumps ? »*

Pendant l'attente, expliquer ce qui se passe. Puis **ouvrir « Requête SQL »
avant de commenter la réponse** :

> « Voilà la requête réellement exécutée. Vous pouvez la lire. Le filtre porte
> bien sur Bumps. Le résultat vient de la base, pas du modèle. »

Montrer l'indicateur **Chiffres vérifiés**.

**2. Une question documentaire** — *« Quelle est la durée de mise en attente
pour une rayure en Z ? »*

Ouvrir « Documents cités ». Insister sur le format :

> « `PROC-FLT-ZSCR § Actions immédiates` : le document et la section exacte.
> Pas "quelque part dans la documentation". »

**3. Une question hors périmètre** — *« Quel est le prix de la tonne d'acier ? »*

> « Il refuse. C'est le comportement attendu, pas une panne. Un assistant qui
> invente un prix serait bien plus problématique. »

### 12-24 min — Exercices en binôme

Annoncer : *« Chacun son tour au clavier. »*

**Exercice 1 — Votre propre question** *(4 min)*
Poser une question de son quotidien. **Consigne : ouvrir les sources avant de
lire la réponse.** Tour de table rapide : qui a obtenu une réponse utilisable ?

**Exercice 2 — Une question combinée** *(4 min)*
> « Quel défaut a causé le plus d'arrêts, et que dit sa procédure ? »

Faire remarquer les deux outils dans « Outils appelés ». Si la réponse ne
traite qu'une moitié — cela arrive — c'est un bon moment pour le dire :

> « Voilà une limite réelle. Dans ce cas, posez les deux moitiés séparément. »

**Exercice 3 — Trouver la faille** *(4 min)*

**L'exercice le plus important.** Consigne :

> « Posez une question et décidez si vous feriez confiance à la réponse.
> Cherchez une raison de vous méfier : un filtre qui ne correspond pas à votre
> question, une source hors sujet, un chiffre non vérifié. »

Faire remonter les cas trouvés. **Valoriser publiquement ceux qui trouvent une
erreur** : c'est le comportement à ancrer. Si personne n'en trouve, montrer
l'exemple préparé.

### 24-28 min — Bonnes pratiques et limites

| Faire | Éviter |
|---|---|
| Nommer les codes : `Z_Scratch`, `L2` | « les défauts », « l'énergie » |
| Une question à la fois | Trois questions en une phrase |
| Ouvrir les sources avant d'agir | Copier le chiffre directement |
| 👎 avec un commentaire | 👎 sans explication |

Les limites à énoncer sans les adoucir :

- Il peut mal orienter une question chiffrée vers la documentation.
- Il peut ne traiter qu'une moitié d'une question combinée.
- Les documents et une partie des données sont **synthétiques** : les mesures
  d'énergie et d'inspection sont réelles, l'usine décrite ne l'est pas.
- Il ne prévoit rien : il ne connaît que l'historique.

### 28-30 min — Retours et suite

> « Le bouton 👎 avec une phrase d'explication est ce qui nous permettra de
> l'améliorer. Un retour enregistre aussi la requête et les documents exacts,
> donc nous pouvons rejouer le cas. »

Distribuer le guide. Indiquer le contact pour les problèmes techniques.

---

## Questions qui reviennent

**« Est-ce qu'il peut casser quelque chose ? »**
Non. Lecture seule, à deux niveaux indépendants. Tests à l'appui.

**« Est-ce que mes questions sortent de l'entreprise ? »**
Non. Le modèle tourne sur nos machines. Les questions sont journalisées avec
leur durée et les outils utilisés ; **le contenu des résultats ne l'est pas**.

**« Pourquoi est-ce si lent ? »**
Parce que le modèle tourne en local plutôt que sur un service externe. C'est un
choix : confidentialité contre rapidité.

**« Pourquoi répond-il faux parfois ? »**
Il écrit sa réponse à partir de ce que ses outils ont trouvé. Si l'outil
choisi n'était pas le bon, la réponse sera incomplète. D'où l'importance des
sources.

**« Est-ce qu'il remplace la documentation ? »**
Non. Il aide à la retrouver. La source fait foi, pas le résumé.

---

## Après la session

- [ ] Noter les questions réellement posées : elles guideront les améliorations
- [ ] Relever les cas où l'assistant s'est trompé, avec leur identifiant de trace
- [ ] Recontacter les participants sous deux semaines : l'utilisent-ils encore ?

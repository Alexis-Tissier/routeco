# Moteur de péage Routeco — règles de preuve

Ce document sépare les **fenêtres de recherche** des **preuves permettant
d'afficher un tarif exact**.

## Principe

La géométrie et les plages `toll=yes` servent à chercher les événements. Elles
ne suffisent jamais, seules, à prouver un montant.

Un résultat de niveau route est `exact` uniquement lorsque le plan contient des
événements tarifaires officiels cohérents et qu'aucun événement physique
traversé ne reste sans tarif.

## Événements exacts

### Système ouvert

Un portique est exact lorsque :

- sa projection passe les contrôles latéraux et de bretelle ;
- un tarif officiel local correspond à son identité ;
- il n'est pas le doublon physique d'un portique déjà compté.

Un portique physiquement traversé sans tarif interdit `exact`.

### Système fermé

Un voyage fermé est exact lorsque :

- l'entrée et la sortie sont identifiées dans le bon ordre ;
- la paire existe dans une matrice officielle classe 1 ;
- le voyage ne chevauche pas un autre voyage retenu ;
- ses gares ne sont pas réutilisées.

## Complétude du plan

`TollPlan` centralise la décision finale.

Les sous-fonctions peuvent produire des segments exacts, mais seule
`_finalize_toll_plan()` produit un `TollQuote` exact.

Un résidu de distance, même inférieur à 5 ou 6 km, n'est plus une preuve
suffisante. Il doit avoir été classé positivement comme bruit OSM sans événement
physique.

## Chaînes de systèmes fermés

Plusieurs matrices fermées peuvent former un plan exact lorsque :

- au moins deux voyages distincts sont retenus ;
- chacun possède une entrée et une sortie officielles ;
- leur ordre sur la route est cohérent ;
- ils ne se chevauchent pas et ne réutilisent pas une gare ;
- aucun événement physique non tarifé n'est détecté.

La portion entre une sortie et l'entrée suivante n'est pas ajoutée d'office au
péage. En revanche, le routage actuel ne fournit pas encore une preuve positive
qu'elle est gratuite. Un budget transitoire distinct de 5 km est donc conservé :
`MAX_UNVERIFIED_CLOSED_CONNECTOR_KM`. Au-delà, le plan reste estimé. Cette valeur
n'a aucun lien avec les marges de recherche de 25 ou 35 km et devra disparaître
lorsque le statut routier de l'intervalle sera transmis explicitement.

## Matrice globale

Une matrice `route_wide` ne peut remplacer un plan partiel que lorsqu'elle
confirme le **même voyage fermé** :

- même entrée physique ;
- même sortie physique ;
- mêmes positions sur la route à 1 km près ;
- opérateur compatible ;
- aucun portique ouvert dans le plan ;
- aucun événement physique non tarifé détecté.

Le prix supérieur ou égal n'est jamais utilisé comme preuve.

## Seuils conservés pour rechercher des candidats

Les valeurs suivantes restent provisoirement dans le générateur de candidats :

- 25 km de marge autour de certaines plages OSM ;
- 35 km / 25 % pour former une fenêtre de recherche globale ;
- 30 km / 18 % pour comparer certaines distances ;
- 45 km / 28 % et 90 km pour élargir la recherche de matrices longues.

Dans le code historique, certaines influencent encore le drapeau
`ClosedMatch.full_range`. Cette migration ne les considère plus directement
dans le finaliseur et interdit d'en ajouter de nouvelles comme preuve. La
prochaine étape devra retirer progressivement leur influence sur
`full_range`, après ajout de diagnostics d'événements.

## Seuils physiques

- 50 m : bretelle ouverte ;
- 60 m : autre portique ouvert ;
- 120 m : barrière principale ;
- 750 m : fusion de plages OSM presque contiguës ;
- 1 km : tolérance d'identité de position et chevauchement fermé ;
- 50 m : tolérance numérique minimale.

Toute évolution de ces valeurs doit être accompagnée d'un test générique et
d'une validation gold.

## Soustraction exacte des intervalles

Le solde non résolu n'est plus calculé par :

```text
distance de la plage OSM - somme approximative des couvertures
```

Le moteur applique désormais :

```text
intervalles GraphHopper toll/unknown pour la classe 1
- unions des matrices fermées exactes
= fragments réellement non résolus
```

Les intervalles `NO` et `HGV` sont exclus pour une voiture classe 1. Les
chevauchements entre matrices sont fusionnés avant soustraction afin de ne
jamais compter deux fois une même distance.

Lorsqu'un candidat transporte les états `toll` GraphHopper, les distances
résiduelles proviennent directement de ces intervalles. Lorsqu'un ancien
candidat n'en transporte aucun, Routeco conserve provisoirement
`TollRange.distance_km` comme base de mesure : une géométrie simplifiée ne doit
pas faire baisser silencieusement une estimation de 100 km à 81,6 km. Le
diagnostic expose alors
`measurement_basis = legacy_declared_range_distance`.

Chaque validation écrit également un manifeste `missing-tariffs-*` regroupant
les intervalles, gares et corridors à examiner. Ce manifeste est une file de
diagnostic : il ne transforme jamais automatiquement un candidat en tarif
officiel.

<!-- ROUTECO_V034_TARIFF_CATALOG -->
## Classification des intervalles et tarifs datés

Le manifeste classe chaque intervalle non résolu selon une cause probable.
Cette classification organise la vérification ; elle ne transforme jamais
seule une estimation en tarif exact.

Les tarifs datés sont séparés des anciens CSV statiques. Chaque ligne contient
une période d'effet, une éventuelle saison annuelle, la classe du véhicule et
un identifiant présent dans le registre des sources officielles.

Une donnée tarifaire spécifique à une installation est autorisée. Une règle de
code spécifique à une ville ou à un trajet reste interdite.

<!-- ROUTECO_V034_OPEN_EVENT_COMPONENTS -->
## Événements ouverts distincts des matrices fermées

Une matrice fermée absorbe un portique ouvert uniquement lorsque le point est
physiquement compris dans le trajet entrée-sortie ou lorsqu'il représente la
même installation que l'une de ses bornes. Une marge arbitraire autour de la
matrice ne constitue plus une preuve d'absorption.

Un portique distinct situé juste avant l'entrée ou juste après la sortie reste
facturable lorsqu'il satisfait les contrôles physiques de projection. Pour les
itinéraires disposant des états GraphHopper détaillés, le composant `toll`
correspondant est considéré comme expliqué par ses événements ouverts exacts
seulement si aucun autre événement physique sans tarif n'y subsiste.

Cette règle ne contient aucun cas particulier lié à une ville, un trajet ou un
opérateur.

## Analyse des systèmes fermés non résolus

Chaque intervalle non résolu contient désormais une analyse de topologie
fermée. Cette analyse est strictement diagnostique : elle ne modifie ni la
confiance ni le prix.

La fenêtre autour des bornes sert uniquement à découvrir des gares candidates.
Elle ne constitue jamais une preuve de complétude. Pour chaque paire ordonnée,
le diagnostic enregistre :

- l'existence ou l'absence d'une matrice officielle ;
- le sens entrée vers sortie ;
- le chevauchement avec un trajet fermé déjà facturé ;
- le prix, l'opérateur et la distance officielle lorsqu'ils existent ;
- l'écart avec les bornes de l'intervalle ;
- le taux de couverture physique de l'intervalle.

Décisions possibles :

- `unique_official_matrix` : une seule matrice officielle non conflictuelle ;
- `multiple_official_matrices` : plusieurs interprétations tarifaires ;
- `boundary_pair_without_matrix` : gares plausibles mais tarif absent ;
- `missing_boundary_candidates` : une borne physique n'est pas identifiée ;
- `no_usable_official_matrix` : toutes les matrices sont rejetées.

Une matrice diagnostiquée comme disponible n'est pas automatiquement ajoutée
au plan. La sélection automatique fera l'objet d'une étape séparée, après
examen des raisons de rejet sur la validation nationale.

## Sélection des matrices fermées résiduelles

Après la sélection globale et la facturation des portiques ouverts, Routeco
peut examiner séparément un composant payant encore non résolu.

Une matrice résiduelle n'est ajoutée que lorsque toutes les conditions suivantes
sont réunies :

- une seule interprétation physique subsiste après déduplication des alias ;
- la matrice possède un tarif officiel ;
- elle couvre au moins 60 % du composant ;
- son entrée ou sa sortie touche une borne du composant à 500 m près ;
- elle ne chevauche aucun trajet fermé déjà facturé ;
- elle ne réutilise une gare que comme sortie puis entrée d'une chaîne continue ;
- elle n'absorbe aucun portique ouvert déjà facturé ;
- aucun événement physique sans tarif ne subsiste dans le composant.

Deux lignes tarifaires ne constituent pas une ambiguïté lorsqu'elles désignent
les mêmes installations physiques, aux mêmes positions, avec le même opérateur,
le même prix et la même distance officielle.

Un dépassement de balisage OSM peut être absorbé sans coût supplémentaire
uniquement lorsqu'il mesure au maximum 500 m, touche directement une borne
exacte et ne contient aucun autre événement de paiement.

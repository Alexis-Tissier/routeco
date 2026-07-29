# Routeco 0.3.1 — intégrité nationale du moteur

Cette version ne contient aucune règle liée à une origine, une destination ou un trajet de validation.

## Péages

- sélection globale des matrices de péage au lieu d'un traitement glouton range par range ;
- interdiction de réutiliser la même gare d'entrée ou la même gare de sortie ;
- interdiction de retenir deux sections exactes qui se chevauchent ;
- dédoublonnage des alias d'une même gare physique à partir du nom normalisé et des coordonnées ;
- un portique ouvert situé dans une section déjà couverte par une matrice fermée n'est plus ajouté ;
- le statut `exact` exige une séquence ordonnée, non chevauchante et entièrement explicable ;
- les positions des sections exactes sur le tracé sont ajoutées au diagnostic et aux rapports ;
- en cas d'incohérence interne, le résultat exact est abandonné au profit d'une estimation honnête.

## Routage

- les profils GraphHopper qui renvoient HTTP 400, notamment sur les longs trajets, sont relancés avec deux modèles progressivement moins agressifs ;
- le rapport distingue les profils relancés avec succès des profils définitivement perdus ;
- les erreurs GraphHopper ne sont plus répétées sous forme de longues traces HTTP dans la sortie normale.

## Validation

- contrôle des gares facturées plusieurs fois ;
- contrôle de l'ordre des sections sur le trajet ;
- contrôle des chevauchements entre sections exactes ;
- compteurs des relances et pertes de profils GraphHopper ;
- 38 tests automatiques.

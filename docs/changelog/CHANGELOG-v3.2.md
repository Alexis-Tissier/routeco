# Routeco 0.3.2 — alternatives robustes et péages dédoublonnés

Cette version répond aux deux défauts principaux révélés par la validation aléatoire de 50 scénarios : perte des profils GraphHopper sur les longs trajets et double facturation de certains portiques présents sous plusieurs alias.

## Routage

- ajout d'une requête GraphHopper native avec `algorithm=alternative_route` ;
- jusqu'à quatre alternatives natives sont récupérées sans modèle personnalisé agressif ;
- les cinq profils économiques restent utilisés en complément ;
- une panne des profils `light`, `balanced`, `economy` ou `free` ne réduit donc plus automatiquement le résultat au seul trajet rapide ;
- les profils ayant réellement nécessité plusieurs tentatives sont désormais comptés, qu'ils aient récupéré ou non ;
- les alternatives natives et personnalisées sont dédoublonnées ensemble.

## Sélection des résultats

- suppression de la coupe naïve aux cinq trajets les plus rapides ;
- conservation garantie du trajet le plus rapide ;
- conservation garantie du trajet le moins cher ;
- conservation du trajet le moins cher dont le péage est fiable ;
- les places restantes sont remplies par des compromis différents en durée, coût et usage de l'autoroute.

## Péages

- détection d'un même portique décrit par plusieurs alias et des coordonnées légèrement différentes ;
- correction des doubles facturations telles que `Ancenis` / `Ancenis Péage` et `Fontaine Larivière` / `Fontaine-Larivière` ;
- distinction conservée entre deux gares réellement différentes comme une gare principale et une gare annexe ;
- les contrôles d'intégrité utilisent désormais le nom précis et la position sur le trajet.

## Validation

- 45 tests automatiques ;
- nouveaux tests pour les alternatives natives GraphHopper ;
- nouveaux tests de non-régression sur les alias de péages ouverts ;
- nouveau test garantissant que le trajet le moins cher n'est pas masqué lorsqu'il existe plus de cinq candidats.

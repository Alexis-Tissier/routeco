# Routeco v3.7 — véritable référence de temps

## Cause

La correction v8 supprimait le modèle personnalisé de la requête `fastest`,
mais le profil interne `car.json` de GraphHopper 11 applique lui-même
`distance_influence: 90`.

Les deux requêtes avaient donc la même pondération : GraphHopper continuait à
préférer une route un peu plus courte même lorsqu'elle était sensiblement plus
lente.

## Correction

- Le profil `car` préparé par Routeco utilise désormais un modèle versionné.
- Les règles d'accès et de vitesse restent celles de la voiture GraphHopper.
- `distance_influence` vaut `0` : la route de référence minimise réellement le
  temps de parcours.
- Les profils `light`, `balanced`, `economy` et `free` continuent à augmenter
  l'influence de la distance et à réduire les priorités autoroute/péage.
- Le lanceur mémorise l'empreinte du profil utilisé pour construire le graphe
  et refuse un cache obsolète.
- `./scripts/routeco.sh rebuild-graph` reconstruit explicitement le cache puis
  redémarre GraphHopper et l'application.

## Conséquence d'installation

La pondération est préparée dans les données Landmarks de GraphHopper. Une
reconstruction unique de `data/graph-cache` est donc obligatoire après cette
mise à jour.

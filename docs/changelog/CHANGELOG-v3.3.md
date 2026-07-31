# Routeco 0.3.3

Cette version reprend les problèmes généraux observés sur la validation aléatoire
France du 29 juillet 2026, sans règle liée à une ville ou à un trajet précis.

## Routage

- le plafond GraphHopper passe de 3 à 8 millions de nœuds visités ;
- les profils longue distance qui atteignent encore la limite sont relancés avec
  un ou deux points intermédiaires échantillonnés sur le trajet le plus rapide ;
- chaque sous-recherche conserve le même modèle autoroute/péage : la segmentation
  réduit l'espace de recherche sans imposer une destination particulière ;
- le délai maximal serveur et client est porté à trois minutes pour les longues
  traversées de la France.

## Péages

- un même site de péage ouvert avec plusieurs branches directionnelles n'est plus
  facturé plusieurs fois ; la branche réellement la plus proche de la géométrie
  est retenue ;
- une plage OSM peut désormais être expliquée par une chaîne de plusieurs
  matrices tarifaires non chevauchantes, utile lors d'un changement de réseau ;
- les parties exactes réduisent maintenant la distance restante à estimer au lieu
  de laisser estimer toute la plage ;
- un résidu inférieur à 5 km et 1 euro autour de tarifs exacts est traité comme
  bruit de balisage OSM et ne dégrade plus la confiance du résultat ;
- les contrôles d'ordre, de chevauchement et de réutilisation des gares restent
  obligatoires avant d'afficher « tarif exact ».

## Tests

- 49 tests automatiques ;
- nouveaux cas : récupération GraphHopper par segmentation, site ouvert à trois
  branches, chaîne de deux réseaux fermés et résidu OSM mineur.

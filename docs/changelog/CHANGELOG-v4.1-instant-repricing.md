# Routeco v4.1 — recalcul économique instantané

## Cache de péages

- Cache LRU en mémoire des tarifications produites pour une géométrie.
- Les tarifs exacts et les trajets sans péage sont partagés entre tous les taux
  d'estimation.
- Les kilomètres non résolus sont recalculés au nouveau taux sans relancer
  l'analyse géométrique.
- Les valeurs renvoyées sont copiées avant usage afin qu'un rendu ou un test ne
  puisse pas modifier l'entrée conservée.
- Les compteurs d'entrées, de succès et d'échecs sont visibles dans
  `/api/health`.

## Recalcul économique

Changer uniquement :

- le prix du carburant ;
- la consommation autoroute ou autres routes ;
- le temps supplémentaire maximal ;
- l'économie minimale ;

réutilise désormais à la fois les tracés GraphHopper et les tarifications. Le
serveur ne refait plus la projection des gares ni la sélection des matrices.

## Données volumineuses

- `ROUTECO_OSM_PBF` permet de conserver le fichier source France sur un autre
  disque.
- `routeco.sh` vérifie que ce disque est monté et maintient un lien local attendu
  par GraphHopper.
- Le graphe généré reste par défaut sur le disque Linux pour les performances.

## Validation

- 180 tests automatiques.
- `verify-cache` mesure désormais le temps de la réponse API complète et contrôle
  les compteurs du cache de péages.

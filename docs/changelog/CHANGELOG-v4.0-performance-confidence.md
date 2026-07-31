# Routeco v4.0 — performances mesurées et estimations prudentes

## Calcul des itinéraires

- Cache LRU en mémoire des géométries et détails GraphHopper, huit couples
  départ-arrivée pendant 30 minutes par défaut.
- Fusion des demandes identiques déjà en cours.
- Limitation configurable du nombre de calculs lourds simultanés.
- Réutilisation d'un client HTTP et de ses connexions vers GraphHopper.
- Les résultats de démonstration ne sont jamais mis en cache.
- Aucun profil, modèle, temps annoncé ou graphe GraphHopper n'est modifié.

## Mesures

- Durée, tentatives, candidats, échecs et récupération segmentée enregistrés
  pour chaque profil.
- p50, p95 et maximum ajoutés aux rapports de validation.
- État et taille estimée du cache disponibles dans `/api/health`.
- Temps de routage ou réutilisation du cache visibles dans l'interface.

## Péages

- Le taux appliqué aux portions sans tarif officiel est réglable indépendamment
  du prix du carburant.
- Une fourchette prudente accompagne le montant central estimé.
- Les composantes exactes conservent une borne basse et haute identiques.
- L'économie minimale garantie est distinguée de l'économie centrale.
- L'index spatial des gares remplace le balayage national complet tout en
  conservant les mêmes projections et seuils géométriques.

## VPS

- Commande `./scripts/routeco.sh doctor`.
- Démarrage ordinaire refusé si le graphe manque ; reconstruction uniquement
  avec la commande explicite `rebuild-graph`.
- Guide 2 OCPU / 12 Gio et exemples systemd/Caddy.
- Configuration conseillée : un calcul lourd simultané et cache de huit trajets.

## Validation

- 178 tests automatiques.
- Tests dédiés au cache, à la fusion des demandes, au sens du trajet, aux
  fourchettes d'estimation, aux limites d'environnement et à l'index spatial.

# Contexte de reprise — Détour / Routeco

Lire aussi `README.md`, `CHANGELOG-v3.7-fastest-time-baseline.md`,
`CHANGELOG-v3.8-national-geocoding-interface.md`,
`CHANGELOG-v3.9-route-diversity.md`,
`CHANGELOG-v4.0-performance-confidence.md`,
`CHANGELOG-v4.1-instant-repricing.md` et le dernier rapport dans
`docs/validation/`.

## Objectif produit

Application française gratuite et auto-hébergeable qui compare :

```text
coût carburant + coût des péages de classe 1
```

Règle de classement :

1. conserver un trajet de référence réellement optimisé sur le temps ;
2. calculer les autres profils pour réduire le coût total ;
3. conserver les rôles matériellement distincts : autoroute et moins de kilomètres ;
4. appliquer le détour maximal et l'économie minimale aux alternatives financières ;
5. regrouper les variantes qui ne créent pas un nouveau palier d'économie ;
6. afficher jusqu'à cinq choix, référence rapide en premier puis coût croissant.

Le profil initial reste une Twingo 2 essence :

- autoroute : 6,5 L/100 km ;
- autres routes : 5,5 L/100 km ;
- prix du carburant modifiable ;
- classe de péage 1.

## Version de code

- Version préparée : **0.4.1**.
- Point de départ de la migration v18 :
  `36d0299d5d0a86063f8ad591d37232c2315b6198`.
- Tests : **180**.
- Le profil GraphHopper préparé `car` utilise `distance_influence: 0`.
- Le graphe France a déjà été reconstruit par la v9 chez l'utilisateur.

## Architecture

- Frontend statique : `static/`.
- API FastAPI : `app/main.py`.
- Géocodage : `app/services/geocoder.py`.
- Index national des communes : `data/communes.sqlite`.
- Mise à jour des communes : `scripts/update_communes.py`.
- BAN facultative pour les adresses : `data/ban.sqlite`.
- Routage : `app/services/routing.py`.
- Coût carburant : `app/services/costs.py`.
- Péages : `app/services/tolls.py`.
- Sélection : `app/services/pareto.py`.
- Validation : `app/services/validation.py` et `scripts/validate_routes.py`.
- GraphHopper : `infra/graphhopper/config.yml`.

## État fonctionnel

- vraie référence rapide validée sur Paris → Grasse ;
- profil `motorway` ajouté pour découvrir les grands détours autoroutiers ;
- profils `light`, `balanced`, `economy` et `free` conservés ;
- toutes les communes françaises disponibles indépendamment des départements BAN ;
- saisie libre validable sans cliquer sur une suggestion ;
- homonymes renvoyés comme choix explicites au lieu d'un choix silencieux ;
- carte OpenStreetMap interactive, tracés cliquables, zoom, recentrage et agrandissement ;
- liens Google Maps, Waze et Apple Plans pour le trajet sélectionné ;
- compteur séparant routes calculées, hors critères, regroupées et affichées ;
- messages techniques de routage masqués dans l'interface ;
- aucun calcul automatique Paris → Lyon au chargement ;
- paliers d'économie : une route plus lente doit économiser au moins le seuil
  demandé par rapport au meilleur coût déjà rencontré.
- jusqu'à cinq rôles utiles ; les trajets autoroutier et court ne sont pas
  supprimés uniquement parce qu'ils ne franchissent pas le seuil d'économie.
- les géométries GraphHopper sont mises en cache par couple départ-arrivée ;
- les résultats du moteur de péage sont mis en cache par géométrie et taux
  d'estimation, pour rendre les recalculs de carburant quasi instantanés ;
- deux demandes identiques simultanées partagent un seul calcul lourd ;
- le prix du carburant, les filtres et le taux d'estimation des péages sont
  recalculés sans modifier les tracés ;
- les rapports exposent p50, p95, échecs et récupérations par profil ;
- les gares de péage sont projetées via un index spatial sans changer les
  critères géométriques ;
- un démarrage ordinaire ne reconstruit jamais silencieusement le graphe France.

## Péages

Les règles restent inchangées :

- aucun tarif ou correctif lié à une paire de villes ;
- `exact` seulement si tous les événements physiques facturables sont expliqués ;
- pas de gare réutilisée, doublon, chevauchement ou ordre impossible ;
- estimation clairement affichée lorsque la matrice officielle manque.
- la partie inconnue utilise un taux réglable et une fourchette prudente ; cette
  fourchette ne constitue jamais une preuve tarifaire.

La lacune connue Le Havre ↔ Rouen par A29/A150 reste indépendante de cette
mise à jour d'interface et de géocodage.

## Données de communes

`./scripts/routeco.sh start` vérifie que l'index contient au moins 30 000
communes. S'il est absent ou incomplet, il est reconstruit atomiquement depuis :

```text
https://geo.api.gouv.fr/communes
```

Commande manuelle :

```bash
./scripts/routeco.sh update-communes
```

Le test réel du 30 juillet 2026 a indexé 34 969 communes. `Versailles`,
`78000 Versailles` et `Prunay-le-Temple` ont été résolus ; `Saint-Aubin` produit
correctement une réponse ambiguë avec plusieurs choix.

## Contraintes

- logique générique France entière ;
- aucune API commerciale obligatoire ;
- données lourdes hors Git ;
- ne pas reconstruire de nouveau le graphe pour cette v12 ;
- ne pas modifier la pondération `distance_influence: 0` du profil rapide ;
- préférer une estimation déclarée à un faux péage exact.
- limiter le VPS personnel à un calcul lourd simultané.

## Commandes principales

```bash
./scripts/routeco.sh start
./scripts/routeco.sh status
./scripts/routeco.sh update-communes
./scripts/routeco.sh verify-geocoding
./scripts/routeco.sh verify-diversity
./scripts/routeco.sh verify-cache
./scripts/routeco.sh validate-random 50
./scripts/routeco.sh validate-gold
./scripts/routeco.sh verify-fastest
./.venv/bin/python -m pytest -q
```

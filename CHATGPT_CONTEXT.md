# Contexte de reprise — Détour / Routeco

Lire aussi `README.md`, `CHANGELOG-v3.7-fastest-time-baseline.md`,
`CHANGELOG-v3.8-national-geocoding-interface.md`,
`CHANGELOG-v3.9-route-diversity.md` et le dernier rapport dans
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

- Version préparée : **0.3.9**.
- Point de départ de la migration v11 :
  `a796cc3c3976e49af8c995034efc22e4868f7b24`.
- Tests : **167**.
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

## Péages

Les règles restent inchangées :

- aucun tarif ou correctif lié à une paire de villes ;
- `exact` seulement si tous les événements physiques facturables sont expliqués ;
- pas de gare réutilisée, doublon, chevauchement ou ordre impossible ;
- estimation clairement affichée lorsque la matrice officielle manque.

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
- ne pas reconstruire de nouveau le graphe pour cette v11 ;
- ne pas modifier la pondération `distance_influence: 0` du profil rapide ;
- préférer une estimation déclarée à un faux péage exact.

## Commandes principales

```bash
./scripts/routeco.sh start
./scripts/routeco.sh status
./scripts/routeco.sh update-communes
./scripts/routeco.sh verify-geocoding
./scripts/routeco.sh verify-diversity
./scripts/routeco.sh validate-random 50
./scripts/routeco.sh validate-gold
./scripts/routeco.sh verify-fastest
./.venv/bin/python -m pytest -q
```

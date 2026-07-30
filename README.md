# Détour / Routeco 0.3.9

Optimiseur de trajets routiers multicritère pour la France, auto-hébergeable et sans API commerciale obligatoire.

Le projet compare plusieurs itinéraires selon :

- le temps supplémentaire maximal accepté ;
- le coût du carburant ;
- la consommation autoroute / autres routes ;
- les péages de classe 1 ;
- le coût total du trajet.

Le profil initial correspond à une **Renault Twingo 2 essence** :

- 6,5 L/100 km sur autoroute ;
- 5,5 L/100 km sur les autres routes ;
- prix du carburant modifiable ;
- véhicule de classe de péage 1.

## État actuel

Fonctionnel :

- routage France avec GraphHopper et OpenStreetMap en local ;
- toutes les communes françaises dans un index SQLite local ;
- adresses détaillées avec la Base Adresse Nationale SQLite lorsqu'elle est installée ;
- plusieurs itinéraires et compromis temps / coût ;
- une référence optimisée uniquement sur le temps ;
- une option autoroutière, un trajet court et des alternatives économiques
  lorsqu'ils sont réellement distincts ;
- calcul séparé carburant / péages ;
- matrices de péages locales ;
- sections payantes multiples ;
- rapports de validation Markdown et JSON ;
- carte OpenStreetMap interactive, sélection des tracés et export GPS ;
- fonctionnement sans Google Maps, HERE, Mapbox ou API commerciale de péage.

Encore incomplet :

- certains tarifs de péage restent estimés quand les données entrée-sortie sont insuffisantes ;
- certains profils longue distance GraphHopper peuvent atteindre la limite de nœuds ;
- le déploiement VPS n'est pas encore finalisé.

Le fichier [`CHATGPT_CONTEXT.md`](CHATGPT_CONTEXT.md) contient l'état exact du projet pour reprendre le développement dans une nouvelle conversation.

## Installation locale

Python 3.11+ et Java 17+ sont requis.

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -U pip
./.venv/bin/python -m pip install -e '.[dev]'
```

GraphHopper et les données France sont volontairement exclus du dépôt Git :

```bash
GRAPHHOPPER_RAM=8g ./scripts/setup_graphhopper.sh
```

Le premier import construit le graphe local et peut prendre plusieurs minutes.

## Lancer Détour

```bash
./scripts/routeco.sh start
```

Puis ouvrir :

```text
http://127.0.0.1:8000
```

Commandes utiles :

```bash
./scripts/routeco.sh status
./scripts/routeco.sh logs
./scripts/routeco.sh restart-app
./scripts/routeco.sh restart
./scripts/routeco.sh verify-geocoding
./scripts/routeco.sh verify-diversity
./scripts/routeco.sh stop
```

## Configuration des données

Copier l'exemple :

```bash
cp .env.example .env
```

Exemple pour placer la BAN sur un autre disque :

```env
ROUTECO_BAN_DB=/chemin/vers/routeco-data/ban/ban.sqlite
```

L'index des communes est créé automatiquement au premier démarrage à partir de
l'API Découpage administratif officielle. Il peut être actualisé manuellement :

```bash
./scripts/routeco.sh update-communes
```

Il est indépendant de la BAN : une commune comme Versailles reste donc
disponible même si son département n'a pas été importé dans `ban.sqlite`.

Les données lourdes restent hors Git :

- `data/france-latest.osm.pbf` ;
- `data/graph-cache/` ;
- `data/ban.sqlite` ou une BAN externe ;
- `data/communes.sqlite` ;
- `data/graphhopper-web-*.jar` ;
- les logs et rapports générés.

Les petites matrices normalisées de `data/tolls/*.csv` sont versionnées afin qu'une nouvelle conversation puisse analyser le moteur sans télécharger les données lourdes.

## Tests

```bash
./.venv/bin/python -m pytest -q
```

La version 0.3.9 contient **167 tests automatiques**.

Une GitHub Action exécute également les tests à chaque push et pull request.

## Validation réelle France

GraphHopper doit tourner :

```bash
./scripts/routeco.sh validate
./scripts/routeco.sh validate-random 50
./scripts/routeco.sh validate-gold
```

Les rapports locaux sont créés dans `data/reports/` et ignorés par Git. Le dernier rapport utile a été copié dans [`docs/validation/`](docs/validation/) pour conserver l'historique de travail.

## Architecture

```text
Navigateur
  ├── interface de comparaison
  ├── détail carburant / péages
  └── carte OpenStreetMap interactive + liens GPS
          ↓
FastAPI
  ├── index national des communes
  ├── BAN SQLite pour les adresses détaillées
  ├── modèle de consommation
  ├── sélection multicritère
  └── appariement des péages
          ↓
GraphHopper local + OpenStreetMap France
```

## Règle de développement importante

Les villes de validation servent uniquement de tests. Le moteur ne doit jamais contenir de correction du type « si départ = Paris et arrivée = Lyon ».

Toute correction doit reposer sur des propriétés générales : géométrie du tracé, ordre des gares, réseau concessionnaire, sections payantes, matrices tarifaires et confiance du résultat.

#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && set -a && source .env && set +a

GH_DATA_DIR="${ROUTECO_GRAPHHOPPER_DATA_DIR:-$ROOT/data}"
mkdir -p "$GH_DATA_DIR"
TMP="$GH_DATA_DIR/france-latest.osm.pbf.tmp"
TARGET="$GH_DATA_DIR/france-latest.osm.pbf"

curl -4 -fL --retry 20 --retry-delay 5 --continue-at - \
  "https://download.geofabrik.de/europe/france-latest.osm.pbf" -o "$TMP"
mv "$TMP" "$TARGET"
rm -rf "$GH_DATA_DIR/graph-cache"
echo "OSM mis à jour. Redémarre GraphHopper pour reconstruire le graphe."

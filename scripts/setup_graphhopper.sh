#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${GRAPHHOPPER_VERSION:-11.0}"
JAR="data/graphhopper-web-${VERSION}.jar"
PBF="data/france-latest.osm.pbf"

if ! command -v java >/dev/null; then
  echo "Java manque. GraphHopper 11 demande Java 17 ou plus récent." >&2
  exit 1
fi
JAVA_MAJOR=$(java -version 2>&1 | awk -F '[".]' '/version/ {print $2; exit}')
if [[ "${JAVA_MAJOR:-0}" -lt 17 ]]; then
  echo "Java ${JAVA_MAJOR:-inconnu} détecté. Installe Java 17 avant GraphHopper 11." >&2
  exit 1
fi

mkdir -p data
if [[ ! -f "$JAR" ]]; then
  curl -fL "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/${VERSION}/graphhopper-web-${VERSION}.jar" -o "$JAR"
fi
if [[ ! -f "$PBF" ]]; then
  echo "Téléchargement du réseau France (fichier volumineux)…"
  curl -fL "https://download.geofabrik.de/europe/france-latest.osm.pbf" -o "$PBF"
fi

echo "Import initial et démarrage de GraphHopper. Le premier lancement construit data/graph-cache."
exec java -Xms2g -Xmx"${GRAPHHOPPER_RAM:-10g}" -jar "$JAR" server infra/graphhopper/config.yml

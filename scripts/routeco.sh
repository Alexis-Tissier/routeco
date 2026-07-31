#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && set -a && source .env && set +a

RUNTIME_DIR="${ROUTECO_RUNTIME_DIR:-$ROOT/.runtime}"
LOG_DIR="${ROUTECO_LOG_DIR:-$ROOT/data/logs}"
BACKEND_PID="$RUNTIME_DIR/backend.pid"
GRAPHHOPPER_PID="$RUNTIME_DIR/graphhopper.pid"
GRAPH_CACHE="$ROOT/data/graph-cache"
GRAPH_PBF_LINK="$ROOT/data/france-latest.osm.pbf"
OSM_PBF_SOURCE="${ROUTECO_OSM_PBF:-$GRAPH_PBF_LINK}"
GRAPH_PROFILE_MODEL="$ROOT/infra/graphhopper/custom_models/routeco_car.json"
GRAPH_PROFILE_MARKER="$GRAPH_CACHE/.routeco-profile-sha256"
DATA_DIR="${ROUTECO_DATA_DIR:-$ROOT/data}"
COMMUNES_DB="${ROUTECO_COMMUNES_DB:-$DATA_DIR/communes.sqlite}"

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

pid_alive() {
  local file="$1"
  [[ -f "$file" ]] || return 1
  local pid
  pid="$(cat "$file" 2>/dev/null || true)"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

wait_http() {
  local url="$1"
  local attempts="${2:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  return 1
}

wait_process_http() {
  local url="$1"
  local pid_file="$2"
  local attempts="${3:-60}"
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    if ! pid_alive "$pid_file"; then
      return 1
    fi
    sleep 1
  done
  return 1
}

ensure_python() {
  if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -U pip
    .venv/bin/python -m pip install -e .
  fi
}

ensure_communes() {
  ensure_python
  if [[ -f "$COMMUNES_DB" ]] && .venv/bin/python - "$COMMUNES_DB" <<'PY' >/dev/null 2>&1
import sqlite3
import sys

with sqlite3.connect(sys.argv[1]) as connection:
    count = connection.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
raise SystemExit(0 if count >= 30_000 else 1)
PY
  then
    return 0
  fi
  echo "Préparation de l'index local des communes françaises…"
  .venv/bin/python scripts/update_communes.py --output "$COMMUNES_DB"
}

find_graphhopper_jar() {
  local explicit="${ROUTECO_GRAPHHOPPER_JAR:-}"
  if [[ -n "$explicit" && -f "$explicit" ]]; then
    printf '%s\n' "$explicit"
    return 0
  fi
  local jar
  jar="$(find "$ROOT/data" -maxdepth 1 -type f -name 'graphhopper-web-*.jar' | sort -V | tail -n 1)"
  [[ -n "$jar" ]] || return 1
  printf '%s\n' "$jar"
}

graph_profile_fingerprint() {
  {
    sed -n '/^graphhopper:/,/^server:/p' "$ROOT/infra/graphhopper/config.yml"
    cat "$GRAPH_PROFILE_MODEL"
  } | sha256sum | awk '{print $1}'
}

graph_cache_matches_profile() {
  [[ ! -d "$GRAPH_CACHE" ]] && return 0
  [[ -f "$GRAPH_PROFILE_MARKER" ]] || return 1
  [[ "$(cat "$GRAPH_PROFILE_MARKER" 2>/dev/null || true)" == "$(graph_profile_fingerprint)" ]]
}

write_graph_profile_marker() {
  [[ -d "$GRAPH_CACHE" ]] || return 1
  graph_profile_fingerprint > "$GRAPH_PROFILE_MARKER"
}

ensure_osm_pbf() {
  if [[ "$OSM_PBF_SOURCE" == "$GRAPH_PBF_LINK" ]]; then
    if [[ ! -f "$GRAPH_PBF_LINK" ]]; then
      echo "Fichier OSM France absent : $GRAPH_PBF_LINK" >&2
      return 1
    fi
    return 0
  fi

  if [[ ! -f "$OSM_PBF_SOURCE" ]]; then
    echo "Fichier OSM externe absent : $OSM_PBF_SOURCE" >&2
    echo "Vérifie que la partition est montée avant de démarrer Routeco." >&2
    return 1
  fi

  mkdir -p "$(dirname "$GRAPH_PBF_LINK")"
  if [[ -L "$GRAPH_PBF_LINK" ]]; then
    rm -f "$GRAPH_PBF_LINK"
  elif [[ -e "$GRAPH_PBF_LINK" ]]; then
    echo "Un fichier local existe encore à la place du lien OSM :" >&2
    echo "  $GRAPH_PBF_LINK" >&2
    return 1
  fi
  ln -s "$OSM_PBF_SOURCE" "$GRAPH_PBF_LINK"
}

ensure_graph_cache_compatible() {
  if graph_cache_matches_profile; then
    return 0
  fi
  echo "Le graphe local a été construit avec un ancien profil de routage." >&2
  echo "Reconstruis-le une seule fois avec :" >&2
  echo "  ./scripts/routeco.sh rebuild-graph" >&2
  return 1
}

start_graphhopper() {
  local mode="${1:-runtime}"
  ensure_osm_pbf
  ensure_graph_cache_compatible
  if curl -fsS http://127.0.0.1:8989/info >/dev/null 2>&1; then
    echo "GraphHopper est déjà opérationnel sur le port 8989."
    return 0
  fi
  if pid_alive "$GRAPHHOPPER_PID"; then
    echo "GraphHopper démarre déjà (PID $(cat "$GRAPHHOPPER_PID"))."
    return 0
  fi
  local jar
  if ! jar="$(find_graphhopper_jar)"; then
    echo "GraphHopper n'est pas installé. Lance d'abord :" >&2
    echo "  GRAPHHOPPER_RAM=8g ./scripts/setup_graphhopper.sh" >&2
    return 1
  fi
  local wait_attempts=90
  if [[ ! -d "$GRAPH_CACHE" ]]; then
    if [[ "$mode" != "import" ]]; then
      echo "Le graphe France est absent. Démarrage automatique refusé pour éviter" >&2
      echo "une reconstruction lourde et involontaire." >&2
      echo "Lance explicitement : ./scripts/routeco.sh rebuild-graph" >&2
      return 1
    fi
    wait_attempts=3600
    echo "Reconstruction explicite du graphe France en cours."
    echo "Cette étape peut prendre plusieurs minutes ; suivi : $LOG_DIR/graphhopper.log"
  fi
  local java_heap="${GRAPHHOPPER_RAM:-8g}"
  if [[ "$mode" == "import" ]]; then
    java_heap="${GRAPHHOPPER_IMPORT_RAM:-10g}"
  fi
  echo "Démarrage de GraphHopper…"
  nohup java -Xms1g -Xmx"$java_heap" \
    -jar "$jar" server "$ROOT/infra/graphhopper/config.yml" \
    >"$LOG_DIR/graphhopper.log" 2>&1 &
  echo $! > "$GRAPHHOPPER_PID"
  if wait_process_http \
    http://127.0.0.1:8989/info \
    "$GRAPHHOPPER_PID" \
    "$wait_attempts"; then
    write_graph_profile_marker
    echo "GraphHopper prêt."
  else
    echo "GraphHopper n'a pas démarré. Consulte : $LOG_DIR/graphhopper.log" >&2
    tail -n 20 "$LOG_DIR/graphhopper.log" >&2 || true
    return 1
  fi
}

start_backend() {
  ensure_graph_cache_compatible
  ensure_communes
  if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Détour est déjà opérationnel sur le port 8000."
    return 0
  fi
  if pid_alive "$BACKEND_PID"; then
    echo "Détour démarre déjà (PID $(cat "$BACKEND_PID"))."
    return 0
  fi
  ensure_python
  echo "Démarrage de Détour…"
  nohup env PYTHONUNBUFFERED=1 .venv/bin/uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 \
    >"$LOG_DIR/detour.log" 2>&1 &
  echo $! > "$BACKEND_PID"
  if wait_process_http \
    http://127.0.0.1:8000/api/health \
    "$BACKEND_PID" \
    30; then
    echo "Détour prêt : http://127.0.0.1:8000"
  else
    echo "Détour ne répond pas. Consulte : $LOG_DIR/detour.log" >&2
    tail -n 20 "$LOG_DIR/detour.log" >&2 || true
    return 1
  fi
}

stop_pid() {
  local file="$1"
  local label="$2"
  if ! pid_alive "$file"; then
    rm -f "$file"
    echo "$label n'est pas lancé par ce script."
    return 0
  fi
  local pid
  pid="$(cat "$file")"
  kill "$pid" 2>/dev/null || true
  for _ in {1..20}; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 0.25
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
  echo "$label arrêté."
}


stop_matching_port() {
  local port="$1"
  local pattern="$2"
  local label="$3"
  local found=0
  local pid
  for pid in $(fuser "${port}/tcp" 2>/dev/null || true); do
    local owner command
    owner="$(ps -o user= -p "$pid" 2>/dev/null | xargs || true)"
    command="$(ps -o args= -p "$pid" 2>/dev/null || true)"
    if [[ "$owner" == "$(id -un)" && "$command" == *"$pattern"* ]]; then
      kill "$pid" 2>/dev/null || true
      for _ in {1..20}; do
        kill -0 "$pid" 2>/dev/null || break
        sleep 0.25
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
      fi
      found=1
    fi
  done
  if [[ "$found" -eq 1 ]]; then
    sleep 1
    echo "$label arrêté (processus existant détecté sur le port $port)."
  fi
}

stop_backend() {
  if pid_alive "$BACKEND_PID"; then
    stop_pid "$BACKEND_PID" "Détour"
  else
    rm -f "$BACKEND_PID"
    stop_matching_port 8000 "uvicorn" "Détour"
  fi
}

stop_graphhopper() {
  if pid_alive "$GRAPHHOPPER_PID"; then
    stop_pid "$GRAPHHOPPER_PID" "GraphHopper"
  else
    rm -f "$GRAPHHOPPER_PID"
    stop_matching_port 8989 "graphhopper" "GraphHopper"
  fi
}

rebuild_graph() {
  stop_backend
  stop_graphhopper
  if [[ -e "$GRAPH_CACHE" ]]; then
    local resolved_cache
    resolved_cache="$(realpath -m "$GRAPH_CACHE")"
    if [[ "$resolved_cache" != "$ROOT/data/graph-cache" ]]; then
      echo "Chemin de cache inattendu, suppression refusée : $resolved_cache" >&2
      return 1
    fi
    rm -rf -- "$resolved_cache"
    echo "Ancien graphe généré supprimé."
  fi
  start_graphhopper import
  start_backend
  status
}

status() {
  local gh="non"
  local api="non"
  curl -fsS http://127.0.0.1:8989/info >/dev/null 2>&1 && gh="oui"
  curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1 && api="oui"
  echo "GraphHopper : $gh"
  echo "Détour      : $api"
  if [[ "$api" == "oui" ]]; then
    curl -fsS http://127.0.0.1:8000/api/health | python3 -m json.tool 2>/dev/null || true
  fi
  echo "Logs        : $LOG_DIR"
}

doctor() {
  local memory_kb cpu_count disk_kb cache_size pbf_size pbf_disk_kb
  memory_kb="$(awk '/^MemTotal:/ {print $2; exit}' /proc/meminfo 2>/dev/null || echo 0)"
  cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)"
  disk_kb="$(df -Pk "$ROOT" | awk 'NR == 2 {print $4}')"
  cache_size="absent"
  if [[ -d "$GRAPH_CACHE" ]]; then
    cache_size="$(du -sh "$GRAPH_CACHE" 2>/dev/null | awk '{print $1}')"
  fi
  pbf_size="absent"
  pbf_disk_kb=0
  if [[ -f "$OSM_PBF_SOURCE" ]]; then
    pbf_size="$(du -sh "$OSM_PBF_SOURCE" 2>/dev/null | awk '{print $1}')"
    pbf_disk_kb="$(df -Pk "$OSM_PBF_SOURCE" | awk 'NR == 2 {print $4}')"
  fi

  echo "Diagnostic ressources Routeco"
  echo "CPU                     : ${cpu_count} cœur(s)"
  echo "RAM                     : $((memory_kb / 1024)) Mio"
  echo "Disque libre            : $((disk_kb / 1024 / 1024)) Gio"
  echo "Cache GraphHopper       : $cache_size"
  echo "Source OSM France       : $pbf_size · $OSM_PBF_SOURCE"
  if (( pbf_disk_kb > 0 )); then
    echo "Disque libre source OSM : $((pbf_disk_kb / 1024 / 1024)) Gio"
  fi
  echo "Heap GraphHopper runtime: ${GRAPHHOPPER_RAM:-8g}"
  echo "Calculs simultanés      : ${ROUTECO_MAX_CONCURRENT_CALCULATIONS:-1}"
  echo "Cache de trajets        : ${ROUTECO_ROUTING_CACHE_ENTRIES:-8} entrée(s), ${ROUTECO_ROUTING_CACHE_TTL:-1800} s"
  echo "Cache de péages         : 96 tarifications de géométrie"

  local warnings=0
  if (( memory_kb < 10 * 1024 * 1024 )); then
    echo "AVERTISSEMENT : moins de 10 Gio de RAM ; graphe France + autres services risqués."
    warnings=$((warnings + 1))
  fi
  if (( disk_kb < 35 * 1024 * 1024 )); then
    echo "AVERTISSEMENT : moins de 35 Gio libres ; mise à jour du graphe déconseillée."
    warnings=$((warnings + 1))
  fi
  if (( cpu_count < 2 )); then
    echo "AVERTISSEMENT : un seul cœur ; les recherches multi-profils seront lentes."
    warnings=$((warnings + 1))
  fi
  if [[ ! -d "$GRAPH_CACHE" ]]; then
    echo "AVERTISSEMENT : cache GraphHopper absent ; import France requis avant utilisation."
    warnings=$((warnings + 1))
  fi
  if (( warnings == 0 )); then
    echo "Verdict : ressources minimales cohérentes pour un usage personnel."
  else
    echo "Verdict : corriger les avertissements avant une mise en ligne permanente."
  fi
}

case "${1:-status}" in
  start)
    start_graphhopper
    start_backend
    status
    ;;
  start-app)
    start_backend
    ;;
  restart-app)
    stop_backend
    start_backend
    ;;
  stop)
    stop_backend
    stop_graphhopper
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  rebuild-graph)
    rebuild_graph
    ;;
  status)
    status
    ;;
  doctor)
    doctor
    ;;
  logs)
    touch "$LOG_DIR/detour.log" "$LOG_DIR/graphhopper.log"
    tail -n 80 -F "$LOG_DIR/detour.log" "$LOG_DIR/graphhopper.log"
    ;;
  validate)
    ensure_python
    shift || true
    exec .venv/bin/python -m scripts.validate_routes "$@"
    ;;
  validate-random)
    ensure_python
    shift || true
    count="${1:-50}"
    if [[ $# -gt 0 ]]; then shift; fi
    exec .venv/bin/python -m scripts.validate_routes --random "$count" "$@"
    ;;
  validate-gold)
    ensure_python
    shift || true
    exec .venv/bin/python -m scripts.validate_routes --gold "$@"
    ;;
  verify-fastest)
    ensure_python
    shift || true
    exec .venv/bin/python -m scripts.verify_fastest_reference "$@"
    ;;
  verify-geocoding)
    ensure_python
    exec .venv/bin/python -m scripts.verify_geocoding
    ;;
  verify-diversity)
    ensure_python
    exec .venv/bin/python -m scripts.verify_route_diversity
    ;;
  verify-cache)
    ensure_python
    exec .venv/bin/python -m scripts.verify_runtime_cache
    ;;
  verify-waypoint)
    ensure_python
    exec .venv/bin/python -m scripts.verify_waypoint
    ;;
  update-communes)
    ensure_python
    exec .venv/bin/python scripts/update_communes.py --output "$COMMUNES_DB"
    ;;
  *)
    cat <<EOF
Usage : ./scripts/routeco.sh COMMANDE

  start          démarre GraphHopper puis Détour
  start-app      démarre seulement Détour
  restart-app    redémarre seulement Détour
  stop           arrête les deux services lancés par ce script
  restart        redémarre les deux services
  rebuild-graph  reconstruit le graphe après un changement de profil
  status         affiche l'état détaillé
  doctor         vérifie CPU, RAM, disque, cache et limites VPS
  logs           suit les deux fichiers de logs
  validate       vérifie la structure sur les trajets de couverture
  validate-random [N] teste N couples de villes sans règle par destination
  validate-gold  vérifie séparément les trajets de référence chiffrés
  verify-fastest vérifie la vraie référence rapide sur un trajet long
  verify-geocoding vérifie la couverture nationale et les homonymes
  verify-diversity vérifie les choix autoroutier et direct sur un trajet régional
  verify-cache   vérifie la réutilisation des tracés lors d'un recalcul économique
  verify-waypoint vérifie un trajet réel avec arrêt intermédiaire imposé
  update-communes actualise l'index local de toutes les communes françaises
EOF
    exit 2
    ;;
esac

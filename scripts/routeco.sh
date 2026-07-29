#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && set -a && source .env && set +a

RUNTIME_DIR="${ROUTECO_RUNTIME_DIR:-$ROOT/.runtime}"
LOG_DIR="${ROUTECO_LOG_DIR:-$ROOT/data/logs}"
BACKEND_PID="$RUNTIME_DIR/backend.pid"
GRAPHHOPPER_PID="$RUNTIME_DIR/graphhopper.pid"

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

ensure_python() {
  if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic' >/dev/null 2>&1; then
    .venv/bin/python -m pip install -U pip
    .venv/bin/python -m pip install -e .
  fi
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

start_graphhopper() {
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
  if [[ ! -d "$ROOT/data/graph-cache" ]]; then
    wait_attempts=3600
    echo "Le graphe France est absent : reconstruction automatique en cours."
    echo "Cette étape peut prendre plusieurs minutes ; suivi : $LOG_DIR/graphhopper.log"
  fi
  echo "Démarrage de GraphHopper…"
  nohup java -Xms1g -Xmx"${GRAPHHOPPER_RAM:-8g}" \
    -jar "$jar" server "$ROOT/infra/graphhopper/config.yml" \
    >"$LOG_DIR/graphhopper.log" 2>&1 &
  echo $! > "$GRAPHHOPPER_PID"
  if wait_http http://127.0.0.1:8989/info "$wait_attempts"; then
    echo "GraphHopper prêt."
  else
    echo "GraphHopper ne répond pas encore. Consulte : $LOG_DIR/graphhopper.log" >&2
    return 1
  fi
}

start_backend() {
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
  if wait_http http://127.0.0.1:8000/api/health 30; then
    echo "Détour prêt : http://127.0.0.1:8000"
  else
    echo "Détour ne répond pas. Consulte : $LOG_DIR/detour.log" >&2
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
  status)
    status
    ;;
  logs)
    touch "$LOG_DIR/detour.log" "$LOG_DIR/graphhopper.log"
    tail -n 80 -F "$LOG_DIR/detour.log" "$LOG_DIR/graphhopper.log"
    ;;
  validate)
    ensure_python
    shift || true
    exec .venv/bin/python scripts/validate_routes.py "$@"
    ;;
  validate-random)
    ensure_python
    shift || true
    count="${1:-50}"
    if [[ $# -gt 0 ]]; then shift; fi
    exec .venv/bin/python scripts/validate_routes.py --random "$count" "$@"
    ;;
  validate-gold)
    ensure_python
    shift || true
    exec .venv/bin/python scripts/validate_routes.py --gold "$@"
    ;;
  *)
    cat <<EOF
Usage : ./scripts/routeco.sh COMMANDE

  start          démarre GraphHopper puis Détour
  start-app      démarre seulement Détour
  restart-app    redémarre seulement Détour
  stop           arrête les deux services lancés par ce script
  restart        redémarre les deux services
  status         affiche l'état détaillé
  logs           suit les deux fichiers de logs
  validate       vérifie la structure sur les trajets de couverture
  validate-random [N] teste N couples de villes sans règle par destination
  validate-gold  vérifie séparément les trajets de référence chiffrés
EOF
    exit 2
    ;;
esac

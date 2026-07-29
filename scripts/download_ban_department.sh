#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && set -a && source .env && set +a

[[ $# -ge 1 ]] || { echo "Usage: scripts/download_ban_department.sh 78 [06 ...]" >&2; exit 2; }
DATA_DIR="${ROUTECO_DATA_DIR:-$ROOT/data}"
BAN_DOWNLOAD_DIR="${ROUTECO_BAN_DOWNLOAD_DIR:-$DATA_DIR/ban}"
BAN_DB="${ROUTECO_BAN_DB:-$DATA_DIR/ban.sqlite}"
mkdir -p "$BAN_DOWNLOAD_DIR" "$(dirname "$BAN_DB")"

for CODE in "$@"; do
  URL="https://adresse.data.gouv.fr/data/ban/adresses/latest/csv/adresses-${CODE}.csv.gz"
  TARGET="$BAN_DOWNLOAD_DIR/adresses-${CODE}.csv.gz"
  if command -v wget >/dev/null 2>&1; then
    wget -4 -c --retry-connrefused --waitretry=5 --timeout=60 --tries=0 -O "$TARGET" "$URL"
  else
    curl -4 -fL --retry 20 --retry-delay 5 --continue-at - "$URL" -o "$TARGET"
  fi
  gzip -t "$TARGET"
done

python3 scripts/import_ban.py "$BAN_DOWNLOAD_DIR"/adresses-*.csv.gz --output "$BAN_DB"
echo "BAN importée dans $BAN_DB."

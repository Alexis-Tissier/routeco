#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && set -a && source .env && set +a

DATA_DIR="${ROUTECO_DATA_DIR:-$ROOT/data}"
SOURCE_DIR="${ROUTECO_OPENTOLLDATA_DIR:-$DATA_DIR/opentolldata}"
TOLLS_DIR="${ROUTECO_TOLLS_DIR:-$DATA_DIR/tolls}"
mkdir -p "$DATA_DIR" "$TOLLS_DIR"

if [[ -d "$SOURCE_DIR/.git" ]]; then
  git -C "$SOURCE_DIR" pull --ff-only
else
  git clone --depth 1 https://github.com/louis2038/OpenTollData.git "$SOURCE_DIR"
fi

python3 scripts/normalize_opentolldata.py "$SOURCE_DIR" --output "$TOLLS_DIR"
echo "Données OpenTollData normalisées dans $TOLLS_DIR. Les compléments officiels présents dans $TOLLS_DIR/official sont conservés."

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q

./scripts/routeco.sh restart-app

echo
echo "Routeco 0.2.3 est installé."
echo "État      : ./scripts/routeco.sh status"
echo "Validation: ./scripts/routeco.sh validate"
echo "Interface : http://127.0.0.1:8000"

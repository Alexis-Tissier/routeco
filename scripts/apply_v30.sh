#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
./scripts/routeco.sh restart-app

echo
echo "Routeco 0.3.0 est installé."
echo "Validation structurelle : ./scripts/routeco.sh validate"
echo "Validation aléatoire    : ./scripts/routeco.sh validate-random 50"
echo "Références chiffrées    : ./scripts/routeco.sh validate-gold"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Environnement Python .venv introuvable." >&2
  echo "Cette archive met à jour une installation Routeco existante." >&2
  exit 1
fi

if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic, pytest' >/dev/null 2>&1; then
  .venv/bin/python -m pip install --no-build-isolation -e '.[dev]'
fi

.venv/bin/python -m pytest -q

# La configuration GraphHopper change dans cette version : un redémarrage des
# deux services est nécessaire, mais le graphe France n'est pas reconstruit.
./scripts/routeco.sh restart

echo
echo "Routeco 0.3.3 est installé."
echo "Validation aléatoire : ./scripts/routeco.sh validate-random 50"
echo "Références chiffrées : ./scripts/routeco.sh validate-gold"

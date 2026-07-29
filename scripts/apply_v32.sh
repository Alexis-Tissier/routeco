#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -x .venv/bin/python ]]; then
  echo "Environnement Python .venv introuvable." >&2
  echo "Cette archive met à jour une installation Routeco existante." >&2
  echo "Relance d'abord ./scripts/run_dev.sh une fois, puis cette commande." >&2
  exit 1
fi

# Une mise à jour de code n'a normalement rien à télécharger : l'environnement
# de la version précédente contient déjà les dépendances nécessaires.
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic, pytest' >/dev/null 2>&1; then
  .venv/bin/python -m pip install --no-build-isolation -e '.[dev]'
fi

.venv/bin/python -m pytest -q
./scripts/routeco.sh restart-app

echo
echo "Routeco 0.3.2 est installé."
echo "Validation aléatoire : ./scripts/routeco.sh validate-random 50"
echo "Références chiffrées : ./scripts/routeco.sh validate-gold"

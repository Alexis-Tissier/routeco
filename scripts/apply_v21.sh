#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

rm -f CHANGELOG-v1.4.md CHANGELOG-v1.5.md CHANGELOG-v1.6.md \
  CHANGELOG-v1.7.md CHANGELOG-v1.8.md CHANGELOG-v1.9.md CHANGELOG-v2.0.md
rm -rf routeco.egg-info .pytest_cache
find . -type d -name __pycache__ -prune -exec rm -rf {} +
chmod +x scripts/*.sh scripts/*.py

if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, httpx, pydantic, pytest' >/dev/null 2>&1; then
  .venv/bin/python -m pip install -e '.[dev]'
fi
.venv/bin/python -m pytest -q

./scripts/routeco.sh restart-app

echo
echo "Routeco 0.2.1 est installé."
echo "État : ./scripts/routeco.sh status"
echo "Validation France : ./scripts/routeco.sh validate"
echo "Interface : http://127.0.0.1:8000"

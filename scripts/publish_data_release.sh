#!/usr/bin/env bash
set -euo pipefail

RELEASE_DIR="${1:-}"
if [[ -z "$RELEASE_DIR" || ! -d "$RELEASE_DIR" ]]; then
  echo "Usage : $0 dist/data-release/data-france-v1" >&2
  exit 2
fi

command -v gh >/dev/null 2>&1 || {
  echo "GitHub CLI (gh) est requis pour publier les fichiers." >&2
  exit 1
}

MANIFEST="$(find "$RELEASE_DIR" -maxdepth 1 -type f -name 'detour-data-france-v*.json' | head -n 1)"
[[ -n "$MANIFEST" ]] || {
  echo "Manifest introuvable dans $RELEASE_DIR" >&2
  exit 1
}

VERSION="$(
  python3 - "$MANIFEST" <<'PY'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])
PY
)"
TAG="data-france-v${VERSION}"
TITLE="Détour — données France v${VERSION}"

if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" \
    --title "$TITLE" \
    --notes "Pack de données locales France pour Détour. Les parties sont vérifiées par SHA-256 et reconstituées automatiquement par l'application."
fi

mapfile -t ASSETS < <(
  find "$RELEASE_DIR" -maxdepth 1 -type f \
    \( -name 'detour-data-france-v*.json' \
       -o -name 'detour-data-france-v*.zip.part*' \
       -o -name 'SHA256SUMS' \) \
    | sort
)

gh release upload "$TAG" "${ASSETS[@]}" --clobber
echo "Publication terminée :"
gh release view "$TAG" --web

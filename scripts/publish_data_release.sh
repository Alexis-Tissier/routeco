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
gh auth status >/dev/null

MANIFEST="$(find "$RELEASE_DIR" -maxdepth 1 -type f -name 'detour-data-france-v*.json' | head -n 1)"
[[ -n "$MANIFEST" ]] || {
  echo "Manifest introuvable dans $RELEASE_DIR" >&2
  exit 1
}

VERSION="$(
  python3 - "$MANIFEST" <<'PY_INNER'
import json
import sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])
PY_INNER
)"
TAG="data-france-v${VERSION}"
TITLE="Détour — données France v${VERSION}"
TARGET_REF="${DETOUR_RELEASE_TARGET:-$(git branch --show-current)}"
MAX_ASSET_BYTES=$((2 * 1024 * 1024 * 1024 - 1))

mapfile -t ASSETS < <(
  find "$RELEASE_DIR" -maxdepth 1 -type f \
    \( -name 'detour-data-france-v*.json' \
       -o -name 'detour-data-france-v*.zip.part*' \
       -o -name 'SHA256SUMS' \) \
    | sort
)

[[ ${#ASSETS[@]} -gt 0 ]] || {
  echo "Aucun fichier à publier dans $RELEASE_DIR" >&2
  exit 1
}

for asset in "${ASSETS[@]}"; do
  size="$(stat -c %s "$asset")"
  if (( size > MAX_ASSET_BYTES )); then
    echo "Fichier trop volumineux pour GitHub Releases : $asset ($size octets)" >&2
    exit 1
  fi
done

NOTES="Pack de données locales France pour Détour. Les parties sont vérifiées par SHA-256, reconstituées puis installées automatiquement par l'application. Cette release de données n'est volontairement pas marquée comme dernière version de l'application."

if ! gh release view "$TAG" >/dev/null 2>&1; then
  gh release create "$TAG" \
    --target "$TARGET_REF" \
    --title "$TITLE" \
    --notes "$NOTES" \
    --latest=false
else
  gh release edit "$TAG" \
    --title "$TITLE" \
    --notes "$NOTES" \
    --latest=false
fi

gh release upload "$TAG" "${ASSETS[@]}" --clobber

echo "Publication terminée :"
gh release view "$TAG" --json tagName,name,url,isPrerelease,assets \
  --jq '{tag: .tagName, nom: .name, url: .url, prerelease: .isPrerelease, fichiers: [.assets[].name]}'

#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${REPO_NAME:-routeco}"
REPO_VISIBILITY="${REPO_VISIBILITY:-private}"
OWNER="${GITHUB_OWNER:-Alexis-Tissier}"

cd "$(dirname "$0")/.."

if [[ ! -d .git ]]; then
  git init -b main
fi

# Identité Git locale au dépôt, sans exposer une adresse personnelle.
if ! git config --local user.name >/dev/null 2>&1; then
  git config --local user.name "$OWNER"
fi
if ! git config --local user.email >/dev/null 2>&1; then
  git config --local user.email "224019552+$OWNER@users.noreply.github.com"
fi

git add .

if ! git diff --cached --quiet; then
  git commit -m "Initial Routeco 0.3.3 import"
fi

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin déjà configuré : $(git remote get-url origin)"
  git push -u origin main
  exit 0
fi

if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  case "$REPO_VISIBILITY" in
    private|public|internal) ;;
    *) echo "REPO_VISIBILITY doit être private, public ou internal." >&2; exit 1 ;;
  esac

  gh repo create "$OWNER/$REPO_NAME" \
    "--$REPO_VISIBILITY" \
    --source=. \
    --remote=origin \
    --push

  echo "Dépôt créé : https://github.com/$OWNER/$REPO_NAME"
else
  cat <<MANUAL
Le dépôt local est prêt et le premier commit est créé.

1. Crée un dépôt GitHub vide nommé : $REPO_NAME
2. Ne coche pas README, .gitignore ou licence.
3. Lance ensuite :

  git remote add origin git@github.com:$OWNER/$REPO_NAME.git
  git push -u origin main

Ou installe GitHub CLI, connecte-toi avec 'gh auth login', puis relance ce script.
MANUAL
fi

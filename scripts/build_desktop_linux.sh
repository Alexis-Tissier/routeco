#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

GRAPHHOPPER_VERSION="11.0"
CACHE_DIR="$ROOT/.desktop-cache"
BUILD_DIR="$ROOT/build/desktop"
DIST_DIR="$ROOT/dist/desktop"
RUNTIME_DIR="$BUILD_DIR/runtime"
PYINSTALLER_DIR="$BUILD_DIR/python"
JRE_DIR="$RUNTIME_DIR/jre"

command -v node >/dev/null || { echo "Node.js manque." >&2; exit 1; }
command -v npm >/dev/null || { echo "npm manque." >&2; exit 1; }
command -v curl >/dev/null || { echo "curl manque." >&2; exit 1; }
command -v tar >/dev/null || { echo "tar manque." >&2; exit 1; }

mkdir -p "$CACHE_DIR" "$RUNTIME_DIR" "$PYINSTALLER_DIR" "$DIST_DIR"
rm -rf "$PYINSTALLER_DIR/detour-backend" "$BUILD_DIR/work" "$BUILD_DIR/spec"

./.venv/bin/python -m pip install --quiet --upgrade \
  "pyinstaller>=6.15,<7" \
  "pillow>=11,<13"

./.venv/bin/python desktop/build_icon.py

GRAPHHOPPER_JAR="$RUNTIME_DIR/graphhopper-web-${GRAPHHOPPER_VERSION}.jar"
if [[ ! -f "$GRAPHHOPPER_JAR" ]]; then
  if [[ -f "data/graphhopper-web-${GRAPHHOPPER_VERSION}.jar" ]]; then
    cp "data/graphhopper-web-${GRAPHHOPPER_VERSION}.jar" "$GRAPHHOPPER_JAR"
  else
    curl -fL \
      "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/${GRAPHHOPPER_VERSION}/graphhopper-web-${GRAPHHOPPER_VERSION}.jar" \
      -o "$GRAPHHOPPER_JAR"
  fi
fi

if [[ ! -x "$JRE_DIR/bin/java" ]]; then
  JRE_ARCHIVE="$CACHE_DIR/temurin-jre21-linux-x64.tar.gz"
  if [[ ! -f "$JRE_ARCHIVE" ]]; then
    curl -fL \
      "https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jre/hotspot/normal/eclipse" \
      -o "$JRE_ARCHIVE"
  fi
  rm -rf "$JRE_DIR" "$CACHE_DIR/jre-extract"
  mkdir -p "$CACHE_DIR/jre-extract"
  tar -xzf "$JRE_ARCHIVE" -C "$CACHE_DIR/jre-extract"
  EXTRACTED="$(find "$CACHE_DIR/jre-extract" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
  [[ -n "$EXTRACTED" ]] || { echo "Runtime Java introuvable." >&2; exit 1; }
  mv "$EXTRACTED" "$JRE_DIR"
fi

./.venv/bin/python -m PyInstaller \
  --noconfirm \
  --clean \
  --onedir \
  --name detour-backend \
  --distpath "$PYINSTALLER_DIR" \
  --workpath "$BUILD_DIR/work" \
  --specpath "$BUILD_DIR/spec" \
  --hidden-import app.main \
  --collect-all uvicorn \
  --add-data "$ROOT/static:static" \
  --add-data "$ROOT/data/demo_places.json:data" \
  --add-data "$ROOT/data/tolls:data/tolls" \
  "$ROOT/desktop/backend_entry.py"

npm --prefix desktop install --no-audit --no-fund
rm -rf "$DIST_DIR"
npm --prefix desktop run dist:linux

echo
echo "Build Linux terminé :"
find "$DIST_DIR" -maxdepth 1 -type f -printf '  %p\n' | sort

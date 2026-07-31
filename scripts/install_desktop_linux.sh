#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APPIMAGE="${1:-}"

if [[ -z "$APPIMAGE" ]]; then
  APPIMAGE="$(find "$ROOT/dist/desktop" -maxdepth 1 -type f -name '*.AppImage' -print -quit)"
fi
[[ -n "$APPIMAGE" && -f "$APPIMAGE" ]] || { echo "AppImage Détour introuvable." >&2; exit 1; }

INSTALL_DIR="$HOME/Applications"
APP_TARGET="$INSTALL_DIR/Detour.AppImage"
WRAPPER="$INSTALL_DIR/Detour"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
DESKTOP_DIR="$HOME/.local/share/applications"

mkdir -p "$INSTALL_DIR" "$ICON_DIR" "$DESKTOP_DIR"
install -m 0755 "$APPIMAGE" "$APP_TARGET"
install -m 0644 "$ROOT/desktop/assets/icon.png" "$ICON_DIR/detour.png"

cat > "$WRAPPER" <<'EOF'
#!/usr/bin/env bash
set -e
APP="$HOME/Applications/Detour.AppImage"
if "$APP" "$@"; then
  exit 0
fi
exec "$APP" --appimage-extract-and-run "$@"
EOF
chmod 0755 "$WRAPPER"

cat > "$DESKTOP_DIR/detour.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Détour
Comment=Le bon détour, au bon prix
Exec=$WRAPPER
Icon=detour
Terminal=false
Categories=Utility;Maps;
StartupWMClass=Détour
EOF
chmod 0644 "$DESKTOP_DIR/detour.desktop"

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true

echo "Détour installé : $APP_TARGET"
echo "Lanceur menu : $DESKTOP_DIR/detour.desktop"

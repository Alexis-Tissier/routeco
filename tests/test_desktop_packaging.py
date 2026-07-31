from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_desktop_package_has_two_linux_targets() -> None:
    package = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
    assert package["build"]["productName"] == "Détour"
    assert package["build"]["linux"]["target"] == ["AppImage", "tar.gz"]
    assert package["build"]["appId"] == "fr.alexistissier.detour"


def test_desktop_downloads_verified_france_release() -> None:
    main = (ROOT / "desktop/main.cjs").read_text(encoding="utf-8")
    backend = (ROOT / "desktop/backend_entry.py").read_text(encoding="utf-8")
    assert "Alexis-Tissier/detour/releases/download/data-france-v1" in main
    assert "sha256_file" in backend
    assert "safe_extract" in backend
    assert "current-france.json" in main


def test_linux_build_bundles_python_java_and_graphhopper() -> None:
    script = (ROOT / "scripts/build_desktop_linux.sh").read_text(encoding="utf-8")
    package = json.loads((ROOT / "desktop/package.json").read_text(encoding="utf-8"))
    assert "PyInstaller" in script
    assert "api.adoptium.net" in script
    assert "graphhopper-web-${GRAPHHOPPER_VERSION}.jar" in script
    destinations = {entry["to"] for entry in package["build"]["extraResources"]}
    assert "backend" in destinations
    assert "jre" in destinations
    assert "graphhopper/graphhopper-web-11.0.jar" in destinations


def test_linux_installer_creates_menu_launcher() -> None:
    script = (ROOT / "scripts/install_desktop_linux.sh").read_text(encoding="utf-8")
    assert "Detour.AppImage" in script
    assert ".local/share/applications" in script
    assert "detour.desktop" in script
    assert "--appimage-extract-and-run" in script

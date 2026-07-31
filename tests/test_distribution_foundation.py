from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_leaflet_zoom_no_longer_overlaps_route_title() -> None:
    content = Path("static/map-adapter.js").read_text(encoding="utf-8")
    assert "zoomControl: false" in content
    assert "L.control.zoom({ position: 'bottomleft' }).addTo(map);" in content


def test_data_release_can_be_built_and_installed_locally(tmp_path: Path) -> None:
    builder = load_module("build_data_release", "scripts/build_data_release.py")
    installer = load_module("install_release_data", "scripts/install_release_data.py")

    graph = tmp_path / "graph-cache"
    graph.mkdir()
    (graph / "nodes").write_bytes(b"graph")
    ban = tmp_path / "ban.sqlite"
    ban.write_bytes(b"ban")
    communes = tmp_path / "communes.sqlite"
    communes.write_bytes(b"communes")

    manifest_path = builder.build_release(
        version="test",
        output_dir=tmp_path / "dist",
        graph_cache=graph,
        ban_db=ban,
        communes_db=communes,
        chunk_mib=1,
    )
    destination = installer.install_from_manifest(
        str(manifest_path),
        data_root=tmp_path / "installed",
        cache_dir=tmp_path / "downloads",
    )
    assert (destination / "graph-cache/nodes").read_bytes() == b"graph"
    assert (destination / "ban.sqlite").read_bytes() == b"ban"
    assert (destination / "communes.sqlite").read_bytes() == b"communes"


def test_download_site_contains_domain_release_links_and_capture() -> None:
    assert Path("site/CNAME").read_text(encoding="utf-8").strip() == ("detour.alexis-tissier.fr")
    html = Path("site/index.html").read_text(encoding="utf-8")
    assert "github.com/Alexis-Tissier/detour/releases/latest" in html
    assert "assets/detour-app.webp" in html
    assert "<strong>Détour</strong>" in html
    assert "<small>Optimiseur de trajet</small>" in html
    assert "assets/detour-logo.svg" in html
    assert Path("site/assets/detour-app.webp").stat().st_size > 100_000
    manifest = json.loads(Path("site/manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["name"] == "Détour"

from __future__ import annotations

import importlib.util
from pathlib import Path


def load_module(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_full_data_release_verifier_accepts_tiny_pack(tmp_path: Path) -> None:
    builder = load_module("build_data_release_v32", "scripts/build_data_release.py")
    pipeline = load_module("prepare_data_release_v32", "scripts/prepare_data_release.py")

    graph = tmp_path / "graph-cache"
    graph.mkdir()
    (graph / "nodes").write_bytes(b"graph")
    ban = tmp_path / "ban.sqlite"
    ban.write_bytes(b"ban")
    communes = tmp_path / "communes.sqlite"
    communes.write_bytes(b"communes")

    manifest = builder.build_release(
        version="test",
        output_dir=tmp_path / "dist",
        graph_cache=graph,
        ban_db=ban,
        communes_db=communes,
        chunk_mib=1,
    )
    assert pipeline.verify_release_dir(manifest.parent) == manifest


def test_data_release_is_never_marked_as_latest_application_release() -> None:
    content = Path("scripts/publish_data_release.sh").read_text(encoding="utf-8")
    assert "--latest=false" in content
    assert "MAX_ASSET_BYTES" in content
    assert "--target" in content

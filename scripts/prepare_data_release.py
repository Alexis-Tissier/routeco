#!/usr/bin/env python3
"""Construit, vérifie et publie un pack de données France pour Détour."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from types import ModuleType
from typing import Any

GIB = 1024**3
REQUIRED_ARCHIVE_ENTRIES = {"ban.sqlite", "communes.sqlite"}


def load_builder() -> ModuleType:
    path = Path(__file__).with_name("build_data_release.py")
    spec = importlib.util.spec_from_file_location("detour_build_data_release", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Impossible de charger {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, text=True, check=check)


def verify_release_dir(release_dir: Path) -> Path:
    manifests = sorted(release_dir.glob("detour-data-france-v*.json"))
    if len(manifests) != 1:
        raise RuntimeError(
            f"Un seul manifest attendu dans {release_dir}, {len(manifests)} trouvé(s)."
        )
    manifest_path = manifests[0]
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    parts = manifest.get("parts", [])
    if not parts:
        raise RuntimeError("Le manifest ne contient aucune partie.")

    for index, part in enumerate(parts, start=1):
        path = release_dir / str(part["name"])
        print(f"Vérification [{index}/{len(parts)}] {path.name}")
        if not path.is_file():
            raise FileNotFoundError(path)
        if path.stat().st_size != int(part["size"]):
            raise RuntimeError(f"Taille incorrecte : {path.name}")
        if sha256_file(path) != str(part["sha256"]):
            raise RuntimeError(f"SHA-256 incorrect : {path.name}")

    with tempfile.NamedTemporaryFile(
        prefix="detour-data-verify-",
        suffix=".zip",
        dir=release_dir,
        delete=False,
    ) as output:
        archive_path = Path(output.name)
        for part in parts:
            with (release_dir / str(part["name"])).open("rb") as source:
                shutil.copyfileobj(source, output, length=8 * 1024 * 1024)

    try:
        archive = manifest["archive"]
        if archive_path.stat().st_size != int(archive["size"]):
            raise RuntimeError("Taille incorrecte pour l'archive reconstituée.")
        if sha256_file(archive_path) != str(archive["sha256"]):
            raise RuntimeError("SHA-256 incorrect pour l'archive reconstituée.")
        with zipfile.ZipFile(archive_path) as zipped:
            bad_member = zipped.testzip()
            if bad_member is not None:
                raise RuntimeError(f"Entrée ZIP corrompue : {bad_member}")
            names = set(zipped.namelist())
            missing = REQUIRED_ARCHIVE_ENTRIES - names
            if missing:
                raise RuntimeError(f"Entrées obligatoires absentes : {sorted(missing)}")
            if not any(name.startswith("graph-cache/") for name in names):
                raise RuntimeError("Le graphe GraphHopper est absent de l'archive.")
    finally:
        archive_path.unlink(missing_ok=True)

    checksums = release_dir / "SHA256SUMS"
    if not checksums.is_file():
        raise RuntimeError("SHA256SUMS est absent.")
    print(f"Pack local validé : {release_dir}")
    return manifest_path


def source_paths(builder: ModuleType) -> tuple[Path, Path, Path]:
    values = builder.parse_env(Path(".env"))
    graph_cache = Path("data/graph-cache")
    ban_db = Path(values.get("ROUTECO_BAN_DB", "data/ban.sqlite"))
    communes_db = Path(values.get("ROUTECO_COMMUNES_DB", "data/communes.sqlite"))
    return graph_cache, ban_db, communes_db


def required_workspace(paths: tuple[Path, Path, Path]) -> int:
    total = 0
    for path in paths:
        if path.is_dir():
            total += sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
        elif path.is_file():
            total += path.stat().st_size
    return max(8 * GIB, int(total * 2.2))


def verify_remote_manifest(tag: str, local_manifest: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="detour-release-check-") as temp:
        destination = Path(temp)
        run(
            [
                "gh",
                "release",
                "download",
                tag,
                "--pattern",
                local_manifest.name,
                "--dir",
                str(destination),
            ]
        )
        remote = destination / local_manifest.name
        if sha256_file(remote) != sha256_file(local_manifest):
            raise RuntimeError("Le manifest publié ne correspond pas au manifest local.")
    print("Manifest GitHub vérifié.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="1")
    parser.add_argument("--output", type=Path, default=Path("dist/data-release"))
    parser.add_argument("--chunk-mib", type=int, default=1900)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    builder = load_builder()
    graph_cache, ban_db, communes_db = source_paths(builder)
    paths = (graph_cache, ban_db, communes_db)
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise FileNotFoundError("Données absentes :\n- " + "\n- ".join(missing))

    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    release_dir = output / f"data-france-v{args.version}"
    manifest_path = release_dir / f"detour-data-france-v{args.version}.json"

    needed = required_workspace(paths)
    available = shutil.disk_usage(output).free
    print(f"Espace estimé nécessaire : {needed / GIB:.1f} Gio")
    print(f"Espace disponible         : {available / GIB:.1f} Gio")
    if available < needed:
        raise RuntimeError("Espace disque insuffisant pour construire et vérifier le pack.")

    if args.rebuild or not manifest_path.exists():
        manifest_path = builder.build_release(
            version=str(args.version),
            output_dir=output,
            graph_cache=graph_cache,
            ban_db=ban_db,
            communes_db=communes_db,
            chunk_mib=args.chunk_mib,
        )
    else:
        print(f"Réutilisation du pack existant : {release_dir}")

    manifest_path = verify_release_dir(release_dir)

    if args.publish:
        run(["gh", "auth", "status"])
        run(["bash", "scripts/publish_data_release.sh", str(release_dir)])
        tag = f"data-france-v{args.version}"
        verify_remote_manifest(tag, manifest_path)

    print("Préparation des données terminée.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

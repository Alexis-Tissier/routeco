#!/usr/bin/env python3
"""Télécharge, vérifie et installe un pack de données Détour."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def default_data_root() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local"))
        return root / "Detour"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Detour"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "detour"


def read_manifest(location: str) -> tuple[dict[str, Any], str]:
    parsed = urllib.parse.urlparse(location)
    if parsed.scheme in {"http", "https"}:
        with urllib.request.urlopen(location) as response:
            data = response.read()
        return json.loads(data), location
    path = Path(location).expanduser().resolve()
    return json.loads(path.read_text(encoding="utf-8")), path.as_uri()


def download_with_resume(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = destination.stat().st_size if destination.exists() else 0
    headers = {"User-Agent": "DetourDataInstaller/0.4.5"}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request)
    except Exception:
        if existing:
            destination.unlink(missing_ok=True)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": "DetourDataInstaller/0.4.5"},
            )
            response = urllib.request.urlopen(request)
        else:
            raise
    status = getattr(response, "status", 200)
    mode = "ab" if existing and status == 206 else "wb"
    with response, destination.open(mode) as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    destination_resolved = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if destination_resolved not in target.parents and target != destination_resolved:
            raise RuntimeError(f"Chemin dangereux dans l'archive : {member.filename}")
    archive.extractall(destination)


def install_from_manifest(
    manifest_location: str,
    *,
    data_root: Path,
    cache_dir: Path | None = None,
) -> Path:
    manifest, manifest_url = read_manifest(manifest_location)
    version = str(manifest["version"])
    parts = manifest["parts"]
    cache = cache_dir or data_root / "downloads" / f"france-v{version}"
    cache.mkdir(parents=True, exist_ok=True)

    for index, part in enumerate(parts, start=1):
        name = part["name"]
        url = urllib.parse.urljoin(manifest_url, name)
        destination = cache / name
        print(f"[{index}/{len(parts)}] {name}")
        download_with_resume(url, destination)
        if destination.stat().st_size != int(part["size"]):
            raise RuntimeError(f"Taille incorrecte : {name}")
        if sha256_file(destination) != part["sha256"]:
            raise RuntimeError(f"Somme SHA-256 incorrecte : {name}")

    archive_path = cache / manifest["archive"]["name"]
    with archive_path.open("wb") as output:
        for part in parts:
            with (cache / part["name"]).open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)
    if sha256_file(archive_path) != manifest["archive"]["sha256"]:
        raise RuntimeError("Somme SHA-256 incorrecte pour l'archive reconstituée.")

    packs_root = data_root / "packs"
    packs_root.mkdir(parents=True, exist_ok=True)
    destination = packs_root / f"france-v{version}"
    staging = packs_root / f".france-v{version}.staging"
    backup = packs_root / f".france-v{version}.backup"
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir(parents=True)

    with zipfile.ZipFile(archive_path) as archive:
        safe_extract(archive, staging)

    if destination.exists():
        destination.rename(backup)
    staging.rename(destination)
    shutil.rmtree(backup, ignore_errors=True)

    pointer = {
        "dataset": "france",
        "version": version,
        "path": str(destination),
        "manifest": manifest_location,
    }
    (data_root / "current-france.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Données installées : {destination}")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--data-root", type=Path, default=default_data_root())
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    install_from_manifest(
        args.manifest,
        data_root=args.data_root.expanduser(),
        cache_dir=args.cache_dir.expanduser() if args.cache_dir else None,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

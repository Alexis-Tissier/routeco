#!/usr/bin/env python3
"""Construit un pack de données Détour fractionné pour GitHub Releases."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_CHUNK_MIB = 1900


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def iter_files(sources: Iterable[tuple[Path, str]]) -> Iterable[tuple[Path, str]]:
    for source, archive_name in sources:
        if source.is_dir():
            for item in sorted(source.rglob("*")):
                if item.is_file():
                    relative = item.relative_to(source).as_posix()
                    yield item, f"{archive_name.rstrip('/')}/{relative}"
        else:
            yield source, archive_name


def split_file(source: Path, output_prefix: Path, chunk_size: int) -> list[Path]:
    parts: list[Path] = []
    with source.open("rb") as stream:
        index = 1
        while stream.tell() < source.stat().st_size:
            part = Path(f"{output_prefix}.part{index:03d}")
            remaining = chunk_size
            with part.open("wb") as output:
                while remaining > 0:
                    block = stream.read(min(8 * 1024 * 1024, remaining))
                    if not block:
                        break
                    output.write(block)
                    remaining -= len(block)
            if part.stat().st_size == 0:
                part.unlink(missing_ok=True)
                break
            parts.append(part)
            index += 1
    return parts


def build_release(
    *,
    version: str,
    output_dir: Path,
    graph_cache: Path,
    ban_db: Path,
    communes_db: Path,
    chunk_mib: int = DEFAULT_CHUNK_MIB,
) -> Path:
    required = {
        "graphe GraphHopper": graph_cache,
        "base BAN": ban_db,
        "base des communes": communes_db,
    }
    missing = [f"{label}: {path}" for label, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Données absentes :\n- " + "\n- ".join(missing))

    release_dir = output_dir / f"data-france-v{version}"
    if release_dir.exists():
        shutil.rmtree(release_dir)
    release_dir.mkdir(parents=True)

    archive_name = f"detour-data-france-v{version}.zip"
    archive_path = release_dir / archive_name
    sources = [
        (graph_cache, "graph-cache"),
        (ban_db, "ban.sqlite"),
        (communes_db, "communes.sqlite"),
    ]

    uncompressed_size = (
        directory_size(graph_cache) + ban_db.stat().st_size + communes_db.stat().st_size
    )
    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=6,
        allowZip64=True,
    ) as archive:
        for source, archive_member in iter_files(sources):
            archive.write(source, archive_member)

    archive_sha = sha256_file(archive_path)
    parts = split_file(
        archive_path,
        release_dir / archive_name,
        chunk_mib * 1024 * 1024,
    )
    archive_path.unlink()

    manifest = {
        "schema": 1,
        "product": "Détour",
        "dataset": "france",
        "version": str(version),
        "created_at": datetime.now(UTC).isoformat(),
        "archive": {
            "name": archive_name,
            "sha256": archive_sha,
            "size": sum(part.stat().st_size for part in parts),
            "uncompressed_size": uncompressed_size,
            "format": "zip",
        },
        "parts": [
            {
                "name": part.name,
                "size": part.stat().st_size,
                "sha256": sha256_file(part),
            }
            for part in parts
        ],
        "layout": {
            "graph_cache": "graph-cache",
            "ban_db": "ban.sqlite",
            "communes_db": "communes.sqlite",
        },
    }
    manifest_path = release_dir / f"detour-data-france-v{version}.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksums = release_dir / "SHA256SUMS"
    checksums.write_text(
        "\n".join(
            [f"{sha256_file(manifest_path)}  {manifest_path.name}"]
            + [f"{sha256_file(part)}  {part.name}" for part in parts]
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Pack créé : {release_dir}")
    print(f"Parties : {len(parts)}")
    print(f"Taille compressée : {manifest['archive']['size'] / 1024**3:.2f} Gio")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, default=Path("dist/data-release"))
    parser.add_argument("--graph-cache", type=Path, default=Path("data/graph-cache"))
    parser.add_argument("--ban-db", type=Path)
    parser.add_argument("--communes-db", type=Path)
    parser.add_argument("--chunk-mib", type=int, default=DEFAULT_CHUNK_MIB)
    args = parser.parse_args()

    env_values = parse_env(Path(".env"))
    ban_db = args.ban_db or Path(env_values.get("ROUTECO_BAN_DB", "data/ban.sqlite"))
    communes_db = args.communes_db or Path(
        env_values.get("ROUTECO_COMMUNES_DB", "data/communes.sqlite")
    )
    build_release(
        version=args.version,
        output_dir=args.output,
        graph_cache=args.graph_cache,
        ban_db=ban_db,
        communes_db=communes_db,
        chunk_mib=args.chunk_mib,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

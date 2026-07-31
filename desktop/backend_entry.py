from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

APP_VERSION = "0.4.7"


def emit(event: str, **payload: Any) -> None:
    print(
        "DETOUR_EVENT "
        + json.dumps({"event": event, **payload}, ensure_ascii=False, separators=(",", ":")),
        flush=True,
    )


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(block_size):
            digest.update(chunk)
    return digest.hexdigest()


def request(url: str, *, headers: dict[str, str] | None = None):
    merged = {"User-Agent": f"DetourDesktop/{APP_VERSION}", **(headers or {})}
    return urllib.request.urlopen(urllib.request.Request(url, headers=merged), timeout=120)


def download_part(url: str, destination: Path, expected_size: int, index: int, count: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    existing = destination.stat().st_size if destination.exists() else 0
    if existing > expected_size:
        destination.unlink()
        existing = 0

    try:
        response = request(url, headers={"Range": f"bytes={existing}-"} if existing else None)
    except Exception:
        if not existing:
            raise
        destination.unlink(missing_ok=True)
        existing = 0
        response = request(url)

    status = getattr(response, "status", 200)
    append = bool(existing and status == 206)
    if not append:
        existing = 0
    downloaded = existing
    mode = "ab" if append else "wb"

    with response, destination.open(mode) as output:
        while True:
            block = response.read(1024 * 1024)
            if not block:
                break
            output.write(block)
            downloaded += len(block)
            emit(
                "download",
                part=index,
                parts=count,
                name=destination.name,
                downloaded=downloaded,
                total=expected_size,
                percent=round(downloaded / expected_size * 100, 1),
            )

    if destination.stat().st_size != expected_size:
        raise RuntimeError(f"Taille incorrecte : {destination.name}")


def safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    members = archive.infolist()
    for index, member in enumerate(members, start=1):
        target = (destination / member.filename).resolve()
        if root not in target.parents and target != root:
            raise RuntimeError(f"Chemin dangereux : {member.filename}")
        archive.extract(member, destination)
        if index % 250 == 0 or index == len(members):
            emit("extract", current=index, total=len(members))


def installed_pack(data_root: Path) -> Path | None:
    pointer_path = data_root / "current-france.json"
    if not pointer_path.exists():
        return None
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
        pack = Path(pointer["path"])
    except (KeyError, OSError, TypeError, ValueError):
        return None
    required = (pack / "graph-cache", pack / "ban.sqlite", pack / "communes.sqlite")
    return pack if all(item.exists() for item in required) else None


def install_data(manifest_url: str, data_root: Path) -> Path:
    current = installed_pack(data_root)
    if current:
        emit("ready", path=str(current), reused=True)
        return current

    data_root.mkdir(parents=True, exist_ok=True)
    emit("manifest")
    with request(manifest_url) as response:
        manifest = json.loads(response.read())

    version = str(manifest["version"])
    parts = manifest["parts"]
    base_url = manifest_url.rsplit("/", 1)[0] + "/"
    cache = data_root / "downloads" / f"france-v{version}"
    cache.mkdir(parents=True, exist_ok=True)

    for index, part in enumerate(parts, start=1):
        name = str(part["name"])
        destination = cache / name
        download_part(
            urllib.parse.urljoin(base_url, name),
            destination,
            int(part["size"]),
            index,
            len(parts),
        )
        emit("verify-part", name=name)
        if sha256_file(destination) != str(part["sha256"]):
            destination.unlink(missing_ok=True)
            raise RuntimeError(f"Somme SHA-256 incorrecte : {name}")

    archive_path = cache / str(manifest["archive"]["name"])
    emit("assemble")
    with archive_path.open("wb") as output:
        for part in parts:
            with (cache / str(part["name"])).open("rb") as source:
                shutil.copyfileobj(source, output, length=1024 * 1024)

    emit("verify-archive")
    if sha256_file(archive_path) != str(manifest["archive"]["sha256"]):
        raise RuntimeError("Somme SHA-256 incorrecte pour l'archive.")

    packs_root = data_root / "packs"
    destination = packs_root / f"france-v{version}"
    staging = packs_root / f".france-v{version}.staging"
    backup = packs_root / f".france-v{version}.backup"
    packs_root.mkdir(parents=True, exist_ok=True)
    shutil.rmtree(staging, ignore_errors=True)
    shutil.rmtree(backup, ignore_errors=True)
    staging.mkdir(parents=True)

    emit("extract-start")
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
        "manifest": manifest_url,
    }
    (data_root / "current-france.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    emit("ready", path=str(destination), reused=False)
    return destination


def serve(args: argparse.Namespace) -> int:
    os.environ["ROUTECO_DATA_DIR"] = str(args.data_dir)
    os.environ["ROUTECO_BAN_DB"] = str(args.data_dir / "ban.sqlite")
    os.environ["ROUTECO_COMMUNES_DB"] = str(args.data_dir / "communes.sqlite")
    os.environ["GRAPHHOPPER_URL"] = args.graphhopper_url

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        log_level="info",
        access_log=False,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="detour-backend")
    parser.add_argument("--version", action="version", version=APP_VERSION)
    subs = parser.add_subparsers(dest="command", required=True)

    install = subs.add_parser("install-data")
    install.add_argument("--manifest-url", required=True)
    install.add_argument("--data-root", type=Path, required=True)

    serve_parser = subs.add_parser("serve")
    serve_parser.add_argument("--data-dir", type=Path, required=True)
    serve_parser.add_argument("--graphhopper-url", default="http://127.0.0.1:8989")

    args = parser.parse_args()
    if args.command == "install-data":
        install_data(args.manifest_url, args.data_root.expanduser().resolve())
        return 0
    return serve(args)


if __name__ == "__main__":
    raise SystemExit(main())

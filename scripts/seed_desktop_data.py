from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def link_or_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() or destination.exists():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()
    try:
        destination.symlink_to(source.resolve(), target_is_directory=source.is_dir())
    except OSError:
        if source.is_dir():
            shutil.copytree(source, destination)
        else:
            shutil.copy2(source, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "detour",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    env = parse_env(root / ".env")
    graph = root / "data/graph-cache"
    ban = Path(env.get("ROUTECO_BAN_DB", root / "data/ban.sqlite")).expanduser()
    communes = Path(env.get("ROUTECO_COMMUNES_DB", root / "data/communes.sqlite")).expanduser()
    missing = [str(item) for item in (graph, ban, communes) if not item.exists()]
    if missing:
        raise SystemExit("Données locales absentes :\n- " + "\n- ".join(missing))

    pack = args.data_root.expanduser() / "packs" / "france-v1"
    pack.mkdir(parents=True, exist_ok=True)
    link_or_copy(graph, pack / "graph-cache")
    link_or_copy(ban, pack / "ban.sqlite")
    link_or_copy(communes, pack / "communes.sqlite")
    pointer = {
        "dataset": "france",
        "version": "1",
        "path": str(pack.resolve()),
        "manifest": "local-development-seed",
    }
    args.data_root.mkdir(parents=True, exist_ok=True)
    (args.data_root / "current-france.json").write_text(
        json.dumps(pointer, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Données desktop locales prêtes : {pack}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

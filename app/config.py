from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _path_from_env(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    return Path(value).expanduser().resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    static_dir: Path
    data_dir: Path
    demo_places: Path
    ban_database: Path
    tolls_dir: Path
    reports_dir: Path
    graphhopper_url: str
    map_style_url: str | None


def load_settings() -> Settings:
    data_dir = _path_from_env("ROUTECO_DATA_DIR", ROOT / "data")
    ban_database = _path_from_env("ROUTECO_BAN_DB", data_dir / "ban.sqlite")
    tolls_dir = _path_from_env("ROUTECO_TOLLS_DIR", data_dir / "tolls")
    reports_dir = _path_from_env("ROUTECO_REPORTS_DIR", data_dir / "reports")
    map_style_url = os.getenv("ROUTECO_MAP_STYLE_URL", "").strip() or None

    return Settings(
        root=ROOT,
        static_dir=ROOT / "static",
        data_dir=data_dir,
        demo_places=ROOT / "data" / "demo_places.json",
        ban_database=ban_database,
        tolls_dir=tolls_dir,
        reports_dir=reports_dir,
        graphhopper_url=os.getenv("GRAPHHOPPER_URL", "http://127.0.0.1:8989").rstrip("/"),
        map_style_url=map_style_url,
    )


settings = load_settings()

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _bounded_int_from_env(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw = os.getenv(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _bounded_float_from_env(
    name: str,
    default: float,
    *,
    minimum: float,
    maximum: float,
) -> float:
    raw = os.getenv(name, "").strip().replace(",", ".")
    try:
        value = float(raw) if raw else default
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


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
    communes_database: Path
    tolls_dir: Path
    reports_dir: Path
    graphhopper_url: str
    map_style_url: str | None
    routing_cache_ttl_seconds: int
    routing_cache_max_entries: int
    max_concurrent_calculations: int
    toll_estimate_eur_per_km: float


def load_settings() -> Settings:
    data_dir = _path_from_env("ROUTECO_DATA_DIR", ROOT / "data")
    ban_database = _path_from_env("ROUTECO_BAN_DB", data_dir / "ban.sqlite")
    communes_database = _path_from_env("ROUTECO_COMMUNES_DB", data_dir / "communes.sqlite")
    tolls_dir = _path_from_env("ROUTECO_TOLLS_DIR", data_dir / "tolls")
    reports_dir = _path_from_env("ROUTECO_REPORTS_DIR", data_dir / "reports")
    map_style_url = os.getenv("ROUTECO_MAP_STYLE_URL", "").strip() or None

    return Settings(
        root=ROOT,
        static_dir=ROOT / "static",
        data_dir=data_dir,
        demo_places=ROOT / "data" / "demo_places.json",
        ban_database=ban_database,
        communes_database=communes_database,
        tolls_dir=tolls_dir,
        reports_dir=reports_dir,
        graphhopper_url=os.getenv("GRAPHHOPPER_URL", "http://127.0.0.1:8989").rstrip("/"),
        map_style_url=map_style_url,
        routing_cache_ttl_seconds=_bounded_int_from_env(
            "ROUTECO_ROUTING_CACHE_TTL",
            1800,
            minimum=0,
            maximum=86400,
        ),
        routing_cache_max_entries=_bounded_int_from_env(
            "ROUTECO_ROUTING_CACHE_ENTRIES",
            8,
            minimum=0,
            maximum=64,
        ),
        max_concurrent_calculations=_bounded_int_from_env(
            "ROUTECO_MAX_CONCURRENT_CALCULATIONS",
            1,
            minimum=1,
            maximum=8,
        ),
        toll_estimate_eur_per_km=_bounded_float_from_env(
            "ROUTECO_TOLL_ESTIMATE_EUR_PER_KM",
            0.105,
            minimum=0.03,
            maximum=0.30,
        ),
    )


settings = load_settings()

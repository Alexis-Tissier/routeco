#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from pathlib import Path


def key_name(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def read_semicolon(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        rows: list[dict[str, str]] = []
        for raw in reader:
            cleaned = {
                str(name).strip().lower(): (value or "").strip()
                for name, value in raw.items()
                if name is not None
            }
            if cleaned and any(cleaned.values()):
                rows.append(cleaned)
        return rows


def find_triplet(source: Path) -> tuple[Path, Path, Path]:
    candidates = [source / "parse", source]
    for base in candidates:
        close = base / "GLOBAL_data_price_close.csv"
        opened = base / "GLOBAL_data_price_open.csv"
        info = base / "GLOBAL_toll_info.csv"
        if close.exists() and opened.exists() and info.exists():
            return close, opened, info
    raise FileNotFoundError(
        "Triplet OpenTollData introuvable : GLOBAL_data_price_close.csv, "
        "GLOBAL_data_price_open.csv et GLOBAL_toll_info.csv."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalise le triplet global OpenTollData.")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/tolls"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    close_path, open_path, info_path = find_triplet(args.source)

    info_rows = read_semicolon(info_path)
    operator_by_name: dict[str, str] = {}
    stations: list[dict[str, str]] = []

    for row in info_rows:
        name = row.get("name", "")
        lat = row.get("lat", "")
        lon = row.get("lon", "")
        if not name or not lat or not lon:
            continue
        operator = (row.get("operator_osm") or "UNKNOWN").strip().upper()
        station_type = row.get("type", "close").strip().lower()
        if station_type == "close":
            station_type = "closed"
        operator_by_name.setdefault(key_name(name), operator)
        stations.append(
            {
                "name": name,
                "osm_name": row.get("osm_name", ""),
                "operator_ref": row.get("operator_ref", ""),
                "operator": operator,
                "lat": lat,
                "lon": lon,
                "type": station_type,
                "booth_node_id": row.get("booth_node_id", ""),
                "booth_way_id": row.get("booth_way_id", ""),
            }
        )

    closed: list[dict[str, str]] = []
    for row in read_semicolon(close_path):
        name_from = row.get("name_from", "")
        name_to = row.get("name_to", "")
        price1 = row.get("price1", "")
        if not name_from or not name_to or not price1:
            continue
        operator = (
            operator_by_name.get(key_name(name_from))
            or operator_by_name.get(key_name(name_to))
            or "UNKNOWN"
        )
        closed.append({"operator": operator, **row})

    opened: list[dict[str, str]] = []
    for row in read_semicolon(open_path):
        name = row.get("name", "")
        price1 = row.get("price1", "")
        if not name or not price1:
            continue
        operator = operator_by_name.get(key_name(name), "UNKNOWN")
        opened.append({"operator": operator, **row})

    def write(name: str, records: list[dict[str, str]], fields: list[str]) -> None:
        with (args.output / name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(records)

    write(
        "stations.csv",
        stations,
        [
            "name",
            "osm_name",
            "operator_ref",
            "operator",
            "lat",
            "lon",
            "type",
            "booth_node_id",
            "booth_way_id",
        ],
    )
    write(
        "closed_prices.csv",
        closed,
        ["operator", "name_from", "name_to", "distance", "price1", "price2", "price3", "price4", "price5"],
    )
    write(
        "open_prices.csv",
        opened,
        ["operator", "name", "distance", "price1", "price2", "price3", "price4", "price5"],
    )

    print(f"Stations: {len(stations)}, tarifs fermés: {len(closed)}, tarifs ouverts: {len(opened)}")


if __name__ == "__main__":
    main()

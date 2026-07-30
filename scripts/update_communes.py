#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
import urllib.request
from collections.abc import Iterable
from pathlib import Path
from typing import Any

DEFAULT_URL = (
    "https://geo.api.gouv.fr/communes"
    "?fields=nom,code,codesPostaux,centre,population,codeDepartement"
    "&format=json&geometry=centre"
)


def normalize_location(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def download_communes(url: str = DEFAULT_URL) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Routeco/0.3 (+local municipality index)"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = json.load(response)
    if not isinstance(payload, list):
        raise TypeError("Le référentiel des communes n'est pas une liste JSON.")
    return payload


def commune_row(item: dict[str, Any]) -> tuple | None:
    centre = item.get("centre") or {}
    coordinates = centre.get("coordinates") if isinstance(centre, dict) else None
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    name = str(item.get("nom") or "").strip()
    code = str(item.get("code") or "").strip()
    if not name or not code:
        return None
    postcodes = " ".join(
        sorted({str(value).strip() for value in item.get("codesPostaux", []) if value})
    )
    return (
        code,
        name,
        normalize_location(name),
        postcodes,
        str(item.get("codeDepartement") or "").strip(),
        max(0, int(item.get("population") or 0)),
        float(coordinates[1]),
        float(coordinates[0]),
    )


def build_database(
    records: Iterable[dict[str, Any]],
    output: Path,
    minimum_count: int = 30_000,
) -> int:
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        connection = sqlite3.connect(temporary)
        connection.executescript(
            """
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            CREATE TABLE communes (
              id INTEGER PRIMARY KEY,
              code TEXT NOT NULL,
              name TEXT NOT NULL,
              normalized_name TEXT NOT NULL,
              postcodes TEXT NOT NULL,
              department_code TEXT NOT NULL,
              population INTEGER NOT NULL,
              lat REAL NOT NULL,
              lon REAL NOT NULL
            );
            CREATE UNIQUE INDEX communes_code_coordinates
              ON communes(code, lat, lon);
            CREATE VIRTUAL TABLE communes_fts USING fts5(
              name, normalized_name, postcodes, department_code,
              content='communes', content_rowid='id',
              tokenize='unicode61 remove_diacritics 2'
            );
            """
        )
        rows = [row for item in records if (row := commune_row(item)) is not None]
        connection.executemany(
            """
            INSERT OR IGNORE INTO communes(
              code, name, normalized_name, postcodes, department_code,
              population, lat, lon
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        connection.execute("INSERT INTO communes_fts(communes_fts) VALUES('rebuild')")
        connection.execute("PRAGMA optimize")
        count = connection.execute("SELECT COUNT(*) FROM communes").fetchone()[0]
        connection.commit()
        connection.close()
        if count < minimum_count:
            raise ValueError(
                f"Référentiel incomplet : {count} communes seulement "
                f"({minimum_count} minimum)."
            )
        os.replace(temporary, output)
        return int(count)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Télécharge et indexe toutes les communes françaises."
    )
    parser.add_argument("--output", type=Path, default=Path("data/communes.sqlite"))
    parser.add_argument("--source-file", type=Path)
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()

    if args.source_file:
        records = json.loads(args.source_file.read_text(encoding="utf-8"))
    else:
        print("Téléchargement du référentiel officiel des communes…")
        records = download_communes(args.url)
    count = build_database(records, args.output)
    print(f"{count:,} communes indexées dans {args.output}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import sqlite3
from pathlib import Path


def pick(row: dict[str, str], *names: str) -> str:
    for name in names:
        if row.get(name):
            return row[name].strip()
    return ""


def open_csv(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return path.open("r", encoding="utf-8", newline="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Importe un ou plusieurs CSV BAN dans SQLite FTS5.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/ban.sqlite"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        args.output.unlink()

    connection = sqlite3.connect(args.output)
    connection.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=OFF;
        CREATE TABLE addresses (
          id INTEGER PRIMARY KEY,
          label TEXT NOT NULL,
          city TEXT NOT NULL,
          postcode TEXT NOT NULL,
          lat REAL NOT NULL,
          lon REAL NOT NULL
        );
        CREATE VIRTUAL TABLE addresses_fts USING fts5(
          label, city, postcode, content='addresses', content_rowid='id',
          tokenize='unicode61 remove_diacritics 2'
        );
    """)
    inserted = 0
    for file in args.files:
        print(f"Import de {file}…")
        with open_csv(file) as handle:
            reader = csv.DictReader(handle, delimiter=";")
            if reader.fieldnames and len(reader.fieldnames) == 1:
                handle.seek(0)
                reader = csv.DictReader(handle, delimiter=",")
            batch = []
            for row in reader:
                lat = pick(row, "lat", "latitude", "y")
                lon = pick(row, "lon", "longitude", "x")
                if not lat or not lon:
                    continue
                number = pick(row, "numero", "numéro")
                suffix = pick(row, "rep", "suffixe")
                street = pick(row, "nom_voie", "voie_nom", "nom_complet")
                postcode = pick(row, "code_postal", "code_post")
                city = pick(row, "nom_commune", "commune_nom")
                label = pick(row, "libelle_acheminement", "label")
                if not label:
                    label = " ".join(part for part in [number + suffix, street, postcode, city] if part)
                try:
                    batch.append((label, city, postcode, float(lat), float(lon)))
                except ValueError:
                    continue
                if len(batch) >= 10000:
                    connection.executemany("INSERT INTO addresses(label,city,postcode,lat,lon) VALUES(?,?,?,?,?)", batch)
                    inserted += len(batch)
                    batch.clear()
            if batch:
                connection.executemany("INSERT INTO addresses(label,city,postcode,lat,lon) VALUES(?,?,?,?,?)", batch)
                inserted += len(batch)
            connection.commit()
    connection.execute("INSERT INTO addresses_fts(addresses_fts) VALUES('rebuild')")
    connection.execute("PRAGMA optimize")
    connection.commit()
    connection.close()
    print(f"{inserted:,} adresses importées dans {args.output}")


if __name__ == "__main__":
    main()

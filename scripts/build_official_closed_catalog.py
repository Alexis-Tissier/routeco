#!/usr/bin/env python3
from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OFFICIAL_DIR = ROOT / "data" / "tolls" / "official"
OUTPUT = OFFICIAL_DIR / "dated_closed_tariffs_2026.csv"
EFFECTIVE_FROM = "2026-02-01"
EFFECTIVE_TO = "2027-01-31"

FIELDS = [
    "operator",
    "name_from",
    "name_to",
    "vehicle_class",
    "price",
    "distance",
    "effective_from",
    "effective_to",
    "season_start",
    "season_end",
    "source_id",
]

INPUTS = [
    (
        OFFICIAL_DIR / "closed_prices_aprr_2026.csv",
        "aprr-class1-2026",
    ),
    (
        OFFICIAL_DIR / "closed_prices_sanef_2026.csv",
        "sanef-class1-2026",
    ),
    (
        OFFICIAL_DIR / "closed_prices_sapn_2026.csv",
        "sapn-class1-2026",
    ),
    (
        OFFICIAL_DIR / "closed_prices_area_2026.csv",
        "area-class1-2026",
    ),
    (
        OFFICIAL_DIR / "closed_prices_escota_2026.csv",
        "escota-class1-2026",
    ),
    (
        OFFICIAL_DIR / "closed_prices_aliae_2026.csv",
        "aliae-class1-2026",
    ),
]

EXPECTED_CELLS = {
    (
        "SANEF",
        "PARIS / ROISSY (péage de Chamant)",
        "CAMBRAI N°14",
    ): 14.90,
    (
        "SANEF",
        "PARIS / ROISSY (péage de Chamant)",
        "PÉRONNE / VALLEE DE LA SOMME N°13",
    ): 10.60,
    (
        "SANEF",
        "PÉRONNE / VALLEE DE LA SOMME N°13",
        "CAMBRAI N°14",
    ): 3.40,
    (
        "SAPN",
        "POISSY / ORGEVAL N°7 à MANTES-SUD N°12",
        "HEUDEBOUVILLE N°18",
    ): 5.40,
    (
        "SAPN",
        "POISSY / ORGEVAL N°7 à MANTES-SUD N°12",
        "INCARVILLE N°19 / A154",
    ): 7.50,
    (
        "AREA",
        "AIGUEBELETTE",
        "ST QUENTIN FAL. BARRIERE",
    ): 11.00,
    (
        "AREA",
        "VOREPPE BARRIERE",
        "VOIRON",
    ): 2.50,
    (
        "ESCOTA",
        "SISTERON-NORD",
        "AIX (A51)",
    ): 14.00,
    (
        "ALIAE",
        "LE MONTET OUEST",
        "MOLINET EST",
    ): 4.20,
}


def _price(value: object) -> float:
    return float(str(value or "").strip().replace(",", "."))


def _source_rows(
    path: Path,
    source_id: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8", newline="") as handle:
        for line_number, source in enumerate(
            csv.DictReader(handle),
            start=2,
        ):
            raw_price = str(source.get("price1") or "").strip()
            if not raw_price:
                continue
            try:
                price = _price(raw_price)
            except ValueError as exc:
                raise ValueError(
                    f"{path}:{line_number}: prix classe 1 invalide"
                ) from exc
            rows.append(
                {
                    "operator": str(
                        source.get("operator") or ""
                    ).strip().upper(),
                    "name_from": str(
                        source.get("name_from") or ""
                    ).strip(),
                    "name_to": str(
                        source.get("name_to") or ""
                    ).strip(),
                    "vehicle_class": "1",
                    "price": f"{price:.2f}",
                    "distance": str(
                        source.get("distance") or ""
                    ).strip(),
                    "effective_from": EFFECTIVE_FROM,
                    "effective_to": EFFECTIVE_TO,
                    "season_start": "",
                    "season_end": "",
                    "source_id": source_id,
                }
            )
    return rows


def build() -> int:
    rows: list[dict[str, str]] = []
    for path, source_id in INPUTS:
        rows.extend(_source_rows(path, source_id))

    indexed = {
        (
            row["operator"],
            row["name_from"],
            row["name_to"],
        ): _price(row["price"])
        for row in rows
    }
    for key, expected in EXPECTED_CELLS.items():
        actual = indexed.get(key)
        if actual is None or abs(actual - expected) > 0.001:
            raise ValueError(
                "Cellule officielle absente ou modifiée : "
                f"{key!r}, attendu {expected:.2f}, obtenu {actual!r}"
            )

    rows.sort(
        key=lambda row: (
            row["operator"],
            row["name_from"],
            row["name_to"],
            row["source_id"],
        )
    )
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=FIELDS,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    count = build()
    print(f"{OUTPUT}: {count} cellules classe 1 datées")


if __name__ == "__main__":
    main()

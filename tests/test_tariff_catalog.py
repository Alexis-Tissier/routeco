from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.tariff_catalog import (
    OpenTariffRecord,
    load_open_tariff_records,
    load_tariff_sources,
)
from app.services.tolls import TollPricingService


def test_recurring_seasons_support_calendar_wraparound() -> None:
    winter = OpenTariffRecord(
        operator="TEST",
        name="Alpha",
        vehicle_class=1,
        price=11.3,
        effective_from=date(2026, 2, 1),
        effective_to=date(2027, 1, 31),
        season_start=(9, 16),
        season_end=(6, 14),
        source_id="source",
    )
    summer = OpenTariffRecord(
        operator="TEST",
        name="Alpha",
        vehicle_class=1,
        price=13.8,
        effective_from=date(2026, 2, 1),
        effective_to=date(2027, 1, 31),
        season_start=(6, 15),
        season_end=(9, 15),
        source_id="source",
    )

    assert winter.applies_on(date(2026, 2, 1))
    assert winter.applies_on(date(2026, 12, 1))
    assert not winter.applies_on(date(2026, 7, 30))
    assert summer.applies_on(date(2026, 7, 30))
    assert not summer.applies_on(date(2026, 12, 1))


def _write_service_data(root: Path) -> None:
    official = root / "official"
    official.mkdir(parents=True)

    with (root / "stations.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name", "osm_name", "operator", "lat", "lon", "type"
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "GARES DE PEAGE DE SAINT GERMAIN",
                "osm_name": "Gares de péage de Saint-Germain",
                "operator": "OFFICIAL",
                "lat": "45.0",
                "lon": "0.005",
                "type": "mainline",
            }
        )

    for filename, fields in (
        (
            "closed_prices.csv",
            ["operator", "name_from", "name_to", "distance", "price1"],
        ),
        ("open_prices.csv", ["operator", "name", "distance", "price1"]),
    ):
        with (root / filename).open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            csv.DictWriter(handle, fieldnames=fields).writeheader()

    (official / "tariff_sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "official-2026",
                        "publisher": "Test",
                        "title": "Tarifs",
                        "url": "https://example.test/tarifs",
                        "effective_from": "2026-02-01",
                        "effective_to": "2027-01-31",
                        "retrieved_at": "2026-07-30",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (official / "dated_open_tariffs_2026.csv").write_text(
        "operator,name,vehicle_class,price,effective_from,effective_to,"
        "season_start,season_end,source_id\n"
        "CEVM,GARES DE PEAGE DE SAINT GERMAIN,1,11.30,2026-02-01,"
        "2027-01-31,09-16,06-14,official-2026\n"
        "CEVM,GARES DE PEAGE DE SAINT GERMAIN,1,13.80,2026-02-01,"
        "2027-01-31,06-15,09-15,official-2026\n",
        encoding="utf-8",
    )


def test_service_selects_tariff_for_pricing_date(tmp_path: Path) -> None:
    _write_service_data(tmp_path)
    summer = TollPricingService(tmp_path, pricing_date=date(2026, 7, 30))
    winter = TollPricingService(tmp_path, pricing_date=date(2026, 12, 1))

    summer_station = next(
        station for station in summer.stations if station.system_type == "open"
    )
    winter_station = next(
        station for station in winter.stations if station.system_type == "open"
    )

    assert summer._lookup_open(summer_station) == 13.8
    assert winter._lookup_open(winter_station) == 11.3
    assert summer._lookup_open_source(summer_station) == "official-2026"
    assert summer.ready is True


def test_unknown_source_id_is_rejected(tmp_path: Path) -> None:
    registry = tmp_path / "sources.json"
    registry.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "known",
                        "publisher": "Test",
                        "title": "Tarifs",
                        "url": "https://example.test/tarifs",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    records = tmp_path / "records.csv"
    records.write_text(
        "operator,name,vehicle_class,price,effective_from,effective_to,"
        "season_start,season_end,source_id\n"
        "TEST,ALPHA,1,2.00,2026-01-01,2026-12-31,,,missing\n",
        encoding="utf-8",
    )

    sources = load_tariff_sources([registry])
    with pytest.raises(ValueError, match="source_id inconnu"):
        load_open_tariff_records([records], sources)

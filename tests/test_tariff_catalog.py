from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from app.services.tariff_catalog import (
    ClosedTariffRecord,
    OpenTariffRecord,
    load_closed_tariff_records,
    load_open_tariff_records,
    load_physical_tariff_aliases,
    load_tariff_sources,
)
from app.services.tolls import TollPricingService, TollStation


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


def _write_closed_catalog(
    root: Path,
    *,
    effective_from: str = "2026-02-01",
    effective_to: str = "2027-01-31",
) -> None:
    official = root / "official"
    official.mkdir(parents=True)
    for filename, header in (
        (
            root / "stations.csv",
            "name,osm_name,operator,lat,lon,type\n",
        ),
        (
            root / "closed_prices.csv",
            (
                "operator,name_from,name_to,distance,price1\n"
                "TEST,TARIFF ALPHA,OMEGA,11.0,9.90\n"
            ),
        ),
        (
            root / "open_prices.csv",
            "operator,name,distance,price1\n",
        ),
    ):
        filename.write_text(header, encoding="utf-8")
    (official / "tariff_sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "official-closed",
                        "publisher": "Test",
                        "title": "Matrice officielle",
                        "url": "https://example.test/closed",
                        "effective_from": effective_from,
                        "effective_to": effective_to,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (official / "dated_closed_tariffs_2026.csv").write_text(
        "operator,name_from,name_to,vehicle_class,price,distance,"
        "effective_from,effective_to,season_start,season_end,source_id\n"
        f"TEST,TARIFF ALPHA,OMEGA,1,2.00,34.07,{effective_from},"
        f"{effective_to},,,official-closed\n",
        encoding="utf-8",
    )
    (official / "physical_tariff_aliases.csv").write_text(
        "operator,physical_name,tariff_name,lat,lon,max_distance_km,"
        "source_id\n"
        "TEST,PHYSICAL ALPHA,TARIFF ALPHA,48.0,2.0,0.8,"
        "official-closed\n",
        encoding="utf-8",
    )


def test_closed_tariff_loader_preserves_dates_distance_and_source(
    tmp_path: Path,
) -> None:
    _write_closed_catalog(tmp_path)
    sources = load_tariff_sources(
        [tmp_path / "official" / "tariff_sources.json"]
    )
    records = load_closed_tariff_records(
        [tmp_path / "official" / "dated_closed_tariffs_2026.csv"],
        sources,
    )

    assert records == [
        ClosedTariffRecord(
            operator="TEST",
            name_from="TARIFF ALPHA",
            name_to="OMEGA",
            vehicle_class=1,
            price=2.0,
            distance_km=34.07,
            effective_from=date(2026, 2, 1),
            effective_to=date(2027, 1, 31),
            season_start=None,
            season_end=None,
            source_id="official-closed",
        )
    ]
    assert records[0].applies_on(date(2026, 7, 30))
    assert not records[0].applies_on(date(2028, 1, 1))


def test_applicable_official_closed_cell_beats_legacy_record(
    tmp_path: Path,
) -> None:
    _write_closed_catalog(tmp_path)
    service = TollPricingService(
        tmp_path,
        pricing_date=date(2026, 7, 30),
    )
    entry = TollStation(
        "PHYSICAL ALPHA",
        "OFFICIAL",
        48.0,
        2.0,
        "closed",
    )
    exit_ = TollStation(
        "OMEGA",
        "TEST",
        48.1,
        2.1,
        "closed",
    )

    selected = service._lookup_closed(entry, exit_)

    assert selected is not None
    assert selected.price == 2.0
    assert selected.source_id == "official-closed"


def test_geographic_alias_is_not_applied_to_distant_homonym(
    tmp_path: Path,
) -> None:
    _write_closed_catalog(tmp_path)
    service = TollPricingService(
        tmp_path,
        pricing_date=date(2026, 7, 30),
    )
    nearby = TollStation(
        "PHYSICAL ALPHA",
        "OFFICIAL",
        48.0,
        2.0,
        "closed",
    )
    distant = TollStation(
        "PHYSICAL ALPHA",
        "OFFICIAL",
        43.0,
        7.0,
        "closed",
    )
    exit_ = TollStation(
        "OMEGA",
        "TEST",
        48.1,
        2.1,
        "closed",
    )

    assert service._lookup_closed(nearby, exit_) is not None
    assert service._lookup_closed(distant, exit_) is None


def test_alias_with_unknown_source_is_rejected(tmp_path: Path) -> None:
    _write_closed_catalog(tmp_path)
    sources = load_tariff_sources(
        [tmp_path / "official" / "tariff_sources.json"]
    )
    aliases = tmp_path / "official" / "physical_tariff_aliases.csv"
    aliases.write_text(
        "operator,physical_name,tariff_name,lat,lon,max_distance_km,"
        "source_id\n"
        "TEST,ALPHA,TARIFF ALPHA,48.0,2.0,0.8,missing\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="source_id inconnu"):
        load_physical_tariff_aliases([aliases], sources)


def test_production_catalog_uses_verified_2026_closed_cells() -> None:
    service = TollPricingService(
        Path("data/tolls"),
        pricing_date=date(2026, 7, 30),
    )
    cases = [
        (
            TollStation(
                "Fleury-En-Biere",
                "APRR",
                48.4285335,
                2.5392307,
                "mainline",
            ),
            TollStation(
                "Ury",
                "APRR",
                48.3386468,
                2.5954078,
                "closed",
            ),
            2.0,
            "aprr-class1-2026",
        ),
        (
            TollStation(
                "Vallee de la Somme",
                "OFFICIAL",
                49.8769621,
                2.8398291,
                "closed",
            ),
            TollStation(
                "Fontaine Notre-Dame",
                "OFFICIAL",
                50.1756716,
                3.1921790,
                "closed",
            ),
            3.4,
            "sanef-class1-2026",
        ),
        (
            TollStation(
                "Buchelay",
                "OFFICIAL",
                48.9836349,
                1.6811606,
                "mainline",
            ),
            TollStation(
                "Incarville",
                "OFFICIAL",
                49.2463003,
                1.1836769,
                "mainline",
            ),
            7.5,
            "sapn-class1-2026",
        ),
        (
            TollStation(
                "Saint Quentin Fallavier Barriere",
                "OFFICIAL",
                45.6545711,
                5.0946733,
                "mainline",
            ),
            TollStation(
                "Aiguebelette",
                "AREA",
                45.5,
                5.7,
                "closed",
            ),
            11.0,
            "area-class1-2026",
        ),
        (
            TollStation(
                "Sisteron Nord",
                "OFFICIAL",
                44.2233057,
                5.9159940,
                "closed",
            ),
            TollStation(
                "Meyrargues",
                "OFFICIAL",
                43.6613054,
                5.5035341,
                "mainline",
            ),
            14.0,
            "escota-class1-2026",
        ),
        (
            TollStation(
                "LE MONTET OUEST",
                "ALIAE",
                46.3891633,
                3.0331607,
                "mainline",
            ),
            TollStation(
                "MOLINET EST",
                "ALIAE",
                46.4632386,
                3.9773172,
                "mainline",
            ),
            4.2,
            "aliae-class1-2026",
        ),
    ]

    for entry, exit_, price, source_id in cases:
        selected = service._lookup_closed(entry, exit_)
        assert selected is not None
        assert selected.price == price
        assert selected.source_id == source_id


def test_production_catalog_prices_a79_full_free_flow_crossing() -> None:
    service = TollPricingService(
        Path("data/tolls"),
        pricing_date=date(2026, 7, 30),
    )
    geometry = [
        [3.0331607, 46.3891633],
        [3.1072282, 46.4173525],
        [3.4261736, 46.5043758],
        [3.4689789, 46.5163715],
        [3.9042445, 46.4562950],
        [3.9773172, 46.4632386],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=45.5,
        toll_ranges=[
            {
                "start_index": 1,
                "end_index": 5,
                "distance_km": 45.5,
            }
        ],
        toll_state_intervals=[
            {
                "start_index": 1,
                "end_index": 5,
                "value": "ALL",
                "class1_status": "toll",
            }
        ],
        street_ref_details=[[0, 5, "A 79"]],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 4.2
    assert quote.stations == [
        "Le Montet Ouest",
        "Molinet Est",
    ]


def test_production_catalog_prices_a50_mainline_barriers() -> None:
    service = TollPricingService(
        Path("data/tolls"),
        pricing_date=date(2026, 7, 30),
    )
    geometry = [
        [5.80, 43.13],
        [5.7719846, 43.1464186],
        [5.68, 43.18],
        [5.5906781, 43.2051152],
        [5.55, 43.22],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=27.4,
        toll_ranges=[
            {
                "start_index": 0,
                "end_index": 4,
                "distance_km": 27.4,
            }
        ],
        toll_state_intervals=[
            {
                "start_index": 0,
                "end_index": 4,
                "value": "ALL",
                "class1_status": "toll",
            }
        ],
        street_ref_details=[[0, 4, "A 50"]],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 5.2
    assert quote.stations == ["Bandol", "La Ciotat"]

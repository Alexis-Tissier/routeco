from __future__ import annotations

import csv
from pathlib import Path

from app.services.tolls import TollPricingService


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_open_service(
    tmp_path: Path,
    stations: list[dict[str, str]],
    prices: list[dict[str, str]],
) -> TollPricingService:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        stations,
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        prices,
    )
    return TollPricingService(tmp_path)


def test_demo_toll_is_not_reported_as_exact(tmp_path: Path) -> None:
    service = make_open_service(tmp_path, [], [])

    quote = service.quote(
        geometry=[[0.0, 45.0], [0.01, 45.0]],
        tolled_km=0.0,
        demo_toll=12.34,
    )

    assert quote.cost == 12.34
    assert quote.confidence == "estimated"
    assert "synthétique" in quote.message


def test_unpriced_open_event_is_not_ignored_as_osm_noise(tmp_path: Path) -> None:
    service = make_open_service(
        tmp_path,
        [
            {
                "name": "PORTIQUE SANS TARIF",
                "osm_name": "Portique sans tarif",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.005",
                "type": "open",
            }
        ],
        [
            {
                "operator": "TEST",
                "name": "PORTIQUE HORS TRAJET",
                "distance": "",
                "price1": "1.00",
            }
        ],
    )

    assert service.ready is True

    quote = service.quote(
        geometry=[[0.0, 45.0], [0.005, 45.0], [0.01, 45.0]],
        tolled_km=1.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.0}],
        road_class_link_details=[[0, 2, False]],
    )

    assert quote.confidence == "estimated"
    assert quote.confidence != "none"


def test_micro_open_quote_is_downgraded_when_one_event_is_unpriced(
    tmp_path: Path,
) -> None:
    service = make_open_service(
        tmp_path,
        [
            {
                "name": "PORTIQUE TARIFE",
                "osm_name": "Portique tarifé",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.001",
                "type": "open",
            },
            {
                "name": "PORTIQUE SANS TARIF",
                "osm_name": "Portique sans tarif",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.004",
                "type": "open",
            },
        ],
        [
            {
                "operator": "TEST",
                "name": "PORTIQUE TARIFE",
                "distance": "",
                "price1": "2.00",
            }
        ],
    )

    quote = service.quote(
        geometry=[
            [0.0, 45.0],
            [0.001, 45.0],
            [0.004, 45.0],
            [0.005, 45.0],
        ],
        tolled_km=0.4,
        toll_ranges=[{"start_index": 0, "end_index": 3, "distance_km": 0.4}],
        road_class_link_details=[[0, 3, False]],
    )

    assert quote.cost == 2.0
    assert quote.confidence == "estimated"
    assert len(quote.segments) == 1
    assert quote.segments[0].confidence == "exact"

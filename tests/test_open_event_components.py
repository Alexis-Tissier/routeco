from __future__ import annotations

import csv
import json
from datetime import date
from pathlib import Path

from app.services.tolls import (
    ClosedMatch,
    ClosedPrice,
    StationProjection,
    TollPricingService,
    TollRange,
    TollStateInterval,
    TollStation,
)


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _service(
    tmp_path: Path,
    stations: list[dict[str, str]],
    closed: list[dict[str, str]],
    opened: list[dict[str, str]],
) -> TollPricingService:
    _write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        stations,
    )
    _write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        closed,
    )
    _write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        opened,
    )
    return TollPricingService(tmp_path)


def test_distinct_open_event_after_closed_exit_is_not_absorbed(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "NET", "lat": "45.0", "lon": "0.0", "type": "closed"},
            {"name": "EXIT", "osm_name": "Exit", "operator": "NET", "lat": "45.0", "lon": "0.4", "type": "closed"},
            {"name": "AFTER GANTRY", "osm_name": "After Gantry", "operator": "NET", "lat": "45.0", "lon": "0.406", "type": "open"},
        ],
        [{"operator": "NET", "name_from": "ENTRY", "name_to": "EXIT", "distance": "31.5", "price1": "5.00"}],
        [{"operator": "NET", "name": "AFTER GANTRY", "distance": "", "price1": "3.00"}],
    )
    stations = {station.name: station for station in service.stations}
    toll_range = TollRange(0, 3, 0.0, 80.0, 80.0)
    closed = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(5.0, 31.5, "NET"),
        StationProjection(stations["ENTRY"], 0.0, 0.0, 1),
        StationProjection(stations["EXIT"], 31.5, 0.0, 2),
        31.5,
        False,
    )
    gantry = next(
        station
        for station in service.stations
        if station.name == "AFTER GANTRY" and station.system_type == "open"
    )
    assert not service._open_projection_absorbed_by_closed_matches(
        StationProjection(gantry, 32.0, 0.0, 3),
        [closed],
    )


def test_open_twin_of_closed_exit_is_absorbed(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "NET", "lat": "45.0", "lon": "0.0", "type": "closed"},
            {"name": "EXIT", "osm_name": "Exit", "operator": "OFFICIAL", "lat": "45.0", "lon": "0.4", "type": "mainline"},
        ],
        [{"operator": "NET", "name_from": "ENTRY", "name_to": "EXIT", "distance": "31.5", "price1": "5.00"}],
        [{"operator": "NET", "name": "EXIT", "distance": "", "price1": "3.00"}],
    )
    entry = next(station for station in service.stations if station.name == "ENTRY")
    closed_exit = next(station for station in service.stations if station.name == "EXIT" and station.system_type != "open")
    open_exit = next(station for station in service.stations if station.name == "EXIT" and station.system_type == "open")
    toll_range = TollRange(0, 2, 0.0, 40.0, 40.0)
    closed = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(5.0, 31.5, "NET"),
        StationProjection(entry, 0.0, 0.0, 1),
        StationProjection(closed_exit, 31.5, 0.0, 2),
        31.5,
        False,
    )
    assert service._open_projection_absorbed_by_closed_matches(
        StationProjection(open_exit, 31.7, 0.0, 2),
        [closed],
    )


def test_dated_additive_open_event_is_not_absorbed_by_closed_exit(
    tmp_path: Path,
) -> None:
    official = tmp_path / "official"
    official.mkdir()
    _write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "NET", "lat": "45.0", "lon": "0.0", "type": "closed"},
            {"name": "BRIDGE", "osm_name": "Bridge", "operator": "OFFICIAL", "lat": "45.0", "lon": "0.4", "type": "mainline"},
        ],
    )
    _write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [{"operator": "NET", "name_from": "ENTRY", "name_to": "BRIDGE", "distance": "31.5", "price1": "5.00"}],
    )
    _write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )
    (official / "tariff_sources.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "bridge-2026",
                        "publisher": "Test",
                        "title": "Bridge",
                        "url": "https://example.test/bridge",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (official / "dated_open_tariffs_2026.csv").write_text(
        "operator,name,vehicle_class,price,effective_from,effective_to,"
        "season_start,season_end,source_id,additive_to_closed\n"
        "BRIDGE-NET,BRIDGE,1,3.00,2026-01-01,2026-12-31,,,"
        "bridge-2026,true\n",
        encoding="utf-8",
    )
    service = TollPricingService(
        tmp_path,
        pricing_date=date(2026, 7, 30),
    )
    entry = next(
        station for station in service.stations
        if station.name == "ENTRY"
    )
    closed_exit = next(
        station for station in service.stations
        if station.name == "BRIDGE"
        and station.system_type != "open"
    )
    open_exit = next(
        station for station in service.stations
        if station.name == "BRIDGE"
        and station.system_type == "open"
    )
    toll_range = TollRange(0, 2, 0.0, 40.0, 40.0)
    closed = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(5.0, 31.5, "NET"),
        StationProjection(entry, 0.0, 0.0, 1),
        StationProjection(closed_exit, 31.5, 0.0, 2),
        31.5,
        False,
    )

    assert not service._open_projection_absorbed_by_closed_matches(
        StationProjection(open_exit, 31.7, 0.0, 2),
        [closed],
    )


def test_directional_mainline_alias_does_not_block_priced_open_event(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {"name": "PEAGE DE THENON", "osm_name": "Péage de Thenon", "operator": "ASF", "lat": "45.15136", "lon": "1.16759", "type": "open"},
            {"name": "Thenon vers Brives", "osm_name": "Thenon vers Brives", "operator": "OFFICIAL", "lat": "45.15133", "lon": "1.16724", "type": "mainline"},
        ],
        [],
        [{"operator": "ASF", "name": "PEAGE DE THENON", "distance": "", "price1": "8.60"}],
    )
    priced = next(
        station for station in service.stations
        if station.name == "PEAGE DE THENON"
    )
    alias = next(
        station for station in service.stations
        if station.name == "Thenon vers Brives"
    )
    projections = [
        StationProjection(priced, 32.0, 0.01, 1),
        StationProjection(alias, 32.1, 0.01, 1),
    ]

    unresolved = service._unpriced_billing_events_in_range(
        projections,
        TollRange(0, 2, 0.0, 61.2, 61.2),
        [],
        [],
        set(service._station_identity_keys(priced)),
    )

    assert unresolved == []


def test_official_closed_boundary_absorbs_event_free_osm_overhang(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, [], [], [])
    entry_station = TollStation(
        "ENTRY", "NET", 45.0, 0.0, "closed"
    )
    exit_station = TollStation(
        "EXIT", "NET", 45.0, 0.4, "closed"
    )
    toll_range = TollRange(0, 3, 0.0, 35.0, 35.0)
    match = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(
            5.0,
            31.0,
            "NET",
            source_id="official-2026",
        ),
        StationProjection(entry_station, 4.0, 0.0, 1),
        StationProjection(exit_station, 35.0, 0.0, 3),
        31.0,
        False,
    )

    resolved = service._closed_boundary_overhang_spans(
        ranges=[toll_range],
        toll_state_intervals=[
            TollStateInterval(
                0, 3, 0.0, 35.0, 35.0, "ALL", "toll"
            )
        ],
        projections=[],
        accepted_closed=[match],
        road_class_link_details=[],
        used_station_keys=set(),
    )

    assert resolved == [(0.0, 4.0)]


def test_short_osm_fragment_is_absorbed_when_its_event_was_priced(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "name": "PRICED BARRIER",
                "osm_name": "Priced Barrier",
                "operator": "NET",
                "lat": "45.0",
                "lon": "0.0",
                "type": "open",
            }
        ],
        [],
        [
            {
                "operator": "NET",
                "name": "PRICED BARRIER",
                "distance": "",
                "price1": "2.90",
            }
        ],
    )
    station = next(
        item
        for item in service.stations
        if item.name == "PRICED BARRIER"
    )
    projection = StationProjection(
        station,
        19.0,
        0.0,
        1,
    )

    resolved = service._is_non_billable_osm_fragment(
        [projection],
        TollRange(0, 2, 20.0, 25.0, 5.0),
        [],
        [19.0],
        [],
        set(service._station_identity_keys(station)),
    )

    assert resolved is True


def test_short_osm_fragment_keeps_a_distinct_unselected_event(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "name": "USED BARRIER",
                "osm_name": "Used Barrier",
                "operator": "NET",
                "lat": "45.0",
                "lon": "0.0",
                "type": "open",
            },
            {
                "name": "SECOND BARRIER",
                "osm_name": "Second Barrier",
                "operator": "NET",
                "lat": "45.0",
                "lon": "0.1",
                "type": "open",
            },
        ],
        [],
        [
            {
                "operator": "NET",
                "name": "USED BARRIER",
                "distance": "",
                "price1": "2.90",
            },
            {
                "operator": "NET",
                "name": "SECOND BARRIER",
                "distance": "",
                "price1": "1.50",
            },
        ],
    )
    stations = {
        item.name: item
        for item in service.stations
    }
    used = StationProjection(
        stations["USED BARRIER"],
        19.0,
        0.0,
        1,
    )
    second = StationProjection(
        stations["SECOND BARRIER"],
        23.0,
        0.0,
        1,
    )

    resolved = service._is_non_billable_osm_fragment(
        [used, second],
        TollRange(0, 2, 20.0, 25.0, 5.0),
        [],
        [19.0],
        [],
        set(
            service._station_identity_keys(
                stations["USED BARRIER"]
            )
        ),
    )

    assert resolved is False


def test_short_adjacent_fragment_accepts_used_closed_boundary(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, [], [], [])
    boundary = TollStation(
        "BOUNDARY",
        "NET",
        45.0,
        0.0,
        "mainline",
    )
    projection = StationProjection(
        boundary,
        10.0,
        0.0,
        1,
    )

    resolved = service._is_non_billable_osm_fragment(
        [projection],
        TollRange(0, 2, 8.6, 10.0, 1.4),
        [],
        [10.0],
        [],
        set(service._station_identity_keys(boundary)),
    )

    assert resolved is True


def test_open_event_resolves_detailed_residual_component(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "NET", "lat": "45.0", "lon": "0.0", "type": "closed"},
            {"name": "EXIT", "osm_name": "Exit", "operator": "NET", "lat": "45.0", "lon": "0.4", "type": "closed"},
            {"name": "AFTER GANTRY", "osm_name": "After Gantry", "operator": "NET", "lat": "45.0", "lon": "0.406", "type": "open"},
        ],
        [{"operator": "NET", "name_from": "ENTRY", "name_to": "EXIT", "distance": "31.5", "price1": "5.00"}],
        [{"operator": "NET", "name": "AFTER GANTRY", "distance": "", "price1": "3.00"}],
    )
    stations = {station.name: station for station in service.stations}
    gantry = next(station for station in service.stations if station.name == "AFTER GANTRY" and station.system_type == "open")
    toll_range = TollRange(0, 3, 0.0, 80.0, 80.0)
    closed = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(5.0, 31.5, "NET"),
        StationProjection(stations["ENTRY"], 0.0, 0.0, 1),
        StationProjection(stations["EXIT"], 31.5, 0.0, 2),
        31.5,
        False,
    )
    projection = StationProjection(gantry, 32.0, 0.0, 3)
    used_keys: set[str] = set()
    for station in (stations["ENTRY"], stations["EXIT"], gantry):
        used_keys.update(service._station_identity_keys(station))
    resolved = service._open_components_priced_by_events(
        projections=[closed.entry, closed.exit, projection],
        toll_range=toll_range,
        toll_state_intervals=[TollStateInterval(0, 3, 0.0, 80.0, 80.0, "ALL", "toll")],
        accepted_closed=[closed],
        accepted_open=[(projection, 3.0)],
        road_class_link_details=[],
        used_station_keys=used_keys,
    )
    assert resolved == [(31.5, 80.0)]


def test_unpriced_event_prevents_open_component_completion(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            {"name": "PRICED GANTRY", "osm_name": "Priced Gantry", "operator": "NET", "lat": "45.0", "lon": "0.4", "type": "open"},
            {"name": "UNPRICED BARRIER", "osm_name": "Unpriced Barrier", "operator": "NET", "lat": "45.0", "lon": "0.6", "type": "mainline"},
        ],
        [],
        [{"operator": "NET", "name": "PRICED GANTRY", "distance": "", "price1": "3.00"}],
    )
    priced = next(station for station in service.stations if station.name == "PRICED GANTRY" and station.system_type == "open")
    unpriced = next(station for station in service.stations if station.name == "UNPRICED BARRIER")
    priced_projection = StationProjection(priced, 30.0, 0.0, 1)
    unpriced_projection = StationProjection(unpriced, 50.0, 0.0, 2)
    toll_range = TollRange(0, 3, 0.0, 80.0, 80.0)
    resolved = service._open_components_priced_by_events(
        projections=[priced_projection, unpriced_projection],
        toll_range=toll_range,
        toll_state_intervals=[TollStateInterval(0, 3, 0.0, 80.0, 80.0, "ALL", "toll")],
        accepted_closed=[],
        accepted_open=[(priced_projection, 3.0)],
        road_class_link_details=[],
        used_station_keys=set(service._station_identity_keys(priced)),
    )
    assert resolved == []

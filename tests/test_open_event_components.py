from __future__ import annotations

import csv
from pathlib import Path

from app.services.tolls import (
    ClosedMatch,
    ClosedPrice,
    StationProjection,
    TollPricingService,
    TollRange,
    TollStateInterval,
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

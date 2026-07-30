from __future__ import annotations

from app.services.routing import GraphHopperClient
from app.services.tolls import (
    ClosedMatch,
    ClosedPrice,
    StationProjection,
    TollPricingService,
    TollRange,
    TollStateInterval,
    TollStation,
)


def test_detail_intervals_preserve_all_graphhopper_states() -> None:
    geometry = [
        [0.0, 45.0],
        [0.1, 45.0],
        [0.2, 45.0],
        [0.3, 45.0],
        [0.4, 45.0],
    ]
    details = [
        [0, 1, "ALL"],
        [1, 2, "HGV"],
        [2, 3, "NO"],
        [3, 4, "MISSING"],
    ]

    intervals = GraphHopperClient._detail_intervals(
        geometry,
        details,
    )

    assert [item["value"] for item in intervals] == [
        "ALL",
        "HGV",
        "NO",
        "MISSING",
    ]
    assert [item["class1_status"] for item in intervals] == [
        "toll",
        "free",
        "free",
        "unknown",
    ]


def _projection(
    name: str,
    operator: str,
    route_km: float,
) -> StationProjection:
    station = TollStation(
        name=name,
        operator=operator,
        lat=45.0,
        lon=route_km / 100.0,
        system_type="closed",
    )
    return StationProjection(
        station=station,
        route_km=route_km,
        lateral_km=0.0,
        segment_index=1,
    )


def _match(
    toll_range: TollRange,
    entry_name: str,
    exit_name: str,
    operator: str,
    start_km: float,
    end_km: float,
    price: float,
) -> ClosedMatch:
    return ClosedMatch(
        range_index=0,
        toll_range=toll_range,
        record=ClosedPrice(
            price=price,
            distance_km=end_km - start_km,
            operator=operator,
        ),
        entry=_projection(entry_name, operator, start_km),
        exit=_projection(exit_name, operator, end_km),
        coverage_km=end_km - start_km,
        full_range=False,
    )


def test_long_connector_is_allowed_when_graphhopper_proves_free() -> None:
    service = object.__new__(TollPricingService)
    toll_range = TollRange(0, 3, 0.0, 100.0, 100.0)
    matches = [
        _match(toll_range, "ALPHA", "BRAVO", "NET1", 0.0, 30.0, 5.0),
        _match(toll_range, "CHARLIE", "DELTA", "NET2", 45.0, 100.0, 7.0),
    ]
    intervals = [
        TollStateInterval(
            start_index=1,
            end_index=2,
            start_km=30.0,
            end_km=45.0,
            distance_km=15.0,
            value="NO",
            class1_status="free",
        )
    ]

    assert service._closed_chain_has_complete_event_topology(
        matches,
        intervals,
    )


def test_short_connector_is_rejected_when_graphhopper_marks_toll() -> None:
    service = object.__new__(TollPricingService)
    toll_range = TollRange(0, 3, 0.0, 70.0, 70.0)
    matches = [
        _match(toll_range, "ALPHA", "BRAVO", "NET1", 0.0, 30.0, 5.0),
        _match(toll_range, "CHARLIE", "DELTA", "NET2", 33.0, 70.0, 7.0),
    ]
    intervals = [
        TollStateInterval(
            start_index=1,
            end_index=2,
            start_km=30.0,
            end_km=33.0,
            distance_km=3.0,
            value="ALL",
            class1_status="toll",
        )
    ]

    assert not service._closed_chain_has_complete_event_topology(
        matches,
        intervals,
    )


def test_unknown_connector_keeps_temporary_five_km_guard() -> None:
    service = object.__new__(TollPricingService)
    toll_range = TollRange(0, 3, 0.0, 80.0, 80.0)

    short_matches = [
        _match(toll_range, "ALPHA", "BRAVO", "NET1", 0.0, 30.0, 5.0),
        _match(toll_range, "CHARLIE", "DELTA", "NET2", 34.0, 80.0, 7.0),
    ]
    long_matches = [
        _match(toll_range, "ALPHA", "BRAVO", "NET1", 0.0, 30.0, 5.0),
        _match(toll_range, "CHARLIE", "DELTA", "NET2", 40.0, 80.0, 7.0),
    ]

    assert service._closed_chain_has_complete_event_topology(
        short_matches,
        [],
    )
    assert not service._closed_chain_has_complete_event_topology(
        long_matches,
        [],
    )

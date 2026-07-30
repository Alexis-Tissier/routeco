from __future__ import annotations

import csv
from pathlib import Path

from app.services.tolls import (
    ClosedMatch,
    ClosedPrice,
    StationProjection,
    TollPricingService,
    TollRange,
    TollSegmentQuote,
    TollStateInterval,
    TollStation,
)


def _write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _service(
    tmp_path: Path,
    matrices: list[dict[str, str]],
) -> TollPricingService:
    _write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [],
    )
    _write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        matrices,
    )
    _write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )
    return TollPricingService(tmp_path)


def _projection(
    name: str,
    operator: str,
    route_km: float,
    *,
    lon: float,
    lateral_km: float = 0.01,
    system_type: str = "closed",
) -> StationProjection:
    return StationProjection(
        station=TollStation(
            name=name,
            osm_name=name.title(),
            operator=operator,
            lat=45.0,
            lon=lon,
            system_type=system_type,
            physical_type=system_type,
        ),
        route_km=route_km,
        lateral_km=lateral_km,
        segment_index=1,
    )


def _match(
    toll_range: TollRange,
    entry: StationProjection,
    exit_: StationProjection,
    *,
    operator: str = "TEST",
    price: float = 2.0,
) -> ClosedMatch:
    return ClosedMatch(
        range_index=0,
        toll_range=toll_range,
        record=ClosedPrice(
            price=price,
            distance_km=None,
            operator=operator,
        ),
        entry=entry,
        exit=exit_,
        coverage_km=max(
            0.0,
            exit_.route_km - entry.route_km,
        ),
        full_range=False,
    )


def test_equivalent_matrix_aliases_are_one_topology_candidate() -> None:
    service = object.__new__(TollPricingService)
    candidates = [
        {
            "entry": "Fleury-En-Biere",
            "exit": "Ury",
            "route_start_km": 55.6,
            "route_end_km": 66.8,
            "matrix_operator": "APRR",
            "price": 2.0,
            "official_distance_km": 34.07,
            "boundary_gap_km": 3.9,
            "interval_coverage_ratio": 0.741,
            "entry_lateral_km": 0.015,
            "exit_lateral_km": 0.17,
        },
        {
            "entry": "Peage De Fleury En Biere",
            "exit": "Ury",
            "route_start_km": 55.8,
            "route_end_km": 66.8,
            "matrix_operator": "APRR",
            "price": 2.0,
            "official_distance_km": 34.07,
            "boundary_gap_km": 4.1,
            "interval_coverage_ratio": 0.726,
            "entry_lateral_km": 0.046,
            "exit_lateral_km": 0.17,
        },
    ]

    deduped = service._dedupe_equivalent_topology_candidates(
        candidates
    )

    assert len(deduped) == 1
    assert deduped[0]["entry"] == "Fleury-En-Biere"


def test_distinct_entry_names_remain_ambiguous() -> None:
    service = object.__new__(TollPricingService)
    candidates = [
        {
            "entry": "ALPHA",
            "exit": "OMEGA",
            "route_start_km": 10.0,
            "route_end_km": 30.0,
            "matrix_operator": "TEST",
            "price": 2.0,
            "official_distance_km": 20.0,
            "boundary_gap_km": 0.0,
            "interval_coverage_ratio": 1.0,
            "entry_lateral_km": 0.01,
            "exit_lateral_km": 0.01,
        },
        {
            "entry": "BETA",
            "exit": "OMEGA",
            "route_start_km": 10.2,
            "route_end_km": 30.0,
            "matrix_operator": "TEST",
            "price": 2.0,
            "official_distance_km": 20.0,
            "boundary_gap_km": 0.2,
            "interval_coverage_ratio": 0.99,
            "entry_lateral_km": 0.01,
            "exit_lateral_km": 0.01,
        },
    ]

    assert len(
        service._dedupe_equivalent_topology_candidates(
            candidates
        )
    ) == 2


def test_unique_residual_matrix_may_share_chain_boundary(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "FLEURY EN BIERE",
                "name_to": "URY",
                "distance": "34.07",
                "price1": "2.00",
            },
            {
                "operator": "TEST",
                "name_from": "URY",
                "name_to": "NEXT",
                "distance": "24",
                "price1": "3.00",
            },
        ],
    )
    toll_range = TollRange(0, 3, 0.0, 40.0, 40.0)

    fleury_a = _projection(
        "FLEURY EN BIERE",
        "OFFICIAL",
        4.0,
        lon=0.040,
    )
    fleury_b = _projection(
        "PEAGE DE FLEURY EN BIERE",
        "TEST",
        4.2,
        lon=0.042,
    )
    ury = _projection(
        "URY",
        "TEST",
        15.0,
        lon=0.150,
    )
    next_station = _projection(
        "NEXT",
        "TEST",
        35.0,
        lon=0.350,
    )
    existing = _match(
        toll_range,
        ury,
        next_station,
        price=3.0,
    )
    used_keys = (
        service._station_identity_keys(ury.station)
        | service._station_identity_keys(next_station.station)
    )

    selected = service._select_unique_residual_closed_match(
        range_index=0,
        toll_range=toll_range,
        interval_start_km=0.0,
        interval_end_km=15.0,
        projections=[
            fleury_a,
            fleury_b,
            ury,
            next_station,
        ],
        existing_closed=[existing],
        used_open=[],
        road_class_link_details=[],
        used_station_keys=used_keys,
    )

    assert selected is not None
    assert selected.record.price == 2.0
    assert selected.exit.station.display_name == "Ury"
    assert (
        service._closed_record_distance_is_supporting_evidence(
            selected.record,
            selected.span_km,
        )
        is False
    )


def test_non_equivalent_residual_matrices_are_not_selected(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "ALPHA",
                "name_to": "OMEGA",
                "distance": "20",
                "price1": "2.00",
            },
            {
                "operator": "TEST",
                "name_from": "BETA",
                "name_to": "OMEGA",
                "distance": "20",
                "price1": "2.00",
            },
        ],
    )
    toll_range = TollRange(0, 3, 0.0, 30.0, 30.0)
    alpha = _projection(
        "ALPHA",
        "TEST",
        0.0,
        lon=0.000,
    )
    beta = _projection(
        "BETA",
        "TEST",
        0.2,
        lon=0.020,
    )
    omega = _projection(
        "OMEGA",
        "TEST",
        30.0,
        lon=0.300,
    )

    selected = service._select_unique_residual_closed_match(
        range_index=0,
        toll_range=toll_range,
        interval_start_km=0.0,
        interval_end_km=30.0,
        projections=[alpha, beta, omega],
        existing_closed=[],
        used_open=[],
        road_class_link_details=[],
        used_station_keys=set(),
    )

    assert selected is None


def test_official_matrix_may_end_at_internal_mainline_boundary(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "ENTRY",
                "name_to": "INTERNAL BARRIER",
                "distance": "21.3",
                "price1": "1.70",
            }
        ],
    )
    for key, record in list(service.closed_prices.items()):
        service.closed_prices[key] = ClosedPrice(
            price=record.price,
            distance_km=record.distance_km,
            operator=record.operator,
            source_id="official-2026",
        )

    toll_range = TollRange(0, 3, 0.0, 38.1, 38.1)
    entry = _projection(
        "ENTRY",
        "TEST",
        0.0,
        lon=0.0,
    )
    internal = _projection(
        "INTERNAL BARRIER",
        "TEST",
        21.3,
        lon=0.213,
        system_type="mainline",
    )

    selected = service._select_unique_residual_closed_match(
        range_index=0,
        toll_range=toll_range,
        interval_start_km=0.0,
        interval_end_km=38.1,
        projections=[entry, internal],
        existing_closed=[],
        used_open=[],
        road_class_link_details=[],
        used_station_keys=set(),
    )

    assert selected is not None
    assert selected.record.price == 1.70
    assert selected.exit.station.is_mainline_barrier


def test_unsourced_matrix_cannot_use_internal_mainline_relaxation(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "ENTRY",
                "name_to": "INTERNAL BARRIER",
                "distance": "21.3",
                "price1": "1.70",
            }
        ],
    )
    toll_range = TollRange(0, 3, 0.0, 38.1, 38.1)
    entry = _projection(
        "ENTRY",
        "TEST",
        0.0,
        lon=0.0,
    )
    internal = _projection(
        "INTERNAL BARRIER",
        "TEST",
        21.3,
        lon=0.213,
        system_type="mainline",
    )

    selected = service._select_unique_residual_closed_match(
        range_index=0,
        toll_range=toll_range,
        interval_start_km=0.0,
        interval_end_km=38.1,
        projections=[entry, internal],
        existing_closed=[],
        used_open=[],
        road_class_link_details=[],
        used_station_keys=set(),
    )

    assert selected is None


def test_boundary_overhang_is_limited_to_half_kilometre(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, [])
    toll_range = TollRange(0, 3, 0.0, 20.0, 20.0)
    entry = _projection(
        "ALPHA",
        "TEST",
        0.3,
        lon=0.003,
    )
    exit_ = _projection(
        "OMEGA",
        "TEST",
        15.0,
        lon=0.150,
    )
    match = _match(toll_range, entry, exit_)
    states = [
        TollStateInterval(
            start_index=0,
            end_index=3,
            start_km=0.0,
            end_km=20.0,
            distance_km=20.0,
            value="ALL",
            class1_status="toll",
        )
    ]
    used = (
        service._station_identity_keys(entry.station)
        | service._station_identity_keys(exit_.station)
    )

    spans = service._closed_boundary_overhang_spans(
        ranges=[toll_range],
        toll_state_intervals=states,
        projections=[entry, exit_],
        accepted_closed=[match],
        road_class_link_details=[],
        used_station_keys=used,
    )

    assert (0.0, 0.3) in spans
    assert all(end - start <= 0.5 for start, end in spans)


def test_cross_source_closed_boundary_twin_is_not_a_second_event(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, [])
    toll_range = TollRange(0, 3, 62.4, 209.5, 147.1)
    entry = _projection(
        "BERSAILLIN",
        "APRR",
        66.3,
        lon=3.15,
    )
    official_exit = _projection(
        "BEYNOST",
        "OFFICIAL",
        209.2,
        lon=4.9967,
        system_type="mainline",
    )
    accepted = _match(
        toll_range,
        entry,
        official_exit,
        operator="APRR",
        price=15.4,
    )
    duplicate = _projection(
        "PEAGE DE BEYNOST - BEYNOST",
        "APRR",
        209.5,
        lon=4.9940,
        system_type="mainline",
    )
    distinct_gantry = _projection(
        "PORTIQUE SUIVANT",
        "APRR",
        209.5,
        lon=4.9940,
        system_type="mainline",
    )
    fragment = TollRange(
        2,
        3,
        209.2,
        209.5,
        0.3,
    )
    used = (
        service._station_identity_keys(entry.station)
        | service._station_identity_keys(official_exit.station)
    )

    assert service._unpriced_billing_events_in_range(
        [entry, official_exit, duplicate],
        fragment,
        [],
        [accepted],
        used,
    ) == []
    assert service._unpriced_billing_events_in_range(
        [entry, official_exit, distinct_gantry],
        fragment,
        [],
        [accepted],
        used,
    ) == [distinct_gantry]


def test_exact_chain_allows_exit_then_same_entry() -> None:
    segments = [
        TollSegmentQuote(
            entry="ALPHA",
            exit="URY",
            operator="TEST",
            cost=2.0,
            distance_km=None,
            confidence="exact",
            route_start_km=4.0,
            route_end_km=15.0,
        ),
        TollSegmentQuote(
            entry="URY",
            exit="OMEGA",
            operator="TEST",
            cost=3.0,
            distance_km=None,
            confidence="exact",
            route_start_km=15.0,
            route_end_km=35.0,
        ),
    ]

    assert TollPricingService._segments_are_integral(segments)


def test_official_long_matrix_replaces_nested_partial_journey() -> None:
    service = object.__new__(TollPricingService)
    partial_range = TollRange(0, 1, 54.3, 96.4, 42.1)
    later_range = TollRange(1, 2, 87.4, 112.1, 24.7)
    entry = _projection(
        "GROUP ENTRY",
        "TEST",
        54.3,
        lon=0.543,
    )
    intermediate = _projection(
        "INTERMEDIATE EXIT",
        "TEST",
        96.4,
        lon=0.964,
    )
    final_exit = _projection(
        "FINAL EXIT",
        "TEST",
        103.6,
        lon=1.036,
    )
    partial = ClosedMatch(
        range_index=0,
        toll_range=partial_range,
        record=ClosedPrice(
            price=5.40,
            distance_km=None,
            operator="TEST",
            source_id="official-2026",
        ),
        entry=entry,
        exit=intermediate,
        coverage_km=42.1,
        full_range=True,
    )
    complete = ClosedMatch(
        range_index=1,
        toll_range=later_range,
        record=ClosedPrice(
            price=7.50,
            distance_km=None,
            operator="TEST",
            source_id="official-2026",
        ),
        entry=entry,
        exit=final_exit,
        coverage_km=24.7,
        full_range=True,
    )

    selected = service._select_closed_matches(
        [partial, complete]
    )

    assert selected == [complete]


def test_unsourced_long_matrix_does_not_dominate_by_span_alone() -> None:
    service = object.__new__(TollPricingService)
    partial_range = TollRange(0, 1, 0.0, 40.0, 40.0)
    later_range = TollRange(1, 2, 30.0, 55.0, 25.0)
    entry = _projection(
        "ENTRY",
        "TEST",
        0.0,
        lon=0.0,
    )
    intermediate = _projection(
        "INTERMEDIATE",
        "TEST",
        40.0,
        lon=0.4,
    )
    final_exit = _projection(
        "FINAL",
        "TEST",
        50.0,
        lon=0.5,
    )
    partial = ClosedMatch(
        range_index=0,
        toll_range=partial_range,
        record=ClosedPrice(
            price=4.0,
            distance_km=None,
            operator="TEST",
        ),
        entry=entry,
        exit=intermediate,
        coverage_km=40.0,
        full_range=True,
    )
    unsourced_long = ClosedMatch(
        range_index=1,
        toll_range=later_range,
        record=ClosedPrice(
            price=6.0,
            distance_km=50.0,
            operator="TEST",
        ),
        entry=entry,
        exit=final_exit,
        coverage_km=25.0,
        full_range=True,
    )

    selected = service._select_closed_matches(
        [partial, unsourced_long]
    )

    assert selected == [partial]

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from app.services.tolls import (
    ClosedMatch,
    ClosedPrice,
    StationProjection,
    TollPlan,
    TollPricingService,
    TollRange,
    TollSegmentQuote,
    TollStation,
)


def test_quote_level_exact_is_centralized_in_plan_finalizer() -> None:
    source_path = Path(inspect.getsourcefile(TollPricingService) or "")
    tree = ast.parse(source_path.read_text(encoding="utf-8"))

    exact_quote_methods: set[str] = set()
    for class_node in tree.body:
        if not isinstance(class_node, ast.ClassDef):
            continue
        if class_node.name != "TollPricingService":
            continue
        for method in class_node.body:
            if not isinstance(method, ast.FunctionDef):
                continue
            for node in ast.walk(method):
                if not isinstance(node, ast.Call):
                    continue
                if not isinstance(node.func, ast.Name):
                    continue
                if node.func.id != "TollQuote" or len(node.args) < 2:
                    continue
                confidence = node.args[1]
                if (
                    isinstance(confidence, ast.Constant)
                    and confidence.value == "exact"
                ):
                    exact_quote_methods.add(method.name)

    assert exact_quote_methods == {"_finalize_toll_plan"}


def test_tiny_residual_with_physical_event_stays_estimated() -> None:
    service = object.__new__(TollPricingService)
    toll_range = TollRange(
        start_index=0,
        end_index=1,
        start_km=0.0,
        end_km=10.0,
        distance_km=10.0,
    )
    segment = TollSegmentQuote(
        entry="Alpha",
        exit="Bravo",
        operator="TEST",
        cost=2.0,
        distance_km=9.95,
        confidence="exact",
        route_start_km=0.0,
        route_end_km=9.95,
    )
    plan = TollPlan(
        exact_cost=2.0,
        station_names=["Alpha", "Bravo"],
        segments=[segment],
        ranges=[toll_range],
        unresolved_indexes=[0],
        unresolved_km_by_range={0: 0.05},
        unresolved_event_ranges={0},
        ignored_noise_indexes=set(),
    )

    quote = service._finalize_toll_plan(plan)

    assert quote is not None
    assert quote.confidence == "estimated"


def test_small_residual_without_positive_noise_proof_stays_estimated() -> None:
    service = object.__new__(TollPricingService)
    toll_range = TollRange(
        start_index=0,
        end_index=1,
        start_km=0.0,
        end_km=10.0,
        distance_km=10.0,
    )
    segment = TollSegmentQuote(
        entry="Alpha",
        exit="Bravo",
        operator="TEST",
        cost=2.0,
        distance_km=9.0,
        confidence="exact",
        route_start_km=0.0,
        route_end_km=9.0,
    )
    plan = TollPlan(
        exact_cost=2.0,
        station_names=["Alpha", "Bravo"],
        segments=[segment],
        ranges=[toll_range],
        unresolved_indexes=[0],
        unresolved_km_by_range={0: 1.0},
        unresolved_event_ranges=set(),
        ignored_noise_indexes=set(),
    )

    quote = service._finalize_toll_plan(plan)

    assert quote is not None
    assert quote.confidence == "estimated"


def test_two_closed_journeys_make_free_connector_explicit() -> None:
    toll_range = TollRange(
        start_index=0,
        end_index=3,
        start_km=0.0,
        end_km=78.6,
        distance_km=78.6,
    )

    def station(name: str, lon: float, operator: str) -> TollStation:
        return TollStation(
            name=name,
            operator=operator,
            lat=45.0,
            lon=lon,
            system_type="closed",
        )

    alpha = StationProjection(
        station=station("ALPHA", 0.0, "NET1"),
        route_km=0.0,
        lateral_km=0.0,
        segment_index=1,
    )
    bravo = StationProjection(
        station=station("BRAVO", 0.45, "NET1"),
        route_km=35.4,
        lateral_km=0.0,
        segment_index=2,
    )
    charlie = StationProjection(
        station=station("CHARLIE", 0.50, "NET2"),
        route_km=39.3,
        lateral_km=0.0,
        segment_index=3,
    )
    delta = StationProjection(
        station=station("DELTA", 1.0, "NET2"),
        route_km=78.6,
        lateral_km=0.0,
        segment_index=4,
    )

    matches = [
        ClosedMatch(
            range_index=0,
            toll_range=toll_range,
            record=ClosedPrice(
                price=5.0,
                distance_km=35.0,
                operator="NET1",
            ),
            entry=alpha,
            exit=bravo,
            coverage_km=35.4,
            full_range=False,
        ),
        ClosedMatch(
            range_index=0,
            toll_range=toll_range,
            record=ClosedPrice(
                price=6.0,
                distance_km=39.0,
                operator="NET2",
            ),
            entry=charlie,
            exit=delta,
            coverage_km=39.3,
            full_range=False,
        ),
    ]

    service = object.__new__(TollPricingService)
    assert (
        service._closed_chain_has_complete_event_topology(
            matches
        )
        is True
    )


def test_large_unverified_closed_connector_is_not_exact() -> None:
    toll_range = TollRange(
        start_index=0,
        end_index=3,
        start_km=0.0,
        end_km=78.6,
        distance_km=78.6,
    )

    def station(name: str, lon: float, operator: str) -> TollStation:
        return TollStation(
            name=name,
            operator=operator,
            lat=45.0,
            lon=lon,
            system_type="closed",
        )

    alpha = StationProjection(
        station=station("ALPHA", 0.0, "NET1"),
        route_km=0.0,
        lateral_km=0.0,
        segment_index=1,
    )
    bravo = StationProjection(
        station=station("BRAVO", 0.4, "NET1"),
        route_km=31.4,
        lateral_km=0.0,
        segment_index=2,
    )
    charlie = StationProjection(
        station=station("CHARLIE", 0.52, "NET2"),
        route_km=40.9,
        lateral_km=0.0,
        segment_index=3,
    )
    delta = StationProjection(
        station=station("DELTA", 1.0, "NET2"),
        route_km=78.6,
        lateral_km=0.0,
        segment_index=4,
    )

    matches = [
        ClosedMatch(
            range_index=0,
            toll_range=toll_range,
            record=ClosedPrice(
                price=5.0,
                distance_km=31.5,
                operator="NET1",
            ),
            entry=alpha,
            exit=bravo,
            coverage_km=31.4,
            full_range=False,
        ),
        ClosedMatch(
            range_index=0,
            toll_range=toll_range,
            record=ClosedPrice(
                price=6.0,
                distance_km=37.8,
                operator="NET2",
            ),
            entry=charlie,
            exit=delta,
            coverage_km=37.7,
            full_range=False,
        ),
    ]

    service = object.__new__(TollPricingService)
    assert (
        service._closed_chain_has_complete_event_topology(
            matches
        )
        is False
    )


def test_route_wide_matrix_cannot_absorb_open_charge() -> None:
    entry_station = TollStation(
        name="ENTRY",
        operator="TEST",
        lat=45.0,
        lon=0.0,
        system_type="closed",
    )
    exit_station = TollStation(
        name="EXIT",
        operator="TEST",
        lat=45.0,
        lon=1.0,
        system_type="closed",
    )
    toll_range = TollRange(
        start_index=0,
        end_index=2,
        start_km=0.0,
        end_km=100.0,
        distance_km=100.0,
    )
    match = ClosedMatch(
        range_index=-1,
        toll_range=toll_range,
        record=ClosedPrice(
            price=50.0,
            distance_km=100.0,
            operator="TEST",
        ),
        entry=StationProjection(
            station=entry_station,
            route_km=0.0,
            lateral_km=0.0,
            segment_index=1,
        ),
        exit=StationProjection(
            station=exit_station,
            route_km=100.0,
            lateral_km=0.0,
            segment_index=2,
        ),
        coverage_km=100.0,
        full_range=True,
    )
    open_segment = TollSegmentQuote(
        entry="GANTRY",
        exit=None,
        operator="TEST",
        cost=1.0,
        distance_km=None,
        confidence="exact",
        route_start_km=50.0,
        route_end_km=50.0,
    )
    plan = TollPlan(
        exact_cost=1.0,
        station_names=["GANTRY"],
        segments=[open_segment],
        ranges=[toll_range],
        unresolved_indexes=[0],
        unresolved_km_by_range={0: 99.0},
        unresolved_event_ranges=set(),
        ignored_noise_indexes=set(),
    )

    assert (
        TollPricingService._route_wide_match_confirms_same_closed_journey(
            match,
            plan,
        )
        is False
    )


def test_route_wide_replacement_does_not_compare_prices() -> None:
    source = inspect.getsource(TollPricingService._quote_from_ranges)
    assert "route_quote.cost" not in source
    assert ">= total" not in source


def test_route_wide_matrix_may_confirm_same_closed_journey() -> None:
    entry_station = TollStation(
        name="COURCY",
        operator="SANEF",
        lat=49.3,
        lon=4.0,
        system_type="closed",
    )
    exit_station = TollStation(
        name="SETQUES",
        operator="SANEF",
        lat=50.7,
        lon=2.1,
        system_type="closed",
    )
    toll_range = TollRange(
        start_index=0,
        end_index=2,
        start_km=0.0,
        end_km=255.5,
        distance_km=255.5,
    )
    match = ClosedMatch(
        range_index=-1,
        toll_range=toll_range,
        record=ClosedPrice(
            price=26.6,
            distance_km=None,
            operator="SANEF",
        ),
        entry=StationProjection(
            station=entry_station,
            route_km=8.1,
            lateral_km=0.0,
            segment_index=1,
        ),
        exit=StationProjection(
            station=exit_station,
            route_km=228.8,
            lateral_km=0.0,
            segment_index=2,
        ),
        coverage_km=220.7,
        full_range=False,
    )
    segment = TollSegmentQuote(
        entry="Courcy",
        exit="Setques",
        operator="SANEF",
        cost=26.6,
        distance_km=None,
        confidence="exact",
        route_start_km=8.1,
        route_end_km=228.8,
    )
    plan = TollPlan(
        exact_cost=26.6,
        station_names=["Courcy", "Setques"],
        segments=[segment],
        ranges=[toll_range],
        unresolved_indexes=[0],
        unresolved_km_by_range={0: 34.8},
        unresolved_event_ranges=set(),
        ignored_noise_indexes=set(),
    )

    assert (
        TollPricingService._route_wide_match_confirms_same_closed_journey(
            match,
            plan,
        )
        is True
    )

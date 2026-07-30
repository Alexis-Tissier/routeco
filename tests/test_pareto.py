from app.models import RouteResult
from app.services.pareto import (
    decorate_routes,
    pareto_front,
    select_economically_distinct_routes,
    select_useful_routes,
)


def route(identifier: str, duration: int, cost: float) -> RouteResult:
    return RouteResult(
        id=identifier, label="", description="", distance_km=100, duration_minutes=duration,
        motorway_km=50, road_km=50, fuel_liters=6, fuel_cost=10, toll_cost=cost-10,
        total_cost=cost, geometry=[[2,48],[3,47]], source="demo"
    )


def test_dominated_route_removed():
    routes = [route("fast", 100, 50), route("good", 120, 35), route("bad", 130, 55)]
    assert [item.id for item in pareto_front(routes)] == ["fast", "good"]


def test_recommended_respects_time_limit():
    routes = decorate_routes([route("fast", 100, 50), route("mid", 130, 38), route("cheap", 180, 20)], 45)
    recommended = next(item for item in routes if "Recommandé" in item.tags)
    assert recommended.id == "mid"


def test_estimated_route_is_not_recommended_when_trusted_route_exists():
    fast = route("fast", 100, 50)
    fast.toll_confidence = "exact"
    estimated = route("estimated", 120, 30)
    estimated.toll_confidence = "estimated"
    trusted = route("trusted", 130, 35)
    trusted.toll_confidence = "none"

    decorated = decorate_routes([fast, estimated, trusted], 45)
    recommended = next(item for item in decorated if "Recommandé" in item.tags)
    assert recommended.id == "trusted"
    assert "Péage estimé" in estimated.tags


def test_representative_selection_keeps_cheapest_route_beyond_first_five():
    from app.services.pareto import select_representative_routes

    routes = [
        route("fast", 100, 80),
        route("r2", 105, 75),
        route("r3", 110, 70),
        route("r4", 115, 65),
        route("r5", 120, 60),
        route("cheap", 180, 20),
    ]
    for item in routes:
        item.toll_confidence = "exact"

    selected = select_representative_routes(routes, max_routes=5)
    selected_ids = {item.id for item in selected}

    assert "fast" in selected_ids
    assert "cheap" in selected_ids
    assert len(selected) == 5


def test_representative_selection_keeps_cheapest_trusted_route():
    from app.services.pareto import select_representative_routes

    fast = route("fast", 100, 80)
    fast.toll_confidence = "exact"
    estimated_cheapest = route("estimated", 130, 20)
    estimated_cheapest.toll_confidence = "estimated"
    trusted = route("trusted", 150, 30)
    trusted.toll_confidence = "none"
    fillers = [route(f"f{index}", 101 + index, 70 - index) for index in range(6)]
    for item in fillers:
        item.toll_confidence = "exact"

    selected = select_representative_routes(
        [fast, estimated_cheapest, trusted, *fillers], max_routes=5
    )
    selected_ids = {item.id for item in selected}

    assert "estimated" in selected_ids
    assert "trusted" in selected_ids


def test_routes_are_ordered_fastest_then_by_total_cost():
    decorated = decorate_routes(
        [
            route("fast", 100, 80),
            route("balanced", 130, 55),
            route("cheap", 170, 30),
        ],
        90,
    )

    assert [item.id for item in decorated] == ["fast", "cheap", "balanced"]


def test_penny_saving_slow_variants_are_grouped_by_minimum_step():
    routes = [
        route("fast", 510, 143.74),
        route("balanced", 667, 71.51),
        route("free-fast", 759, 45.90),
        route("free-middle", 770, 45.79),
        route("free-slow", 785, 45.60),
    ]

    selected = select_economically_distinct_routes(routes, minimum_step_savings=5)

    assert [item.id for item in selected] == ["fast", "balanced", "free-fast"]


def test_trusted_cost_step_survives_a_cheaper_estimated_route():
    fast = route("fast", 100, 100)
    fast.toll_confidence = "exact"
    estimated = route("estimated", 120, 50)
    estimated.toll_confidence = "estimated"
    trusted = route("trusted", 130, 52)
    trusted.toll_confidence = "exact"

    selected = select_economically_distinct_routes(
        [fast, estimated, trusted],
        minimum_step_savings=5,
    )

    assert [item.id for item in selected] == ["fast", "estimated", "trusted"]


def test_useful_routes_keep_motorway_and_short_distance_roles() -> None:
    motorway = route("motorway", 317, 128.57)
    motorway.distance_km = 570
    motorway.motorway_km = 520
    motorway.road_km = 50
    motorway.profile = "motorway"

    direct = route("direct", 326, 63.57)
    direct.distance_km = 400
    direct.motorway_km = 114
    direct.road_km = 286

    balanced = route("balanced", 345, 54.0)
    balanced.distance_km = 410
    balanced.motorway_km = 70
    balanced.road_km = 340

    free = route("free", 360, 44.74)
    free.distance_km = 406
    free.motorway_km = 21
    free.road_km = 385

    selected = select_useful_routes(
        [motorway, direct, balanced, free],
        minimum_savings=5,
        max_routes=5,
    )
    decorated = decorate_routes(selected, 45)

    assert [item.id for item in decorated] == [
        "motorway",
        "free",
        "balanced",
        "direct",
    ]
    assert "Plus rapide" in motorway.tags
    assert "Autoroute" in motorway.tags
    assert "Moins de km" in direct.tags


def test_motorway_role_survives_when_local_model_times_it_slightly_slower() -> None:
    direct = route("direct", 330, 63.57)
    direct.distance_km = 400
    direct.motorway_km = 114
    direct.road_km = 286

    motorway = route("motorway", 340, 128.57)
    motorway.distance_km = 570
    motorway.motorway_km = 520
    motorway.road_km = 50
    motorway.profile = "motorway"

    free = route("free", 373, 44.74)
    free.distance_km = 406
    free.motorway_km = 21
    free.road_km = 385

    selected = select_useful_routes(
        [direct, motorway, free],
        minimum_savings=5,
        max_routes=5,
    )

    assert {item.id for item in selected} == {"direct", "motorway", "free"}


def test_useful_routes_still_group_penny_apart_no_toll_variants() -> None:
    routes = [
        route("fast", 510, 143.74),
        route("balanced", 667, 71.51),
        route("free-fast", 759, 45.90),
        route("free-middle", 770, 45.79),
        route("free-slow", 785, 45.60),
    ]

    selected = select_useful_routes(
        routes,
        minimum_savings=5,
        max_routes=5,
    )

    assert [item.id for item in selected] == ["fast", "balanced", "free-fast"]

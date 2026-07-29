from app.models import RouteResult
from app.services.pareto import decorate_routes, pareto_front


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

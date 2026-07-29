from __future__ import annotations

from app.models import RouteResult


def pareto_front(routes: list[RouteResult]) -> list[RouteResult]:
    """Keep routes that are not both slower and more expensive than another route."""
    frontier: list[RouteResult] = []
    for candidate in routes:
        dominated = any(
            other.id != candidate.id
            and other.duration_minutes <= candidate.duration_minutes
            and other.total_cost <= candidate.total_cost
            and (
                other.duration_minutes < candidate.duration_minutes
                or other.total_cost < candidate.total_cost
            )
            for other in routes
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda route: (route.duration_minutes, route.total_cost))


def decorate_routes(routes: list[RouteResult], max_extra_minutes: int | None) -> list[RouteResult]:
    if not routes:
        return []

    fastest = min(routes, key=lambda route: route.duration_minutes)
    cheapest = min(routes, key=lambda route: route.total_cost)
    limit = None if max_extra_minutes is None else fastest.duration_minutes + max_extra_minutes

    eligible = [route for route in routes if limit is None or route.duration_minutes <= limit]
    trusted = [route for route in eligible if route.toll_confidence in {"exact", "none", "missing"}]
    recommended = min(trusted, key=lambda route: route.total_cost) if trusted else None
    untrusted_best = min(eligible, key=lambda route: route.total_cost) if eligible else fastest

    for route in routes:
        route.extra_minutes = max(0, route.duration_minutes - fastest.duration_minutes)
        route.savings = round(fastest.total_cost - route.total_cost, 2)
        route.within_limit = limit is None or route.duration_minutes <= limit
        tags: list[str] = []
        if route.id == fastest.id:
            tags.append("Plus rapide")
        if recommended is not None and route.id == recommended.id and route.id != fastest.id:
            tags.append("Recommandé")
        elif (
            recommended is None
            and route.id == untrusted_best.id
            and route.id != fastest.id
            and route.toll_confidence == "estimated"
        ):
            tags.append("À vérifier")
        if route.id == cheapest.id:
            tags.append("Moins cher")
        if route.toll_confidence == "estimated" and "À vérifier" not in tags:
            tags.append("Péage estimé")
        route.tags = tags

        if "Plus rapide" in tags:
            route.label = "Le plus rapide"
            route.description = "Le trajet de référence, optimisé uniquement sur la durée."
        elif "Recommandé" in tags:
            route.label = "Le meilleur compromis"
            route.description = "Le moins cher dans la limite choisie avec un péage fiable."
        elif "À vérifier" in tags:
            route.label = "Compromis à vérifier"
            route.description = "Potentiellement intéressant, mais une partie du péage reste estimée."
        elif "Moins cher" in tags:
            route.label = "Le plus économique"
            route.description = "L'économie maximale parmi les alternatives proposées."
        else:
            route.label = "Alternative équilibrée"
            route.description = "Un compromis intermédiaire entre durée, carburant et péages."
    return sorted(routes, key=lambda route: route.duration_minutes)


def select_representative_routes(
    routes: list[RouteResult], max_routes: int = 5
) -> list[RouteResult]:
    """Keep the routes that matter instead of merely the five fastest.

    Native GraphHopper alternatives can produce more than five candidates. A
    simple duration slice can hide the cheapest or the only trusted economical
    route. This selector anchors the fastest, cheapest trusted and cheapest
    overall routes, then fills the remaining slots with geometrically diverse
    trade-offs in time, cost and motorway usage.
    """
    if len(routes) <= max_routes:
        return sorted(routes, key=lambda route: route.duration_minutes)

    fastest = min(routes, key=lambda route: route.duration_minutes)
    cheapest = min(routes, key=lambda route: route.total_cost)
    trusted = [
        route
        for route in routes
        if route.toll_confidence in {"exact", "none", "missing"}
    ]
    cheapest_trusted = min(trusted, key=lambda route: route.total_cost) if trusted else None

    selected: list[RouteResult] = []
    selected_ids: set[str] = set()

    def add(route: RouteResult | None) -> None:
        if route is not None and route.id not in selected_ids and len(selected) < max_routes:
            selected.append(route)
            selected_ids.add(route.id)

    add(fastest)
    add(cheapest_trusted)
    add(cheapest)

    time_values = [route.duration_minutes for route in routes]
    cost_values = [route.total_cost for route in routes]
    motorway_values = [route.motorway_km for route in routes]
    time_span = max(1.0, float(max(time_values) - min(time_values)))
    cost_span = max(0.01, float(max(cost_values) - min(cost_values)))
    motorway_span = max(1.0, float(max(motorway_values) - min(motorway_values)))

    def vector(route: RouteResult) -> tuple[float, float, float]:
        return (
            (route.duration_minutes - min(time_values)) / time_span,
            (route.total_cost - min(cost_values)) / cost_span,
            (route.motorway_km - min(motorway_values)) / motorway_span,
        )

    def distance(first: RouteResult, second: RouteResult) -> float:
        a = vector(first)
        b = vector(second)
        return sum((left - right) ** 2 for left, right in zip(a, b)) ** 0.5

    while len(selected) < max_routes:
        remaining = [route for route in routes if route.id not in selected_ids]
        if not remaining:
            break
        # Prefer candidates far from all selected anchors. A small trust bonus
        # prevents an estimated route from beating an equally diverse exact one.
        best = max(
            remaining,
            key=lambda route: (
                min(distance(route, current) for current in selected)
                + (0.04 if route.toll_confidence in {"exact", "none", "missing"} else 0.0),
                -route.duration_minutes,
            ),
        )
        add(best)

    return sorted(selected, key=lambda route: route.duration_minutes)

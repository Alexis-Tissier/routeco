from __future__ import annotations

from app.models import RouteResult

TRUSTED_TOLL_CONFIDENCES = {"exact", "none", "missing"}


def _motorway_anchor(routes: list[RouteResult]) -> RouteResult | None:
    """Return a genuinely different motorway-rich option when one exists."""
    if not routes:
        return None
    fastest = min(routes, key=lambda route: route.duration_minutes)
    anchor = max(
        routes,
        key=lambda route: (
            route.motorway_km,
            route.motorway_km / max(1.0, route.distance_km),
            -route.duration_minutes,
        ),
    )
    if anchor.id == fastest.id:
        motorway_ratio = anchor.motorway_km / max(1.0, anchor.distance_km)
        if anchor.profile == "motorway" or (
            anchor.motorway_km >= 30.0 and motorway_ratio >= 0.65
        ):
            return anchor
        return None
    motorway_gain = anchor.motorway_km - fastest.motorway_km
    ratio_gain = (
        anchor.motorway_km / max(1.0, anchor.distance_km)
        - fastest.motorway_km / max(1.0, fastest.distance_km)
    )
    if motorway_gain >= max(20.0, fastest.distance_km * 0.08) and ratio_gain >= 0.10:
        return anchor
    return None


def _shortest_anchor(routes: list[RouteResult]) -> RouteResult | None:
    """Return a materially shorter route, not a rounding-level difference."""
    if not routes:
        return None
    fastest = min(routes, key=lambda route: route.duration_minutes)
    shortest = min(
        routes,
        key=lambda route: (route.distance_km, route.duration_minutes),
    )
    saved_km = fastest.distance_km - shortest.distance_km
    if shortest.id == fastest.id or saved_km >= max(8.0, fastest.distance_km * 0.03):
        return shortest
    return None


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
    motorway = _motorway_anchor(routes)
    shortest = _shortest_anchor(routes)
    limit = None if max_extra_minutes is None else fastest.duration_minutes + max_extra_minutes

    eligible = [route for route in routes if limit is None or route.duration_minutes <= limit]
    trusted = [
        route
        for route in eligible
        if route.toll_confidence in TRUSTED_TOLL_CONFIDENCES
    ]
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
        if motorway is not None and route.id == motorway.id:
            tags.append("Autoroute")
        if shortest is not None and route.id == shortest.id:
            tags.append("Moins de km")
        if route.toll_confidence == "estimated" and "À vérifier" not in tags:
            tags.append("Péage estimé")
        route.tags = tags

        if "Plus rapide" in tags:
            route.label = "Le plus rapide"
            route.description = "Le trajet de référence, optimisé uniquement sur la durée."
        elif "Recommandé" in tags:
            route.label = "Le meilleur compromis"
            route.description = "Le moins cher dans la limite choisie avec un péage fiable."
        elif "Autoroute" in tags:
            route.label = "L'option autoroutière"
            route.description = "Plus de kilomètres, mais un trajet largement autoroutier."
        elif "Moins de km" in tags:
            route.label = "Le plus direct"
            route.description = "La distance la plus courte parmi les itinéraires proposés."
        elif "À vérifier" in tags:
            route.label = "Compromis à vérifier"
            route.description = "Potentiellement intéressant, mais une partie du péage reste estimée."
        elif "Moins cher" in tags:
            route.label = "Le plus économique"
            route.description = "L'économie maximale parmi les alternatives proposées."
        else:
            route.label = "Alternative équilibrée"
            route.description = "Un compromis intermédiaire entre durée, carburant et péages."
    alternatives = sorted(
        (route for route in routes if route.id != fastest.id),
        key=lambda route: (route.total_cost, route.duration_minutes),
    )
    return [fastest, *alternatives]


def select_economically_distinct_routes(
    routes: list[RouteResult],
    minimum_step_savings: float,
) -> list[RouteResult]:
    """Keep meaningful cost steps, not penny-saving versions of one trade-off.

    Alternatives are walked from fast to slow. A slower candidate is useful only
    when it lowers the best cost seen so far by the requested amount. The fastest
    route is always preserved as the time baseline.
    """
    if not routes:
        return []
    fastest = min(routes, key=lambda route: route.duration_minutes)
    threshold = max(0.50, float(minimum_step_savings))
    selected = [fastest]
    best_cost = fastest.total_cost
    trusted_confidences = {"exact", "none", "missing"}
    best_trusted_cost = (
        fastest.total_cost
        if fastest.toll_confidence in trusted_confidences
        else float("inf")
    )
    for route in sorted(
        (item for item in routes if item.id != fastest.id),
        key=lambda item: (item.duration_minutes, item.total_cost),
    ):
        creates_cost_step = route.total_cost <= best_cost - threshold + 1e-9
        creates_trusted_step = (
            route.toll_confidence in trusted_confidences
            and route.total_cost <= best_trusted_cost - threshold + 1e-9
        )
        if creates_cost_step or creates_trusted_step:
            selected.append(route)
            best_cost = route.total_cost
            if route.toll_confidence in trusted_confidences:
                best_trusted_cost = route.total_cost
    return selected


def select_useful_routes(
    routes: list[RouteResult],
    minimum_savings: float,
    max_routes: int = 5,
) -> list[RouteResult]:
    """Keep up to five distinct route roles instead of only saving steps.

    The fastest route is the time baseline. A materially more motorway-heavy
    route and a materially shorter route are useful choices in their own right,
    even when they are not cheaper. Cost-oriented alternatives still need to
    meet the requested saving threshold and create a new saving step.
    """
    if not routes or max_routes <= 0:
        return []

    fastest = min(routes, key=lambda route: route.duration_minutes)

    selected: list[RouteResult] = []
    selected_ids: set[str] = set()

    def add(route: RouteResult | None) -> None:
        if route is None or route.id in selected_ids or len(selected) >= max_routes:
            return
        selected.append(route)
        selected_ids.add(route.id)

    add(fastest)
    add(_motorway_anchor(routes))
    add(_shortest_anchor(routes))

    saving_steps = select_economically_distinct_routes(
        routes,
        minimum_step_savings=minimum_savings,
    )
    for route in saving_steps:
        add(route)

    return selected


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
        return decorate_routes(routes, None)

    fastest = min(routes, key=lambda route: route.duration_minutes)
    cheapest = min(routes, key=lambda route: route.total_cost)
    trusted = [
        route
        for route in routes
        if route.toll_confidence in TRUSTED_TOLL_CONFIDENCES
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
                + (
                    0.04
                    if route.toll_confidence in TRUSTED_TOLL_CONFIDENCES
                    else 0.0
                ),
                -route.duration_minutes,
            ),
        )
        add(best)

    return decorate_routes(selected, None)

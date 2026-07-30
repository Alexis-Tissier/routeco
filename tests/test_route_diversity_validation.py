from __future__ import annotations

import httpx
import pytest

from scripts.verify_route_diversity import verify


def route(
    identifier: str,
    duration: int,
    distance: float,
    motorway: float,
    tags: list[str],
) -> dict:
    return {
        "id": identifier,
        "duration_minutes": duration,
        "distance_km": distance,
        "motorway_km": motorway,
        "tags": tags,
    }


def client_for(routes: list[dict]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "engine": "graphhopper",
                "candidate_count": 7,
                "routes": routes,
            },
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_route_diversity_verifier_accepts_distinct_roles() -> None:
    routes = [
        route("motorway", 317, 570, 520, ["Plus rapide", "Autoroute"]),
        route("direct", 326, 400, 114, ["Moins de km"]),
        route("free", 360, 406, 21, ["Moins cher"]),
    ]

    with client_for(routes) as client:
        verify(client, "http://routeco.test")


def test_verifier_accepts_shortest_economic_step_without_distance_badge() -> None:
    routes = [
        route("fastest", 326, 400, 114, ["Plus rapide"]),
        route("motorway", 330, 570, 520, ["Autoroute"]),
        # Six kilometres do not cross the selector's materiality threshold.
        # This route may still be displayed as an economic step, without using
        # a dedicated "Moins de km" role.
        route("economy", 334, 394, 110, ["Recommandé"]),
    ]

    with client_for(routes) as client:
        verify(client, "http://routeco.test")


def test_verifier_rejects_missing_badge_for_materially_shorter_route() -> None:
    routes = [
        route("fastest", 317, 450, 200, ["Plus rapide"]),
        route("motorway", 325, 570, 520, ["Autoroute"]),
        route("direct", 326, 400, 114, ["Recommandé"]),
    ]

    with (
        client_for(routes) as client,
        pytest.raises(RuntimeError, match="réellement plus direct"),
    ):
        verify(client, "http://routeco.test")


def test_route_diversity_verifier_rejects_two_displayed_routes() -> None:
    routes = [
        route("direct", 330, 400, 114, ["Plus rapide", "Moins de km"]),
        route("free", 373, 406, 21, ["Moins cher"]),
    ]

    with (
        client_for(routes) as client,
        pytest.raises(RuntimeError, match="entre trois et cinq"),
    ):
        verify(client, "http://routeco.test")

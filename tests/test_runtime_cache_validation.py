from __future__ import annotations

import httpx
import pytest

from scripts.verify_runtime_cache import verify


def route_response(
    *,
    cache_hit: bool,
    fuel_cost: float,
    routing_seconds: float,
) -> dict:
    return {
        "engine": "graphhopper",
        "candidate_count": 4,
        "cache_hit": cache_hit,
        "routing_seconds": routing_seconds,
        "routes": [
            {
                "id": "fastest-stable",
                "duration_minutes": 180,
                "distance_km": 300.0,
                "fuel_cost": fuel_cost,
                "toll_cost": 18.40,
                "geometry": [[2.13, 48.80], [5.04, 47.32]],
            }
        ],
    }


def client_for(*, mutate_geometry: bool = False) -> httpx.Client:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/api/health":
            return httpx.Response(
                200,
                json={
                    "routing_cache": {
                        "hits": 1 if calls > 1 else 0,
                        "estimated_bytes": 1024,
                    },
                    "toll_quote_cache": {
                        "hits": 4 if calls > 1 else 0,
                        "misses": 4,
                        "entries": 4,
                    },
                },
                request=request,
            )
        calls += 1
        payload = route_response(
            cache_hit=calls > 1,
            fuel_cost=30.0 if calls == 1 else 34.0,
            routing_seconds=12.0 if calls == 1 else 0.01,
        )
        if mutate_geometry and calls > 1:
            payload["routes"][0]["geometry"] = [
                [2.13, 48.80],
                [4.00, 46.00],
                [5.04, 47.32],
            ]
        return httpx.Response(200, json=payload, request=request)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_runtime_cache_verifier_accepts_cost_only_recalculation() -> None:
    with client_for() as client:
        verify(client, "http://routeco.test")


def test_runtime_cache_verifier_rejects_geometry_mutation() -> None:
    with (
        client_for(mutate_geometry=True) as client,
        pytest.raises(RuntimeError, match="modifié le tracé"),
    ):
        verify(client, "http://routeco.test")

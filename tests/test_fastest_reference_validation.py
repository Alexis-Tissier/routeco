from __future__ import annotations

import json

import httpx
import pytest

from scripts.verify_fastest_reference import verify


def transport(*, prepared_minutes: int = 500) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if request.url.path == "/route":
            compromise = "custom_model" in body
            minutes = 563 if compromise else prepared_minutes
            distance = 847_000 if compromise else 930_000
            return httpx.Response(
                200,
                json={
                    "paths": [
                        {
                            "distance": distance,
                            "time": minutes * 60_000,
                        }
                    ]
                },
            )
        if request.url.path == "/api/routes":
            return httpx.Response(
                200,
                json={
                    "engine": "graphhopper",
                    "routes": [
                        {
                            "duration_minutes": prepared_minutes,
                            "tags": ["Plus rapide"],
                        },
                        {
                            "duration_minutes": 563,
                            "tags": [],
                        },
                    ],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_runtime_verifier_accepts_a_true_fastest_baseline() -> None:
    with httpx.Client(transport=transport()) as client:
        verify(client, "http://routeco.test", "http://graphhopper.test")


def test_runtime_verifier_rejects_the_v8_equivalent_weighting() -> None:
    with httpx.Client(transport=transport(prepared_minutes=563)) as client:
        with pytest.raises(RuntimeError, match="strictement plus rapide"):
            verify(client, "http://routeco.test", "http://graphhopper.test")

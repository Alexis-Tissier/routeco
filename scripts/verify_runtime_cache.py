#!/usr/bin/env python3
from __future__ import annotations

import argparse

import httpx


def _request_payload(
    *,
    fuel_price: float,
    toll_estimate_rate: float,
) -> dict:
    # Validation coordinates only. They do not participate in production
    # routing rules and merely provide a stable regional cache probe.
    return {
        "start": {"lat": 48.8014, "lon": 2.1301},
        "end": {"lat": 47.3220, "lon": 5.0415},
        "start_label": "Point de contrôle A",
        "end_label": "Point de contrôle B",
        "fuel_type": "SP95-E10",
        "fuel_price": fuel_price,
        "max_extra_minutes": None,
        "min_savings": 0,
        "show_all": True,
        "motorway_consumption": 6.5,
        "road_consumption": 5.5,
        "toll_estimate_rate": toll_estimate_rate,
    }


def _fastest(payload: dict) -> dict:
    routes = payload.get("routes") or []
    if not routes:
        raise RuntimeError("Routeco n'a renvoyé aucun itinéraire.")
    return min(
        routes,
        key=lambda route: (
            int(route["duration_minutes"]),
            float(route["distance_km"]),
        ),
    )


def verify(client: httpx.Client, api_url: str) -> None:
    endpoint = f"{api_url.rstrip('/')}/api/routes"
    first_response = client.post(
        endpoint,
        json=_request_payload(
            fuel_price=1.82,
            toll_estimate_rate=0.105,
        ),
    )
    first_response.raise_for_status()
    first = first_response.json()
    if first.get("engine") != "graphhopper":
        raise RuntimeError("Routeco a basculé en mode démonstration.")

    second_response = client.post(
        endpoint,
        json=_request_payload(
            fuel_price=2.10,
            toll_estimate_rate=0.140,
        ),
    )
    second_response.raise_for_status()
    second = second_response.json()
    if not second.get("cache_hit"):
        raise RuntimeError("Le second calcul identique n'a pas réutilisé les tracés.")
    if first.get("candidate_count") != second.get("candidate_count"):
        raise RuntimeError("Le nombre de candidats a changé pendant le recalcul des coûts.")

    first_fastest = _fastest(first)
    second_fastest = _fastest(second)
    immutable = ("id", "duration_minutes", "distance_km", "geometry")
    changed = [
        field for field in immutable if first_fastest.get(field) != second_fastest.get(field)
    ]
    if changed:
        raise RuntimeError(
            "Le recalcul économique a modifié le tracé rapide : " + ", ".join(changed) + "."
        )
    if first_fastest.get("fuel_cost") == second_fastest.get("fuel_cost"):
        raise RuntimeError("Le carburant n'a pas été recalculé sur les tracés en cache.")

    health_response = client.get(f"{api_url.rstrip('/')}/api/health")
    health_response.raise_for_status()
    health = health_response.json()
    cache = health.get("routing_cache") or {}
    if int(cache.get("hits") or 0) < 1:
        raise RuntimeError("Le compteur de cache n'a enregistré aucune réutilisation.")

    print(
        "Cache Routeco validé : "
        f"{first.get('candidate_count', 0)} candidats ; "
        f"premier routage {float(first.get('routing_seconds') or 0):.1f} s, "
        f"recalcul {float(second.get('routing_seconds') or 0):.3f} s ; "
        f"{int(cache.get('estimated_bytes') or 0) / 1024 / 1024:.1f} Mio."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie le cache de géométries Routeco.")
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
    )
    args = parser.parse_args()
    with httpx.Client(timeout=240, trust_env=False) as client:
        verify(client, args.api_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

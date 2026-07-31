#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import time

import httpx

START = {"lat": 48.8014, "lon": 2.1301}
VIA = {"lat": 48.4469, "lon": 1.4890}
END = {"lat": 48.4047, "lon": 2.7016}


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lon1, lat1 = first
    lon2, lat2 = second
    radius = 6371.0088
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    value = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def payload(fuel_price: float) -> dict:
    return {
        "start": START,
        "end": END,
        "via": [VIA],
        "start_label": "Versailles",
        "via_labels": ["Chartres"],
        "end_label": "Fontainebleau",
        "fuel_type": "SP95-E10",
        "fuel_price": fuel_price,
        "max_extra_minutes": None,
        "min_savings": 0,
        "show_all": True,
        "motorway_consumption": 6.5,
        "road_consumption": 5.5,
        "toll_estimate_rate": 0.105,
    }


def fastest(response: dict) -> dict:
    routes = response.get("routes") or []
    if not routes:
        raise RuntimeError("Aucun itinéraire avec arrêt n'a été renvoyé.")
    return min(
        routes,
        key=lambda route: (
            int(route["duration_minutes"]),
            float(route["distance_km"]),
        ),
    )


def verify(client: httpx.Client, api_url: str) -> None:
    endpoint = f"{api_url.rstrip('/')}/api/routes"

    started = time.perf_counter()
    first_response = client.post(endpoint, json=payload(1.82))
    first_seconds = time.perf_counter() - started
    first_response.raise_for_status()
    first = first_response.json()
    if first.get("engine") != "graphhopper":
        raise RuntimeError("Le contrôle avec arrêt a basculé en mode démonstration.")

    route = fastest(first)
    geometry = route.get("geometry") or []
    nearest = min(
        (
            haversine_km(
                (float(point[0]), float(point[1])),
                (VIA["lon"], VIA["lat"]),
            )
            for point in geometry
        ),
        default=float("inf"),
    )
    if nearest > 1.5:
        raise RuntimeError(
            f"L'itinéraire ne passe pas par l'arrêt imposé : écart {nearest:.2f} km."
        )

    started = time.perf_counter()
    second_response = client.post(endpoint, json=payload(2.05))
    second_seconds = time.perf_counter() - started
    second_response.raise_for_status()
    second = second_response.json()
    if not second.get("cache_hit"):
        raise RuntimeError("Le trajet avec arrêt n'a pas été réutilisé depuis le cache.")
    if second_seconds > 2.5:
        raise RuntimeError(
            f"Le recalcul du trajet avec arrêt reste trop lent : {second_seconds:.3f} s."
        )

    second_route = fastest(second)
    immutable = ("id", "geometry", "duration_minutes", "distance_km", "toll_cost")
    changed = [field for field in immutable if route.get(field) != second_route.get(field)]
    if changed:
        raise RuntimeError("Le recalcul a modifié le trajet avec arrêt : " + ", ".join(changed))
    if route.get("fuel_cost") == second_route.get("fuel_cost"):
        raise RuntimeError("Le nouveau prix du carburant n'a pas été appliqué.")

    print(
        "Arrêt intermédiaire validé : "
        f"{first.get('candidate_count', 0)} candidats ; "
        f"écart à l'étape {nearest:.3f} km ; "
        f"premier calcul {first_seconds:.2f} s ; "
        f"recalcul complet {second_seconds:.3f} s."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie un trajet Routeco passant par une étape imposée."
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
    )
    args = parser.parse_args()
    with httpx.Client(timeout=300, trust_env=False) as client:
        verify(client, args.api_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

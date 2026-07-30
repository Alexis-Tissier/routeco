#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import dataclass

import httpx

from app.config import settings


@dataclass(frozen=True, slots=True)
class RawRoute:
    distance_km: float
    duration_minutes: int


def raw_route(
    client: httpx.Client,
    graphhopper_url: str,
    points: list[list[float]],
    *,
    distance_influence: float | None = None,
) -> RawRoute:
    body: dict = {
        "points": points,
        "profile": "car",
        "locale": "fr",
        "instructions": False,
        "points_encoded": False,
    }
    if distance_influence is not None:
        body["custom_model"] = {
            "distance_influence": distance_influence,
        }
    response = client.post(f"{graphhopper_url.rstrip('/')}/route", json=body)
    response.raise_for_status()
    payload = response.json()
    paths = payload.get("paths", [])
    if not paths:
        raise RuntimeError("GraphHopper n'a renvoyé aucun itinéraire.")
    path = paths[0]
    return RawRoute(
        distance_km=round(float(path["distance"]) / 1000, 1),
        duration_minutes=round(float(path["time"]) / 60000),
    )


def verify(
    client: httpx.Client,
    api_url: str,
    graphhopper_url: str,
) -> None:
    # Test de validation uniquement : aucune de ces coordonnées n'entre dans le
    # moteur ou dans sa logique de production. Ce trajet long reproduit la
    # différence entre temps minimal et compromis distance/temps.
    start = {"lat": 48.8566, "lon": 2.3522}
    end = {"lat": 43.6584, "lon": 6.9222}
    points = [[start["lon"], start["lat"]], [end["lon"], end["lat"]]]

    fastest = raw_route(client, graphhopper_url, points)
    old_compromise = raw_route(
        client,
        graphhopper_url,
        points,
        distance_influence=90,
    )
    if fastest.duration_minutes >= old_compromise.duration_minutes:
        raise RuntimeError(
            "Le profil préparé ne produit pas une route strictement plus "
            "rapide que l'ancien compromis distance/temps : "
            f"{fastest.duration_minutes} min contre "
            f"{old_compromise.duration_minutes} min."
        )

    response = client.post(
        f"{api_url.rstrip('/')}/api/routes",
        json={
            "start": start,
            "end": end,
            "start_label": "Paris",
            "end_label": "Grasse",
            "fuel_type": "SP95-E10",
            "fuel_price": 1.82,
            "max_extra_minutes": None,
            "min_savings": 0,
            "show_all": True,
            "motorway_consumption": 6.5,
            "road_consumption": 5.5,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("engine") != "graphhopper":
        raise RuntimeError("Routeco a basculé en mode démonstration.")
    routes = payload.get("routes", [])
    if not routes:
        raise RuntimeError("Routeco n'a renvoyé aucun itinéraire.")
    displayed_fastest = min(
        routes,
        key=lambda route: route["duration_minutes"],
    )
    if displayed_fastest["duration_minutes"] != fastest.duration_minutes:
        raise RuntimeError(
            "La référence GraphHopper et le plus rapide affiché divergent : "
            f"{fastest.duration_minutes} min contre "
            f"{displayed_fastest['duration_minutes']} min."
        )
    if "Plus rapide" not in displayed_fastest.get("tags", []):
        raise RuntimeError(
            "L'itinéraire au temps minimal n'est pas étiqueté « Plus rapide »."
        )

    print(
        "Référence rapide validée : "
        f"{fastest.duration_minutes} min / {fastest.distance_km:.1f} km ; "
        "ancien compromis : "
        f"{old_compromise.duration_minutes} min / "
        f"{old_compromise.distance_km:.1f} km."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie la véritable référence rapide Routeco."
    )
    parser.add_argument(
        "--api-url",
        default="http://127.0.0.1:8000",
    )
    parser.add_argument(
        "--graphhopper-url",
        default=settings.graphhopper_url,
    )
    args = parser.parse_args()
    with httpx.Client(timeout=240, trust_env=False) as client:
        verify(client, args.api_url, args.graphhopper_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

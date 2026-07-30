#!/usr/bin/env python3
from __future__ import annotations

import argparse

import httpx


def verify(client: httpx.Client, api_url: str) -> None:
    """Verify a regional journey where motorway and direct routes diverge.

    The coordinates are a regression scenario only. Production routing and
    selection remain entirely independent from any city or corridor.
    """
    response = client.post(
        f"{api_url.rstrip('/')}/api/routes",
        json={
            "start": {"lat": 43.6584, "lon": 6.9222},
            "end": {"lat": 45.8567, "lon": 6.6178},
            "start_label": "Grasse",
            "end_label": "Megève",
            "fuel_type": "SP95-E10",
            "fuel_price": 1.99,
            "max_extra_minutes": 45,
            "min_savings": 5,
            "show_all": False,
            "motorway_consumption": 6.5,
            "road_consumption": 5.5,
        },
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("engine") != "graphhopper":
        raise RuntimeError("Routeco a basculé en mode démonstration.")

    routes = payload.get("routes", [])
    route_summary = "; ".join(
        (
            f"{route.get('id', '?')}: "
            f"{route.get('duration_minutes', '?')} min, "
            f"{float(route.get('distance_km', 0)):.1f} km, "
            f"{float(route.get('motorway_km', 0)):.1f} km autoroute, "
            f"tags={route.get('tags', [])}"
        )
        for route in routes
    )
    if not 3 <= len(routes) <= 5:
        raise RuntimeError(
            "La sélection régionale devrait afficher entre trois et cinq "
            f"choix utiles ; résultat : {len(routes)}. {route_summary}"
        )
    durations = [int(route["duration_minutes"]) for route in routes]
    if durations[0] != min(durations):
        raise RuntimeError(
            "Le premier trajet affiché n'est pas le plus rapide. "
            f"{route_summary}"
        )

    motorway = max(routes, key=lambda route: float(route["motorway_km"]))
    direct = min(routes, key=lambda route: float(route["distance_km"]))
    distance_span = float(motorway["distance_km"]) - float(direct["distance_km"])
    motorway_span = float(motorway["motorway_km"]) - float(direct["motorway_km"])
    if distance_span < 80 or motorway_span < 100:
        raise RuntimeError(
            "Le grand choix autoroutier et le trajet direct ne sont pas tous "
            "les deux présents : "
            f"écart distance {distance_span:.1f} km, "
            f"écart autoroute {motorway_span:.1f} km. {route_summary}"
        )
    if "Autoroute" not in motorway.get("tags", []):
        raise RuntimeError(
            "Le choix autoroutier n'est pas identifié dans l'interface. "
            f"{route_summary}"
        )

    # The shortest displayed route is not necessarily a dedicated
    # "Moins de km" role. It can be only a few kilometres shorter than the
    # fastest route and already be present as an economic step. Production
    # deliberately avoids spending a display slot on such a rounding-level
    # difference. Require the badge only when the route is the fastest itself
    # or when it crosses the same materiality threshold as the selector.
    fastest = min(
        routes,
        key=lambda route: (
            int(route["duration_minutes"]),
            float(route["distance_km"]),
        ),
    )
    saved_km = float(fastest["distance_km"]) - float(direct["distance_km"])
    direct_is_role = (
        direct.get("id") == fastest.get("id")
        or saved_km >= max(8.0, float(fastest["distance_km"]) * 0.03)
    )
    if direct_is_role and "Moins de km" not in direct.get("tags", []):
        raise RuntimeError(
            "Le trajet réellement plus direct n'est pas identifié dans "
            f"l'interface. {route_summary}"
        )

    print(
        "Diversité régionale validée : "
        f"{payload.get('candidate_count', 0)} calculés, "
        f"{len(routes)} affichés ; "
        f"autoroutier {motorway['duration_minutes']} min / "
        f"{motorway['distance_km']:.1f} km, "
        f"direct {direct['duration_minutes']} min / "
        f"{direct['distance_km']:.1f} km."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie la diversité des itinéraires régionaux Routeco."
    )
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

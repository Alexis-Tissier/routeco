from __future__ import annotations

import hashlib
import math

from app.models import Coordinate
from app.services.geo import haversine_km


def _curve_points(start: Coordinate, end: Coordinate, bend: float, phase: float) -> list[list[float]]:
    points: list[list[float]] = []
    dx = end.lon - start.lon
    dy = end.lat - start.lat
    length = math.hypot(dx, dy) or 1
    nx, ny = -dy / length, dx / length
    for index in range(35):
        t = index / 34
        envelope = math.sin(math.pi * t)
        wave = math.sin((t + phase) * math.pi * 2) * 0.25
        offset = bend * envelope * (1 + wave)
        lon = start.lon + dx * t + nx * offset
        lat = start.lat + dy * t + ny * offset
        points.append([round(lon, 6), round(lat, 6)])
    return points


def demo_candidates(start: Coordinate, end: Coordinate) -> list[dict]:
    direct = max(25.0, haversine_km((start.lon, start.lat), (end.lon, end.lat)))
    seed = int(hashlib.sha1(f"{start.lat},{start.lon},{end.lat},{end.lon}".encode()).hexdigest()[:6], 16)
    jitter = ((seed % 9) - 4) / 100
    configs = [
        ("fast", 1.16 + jitter, 0.88, 0.090, 0.055, 0.03),
        ("light", 1.19 + jitter, 0.70, 0.071, 0.050, -0.04),
        ("mixed", 1.23 + jitter, 0.47, 0.042, 0.045, 0.08),
        ("free", 1.31 + jitter, 0.08, 0.000, 0.040, -0.10),
    ]
    results: list[dict] = []
    for index, (name, factor, motorway_share, toll_rate, bend, phase) in enumerate(configs):
        distance = direct * factor
        motorway_km = distance * motorway_share
        road_km = distance - motorway_km
        # Weighted travel time plus realistic transition/urban overhead.
        hours = motorway_km / 112 + road_km / 73 + 0.20 + index * 0.05
        results.append(
            {
                "id": f"demo-{name}",
                "distance_km": round(distance, 1),
                "duration_minutes": round(hours * 60),
                "motorway_km": round(motorway_km, 1),
                "road_km": round(road_km, 1),
                "tolled_km": round(motorway_km * (0.86 if toll_rate else 0), 1),
                "demo_toll": round(motorway_km * toll_rate, 2),
                "geometry": _curve_points(start, end, bend, phase),
                "source": "demo",
            }
        )
    return results

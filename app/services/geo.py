from __future__ import annotations

import math
from collections.abc import Iterable

EARTH_RADIUS_KM = 6371.0088


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance in km. Coordinates are (lon, lat)."""
    lon1, lat1 = map(math.radians, a)
    lon2, lat2 = map(math.radians, b)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def polyline_distance_km(points: Iterable[list[float]]) -> float:
    sequence = list(points)
    return sum(
        haversine_km((sequence[i - 1][0], sequence[i - 1][1]), (sequence[i][0], sequence[i][1]))
        for i in range(1, len(sequence))
    )


def point_segment_projection_km(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    """Return (lateral distance in km, segment fraction from 0 to 1)."""
    lon, lat = point
    lat0 = math.radians(lat)
    x = lon * math.cos(lat0) * 111.32
    y = lat * 110.574
    x1 = start[0] * math.cos(lat0) * 111.32
    y1 = start[1] * 110.574
    x2 = end[0] * math.cos(lat0) * 111.32
    y2 = end[1] * 110.574
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x - x1, y - y1), 0.0
    fraction = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    distance = math.hypot(x - (x1 + fraction * dx), y - (y1 + fraction * dy))
    return distance, fraction


def point_segment_distance_km(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    """Fast local planar approximation, sufficient for toll-station matching."""
    return point_segment_projection_km(point, start, end)[0]

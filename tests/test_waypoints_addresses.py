from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models import Coordinate, GeocodeResult, RouteRequest
from app.services.geocoder import LocalGeocoder
from app.services.routing import GraphHopperClient


class StubGeocoder(LocalGeocoder):
    def __init__(self) -> None:
        self.database_path = Path("/missing-ban.sqlite")
        self.communes_database_path = Path("/missing-communes.sqlite")
        self.demo_places = []

    def _search_ban(self, query: str, limit: int) -> list[GeocodeResult]:
        del query, limit
        return [
            GeocodeResult(
                label="12 Rue de Paris 78000 Versailles",
                city="Versailles",
                postcode="78000",
                lat=48.801,
                lon=2.130,
                source="ban",
                kind="address",
            )
        ]

    def _search_communes(self, query: str, limit: int) -> list[GeocodeResult]:
        del query, limit
        return [
            GeocodeResult(
                label="Versailles (78000 · 78)",
                city="Versailles",
                postcode="78000",
                lat=48.804,
                lon=2.120,
                source="commune",
                kind="municipality",
                code="78646",
                department_code="78",
            )
        ]


def test_address_like_query_prioritizes_ban_address() -> None:
    results = StubGeocoder().search("12 rue de Paris Versailles")
    assert results[0].kind == "address"


def test_city_query_prioritizes_commune_center() -> None:
    results = StubGeocoder().search("Versailles")
    assert results[0].kind == "municipality"


def test_route_request_accepts_ordered_waypoints() -> None:
    request = RouteRequest(
        start={"lat": 48.8, "lon": 2.1},
        end={"lat": 48.9, "lon": 2.2},
        via=[
            {"lat": 48.81, "lon": 2.12},
            {"lat": 48.82, "lon": 2.14},
        ],
        via_labels=["Arrêt A", " Arrêt B "],
    )
    assert len(request.via) == 2
    assert request.via_labels == ["Arrêt A", "Arrêt B"]


def test_route_request_rejects_more_than_three_waypoints() -> None:
    with pytest.raises(ValidationError):
        RouteRequest(
            start={"lat": 48.8, "lon": 2.1},
            end={"lat": 48.9, "lon": 2.2},
            via=[
                {"lat": 48.81, "lon": 2.11},
                {"lat": 48.82, "lon": 2.12},
                {"lat": 48.83, "lon": 2.13},
                {"lat": 48.84, "lon": 2.14},
            ],
        )


def test_routing_cache_key_includes_ordered_waypoints() -> None:
    start = Coordinate(lat=48.8, lon=2.1)
    end = Coordinate(lat=47.3, lon=5.0)
    chartres = Coordinate(lat=48.45, lon=1.49)
    orleans = Coordinate(lat=47.90, lon=1.91)

    direct = GraphHopperClient._cache_key(start, end)
    through_chartres = GraphHopperClient._cache_key(start, end, [chartres])
    through_orleans = GraphHopperClient._cache_key(start, end, [orleans])
    reversed_stops = GraphHopperClient._cache_key(
        start,
        end,
        [orleans, chartres],
    )
    ordered_stops = GraphHopperClient._cache_key(
        start,
        end,
        [chartres, orleans],
    )

    assert direct != through_chartres
    assert through_chartres != through_orleans
    assert ordered_stops != reversed_stops


def test_frontend_exposes_waypoint_and_map_picker() -> None:
    app_js = Path("static/app.js").read_text(encoding="utf-8")
    map_js = Path("static/map-adapter.js").read_text(encoding="utf-8")

    assert "id = 'via-field'" in app_js
    assert "via: via ? [via] : []" in app_js
    assert "Choisir sur la carte" in app_js
    assert "pickPoint(callback)" in map_js

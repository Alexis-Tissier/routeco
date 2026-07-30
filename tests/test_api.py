from fastapi.testclient import TestClient

from app.main import app
from app.models import GeocodeResult
from app.services.geocoder import AmbiguousLocationError

client = TestClient(app)


def test_geocode_resolve_reports_homonyms_instead_of_guessing(monkeypatch):
    from app.main import geocoder

    choices = [
        GeocodeResult(
            label="Saint-Aubin (31460 · 31)",
            city="Saint-Aubin",
            postcode="31460",
            department_code="31",
            code="31470",
            lat=43.696,
            lon=1.758,
            source="commune",
            kind="municipality",
        ),
        GeocodeResult(
            label="Saint-Aubin (40250 · 40)",
            city="Saint-Aubin",
            postcode="40250",
            department_code="40",
            code="40249",
            lat=43.712,
            lon=-0.699,
            source="commune",
            kind="municipality",
        ),
    ]

    def ambiguous(query: str):
        raise AmbiguousLocationError(query, choices)

    monkeypatch.setattr(geocoder, "resolve", ambiguous)
    response = client.get("/api/geocode/resolve", params={"q": "Saint-Aubin"})

    assert response.status_code == 409
    assert len(response.json()["detail"]["choices"]) == 2


def test_home():
    assert client.get("/").status_code == 200


def test_demo_route_calculation():
    response = client.post("/api/routes", json={
        "start": {"lat": 48.8566, "lon": 2.3522},
        "end": {"lat": 45.7640, "lon": 4.8357},
        "fuel_type": "SP95-E10",
        "fuel_price": 1.82,
        "max_extra_minutes": 60,
        "show_all": False,
        "motorway_consumption": 6.5,
        "road_consumption": 5.5
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["routes"]
    assert payload["engine"] in {"demo", "graphhopper"}
    assert payload["candidate_count"] >= len(payload["routes"])


def test_slower_more_expensive_routes_are_not_presented_as_useful(monkeypatch):
    from app.main import routing
    from app.services.routing import EngineResult

    async def fake_candidates(start, end):
        geometry = [[2.0, 48.0], [3.0, 47.0]]
        return EngineResult(
            engine="graphhopper",
            message="3 itinéraires candidats calculés localement.",
            candidates=[
                {
                    "id": "fast", "distance_km": 100.0, "duration_minutes": 100,
                    "motorway_km": 90.0, "road_km": 10.0, "tolled_km": 0.0,
                    "toll_ranges": [], "geometry": geometry, "source": "graphhopper",
                },
                {
                    "id": "different", "distance_km": 105.0, "duration_minutes": 120,
                    "motorway_km": 40.0, "road_km": 65.0, "tolled_km": 0.0,
                    "toll_ranges": [], "geometry": [[2.0, 48.0], [2.5, 46.8], [3.0, 47.0]],
                    "source": "graphhopper",
                },
                {
                    "id": "slow", "distance_km": 110.0, "duration_minutes": 130,
                    "motorway_km": 20.0, "road_km": 90.0, "tolled_km": 0.0,
                    "toll_ranges": [], "geometry": [[2.0, 48.0], [2.2, 46.5], [3.0, 47.0]],
                    "source": "graphhopper",
                },
            ],
        )

    monkeypatch.setattr(routing, "candidates", fake_candidates)
    response = client.post("/api/routes", json={
        "start": {"lat": 48.8566, "lon": 2.3522},
        "end": {"lat": 45.7640, "lon": 4.8357},
        "fuel_type": "SP95-E10",
        "fuel_price": 1.82,
        "max_extra_minutes": 45,
        "min_savings": 0,
        "show_all": False,
        "motorway_consumption": 6.5,
        "road_consumption": 5.5,
    })
    assert response.status_code == 200
    payload = response.json()
    ids = [route["id"] for route in payload["routes"]]
    assert ids == ["fast"]
    assert payload["candidate_count"] == 3
    assert payload["hidden_count"] == 2


def test_minimum_savings_keeps_fastest_and_filters_weak_alternatives(monkeypatch):
    from app.main import routing
    from app.services.routing import EngineResult

    async def fake_candidates(start, end):
        geometry = [[2.0, 48.0], [3.0, 47.0]]
        return EngineResult(
            engine="graphhopper",
            message="3 itinéraires candidats calculés localement.",
            candidates=[
                {"id": "fast", "distance_km": 100.0, "duration_minutes": 100,
                 "motorway_km": 100.0, "road_km": 0.0, "tolled_km": 0.0,
                 "toll_ranges": [], "geometry": geometry, "source": "graphhopper"},
                {"id": "weak", "distance_km": 99.0, "duration_minutes": 110,
                 "motorway_km": 99.0, "road_km": 0.0, "tolled_km": 0.0,
                 "toll_ranges": [], "geometry": geometry, "source": "graphhopper"},
                {"id": "strong", "distance_km": 70.0, "duration_minutes": 120,
                 "motorway_km": 0.0, "road_km": 70.0, "tolled_km": 0.0,
                 "toll_ranges": [], "geometry": geometry, "source": "graphhopper"},
            ],
        )

    monkeypatch.setattr(routing, "candidates", fake_candidates)
    response = client.post("/api/routes", json={
        "start": {"lat": 48.0, "lon": 2.0}, "end": {"lat": 47.0, "lon": 3.0},
        "fuel_price": 2.0, "max_extra_minutes": 45, "min_savings": 3,
        "motorway_consumption": 6.5, "road_consumption": 5.5,
    })
    payload = response.json()
    assert payload["candidate_count"] == 3
    assert [route["id"] for route in payload["routes"]] == ["fast", "strong"]

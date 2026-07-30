import json
from pathlib import Path

import pytest

from app.services.geocoder import AmbiguousLocationError, LocalGeocoder
from scripts.update_communes import build_database


def commune(
    code: str,
    name: str,
    postcode: str,
    department: str,
    lon: float,
    lat: float,
    population: int,
) -> dict:
    return {
        "code": code,
        "nom": name,
        "codesPostaux": [postcode],
        "codeDepartement": department,
        "population": population,
        "centre": {"type": "Point", "coordinates": [lon, lat]},
    }


@pytest.fixture
def geocoder(tmp_path: Path) -> LocalGeocoder:
    communes_path = tmp_path / "communes.sqlite"
    build_database(
        [
            commune("78646", "Versailles", "78000", "78", 2.1301, 48.8014, 83_583),
            commune("31470", "Saint-Aubin", "31460", "31", 1.758, 43.696, 540),
            commune("40249", "Saint-Aubin", "40250", "40", -0.699, 43.712, 570),
        ],
        communes_path,
        minimum_count=3,
    )
    demo_path = tmp_path / "demo.json"
    demo_path.write_text(
        json.dumps(
            [
                {
                    "label": "Paris, 75001",
                    "city": "Paris",
                    "postcode": "75001",
                    "lat": 48.8566,
                    "lon": 2.3522,
                }
            ]
        ),
        encoding="utf-8",
    )
    return LocalGeocoder(tmp_path / "missing-ban.sqlite", demo_path, communes_path)


def test_any_indexed_commune_is_available_without_its_ban_department(
    geocoder: LocalGeocoder,
) -> None:
    results = geocoder.search("Versailles")

    assert results[0].source == "commune"
    assert results[0].city == "Versailles"
    assert results[0].postcode == "78000"
    assert results[0].label == "Versailles (78000 · 78)"


def test_unambiguous_free_text_commune_resolves_without_suggestion_click(
    geocoder: LocalGeocoder,
) -> None:
    result = geocoder.resolve("versailles")

    assert result.code == "78646"
    assert result.lat == pytest.approx(48.8014)
    assert result.lon == pytest.approx(2.1301)


def test_postcode_and_city_resolve_the_same_commune(geocoder: LocalGeocoder) -> None:
    result = geocoder.resolve("78000 Versailles")

    assert result.code == "78646"


def test_homonymous_commune_requires_an_explicit_choice(
    geocoder: LocalGeocoder,
) -> None:
    with pytest.raises(AmbiguousLocationError) as caught:
        geocoder.resolve("Saint-Aubin")

    assert {choice.department_code for choice in caught.value.choices} == {"31", "40"}

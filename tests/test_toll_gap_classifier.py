from __future__ import annotations

from app.services.toll_gap_classifier import classify_unresolved_interval


def _item(**updates):
    value = {
        "route_start_km": 10.0,
        "route_end_km": 20.0,
        "unresolved_km": 10.0,
        "nearby_stations": [],
        "exact_segments": [],
    }
    value.update(updates)
    return value


def test_known_open_tariff_not_selected() -> None:
    cause = classify_unresolved_interval(
        _item(
            nearby_stations=[
                {
                    "name": "Portique Gamma",
                    "system_type": "open",
                    "physical_type": "open",
                    "route_km": 15.0,
                    "lateral_km": 0.02,
                    "open_price": 3.2,
                }
            ]
        )
    )
    assert cause == "known_open_tariff_not_selected"


def test_small_fragment_next_to_exact_boundary_is_overhang() -> None:
    cause = classify_unresolved_interval(
        _item(
            route_start_km=20.0,
            route_end_km=20.3,
            unresolved_km=0.3,
            exact_segments=[
                {
                    "entry": "Alpha",
                    "exit": "Bravo",
                    "route_start_km": 0.0,
                    "route_end_km": 20.0,
                }
            ],
        )
    )
    assert cause == "boundary_overhang"


def test_closed_stations_on_both_boundaries_request_matrix() -> None:
    cause = classify_unresolved_interval(
        _item(
            nearby_stations=[
                {
                    "name": "Alpha",
                    "system_type": "closed",
                    "physical_type": "closed",
                    "distance_to_interval_start_km": 0.1,
                    "distance_to_interval_end_km": 9.9,
                },
                {
                    "name": "Bravo",
                    "system_type": "closed",
                    "physical_type": "closed",
                    "distance_to_interval_start_km": 9.8,
                    "distance_to_interval_end_km": 0.2,
                },
            ]
        )
    )
    assert cause == "missing_closed_matrix"


def test_no_nearby_station_is_unknown_corridor() -> None:
    assert classify_unresolved_interval(_item()) == "unknown_osm_corridor"

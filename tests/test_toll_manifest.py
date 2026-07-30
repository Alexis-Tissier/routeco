from __future__ import annotations

from app.services.toll_manifest import (
    build_missing_toll_manifest,
    render_missing_toll_manifest,
)


def test_manifest_aggregates_station_and_corridor_candidates() -> None:
    payload = {
        "generated_at": "2026-07-30T10:45:54Z",
        "summary": {
            "errors": 1,
        },
        "results": [
            {
                "id": "scenario",
                "name": "Scénario",
                "routes": [
                    {
                        "id": "route",
                        "toll_diagnostics": [
                            {
                                "kind": "unresolved_toll_interval",
                                "route_start_km": 10.0,
                                "route_end_km": 20.0,
                                "unresolved_km": 10.0,
                                "nearby_stations": [
                                    {
                                        "name": "Portique Alpha",
                                        "operator": "TEST",
                                        "system_type": "open",
                                        "physical_type": "mainline",
                                        "route_km": 10.2,
                                        "lateral_km": 0.02,
                                        "open_price": None,
                                    },
                                    {
                                        "name": "Sortie Bravo",
                                        "operator": "TEST",
                                        "system_type": "closed",
                                        "physical_type": "closed",
                                        "route_km": 19.8,
                                        "lateral_km": 0.03,
                                        "open_price": None,
                                    },
                                ],
                                "toll_states": [],
                                "exact_segments": [],
                            }
                        ],
                    }
                ],
            }
        ],
    }

    manifest = build_missing_toll_manifest(payload)

    assert manifest["summary"]["unresolved_intervals"] == 1
    assert manifest["summary"]["affected_routes"] == 1
    assert len(manifest["station_review_candidates"]) == 1
    assert (
        manifest["station_review_candidates"][0]["kind"]
        == "missing_open_tariff"
    )
    assert len(manifest["corridor_review_candidates"]) == 1

    markdown = render_missing_toll_manifest(manifest)
    assert "Portique Alpha" in markdown
    assert "10.0→20.0 km" in markdown

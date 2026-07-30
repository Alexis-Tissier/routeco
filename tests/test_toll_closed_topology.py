from __future__ import annotations

import csv
from pathlib import Path

from app.services.toll_gap_classifier import (
    classify_unresolved_interval,
)
from app.services.toll_manifest import build_missing_toll_manifest
from app.services.tolls import (
    StationProjection,
    TollPricingService,
    TollSegmentQuote,
    TollStation,
)


def _write_csv(
    path: Path,
    fields: list[str],
    rows: list[dict[str, str]],
) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _service(
    tmp_path: Path,
    matrices: list[dict[str, str]],
) -> TollPricingService:
    _write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [],
    )
    _write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        matrices,
    )
    _write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )
    return TollPricingService(tmp_path)


def _projection(
    name: str,
    operator: str,
    route_km: float,
    *,
    lateral_km: float = 0.01,
) -> StationProjection:
    return StationProjection(
        station=TollStation(
            name=name,
            osm_name=name.title(),
            operator=operator,
            lat=45.0,
            lon=route_km / 100.0,
            system_type="closed",
            physical_type="closed",
        ),
        route_km=route_km,
        lateral_km=lateral_km,
        segment_index=1,
    )


def test_topology_finds_one_official_matrix(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "ALPHA",
                "name_to": "BRAVO",
                "distance": "30",
                "price1": "4.50",
            }
        ],
    )

    analysis = service._analyze_closed_interval_topology(
        interval_start_km=10.0,
        interval_end_km=40.0,
        projections=[
            _projection("ALPHA", "TEST", 10.0),
            _projection("BRAVO", "TEST", 40.0),
        ],
        segments=[],
    )

    assert analysis["decision"] == "unique_official_matrix"
    assert analysis["available_matrix_count"] == 1
    assert analysis["matrix_candidates"][0]["price"] == 4.5


def test_topology_reports_missing_matrix(tmp_path: Path) -> None:
    service = _service(tmp_path, [])

    analysis = service._analyze_closed_interval_topology(
        interval_start_km=10.0,
        interval_end_km=40.0,
        projections=[
            _projection("ALPHA", "TEST", 10.0),
            _projection("BRAVO", "TEST", 40.0),
        ],
        segments=[],
    )

    assert analysis["decision"] == "boundary_pair_without_matrix"
    assert "no_official_matrix" in (
        analysis["matrix_candidates"][0]["reasons"]
    )


def test_topology_rejects_overlap_with_existing_journey(
    tmp_path: Path,
) -> None:
    service = _service(
        tmp_path,
        [
            {
                "operator": "TEST",
                "name_from": "ALPHA",
                "name_to": "BRAVO",
                "distance": "30",
                "price1": "4.50",
            }
        ],
    )
    existing = TollSegmentQuote(
        entry="EXISTING A",
        exit="EXISTING B",
        operator="TEST",
        cost=3.0,
        distance_km=20.0,
        confidence="exact",
        route_start_km=20.0,
        route_end_km=35.0,
    )

    analysis = service._analyze_closed_interval_topology(
        interval_start_km=10.0,
        interval_end_km=40.0,
        projections=[
            _projection("ALPHA", "TEST", 10.0),
            _projection("BRAVO", "TEST", 40.0),
        ],
        segments=[existing],
    )

    assert analysis["available_matrix_count"] == 0
    assert "overlaps_existing_closed_segment" in (
        analysis["matrix_candidates"][0]["reasons"]
    )


def test_classifier_uses_closed_topology_decision() -> None:
    occurrence = {
        "unresolved_km": 20.0,
        "nearby_stations": [],
        "exact_segments": [],
        "closed_topology": {
            "decision": "unique_official_matrix",
        },
    }

    assert (
        classify_unresolved_interval(occurrence)
        == "closed_matrix_candidate_available"
    )


def test_manifest_preserves_closed_topology() -> None:
    topology = {
        "decision": "boundary_pair_without_matrix",
        "available_matrix_count": 0,
        "matrix_candidates": [],
    }
    validation = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "summary": {},
        "results": [
            {
                "id": "generic",
                "name": "Generic",
                "routes": [
                    {
                        "id": "route",
                        "toll_diagnostics": [
                            {
                                "kind": "unresolved_toll_interval",
                                "route_start_km": 10.0,
                                "route_end_km": 30.0,
                                "unresolved_km": 20.0,
                                "nearby_stations": [],
                                "exact_segments": [],
                                "toll_states": [],
                                "closed_topology": topology,
                            }
                        ],
                    }
                ],
            }
        ],
    }

    manifest = build_missing_toll_manifest(validation)

    occurrence = manifest["unresolved_intervals"][0]
    assert occurrence["closed_topology"] == topology
    assert occurrence["cause"] == "missing_closed_matrix"

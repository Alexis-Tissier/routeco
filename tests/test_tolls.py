from __future__ import annotations

import csv
from pathlib import Path

from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def make_service(tmp_path: Path) -> TollPricingService:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "PEAGE DE FLEURY EN BIERE",
                "osm_name": "Péage de Fleury-en-Bière",
                "operator": "APRR",
                "lat": "48.4266295",
                "lon": "2.5401807",
                "type": "closed",
            },
            {
                "name": "PEAGE DE VILLEFRANCHE LIMAS",
                "osm_name": "Péage de Villefranche-Limas",
                "operator": "APRR",
                "lat": "45.9732236",
                "lon": "4.7324254",
                "type": "closed",
            },
            {
                "name": "BARRIERE TEST",
                "osm_name": "Barrière test",
                "operator": "ASF",
                "lat": "44.5000",
                "lon": "4.8000",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "APRR",
                "name_from": "PEAGE DE FLEURY EN BIERE",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "430.28",
                "price1": "41.30",
            },
            {
                "operator": "APRR",
                "name_from": "PEAGE DE VILLEFRANCHE LIMAS",
                "name_to": "PEAGE DE FLEURY EN BIERE",
                "distance": "430.28",
                "price1": "41.30",
            },
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "ASF",
                "name": "BARRIERE TEST",
                "distance": "1.0",
                "price1": "2.40",
            }
        ],
    )
    return TollPricingService(tmp_path)


def test_exact_closed_toll_from_graphhopper_range(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [
        [2.45, 48.55],
        [2.5401807, 48.4266295],
        [3.70, 47.20],
        [4.7324254, 45.9732236],
        [4.84, 45.75],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=397.0,
        toll_ranges=[{"start_index": 1, "end_index": 3, "distance_km": 397.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 41.30
    assert quote.stations == ["Péage de Fleury-en-Bière", "Péage de Villefranche-Limas"]


def test_exact_open_barrier(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [[4.79, 44.49], [4.80, 44.50], [4.81, 44.51]]

    quote = service.quote(
        geometry=geometry,
        tolled_km=1.5,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.5}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 2.40
    assert quote.stations == ["Barrière test"]


def test_estimate_when_no_reliable_station_pair(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [[0.0, 45.0], [0.5, 45.1], [1.0, 45.2]]

    quote = service.quote(
        geometry=geometry,
        tolled_km=100.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 100.0}],
    )

    assert quote.confidence == "estimated"
    assert quote.cost == 10.50


def test_graphhopper_toll_details_are_merged() -> None:
    geometry = [[2.0, 48.0], [2.1, 47.9], [2.2, 47.8], [2.3, 47.7], [2.4, 47.6]]
    details = [[0, 2, "ALL"], [2, 4, "ALL"]]

    ranges = GraphHopperClient._detail_ranges(geometry, details, {"ALL", "HGV"})

    assert len(ranges) == 1
    assert ranges[0]["start_index"] == 0
    assert ranges[0]["end_index"] == 4
    assert ranges[0]["distance_km"] > 0


def test_exact_closed_toll_when_osm_range_boundaries_are_far_from_plazas(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [
        [2.35, 48.85],          # Paris: toll tag can start before the plaza
        [2.45, 48.55],
        [2.5401807, 48.4266295],
        [3.70, 47.20],
        [4.7324254, 45.9732236],
        [4.84, 45.75],          # Lyon: toll tag can end after the plaza
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=397.0,
        toll_ranges=[{"start_index": 0, "end_index": 5, "distance_km": 397.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 41.30
    assert quote.stations == ["Péage de Fleury-en-Bière", "Péage de Villefranche-Limas"]


def test_long_mainline_route_prefers_crossed_barrier_over_nearby_exit(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "PEAGE DE FLEURY EN BIERE",
                "osm_name": "Péage de Fleury-en-Bière",
                "operator": "APRR",
                "lat": "48.4266295",
                "lon": "2.5401807",
                "type": "closed",
            },
            {
                "name": "FONTAINEBLEAU",
                "osm_name": "Fontainebleau",
                "operator": "APRR",
                "lat": "48.2896884",
                "lon": "2.6832481",
                "type": "closed",
            },
            {
                "name": "PEAGE DE VILLEFRANCHE LIMAS",
                "osm_name": "Péage de Villefranche-Limas",
                "operator": "APRR",
                "lat": "45.9732236",
                "lon": "4.7324254",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "APRR",
                "name_from": "PEAGE DE FLEURY EN BIERE",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "430.28",
                "price1": "41.30",
            },
            {
                "operator": "APRR",
                "name_from": "FONTAINEBLEAU",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "387.33",
                "price1": "36.80",
            },
        ],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)

    # The route crosses the Fleury mainline barrier. The Fontainebleau exit plaza
    # is merely close to the motorway and must not be treated as the entry point.
    geometry = [
        [2.35, 48.85],
        [2.45, 48.55],
        [2.5401807, 48.4266295],
        [3.70, 47.20],
        [4.7324254, 45.9732236],
        [4.84, 45.75],
    ]
    quote = service.quote(
        geometry=geometry,
        tolled_km=397.0,
        toll_ranges=[{"start_index": 0, "end_index": 5, "distance_km": 397.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 41.30
    assert quote.stations == ["Péage de Fleury-en-Bière", "Péage de Villefranche-Limas"]


def test_mainline_barrier_marker_is_not_removed_by_name_normalization() -> None:
    from app.services.tolls import TollStation

    barrier = TollStation(
        name="PEAGE DE FLEURY EN BIERE",
        osm_name="",
        operator="APRR",
        lat=48.4266295,
        lon=2.5401807,
        system_type="closed",
    )
    exit_plaza = TollStation(
        name="FONTAINEBLEAU",
        osm_name="",
        operator="APRR",
        lat=48.2896884,
        lon=2.6832481,
        system_type="closed",
    )

    assert barrier.is_mainline_barrier is True
    assert exit_plaza.is_mainline_barrier is False


def test_long_route_uses_mainline_pair_before_boundary_exit_pair(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "PEAGE DE FLEURY EN BIERE",
                "osm_name": "Péage de Fleury-en-Bière",
                "operator": "APRR",
                "lat": "48.4266295",
                "lon": "2.5401807",
                "type": "closed",
            },
            {
                "name": "FONTAINEBLEAU",
                "osm_name": "Fontainebleau",
                "operator": "APRR",
                "lat": "48.2896884",
                "lon": "2.6832481",
                "type": "closed",
            },
            {
                "name": "PEAGE DE VILLEFRANCHE LIMAS",
                "osm_name": "Péage de Villefranche-Limas",
                "operator": "APRR",
                "lat": "45.9732236",
                "lon": "4.7324254",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "APRR",
                "name_from": "PEAGE DE FLEURY EN BIERE",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "430.28",
                "price1": "41.30",
            },
            {
                "operator": "APRR",
                "name_from": "FONTAINEBLEAU",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "387.33",
                "price1": "36.80",
            },
        ],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)

    # Geometry deliberately passes close to both Fleury-en-Bière and the
    # Fontainebleau exit plaza. The GraphHopper toll range starts at the latter,
    # reproducing the real Paris-Lyon failure seen in v1.6.
    geometry = [
        [2.35, 48.85],
        [2.5401807, 48.4266295],
        [2.6832481, 48.2896884],
        [3.70, 47.20],
        [4.7324254, 45.9732236],
        [4.84, 45.75],
    ]
    quote = service.quote(
        geometry=geometry,
        tolled_km=397.0,
        toll_ranges=[{"start_index": 2, "end_index": 5, "distance_km": 397.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 41.30
    assert quote.stations == ["Péage de Fleury-en-Bière", "Péage de Villefranche-Limas"]


def test_separate_toll_ranges_do_not_charge_same_route_wide_pair_twice(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [
        [2.35, 48.85],
        [2.5401807, 48.4266295],
        [2.95, 48.05],
        [3.10, 47.90],
        [3.25, 47.75],
        [3.40, 47.60],
        [3.65, 47.30],
        [4.20, 46.55],
        [4.7324254, 45.9732236],
        [4.84, 45.75],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=360.0,
        toll_ranges=[
            {"start_index": 0, "end_index": 2, "distance_km": 175.0},
            {"start_index": 6, "end_index": 9, "distance_km": 185.0},
        ],
    )

    # The full Fleury→Villefranche fare is not valid for each separated range.
    # Until both local entry/exit pairs are identified, the honest result is an
    # estimate, never 2 × 41.30 €.
    assert quote.confidence == "estimated"
    assert quote.cost == 37.80
    assert quote.cost != 82.60


def test_second_closed_range_accepts_exit_barrier_16km_before_osm_toll_end(tmp_path: Path) -> None:
    """Regression for Paris→Lyon mixed route: Chalon Centre→Villefranche-Limas.

    GraphHopper's second toll range ends about 16.4 km after the physical
    Villefranche-Limas barrier. The boundary matcher must still resolve the
    official matrix pair, while preferring the mainline barrier over the nearby
    Villefranche-Ville ramp plaza.
    """
    from app.services.tolls import StationProjection, TollRange, TollStation

    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "CHALON CENTRE",
                "osm_name": "Chalon Centre",
                "operator": "APRR",
                "lat": "46.78",
                "lon": "4.84",
                "type": "closed",
            },
            {
                "name": "VILLEFRANCHE VILLE",
                "osm_name": "Villefranche Ville",
                "operator": "APRR",
                "lat": "45.99",
                "lon": "4.73",
                "type": "closed",
            },
            {
                "name": "PEAGE DE VILLEFRANCHE LIMAS",
                "osm_name": "Péage de Villefranche-Limas",
                "operator": "APRR",
                "lat": "45.9732236",
                "lon": "4.7324254",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "APRR",
                "name_from": "CHALON CENTRE",
                "name_to": "VILLEFRANCHE VILLE",
                "distance": "97.85",
                "price1": "7.90",
            },
            {
                "operator": "APRR",
                "name_from": "CHALON CENTRE",
                "name_to": "PEAGE DE VILLEFRANCHE LIMAS",
                "distance": "128.30",
                "price1": "11.50",
            },
        ],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)

    stations = {station.name: station for station in service.stations}
    projections = [
        StationProjection(stations["CHALON CENTRE"], 327.2, 0.01, 1),
        StationProjection(stations["VILLEFRANCHE VILLE"], 425.8, 0.02, 2),
        StationProjection(stations["PEAGE DE VILLEFRANCHE LIMAS"], 426.3, 0.04, 3),
    ]
    toll_range = TollRange(
        start_index=0,
        end_index=3,
        start_km=327.2,
        end_km=442.7,
        distance_km=115.5,
    )

    pair = service._best_closed_pair(projections, toll_range)

    assert pair is not None
    record, entry, exit_ = pair
    assert record.price == 11.50
    assert entry.station.name == "CHALON CENTRE"
    assert exit_.station.name == "PEAGE DE VILLEFRANCHE LIMAS"


def test_exact_quote_exposes_structured_segment(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    geometry = [
        [2.45, 48.55],
        [2.5401807, 48.4266295],
        [3.70, 47.20],
        [4.7324254, 45.9732236],
        [4.84, 45.75],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=397.0,
        toll_ranges=[{"start_index": 1, "end_index": 3, "distance_km": 397.0}],
    )

    assert len(quote.segments) == 1
    segment = quote.segments[0]
    assert segment.entry == "Péage de Fleury-en-Bière"
    assert segment.exit == "Péage de Villefranche-Limas"
    assert segment.operator == "APRR"
    assert segment.cost == 41.30
    assert segment.confidence == "exact"


def test_estimated_quote_exposes_estimated_segment(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    quote = service.quote(
        geometry=[[0.0, 45.0], [0.5, 45.1], [1.0, 45.2]],
        tolled_km=100.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 100.0}],
    )

    assert len(quote.segments) == 1
    assert quote.segments[0].confidence == "estimated"
    assert quote.segments[0].distance_km == 100.0
    assert quote.segments[0].cost == quote.cost == 10.50


def test_official_sanef_aliases_are_loaded():
    from app.services.tolls import TollStation

    service = TollPricingService(Path("data/tolls"))
    entry = TollStation("Chamant", "OFFICIAL", 49.2, 2.6, "mainline")
    exit_ = TollStation("Fresnes", "OFFICIAL", 50.3, 2.9, "mainline")
    record = service._lookup_closed(entry, exit_)
    assert record is not None
    assert record.operator == "SANEF"
    assert record.price == 18.9


def test_official_sapn_group_price_is_loaded():
    from app.services.tolls import TollStation

    service = TollPricingService(Path("data/tolls"))
    entry = TollStation(
        "POISSY / ORGEVAL N°7 à MANTES-SUD N°12", "SAPN", 48.98, 1.68, "mainline"
    )
    exit_ = TollStation(
        "CRIQUEBEUF N°20 à MAISON-BRÛLEE N°24 / ROUEN LES ESSARTS (A139)",
        "SAPN",
        49.32,
        1.01,
        "closed",
    )
    record = service._lookup_closed(entry, exit_)
    assert record is not None
    assert record.price == 7.5


def test_unmatched_micro_toll_is_ignored(tmp_path):
    service = TollPricingService(tmp_path)
    quote = service.quote([[2.0, 48.0], [2.01, 48.01]], 0.4, [])
    assert quote.cost == 0
    assert quote.confidence == "none"


def test_sanef_route_geometry_resolves_exactly():
    service = TollPricingService(Path("data/tolls"))
    geometry = [
        [2.35, 48.86],
        [2.6277637, 49.2157943],  # Chamant
        [2.9115710, 50.3248423],  # Fresnes
        [3.0573, 50.6292],
    ]
    quote = service.quote(
        geometry,
        152.7,
        [{"start_index": 1, "end_index": 2, "distance_km": 152.7}],
    )
    assert quote.confidence == "exact"
    assert quote.cost == 18.9


def test_sapn_flux_free_group_resolves_exactly():
    service = TollPricingService(Path("data/tolls"))
    geometry = [
        [2.3522, 48.8566],
        [1.6811606, 48.9836349],  # Buchelay flux-free gantry
        [1.2326316, 49.1912869],  # Heudebouville flux-free gantry
        [1.0065, 49.3216],  # Rouen Les Essarts tariff group
        [1.0993, 49.4432],
    ]
    quote = service.quote(
        geometry,
        55.7,
        [{"start_index": 1, "end_index": 3, "distance_km": 55.7}],
    )
    assert quote.confidence == "exact"
    assert quote.cost == 7.5


def test_tiny_osm_range_never_matches_a_distant_closed_matrix_pair(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "START", "osm_name": "Start", "operator": "APRR", "lat": "48.0", "lon": "2.0", "type": "closed"},
            {"name": "END", "osm_name": "End", "operator": "APRR", "lat": "46.0", "lon": "4.0", "type": "closed"},
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [{"operator": "APRR", "name_from": "START", "name_to": "END", "distance": "269.5", "price1": "24.80"}],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)

    quote = service.quote(
        geometry=[[2.0, 48.0], [3.0, 47.0], [4.0, 46.0]],
        tolled_km=0.1,
        toll_ranges=[{"start_index": 0, "end_index": 1, "distance_km": 0.1}],
    )

    assert quote.confidence == "none"
    assert quote.cost == 0.0


def test_sapn_flux_free_open_gantries_are_summed_exactly(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "BUCHELAY", "osm_name": "Buchelay", "operator": "OFFICIAL", "lat": "48.9836349", "lon": "1.6811606", "type": "mainline"},
            {"name": "HEUDEBOUVILLE", "osm_name": "Heudebouville", "operator": "OFFICIAL", "lat": "49.1912869", "lon": "1.2326316", "type": "mainline"},
        ],
    )
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {"operator": "SAPN", "name": "BUCHELAY", "distance": "", "price1": "3.00"},
            {"operator": "SAPN", "name": "HEUDEBOUVILLE", "distance": "", "price1": "4.50"},
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [
        [2.0, 48.9],
        [1.6811606, 48.9836349],
        [1.2326316, 49.1912869],
        [1.1, 49.44],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=55.7,
        toll_ranges=[{"start_index": 1, "end_index": 2, "distance_km": 55.7}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 7.50
    assert [segment.cost for segment in quote.segments] == [3.0, 4.5]


def test_long_closed_system_is_not_replaced_by_open_plazas_inside_range(tmp_path: Path) -> None:
    """Open gantries near a long closed journey must not override its matrix fare."""
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "TEST", "lat": "48.0", "lon": "2.0", "type": "closed"},
            {"name": "MID GANTRY", "osm_name": "Mid Gantry", "operator": "TEST", "lat": "47.5", "lon": "2.5", "type": "open"},
            {"name": "EXIT", "osm_name": "Exit", "operator": "TEST", "lat": "47.0", "lon": "3.0", "type": "closed"},
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [{"operator": "TEST", "name_from": "ENTRY", "name_to": "EXIT", "distance": "110", "price1": "20.00"}],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [{"operator": "TEST", "name": "MID GANTRY", "distance": "", "price1": "3.00"}],
    )
    service = TollPricingService(tmp_path)
    geometry = [[2.0, 48.0], [2.5, 47.5], [3.0, 47.0]]

    quote = service.quote(
        geometry=geometry,
        tolled_km=110.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 110.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 20.0
    assert len(quote.segments) == 1
    assert quote.segments[0].entry == "Entry"
    assert quote.segments[0].exit == "Exit"


def test_open_tariff_can_promote_matching_official_station_without_route_rule(tmp_path: Path) -> None:
    """Station and tariff sources can be joined by name without hard-coded journeys."""
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "GENERIC GANTRY",
                "osm_name": "Generic Gantry",
                "operator": "OFFICIAL",
                "lat": "48.0",
                "lon": "2.0",
                "type": "closed",
            }
        ],
    )
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [{"operator": "NETWORK", "name": "GENERIC GANTRY", "distance": "", "price1": "4.20"}],
    )
    service = TollPricingService(tmp_path)

    assert any(
        station.system_type == "open" and station.operator == "NETWORK"
        for station in service.stations
    )
    quote = service.quote(
        geometry=[[1.999, 48.0], [2.0, 48.0], [2.001, 48.0]],
        tolled_km=0.3,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 0.3}],
    )
    assert quote.confidence == "exact"
    assert quote.cost == 4.2


def test_overlapping_closed_matches_cannot_reuse_same_entry() -> None:
    from app.services.tolls import (
        ClosedMatch,
        ClosedPrice,
        StationProjection,
        TollRange,
        TollStation,
    )

    service = TollPricingService(Path("data/tolls"))
    entry = TollStation("ENTRY", "TEST", 48.0, 2.0, "closed", "Entry")
    short_exit = TollStation("SHORT EXIT", "TEST", 47.5, 2.5, "closed", "Short Exit")
    long_exit = TollStation("LONG EXIT", "TEST", 47.0, 3.0, "closed", "Long Exit")
    short = ClosedMatch(
        0,
        TollRange(0, 1, 0.0, 40.0, 40.0),
        ClosedPrice(5.0, 40.0, "TEST"),
        StationProjection(entry, 0.0, 0.01, 0),
        StationProjection(short_exit, 40.0, 0.01, 1),
    )
    long = ClosedMatch(
        1,
        TollRange(0, 2, 0.0, 100.0, 100.0),
        ClosedPrice(12.0, 100.0, "TEST"),
        StationProjection(entry, 0.0, 0.01, 0),
        StationProjection(long_exit, 100.0, 0.01, 2),
    )

    accepted = service._select_closed_matches([short, long])

    assert accepted == [long]


def test_overlapping_closed_spans_are_never_both_selected() -> None:
    from app.services.tolls import (
        ClosedMatch,
        ClosedPrice,
        StationProjection,
        TollRange,
        TollStation,
    )

    service = TollPricingService(Path("data/tolls"))
    stations = [
        TollStation("A", "TEST", 48.0, 2.0, "closed", "A"),
        TollStation("B", "TEST", 47.8, 2.2, "closed", "B"),
        TollStation("C", "TEST", 47.2, 2.8, "closed", "C"),
        TollStation("D", "TEST", 47.0, 3.0, "closed", "D"),
    ]
    first = ClosedMatch(
        0,
        TollRange(0, 2, 0.0, 80.0, 80.0),
        ClosedPrice(10.0, 80.0, "TEST"),
        StationProjection(stations[0], 0.0, 0.01, 0),
        StationProjection(stations[2], 80.0, 0.01, 2),
    )
    second = ClosedMatch(
        1,
        TollRange(1, 3, 20.0, 100.0, 80.0),
        ClosedPrice(9.0, 80.0, "TEST"),
        StationProjection(stations[1], 20.0, 0.01, 1),
        StationProjection(stations[3], 100.0, 0.01, 3),
    )

    accepted = service._select_closed_matches([first, second])

    assert len(accepted) == 1


def test_open_station_aliases_at_same_physical_point_are_charged_once(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "FONTAINE LARIVIERE",
                "osm_name": "Fontaine Larivière",
                "operator": "APRR",
                "lat": "48.00010",
                "lon": "2.00010",
                "type": "open",
            },
            {
                "name": "FONTAINE-LARIVIERE",
                "osm_name": "Fontaine-Larivière",
                "operator": "APRR",
                "lat": "48.00025",
                "lon": "2.00025",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "APRR",
                "name": "FONTAINE LARIVIERE",
                "distance": "",
                "price1": "3.10",
            }
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [[1.999, 48.0], [2.0002, 48.0002], [2.001, 48.001]]

    quote = service.quote(
        geometry=geometry,
        tolled_km=1.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 3.10
    assert len(quote.segments) == 1


def test_exact_segments_integrity_rejects_duplicate_entry() -> None:
    from app.services.tolls import TollSegmentQuote

    segments = [
        TollSegmentQuote("Same", "Exit 1", "TEST", 2.0, 10.0, "exact", 0.0, 10.0),
        TollSegmentQuote("Same", "Exit 2", "TEST", 3.0, 20.0, "exact", 12.0, 32.0),
    ]

    assert TollPricingService._segments_are_integral(segments) is False


def test_open_aliases_named_peage_are_charged_once(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "ANCENIS",
                "osm_name": "Ancenis",
                "operator": "COFIROUTE",
                "lat": "47.30000",
                "lon": "-1.20000",
                "type": "open",
            },
            {
                "name": "ANCENIS PEAGE",
                "osm_name": "Ancenis Péage",
                "operator": "COFIROUTE",
                "lat": "47.30020",
                "lon": "-1.20020",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {"operator": "COFIROUTE", "name": "ANCENIS", "distance": "", "price1": "10.40"},
            {"operator": "COFIROUTE", "name": "ANCENIS PEAGE", "distance": "", "price1": "10.40"},
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [[-1.201, 47.299], [-1.2001, 47.3001], [-1.199, 47.301]]

    quote = service.quote(
        geometry=geometry,
        tolled_km=1.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 10.40
    assert len(quote.segments) == 1


def test_distinct_principal_and_annex_open_plazas_are_not_merged(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "BOURNEVILLE PRINCIPALE",
                "osm_name": "Bourneville Principale",
                "operator": "SAPN",
                "lat": "49.3775656",
                "lon": "0.6256659",
                "type": "open",
            },
            {
                "name": "BOURNEVILLE ANNEXE",
                "osm_name": "Bourneville Annexe",
                "operator": "SAPN",
                "lat": "49.3876648",
                "lon": "0.6013093",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {"operator": "SAPN", "name": "BOURNEVILLE PRINCIPALE", "distance": "", "price1": "3.30"},
            {"operator": "SAPN", "name": "BOURNEVILLE ANNEXE", "distance": "", "price1": "3.30"},
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [
        [0.6256659, 49.3775656],
        [0.613, 49.382],
        [0.6013093, 49.3876648],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=3.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 3.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 6.60
    assert len(quote.segments) == 2


def test_open_directional_branches_at_one_site_are_not_added_together(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "ANCENIS DIR ANGERS",
                "osm_name": "Ancenis dir Angers",
                "operator": "COFIROUTE",
                "lat": "47.402548",
                "lon": "-1.193525",
                "type": "open",
            },
            {
                "name": "ANCENIS DIR NANTES",
                "osm_name": "Ancenis dir Nantes",
                "operator": "COFIROUTE",
                "lat": "47.399363",
                "lon": "-1.192774",
                "type": "open",
            },
            {
                "name": "ANCENIS PEAGE",
                "osm_name": "Ancenis Péage",
                "operator": "COFIROUTE",
                "lat": "47.400699",
                "lon": "-1.195879",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {"operator": "COFIROUTE", "name": "ANCENIS DIR ANGERS", "distance": "", "price1": "5.20"},
            {"operator": "COFIROUTE", "name": "ANCENIS DIR NANTES", "distance": "", "price1": "3.60"},
            {"operator": "COFIROUTE", "name": "ANCENIS PEAGE", "distance": "", "price1": "10.40"},
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [
        [-1.1980, 47.4002],
        [-1.195879, 47.400699],
        [-1.1910, 47.4012],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=1.0,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.0}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 10.40
    assert len(quote.segments) == 1
    assert quote.segments[0].entry == "Ancenis Péage"


def test_minor_osm_residual_is_ignored_after_exact_matrix(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "ENTRY", "osm_name": "Entry", "operator": "TEST", "lat": "48.0", "lon": "2.0", "type": "closed"},
            {"name": "EXIT", "osm_name": "Exit", "operator": "TEST", "lat": "47.0", "lon": "3.0", "type": "closed"},
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [{"operator": "TEST", "name_from": "ENTRY", "name_to": "EXIT", "distance": "130", "price1": "12.00"}],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    geometry = [
        [2.0, 48.0],
        [2.4, 47.6],
        [3.0, 47.0],
        [3.03, 46.97],
        [3.05, 46.95],
    ]

    quote = service.quote(
        geometry=geometry,
        tolled_km=132.0,
        toll_ranges=[
            {"start_index": 0, "end_index": 2, "distance_km": 130.0},
            {"start_index": 3, "end_index": 4, "distance_km": 2.0},
        ],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 12.0
    assert len(quote.segments) == 1
    assert all(segment.confidence == "exact" for segment in quote.segments)


def test_one_osm_range_can_be_explained_by_multiple_closed_matrices(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "ALPHA", "osm_name": "Alpha", "operator": "NET1", "lat": "45.0", "lon": "0.0", "type": "mainline"},
            {"name": "BRAVO", "osm_name": "Bravo", "operator": "NET1", "lat": "45.0", "lon": "0.45", "type": "mainline"},
            {"name": "CHARLIE", "osm_name": "Charlie", "operator": "NET2", "lat": "45.0", "lon": "0.50", "type": "mainline"},
            {"name": "DELTA", "osm_name": "Delta", "operator": "NET2", "lat": "45.0", "lon": "1.0", "type": "mainline"},
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {"operator": "NET1", "name_from": "ALPHA", "name_to": "BRAVO", "distance": "35", "price1": "5.00"},
            {"operator": "NET2", "name_from": "CHARLIE", "name_to": "DELTA", "distance": "39", "price1": "6.00"},
        ],
    )
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    geometry = [[0.0, 45.0], [0.45, 45.0], [0.50, 45.0], [1.0, 45.0]]
    distance = 78.6

    quote = service.quote(
        geometry=geometry,
        tolled_km=distance,
        toll_ranges=[{"start_index": 0, "end_index": 3, "distance_km": distance}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 11.0
    assert [(segment.entry, segment.exit) for segment in quote.segments] == [("Alpha", "Bravo"), ("Charlie", "Delta")]

# ROUTECO_V034_RELIABILITY_PATCH
def test_station_projection_uses_latitude_aware_longitude_margin(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "OFFSET", "osm_name": "Offset", "operator": "TEST", "lat": "50.050", "lon": "2.030", "type": "closed"}
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    projections, _ = service._project_stations([[2.0, 50.0], [2.0, 50.1]])
    assert projections
    assert projections[0].lateral_km < 2.5


def test_sparse_raw_toll_ranges_are_not_merged_by_point_count(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    geometry = [[0.0, 45.0], [0.001, 45.0], [2.0, 45.0], [2.001, 45.0]]
    _, cumulative = service._project_stations(geometry)
    ranges = service._prepare_ranges(geometry, cumulative, [
        {"start_index": 0, "end_index": 1, "distance_km": 0.1},
        {"start_index": 2, "end_index": 3, "distance_km": 0.1},
    ])
    assert len(ranges) == 2


def test_boundary_pair_rejects_gross_matrix_distance_mismatch(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "ENTRY", "osm_name": "Entry", "operator": "TEST", "lat": "45.0", "lon": "0.0", "type": "closed"},
        {"name": "EXIT", "osm_name": "Exit", "operator": "TEST", "lat": "45.0", "lon": "0.6", "type": "closed"},
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [
        {"operator": "TEST", "name_from": "ENTRY", "name_to": "EXIT", "distance": "500", "price1": "35.00"}
    ])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    distance = 47.2
    quote = service.quote([[0.0, 45.0], [0.6, 45.0]], distance, [{"start_index": 0, "end_index": 1, "distance_km": distance}])
    assert quote.confidence == "estimated"


def test_incomplete_closed_chain_keeps_residual_estimated(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "ALPHA", "osm_name": "Alpha", "operator": "NET1", "lat": "45.0", "lon": "0.0", "type": "mainline"},
        {"name": "BRAVO", "osm_name": "Bravo", "operator": "NET1", "lat": "45.0", "lon": "0.4", "type": "mainline"},
        {"name": "CHARLIE", "osm_name": "Charlie", "operator": "NET2", "lat": "45.0", "lon": "0.52", "type": "mainline"},
        {"name": "DELTA", "osm_name": "Delta", "operator": "NET2", "lat": "45.0", "lon": "1.0", "type": "mainline"},
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [
        {"operator": "NET1", "name_from": "ALPHA", "name_to": "BRAVO", "distance": "31.5", "price1": "5.00"},
        {"operator": "NET2", "name_from": "CHARLIE", "name_to": "DELTA", "distance": "37.8", "price1": "6.00"},
    ])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    geometry = [[0.0, 45.0], [0.4, 45.0], [0.52, 45.0], [1.0, 45.0]]
    distance = 78.6
    quote = service.quote(geometry, distance, [{"start_index": 0, "end_index": 3, "distance_km": distance}])
    assert quote.confidence == "estimated"
    assert any(segment.confidence == "estimated" for segment in quote.segments)


def test_single_verified_open_gantry_resolves_its_open_range(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "OPEN ONE", "osm_name": "Open One", "operator": "TEST", "lat": "45.0", "lon": "0.5", "type": "open"}
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [
        {"operator": "TEST", "name": "OPEN ONE", "distance": "", "price1": "2.00"}
    ])
    service = TollPricingService(tmp_path)
    geometry = [[0.0, 45.0], [0.5, 45.0], [1.0, 45.0]]
    distance = 78.6
    quote = service.quote(
        geometry,
        distance,
        [{"start_index": 0, "end_index": 2, "distance_km": distance}],
    )
    assert quote.confidence == "exact"
    assert quote.cost == 2.0
    assert len(quote.segments) == 1
    assert quote.segments[0].entry == "Open One"


def test_open_gantry_off_route_does_not_resolve_range(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "OPEN FAR", "osm_name": "Open Far", "operator": "TEST", "lat": "45.04", "lon": "0.5", "type": "open"}
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [
        {"operator": "TEST", "name": "OPEN FAR", "distance": "", "price1": "2.00"}
    ])
    service = TollPricingService(tmp_path)
    geometry = [[0.0, 45.0], [0.5, 45.0], [1.0, 45.0]]
    distance = 78.6
    quote = service.quote(
        geometry,
        distance,
        [{"start_index": 0, "end_index": 2, "distance_km": distance}],
    )
    assert quote.confidence == "estimated"
    assert quote.cost == 8.25


# ROUTECO_V034_VALIDATION_HOTFIX
def test_closed_chain_ignores_boundary_padding_but_not_internal_gaps(tmp_path: Path) -> None:
    write_csv(tmp_path / "stations.csv", ["name", "osm_name", "operator", "lat", "lon", "type"], [
        {"name": "ALPHA", "osm_name": "Alpha", "operator": "NET1", "lat": "45.0", "lon": "0.10", "type": "mainline"},
        {"name": "BRAVO", "osm_name": "Bravo", "operator": "NET1", "lat": "45.0", "lon": "0.50", "type": "mainline"},
        {"name": "CHARLIE", "osm_name": "Charlie", "operator": "NET2", "lat": "45.0", "lon": "0.506", "type": "mainline"},
        {"name": "DELTA", "osm_name": "Delta", "operator": "NET2", "lat": "45.0", "lon": "0.90", "type": "mainline"},
    ])
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [
        {"operator": "NET1", "name_from": "ALPHA", "name_to": "BRAVO", "distance": "31.5", "price1": "5.00"},
        {"operator": "NET2", "name_from": "CHARLIE", "name_to": "DELTA", "distance": "31.0", "price1": "6.00"},
    ])
    write_csv(tmp_path / "open_prices.csv", ["operator", "name", "distance", "price1"], [])
    service = TollPricingService(tmp_path)
    geometry = [
        [0.0, 45.0],
        [0.10, 45.0],
        [0.50, 45.0],
        [0.506, 45.0],
        [0.90, 45.0],
        [1.0, 45.0],
    ]
    distance = 78.6
    quote = service.quote(
        geometry,
        distance,
        [{"start_index": 0, "end_index": 5, "distance_km": distance}],
    )
    assert quote.confidence == "exact"
    assert quote.cost == 11.0
    assert len(quote.segments) == 2

# ROUTECO_V034_OPEN_RAMP_FOLLOWUP
def test_open_exit_ramp_is_not_charged_when_route_stays_on_mainline(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "PEAGE DE MAINLINE",
                "osm_name": "Péage principal",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.25",
                "type": "open",
            },
            {
                "name": "RAMP TEST FL E",
                "osm_name": "Ramp Test",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.50",
                "type": "open",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name": "PEAGE DE MAINLINE",
                "distance": "",
                "price1": "4.00",
            },
            {
                "operator": "TEST",
                "name": "RAMP TEST FL E",
                "distance": "",
                "price1": "2.60",
            },
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [
        [0.0, 45.0],
        [0.25, 45.0],
        [0.50, 45.0],
        [1.0, 45.0],
    ]
    distance = 78.6
    quote = service.quote(
        geometry,
        distance,
        [{"start_index": 0, "end_index": 3, "distance_km": distance}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 4.0
    assert [segment.entry for segment in quote.segments] == ["Péage principal"]

# ROUTECO_V034_PHYSICAL_OPEN_TOPOLOGY
def test_materialized_open_interchange_is_not_charged_on_mainline(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "MAINLINE A",
                "osm_name": "Mainline A",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.10",
                "type": "mainline",
            },
            {
                "name": "INTERCHANGE B",
                "osm_name": "Interchange B",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.45",
                "type": "closed",
            },
            {
                "name": "MAINLINE C",
                "osm_name": "Mainline C",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.80",
                "type": "mainline",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name": "MAINLINE A",
                "distance": "",
                "price1": "10.00",
            },
            {
                "operator": "TEST",
                "name": "INTERCHANGE B",
                "distance": "",
                "price1": "2.60",
            },
            {
                "operator": "TEST",
                "name": "MAINLINE C",
                "distance": "",
                "price1": "3.00",
            },
        ],
    )
    service = TollPricingService(tmp_path)
    geometry = [
        [0.0, 45.0],
        [0.10, 45.0],
        [0.45, 45.0],
        [0.80, 45.0],
        [1.0, 45.0],
    ]
    distance = 78.6
    quote = service.quote(
        geometry,
        distance,
        [{"start_index": 0, "end_index": 4, "distance_km": distance}],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 13.0
    assert [segment.entry for segment in quote.segments] == [
        "Mainline A",
        "Mainline C",
    ]

# ROUTECO_V034_OPEN_RAMP_PATH_TOPOLOGY
def test_open_interchange_requires_a_link_road(tmp_path: Path) -> None:
    from app.services.tolls import StationProjection, TollRange, TollStation

    service = TollPricingService(tmp_path)
    service.open_prices[("TEST", "interchange")] = 2.60

    station = TollStation(
        name="INTERCHANGE",
        osm_name="Interchange",
        operator="TEST",
        lat=45.0,
        lon=1.0,
        system_type="open",
        physical_type="closed",
    )
    projection = StationProjection(
        station=station,
        route_km=10.2,
        lateral_km=0.01,
        segment_index=1,
    )
    toll_range = TollRange(
        start_index=0,
        end_index=2,
        start_km=10.0,
        end_km=30.0,
        distance_km=20.0,
    )

    mainline = service._open_stations_in_range(
        [projection],
        toll_range,
        [[0, 2, False]],
    )
    ramp = service._open_stations_in_range(
        [projection],
        toll_range,
        [[0, 2, True]],
    )

    assert mainline == []
    assert ramp == [projection]

# ROUTECO_V034_CANDIDATE_PIPELINE_FIX
def test_quote_candidate_forwards_all_routing_metadata() -> None:
    from app.services.tolls import TollPricingService, TollQuote

    class RecordingService(TollPricingService):
        def __init__(self) -> None:
            self.received = None

        def quote(
            self,
            geometry,
            tolled_km,
            toll_ranges=None,
            road_class_link_details=None,
            demo_toll=None,
            toll_state_intervals=None,
        ) -> TollQuote:
            self.received = {
                "geometry": geometry,
                "tolled_km": tolled_km,
                "toll_ranges": toll_ranges,
                "toll_state_intervals": toll_state_intervals,
                "road_class_link_details": road_class_link_details,
                "demo_toll": demo_toll,
            }
            return TollQuote(0.0, "none", [], "test")

    candidate = {
        "geometry": [[2.0, 48.0], [2.1, 48.0], [2.2, 48.0]],
        "tolled_km": 10.0,
        "toll_ranges": [
            {"start_index": 0, "end_index": 2, "distance_km": 10.0}
        ],
        "toll_state_intervals": [
            {
                "start_index": 0,
                "end_index": 2,
                "distance_km": 10.0,
                "value": "ALL",
                "class1_status": "toll",
            }
        ],
        "road_class_link_details": [[0, 2, False]],
        "demo_toll": None,
    }
    service = RecordingService()
    service.quote_candidate(candidate)

    assert service.received == {
        "geometry": candidate["geometry"],
        "tolled_km": 10.0,
        "toll_ranges": candidate["toll_ranges"],
        "toll_state_intervals": candidate["toll_state_intervals"],
        "road_class_link_details": [[0, 2, False]],
        "demo_toll": None,
    }

# ROUTECO_V034_BIDIRECTIONAL_TARIFFS
def test_closed_matrix_is_available_in_reverse_direction(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "ALPHA",
                "osm_name": "Alpha",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.0",
                "type": "closed",
            },
            {
                "name": "OMEGA",
                "osm_name": "Omega",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "1.0",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name_from": "ALPHA",
                "name_to": "OMEGA",
                "distance": "80.0",
                "price1": "12.30",
            }
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )

    service = TollPricingService(tmp_path)
    alpha = next(station for station in service.stations if station.name == "ALPHA")
    omega = next(station for station in service.stations if station.name == "OMEGA")

    forward = service._lookup_closed(alpha, omega)
    reverse = service._lookup_closed(omega, alpha)

    assert forward is not None
    assert reverse is not None
    assert forward.price == 12.30
    assert reverse.price == 12.30


def test_explicit_reverse_fare_overrides_symmetric_fallback(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "ALPHA",
                "osm_name": "Alpha",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.0",
                "type": "closed",
            },
            {
                "name": "OMEGA",
                "osm_name": "Omega",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "1.0",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name_from": "ALPHA",
                "name_to": "OMEGA",
                "distance": "80.0",
                "price1": "12.30",
            },
            {
                "operator": "TEST",
                "name_from": "OMEGA",
                "name_to": "ALPHA",
                "distance": "80.0",
                "price1": "13.10",
            },
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )

    service = TollPricingService(tmp_path)
    alpha = next(station for station in service.stations if station.name == "ALPHA")
    omega = next(station for station in service.stations if station.name == "OMEGA")

    reverse = service._lookup_closed(omega, alpha)

    assert reverse is not None
    assert reverse.price == 13.10

# ROUTECO_V034_GLOBAL_TOLL_PLAN
def test_global_selector_prefers_maximum_exact_coverage(tmp_path: Path) -> None:
    from app.services.tolls import (
        ClosedMatch,
        ClosedPrice,
        StationProjection,
        TollRange,
        TollStation,
    )

    service = make_service(tmp_path)
    toll_range = TollRange(0, 10, 0.0, 250.0, 250.0)
    entry = TollStation("ENTRY", "TEST", 45.0, 0.0, "closed")
    local_exit = TollStation("LOCAL", "TEST", 45.0, 0.1, "closed")
    main_exit = TollStation("MAIN", "TEST", 45.0, 2.0, "closed")

    short = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(3.40, None, "TEST"),
        StationProjection(entry, 8.0, 0.01, 1),
        StationProjection(local_exit, 25.0, 0.01, 2),
        coverage_km=17.0,
        full_range=False,
    )
    long = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(32.90, None, "TEST"),
        StationProjection(entry, 8.0, 0.01, 1),
        StationProjection(main_exit, 228.0, 0.01, 9),
        coverage_km=250.0,
        full_range=True,
    )

    assert service._select_closed_matches([short, long]) == [long]


def test_range_proposals_include_boundary_and_route_wide_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from app.services.tolls import ClosedPrice, StationProjection, TollRange, TollStation

    service = make_service(tmp_path)
    toll_range = TollRange(0, 10, 0.0, 250.0, 250.0)
    entry = StationProjection(TollStation("ENTRY", "TEST", 45.0, 0.0, "closed"), 8.0, 0.01, 1)
    local_exit = StationProjection(TollStation("LOCAL", "TEST", 45.0, 0.1, "closed"), 25.0, 0.01, 2)
    main_exit = StationProjection(TollStation("MAIN", "TEST", 45.0, 2.0, "closed"), 228.0, 0.01, 9)

    monkeypatch.setattr(service, "_best_closed_pair", lambda projections, value: (ClosedPrice(3.40, None, "TEST"), entry, local_exit))
    monkeypatch.setattr(service, "_route_wide_pair", lambda projections, value, target: (ClosedPrice(32.90, None, "TEST"), entry, main_exit))
    monkeypatch.setattr(service, "_best_closed_chain", lambda projections, value, index: ([], False))

    proposals = service._closed_proposals_for_range([entry, local_exit, main_exit], toll_range, 0)

    assert len(proposals) == 2
    assert max(item.span_km for item in proposals) == 220.0


def test_isolated_micro_ranges_without_billing_event_are_ignored(tmp_path: Path) -> None:
    service = make_service(tmp_path)
    quote = service.quote(
        geometry=[[0.00, 45.0], [0.01, 45.0], [0.02, 45.0], [0.03, 45.0]],
        tolled_km=2.0,
        toll_ranges=[
            {"start_index": 0, "end_index": 1, "distance_km": 1.1},
            {"start_index": 2, "end_index": 3, "distance_km": 0.9},
        ],
        road_class_link_details=[[0, 3, False]],
    )

    assert quote.confidence == "none"
    assert quote.cost == 0.0
    assert "Fragments OSM" in quote.message


def test_short_range_crossing_mainline_barrier_remains_unresolved(tmp_path: Path) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {"name": "BARRIERE SANS TARIF", "osm_name": "Barrière sans tarif", "operator": "TEST", "lat": "45.0", "lon": "0.01", "type": "mainline"},
            {"name": "AUTRE PORTIQUE", "osm_name": "Autre portique", "operator": "TEST", "lat": "46.0", "lon": "1.0", "type": "open"},
        ],
    )
    write_csv(tmp_path / "closed_prices.csv", ["operator", "name_from", "name_to", "distance", "price1"], [])
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [{"operator": "TEST", "name": "AUTRE PORTIQUE", "distance": "", "price1": "1.00"}],
    )
    service = TollPricingService(tmp_path)

    quote = service.quote(
        geometry=[[0.0, 45.0], [0.01, 45.0], [0.02, 45.0]],
        tolled_km=1.5,
        toll_ranges=[{"start_index": 0, "end_index": 2, "distance_km": 1.5}],
        road_class_link_details=[[0, 2, False]],
    )

    assert quote.confidence == "estimated"
    assert quote.cost > 0.0


# ROUTECO_V034_OPEN_AFTER_CLOSED_HOTFIX


# ROUTECO_V034_LONG_MATRIX_PRIORITY_FIX
def test_long_group_matrix_beats_included_short_submatrix(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "GROUP START",
                "osm_name": "Group Start",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.0",
                "type": "mainline",
            },
            {
                "name": "LOCAL END",
                "osm_name": "Local End",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.50",
                "type": "mainline",
            },
            {
                "name": "GROUP END",
                "osm_name": "Group End",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.70",
                "type": "mainline",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name_from": "GROUP START",
                "name_to": "LOCAL END",
                "distance": "",
                "price1": "5.40",
            },
            {
                "operator": "TEST",
                "name_from": "GROUP START",
                "name_to": "GROUP END",
                "distance": "",
                "price1": "7.50",
            },
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )

    service = TollPricingService(tmp_path)
    geometry = [
        [0.0, 45.0],
        [0.50, 45.0],
        [0.70, 45.0],
    ]
    quote = service.quote(
        geometry=geometry,
        tolled_km=55.0,
        toll_ranges=[
            {
                "start_index": 0,
                "end_index": 2,
                "distance_km": 55.0,
            }
        ],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 7.50
    assert len(quote.segments) == 1
    assert quote.segments[0].entry == "Group Start"
    assert quote.segments[0].exit == "Group End"


def test_real_sub_euro_open_charge_is_not_discarded(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "SMALL REAL GANTRY",
                "osm_name": "Small Real Gantry",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.01",
                "type": "open",
            }
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name": "SMALL REAL GANTRY",
                "distance": "",
                "price1": "0.80",
            }
        ],
    )

    service = TollPricingService(tmp_path)
    quote = service.quote(
        geometry=[[0.0, 45.0], [0.02, 45.0]],
        tolled_km=1.6,
        toll_ranges=[
            {
                "start_index": 0,
                "end_index": 1,
                "distance_km": 1.6,
            }
        ],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 0.80

# ROUTECO_V034_BILLING_SEMANTICS_FIX
def test_nested_closed_matrix_cannot_hide_maximal_exact_journey(
    tmp_path: Path,
) -> None:
    from app.services.tolls import (
        ClosedMatch,
        ClosedPrice,
        StationProjection,
        TollRange,
        TollStation,
    )

    service = make_service(tmp_path)
    toll_range = TollRange(0, 10, 0.0, 100.0, 100.0)
    start = TollStation("START", "TEST", 45.0, 0.0, "closed")
    middle = TollStation("MIDDLE", "TEST", 45.0, 0.5, "closed")
    end = TollStation("END", "TEST", 45.0, 1.0, "closed")

    short = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(5.40, None, "TEST"),
        StationProjection(start, 15.0, 0.01, 1),
        StationProjection(middle, 60.0, 0.01, 5),
        coverage_km=100.0,
        full_range=True,
    )
    long = ClosedMatch(
        0,
        toll_range,
        ClosedPrice(7.50, None, "TEST"),
        StationProjection(start, 15.0, 0.01, 1),
        StationProjection(end, 85.0, 0.01, 9),
        coverage_km=70.0,
        full_range=False,
    )

    normalized = service._normalize_closed_proposals(
        [short, long],
        [short.entry, short.exit, long.exit],
        toll_range,
    )

    assert short.full_range is False
    assert long.full_range is True
    assert service._select_closed_matches(normalized) == [long]


def test_resolved_closed_range_still_charges_distinct_open_event(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "OPEN EVENT",
                "osm_name": "Open Event",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.02",
                "type": "open",
            },
            {
                "name": "CLOSED START",
                "osm_name": "Closed Start",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.10",
                "type": "closed",
            },
            {
                "name": "CLOSED END",
                "osm_name": "Closed End",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.20",
                "type": "closed",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name_from": "CLOSED START",
                "name_to": "CLOSED END",
                "distance": "",
                "price1": "5.40",
            }
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name": "OPEN EVENT",
                "distance": "",
                "price1": "2.10",
            }
        ],
    )

    service = TollPricingService(tmp_path)
    quote = service.quote(
        geometry=[
            [0.00, 45.0],
            [0.02, 45.0],
            [0.10, 45.0],
            [0.20, 45.0],
            [0.30, 45.0],
        ],
        tolled_km=23.6,
        toll_ranges=[
            {
                "start_index": 0,
                "end_index": 4,
                "distance_km": 23.6,
            }
        ],
        road_class_link_details=[[0, 4, False]],
    )

    assert quote.confidence == "exact"
    assert quote.cost == 7.50
    assert sorted(segment.cost for segment in quote.segments) == [2.10, 5.40]


def test_unpriced_mainline_event_prevents_silent_residual_removal(
    tmp_path: Path,
) -> None:
    write_csv(
        tmp_path / "stations.csv",
        ["name", "osm_name", "operator", "lat", "lon", "type"],
        [
            {
                "name": "CLOSED START",
                "osm_name": "Closed Start",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.05",
                "type": "closed",
            },
            {
                "name": "CLOSED END",
                "osm_name": "Closed End",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.15",
                "type": "closed",
            },
            {
                "name": "BARRIERE SANS TARIF",
                "osm_name": "Barrière sans tarif",
                "operator": "TEST",
                "lat": "45.0",
                "lon": "0.19",
                "type": "mainline",
            },
        ],
    )
    write_csv(
        tmp_path / "closed_prices.csv",
        ["operator", "name_from", "name_to", "distance", "price1"],
        [
            {
                "operator": "TEST",
                "name_from": "CLOSED START",
                "name_to": "CLOSED END",
                "distance": "",
                "price1": "4.00",
            }
        ],
    )
    write_csv(
        tmp_path / "open_prices.csv",
        ["operator", "name", "distance", "price1"],
        [],
    )

    service = TollPricingService(tmp_path)
    quote = service.quote(
        geometry=[
            [0.00, 45.0],
            [0.05, 45.0],
            [0.15, 45.0],
            [0.19, 45.0],
            [0.20, 45.0],
        ],
        tolled_km=15.8,
        toll_ranges=[
            {
                "start_index": 0,
                "end_index": 4,
                "distance_km": 15.8,
            }
        ],
        road_class_link_details=[[0, 4, False]],
    )

    assert quote.confidence == "estimated"

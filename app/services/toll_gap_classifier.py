from __future__ import annotations

import re
import unicodedata
from typing import Any


CAUSE_PRIORITY = {
    "missing_open_tariff": 10,
    "known_open_tariff_not_selected": 20,
    "closed_matrix_candidate_available": 25,
    "missing_closed_matrix": 30,
    "ambiguous_closed_topology": 35,
    "station_topology_review": 40,
    "boundary_overhang": 50,
    "unknown_osm_corridor": 60,
    "ambiguous_toll_interval": 70,
}

CAUSE_ACTION = {
    "missing_open_tariff": (
        "Importer le tarif officiel classe 1 du portique ou de la barrière."
    ),
    "known_open_tariff_not_selected": (
        "Vérifier pourquoi un tarif ouvert déjà présent n'est pas sélectionné."
    ),
    "closed_matrix_candidate_available": (
        "Une matrice officielle existe : vérifier pourquoi elle n'est pas "
        "retenue par le solveur."
    ),
    "missing_closed_matrix": (
        "Rechercher la cellule officielle entrée-sortie correspondante."
    ),
    "ambiguous_closed_topology": (
        "Plusieurs matrices officielles sont possibles : lever l'ambiguïté "
        "physique avant toute sélection."
    ),
    "station_topology_review": (
        "Vérifier le type physique, les alias et le sens de circulation."
    ),
    "boundary_overhang": (
        "Vérifier si le fragment est un dépassement de balisage OSM."
    ),
    "unknown_osm_corridor": (
        "Contrôler le balisage OSM et rechercher un événement absent de la base."
    ),
    "ambiguous_toll_interval": (
        "Revoir manuellement la topologie et les sources tarifaires."
    ),
}


def key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(
        char for char in text if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _matches_exact_boundary(
    station: dict[str, Any],
    segments: list[dict[str, Any]],
) -> bool:
    station_key = key(str(station.get("name") or ""))
    route_km = float(station.get("route_km") or 0.0)
    if not station_key:
        return False
    for segment in segments:
        for label_field, km_field in (
            ("entry", "route_start_km"),
            ("exit", "route_end_km"),
        ):
            label = key(str(segment.get(label_field) or ""))
            raw_km = segment.get(km_field)
            if not label or raw_km is None:
                continue
            if label == station_key and abs(route_km - float(raw_km)) <= 1.0:
                return True
    return False


def _closed_boundary_candidates(
    nearby: list[dict[str, Any]],
    distance_field: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for station in nearby:
        system_type = str(station.get("system_type") or "").lower()
        physical_type = str(station.get("physical_type") or "").lower()
        if system_type not in {"closed", "mainline", "barrier"} and (
            physical_type not in {"closed", "mainline", "barrier"}
        ):
            continue
        if float(station.get(distance_field) or 999.0) <= 2.0:
            output.append(station)
    return output


def classify_unresolved_interval(
    occurrence: dict[str, Any],
) -> str:
    nearby = list(occurrence.get("nearby_stations", []))
    exact_segments = list(occurrence.get("exact_segments", []))
    unresolved_km = float(occurrence.get("unresolved_km") or 0.0)

    topology = dict(
        occurrence.get("closed_topology") or {}
    )
    topology_decision = str(
        topology.get("decision") or ""
    )
    if topology_decision == "unique_official_matrix":
        return "closed_matrix_candidate_available"
    if topology_decision == "multiple_official_matrices":
        return "ambiguous_closed_topology"
    if topology_decision == "boundary_pair_without_matrix":
        return "missing_closed_matrix"

    if unresolved_km <= 0.5 and exact_segments:
        start_km = float(occurrence.get("route_start_km") or 0.0)
        end_km = float(occurrence.get("route_end_km") or 0.0)
        boundaries = [
            float(value)
            for segment in exact_segments
            for value in (
                segment.get("route_start_km"),
                segment.get("route_end_km"),
            )
            if value is not None
        ]
        if any(
            min(abs(start_km - value), abs(end_km - value)) <= 0.5
            for value in boundaries
        ):
            return "boundary_overhang"

    known_open = [
        station
        for station in nearby
        if station.get("open_price") is not None
        and float(station.get("lateral_km") or 999.0) <= 0.12
        and not _matches_exact_boundary(station, exact_segments)
    ]
    if known_open:
        return "known_open_tariff_not_selected"

    missing_open = [
        station
        for station in nearby
        if str(station.get("system_type") or "").lower() == "open"
        and station.get("open_price") is None
        and float(station.get("lateral_km") or 999.0) <= 0.12
    ]
    if missing_open:
        return "missing_open_tariff"

    starts = _closed_boundary_candidates(
        nearby, "distance_to_interval_start_km"
    )
    ends = _closed_boundary_candidates(
        nearby, "distance_to_interval_end_km"
    )
    if starts and ends:
        pairs = {
            (key(str(start.get("name") or "")), key(str(end.get("name") or "")))
            for start in starts
            for end in ends
        }
        if any(left and right and left != right for left, right in pairs):
            return "missing_closed_matrix"

    if not nearby:
        return "unknown_osm_corridor"

    if any(
        str(station.get("system_type") or "").lower()
        in {"mainline", "barrier", "closed"}
        or str(station.get("physical_type") or "").lower()
        in {"mainline", "barrier", "closed"}
        for station in nearby
    ):
        return "station_topology_review"

    return "ambiguous_toll_interval"

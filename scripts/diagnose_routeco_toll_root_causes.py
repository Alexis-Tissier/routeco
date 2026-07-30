#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.models import Coordinate
from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService
from app.services.validation import load_scenarios


def station_payload(service: TollPricingService, projection: Any) -> dict[str, Any]:
    station = projection.station
    link_value = service._road_class_link_at_projection(
        projection,
        getattr(service, "_diagnostic_road_class_link_details", None),
    )
    return {
        "name": station.display_name,
        "raw_name": station.name,
        "operator": station.operator,
        "system_type": station.system_type,
        "physical_type": station.physical_type,
        "mainline_barrier": station.is_mainline_barrier,
        "route_km": round(projection.route_km, 3),
        "lateral_km": round(projection.lateral_km, 4),
        "segment_index": projection.segment_index,
        "road_class_link": link_value,
        "open_price": service._lookup_open(station),
    }


def pair_payload(pair: Any) -> dict[str, Any] | None:
    if pair is None:
        return None
    record, entry, exit_ = pair
    return {
        "entry": entry.station.display_name,
        "exit": exit_.station.display_name,
        "operator": record.operator,
        "price": record.price,
        "matrix_distance_km": record.distance_km,
        "entry_route_km": round(entry.route_km, 3),
        "exit_route_km": round(exit_.route_km, 3),
        "span_km": round(exit_.route_km - entry.route_km, 3),
    }


def quote_payload(quote: Any) -> dict[str, Any]:
    return {
        "cost": quote.cost,
        "confidence": quote.confidence,
        "message": quote.message,
        "segments": [asdict(segment) for segment in quote.segments],
    }


def classify_range(
    start_candidates: list[Any],
    end_candidates: list[Any],
    open_matches: list[Any],
    best_pair: Any,
    route_wide: Any,
    chain: list[Any],
    matrix_pairs: list[dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if open_matches:
        reasons.append("Un ou plusieurs péages ouverts exacts sont projetés dans la plage.")
    if route_wide is not None:
        reasons.append(
            "Une matrice route-wide existe : la perte d'exactitude vient probablement "
            "de la couverture, de l'intégrité ou de la sélection globale."
        )
    if best_pair is not None:
        reasons.append(
            "Une paire fermée de frontière existe : inspecter la couverture résiduelle "
            "et les autres plages OSM."
        )
    if chain:
        reasons.append(
            "Une chaîne de matrices existe mais n'est pas jugée complète ou entre en conflit."
        )
    if not start_candidates:
        reasons.append("Aucune gare crédible n'est projetée près du début de la plage.")
    if not end_candidates:
        reasons.append("Aucune gare crédible n'est projetée près de la fin de la plage.")
    if start_candidates and end_candidates and not matrix_pairs:
        reasons.append(
            "Des gares existent aux deux frontières, mais aucune matrice tarifaire "
            "non ambiguë ne relie leurs alias/opérateurs."
        )
    if matrix_pairs and best_pair is None and route_wide is None:
        reasons.append(
            "Une matrice existe entre des gares voisines, mais elle est rejetée par "
            "les contrôles de distance, de position ou de topologie."
        )
    if not reasons:
        reasons.append(
            "Aucune cause unique détectée automatiquement ; inspecter les projections "
            "et les plages brutes dans le JSON."
        )
    return reasons


async def run(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text(encoding="utf-8"))
    scenarios = {
        scenario["id"]: scenario
        for scenario in load_scenarios(args.scenarios)
    }

    target_routes: dict[str, set[str]] = {}
    for result in report.get("results", []):
        for route in result.get("routes", []):
            confidence = route.get("toll_confidence")
            tolled_km = float(route.get("tolled_km") or 0.0)
            if confidence == "estimated":
                target_routes.setdefault(result["id"], set()).add(route["id"])
            elif args.include_none and confidence == "none" and tolled_km > 0.5:
                target_routes.setdefault(result["id"], set()).add(route["id"])

    routing = GraphHopperClient(settings.graphhopper_url, timeout_seconds=args.timeout)
    tolls = TollPricingService(settings.tolls_dir)

    if not await routing.available():
        print(f"ERREUR : GraphHopper ne répond pas sur {settings.graphhopper_url}.")
        return 2
    if not tolls.ready:
        print(f"ERREUR : données de péage absentes dans {settings.tolls_dir}.")
        return 2

    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "source_report": str(args.report),
        "summary": {
            "target_scenarios": len(target_routes),
            "target_routes": sum(len(ids) for ids in target_routes.values()),
            "stations": len(tolls.stations),
            "closed_pairs": len(tolls.closed_prices),
            "open_prices": len(tolls.open_prices),
        },
        "results": [],
    }

    for scenario_id, wanted_ids in target_routes.items():
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            payload["results"].append(
                {
                    "scenario_id": scenario_id,
                    "error": "Scénario absent de validation/scenarios.json",
                }
            )
            continue

        print(f"Diagnostic : {scenario['name']}…", flush=True)
        engine = await routing.candidates(
            Coordinate(**scenario["start"]),
            Coordinate(**scenario["end"]),
        )
        candidates = {candidate["id"]: candidate for candidate in engine.candidates}

        scenario_result: dict[str, Any] = {
            "scenario_id": scenario_id,
            "scenario": scenario["name"],
            "engine": engine.engine,
            "missing_candidate_ids": sorted(wanted_ids - set(candidates)),
            "routes": [],
        }

        for route_id in sorted(wanted_ids):
            candidate = candidates.get(route_id)
            if candidate is None:
                continue

            geometry = candidate.get("geometry", [])
            raw_ranges = candidate.get("toll_ranges") or []
            details = candidate.get("road_class_link_details") or []
            setattr(tolls, "_diagnostic_road_class_link_details", details)

            quote = (
                tolls.quote_candidate(candidate)
                if hasattr(tolls, "quote_candidate")
                else tolls.quote(
                    geometry=geometry,
                    tolled_km=candidate.get("tolled_km", 0.0),
                    toll_ranges=raw_ranges,
                    road_class_link_details=details,
                    demo_toll=candidate.get("demo_toll"),
                )
            )

            projections, cumulative = tolls._project_stations(geometry)
            prepared = tolls._prepare_ranges(geometry, cumulative, raw_ranges)

            route_result: dict[str, Any] = {
                "route_id": route_id,
                "profile": candidate.get("profile"),
                "duration_minutes": candidate.get("duration_minutes"),
                "distance_km": candidate.get("distance_km"),
                "motorway_km": candidate.get("motorway_km"),
                "tolled_km": candidate.get("tolled_km"),
                "raw_toll_ranges": raw_ranges,
                "road_class_link_detail_count": len(details),
                "quote": quote_payload(quote),
                "ranges": [],
            }

            for range_index, toll_range in enumerate(prepared):
                start_candidates = [
                    projection
                    for _, projection in tolls._boundary_candidates(
                        projections,
                        toll_range.start_km,
                        30.0,
                        2.5,
                    )[:12]
                ]
                end_candidates = [
                    projection
                    for _, projection in tolls._boundary_candidates(
                        projections,
                        toll_range.end_km,
                        30.0,
                        2.5,
                    )[:12]
                ]

                matrix_pairs: list[dict[str, Any]] = []
                for entry in start_candidates:
                    for exit_ in end_candidates:
                        if exit_.route_km <= entry.route_km + 0.05:
                            continue
                        record = tolls._lookup_closed(entry.station, exit_.station)
                        if record is None:
                            continue
                        matrix_pairs.append(
                            {
                                "entry": entry.station.display_name,
                                "exit": exit_.station.display_name,
                                "operator": record.operator,
                                "price": record.price,
                                "matrix_distance_km": record.distance_km,
                                "projected_span_km": round(
                                    exit_.route_km - entry.route_km,
                                    3,
                                ),
                            }
                        )

                best_pair = tolls._best_closed_pair(projections, toll_range)
                route_wide = tolls._route_wide_pair(
                    projections,
                    toll_range,
                    toll_range.distance_km,
                )
                chain, chain_complete = tolls._best_closed_chain(
                    projections,
                    toll_range,
                    range_index,
                )
                open_matches = tolls._open_stations_in_range(
                    projections,
                    toll_range,
                    details,
                )

                route_result["ranges"].append(
                    {
                        "range_index": range_index,
                        "start_index": toll_range.start_index,
                        "end_index": toll_range.end_index,
                        "start_km": round(toll_range.start_km, 3),
                        "end_km": round(toll_range.end_km, 3),
                        "distance_km": round(toll_range.distance_km, 3),
                        "start_candidates": [
                            station_payload(tolls, item) for item in start_candidates
                        ],
                        "end_candidates": [
                            station_payload(tolls, item) for item in end_candidates
                        ],
                        "open_matches": [
                            station_payload(tolls, item) for item in open_matches
                        ],
                        "matrix_pairs_near_boundaries": matrix_pairs,
                        "best_closed_pair": pair_payload(best_pair),
                        "route_wide_pair": pair_payload(route_wide),
                        "closed_chain": [
                            {
                                "entry": match.entry.station.display_name,
                                "exit": match.exit.station.display_name,
                                "price": match.record.price,
                                "operator": match.record.operator,
                                "coverage_km": match.coverage_km,
                                "full_range": match.full_range,
                            }
                            for match in chain
                        ],
                        "closed_chain_complete": chain_complete,
                        "diagnosis": classify_range(
                            start_candidates,
                            end_candidates,
                            open_matches,
                            best_pair,
                            route_wide,
                            chain,
                            matrix_pairs,
                        ),
                    }
                )

            scenario_result["routes"].append(route_result)

        payload["results"].append(scenario_result)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    markdown = args.output.with_suffix(".md")
    lines = [
        "# Diagnostic générique des péages non résolus",
        "",
        f"Source : `{args.report}`",
        "",
        f"- Scénarios analysés : **{payload['summary']['target_scenarios']}**",
        f"- Itinéraires analysés : **{payload['summary']['target_routes']}**",
        "",
    ]
    for result in payload["results"]:
        lines.extend(["", f"## {result.get('scenario', result['scenario_id'])}", ""])
        if result.get("error"):
            lines.append(f"- Erreur : {result['error']}")
            continue
        for route in result.get("routes", []):
            lines.extend(
                [
                    f"### {route['route_id']}",
                    "",
                    f"- Profil : `{route.get('profile')}`",
                    f"- Péage : **{route['quote']['cost']:.2f} €** "
                    f"(`{route['quote']['confidence']}`)",
                    f"- Kilomètres payants : **{float(route.get('tolled_km') or 0):.1f} km**",
                    "",
                ]
            )
            for toll_range in route["ranges"]:
                lines.append(
                    f"- Plage {toll_range['range_index']} : "
                    f"{toll_range['start_km']:.1f} → {toll_range['end_km']:.1f} km, "
                    f"{toll_range['distance_km']:.1f} km payants"
                )
                for reason in toll_range["diagnosis"]:
                    lines.append(f"  - {reason}")
            lines.append("")
    markdown.write_text("\n".join(lines), encoding="utf-8")

    print()
    print(f"Diagnostic JSON : {args.output}")
    print(f"Diagnostic MD   : {markdown}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnostiquer toutes les portions de péage estimées sans règle "
            "spécifique à un trajet."
        )
    )
    parser.add_argument("report", type=Path)
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path("validation/scenarios.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/reports/toll-root-cause-audit.json"),
    )
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--include-none", action="store_true")
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()

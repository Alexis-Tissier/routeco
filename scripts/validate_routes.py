#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import random
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.services.routing import GraphHopperClient
from app.services.toll_manifest import (
    build_missing_toll_manifest,
    render_missing_toll_manifest,
)
from app.services.tolls import TollPricingService
from app.services.validation import (
    load_scenarios,
    render_markdown,
    report_payload,
    validate_scenario,
)


def random_scenarios(cities_path: Path, count: int, seed: int) -> list[dict]:
    cities = json.loads(cities_path.read_text(encoding="utf-8"))
    if len(cities) < 2:
        return []
    rng = random.Random(seed)
    pairs = [(a, b) for a in cities for b in cities if a["name"] != b["name"]]
    rng.shuffle(pairs)
    scenarios: list[dict] = []
    for index, (start, end) in enumerate(pairs[:count], start=1):
        scenarios.append(
            {
                "id": f"random-{seed}-{index}",
                "name": f"{start['name']} → {end['name']}",
                "start": {"lat": start["lat"], "lon": start["lon"]},
                "end": {"lat": end["lat"], "lon": end["lon"]},
                "min_routes": 1,
            }
        )
    return scenarios


async def run(args: argparse.Namespace) -> int:
    routing = GraphHopperClient(settings.graphhopper_url, timeout_seconds=args.timeout)
    tolls = TollPricingService(settings.tolls_dir)

    if not await routing.available():
        print(f"ERREUR : GraphHopper ne répond pas sur {settings.graphhopper_url}.")
        return 2
    if not tolls.ready:
        print(f"ERREUR : données de péage absentes dans {settings.tolls_dir}.")
        return 2

    if args.random:
        scenarios = random_scenarios(args.cities, args.random, args.seed)
    else:
        scenarios = load_scenarios(args.scenarios)
    if args.only:
        wanted = set(args.only)
        scenarios = [scenario for scenario in scenarios if scenario["id"] in wanted]
        missing = wanted - {scenario["id"] for scenario in scenarios}
        if missing:
            print(f"ERREUR : scénario(s) inconnu(s) : {', '.join(sorted(missing))}")
            return 2

    results = []
    for index, scenario in enumerate(scenarios, start=1):
        print(f"[{index}/{len(scenarios)}] {scenario['name']}…", flush=True)
        result = await validate_scenario(
            scenario,
            routing,
            tolls,
            fuel_price=args.fuel_price,
            motorway_consumption=args.motorway_consumption,
            road_consumption=args.road_consumption,
            strict=args.strict,
            enforce_gold=args.gold,
        )
        results.append(result)
        print(
            f"  {len(result.routes)} routes · {result.errors} erreur(s) · "
            f"{result.warnings} avertissement(s) · "
            f"routage {result.routing_seconds:.1f} s · "
            f"péages {result.toll_pricing_seconds:.2f} s"
        )

    payload = report_payload(results, strict=args.strict)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = args.output_dir or settings.reports_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"validation-{stamp}.md"
    json_path = output_dir / f"validation-{stamp}.json"
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    missing_manifest = build_missing_toll_manifest(payload)
    missing_json_path = output_dir / f"missing-tariffs-{stamp}.json"
    missing_markdown_path = output_dir / f"missing-tariffs-{stamp}.md"
    missing_json_path.write_text(
        json.dumps(
            missing_manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    missing_markdown_path.write_text(
        render_missing_toll_manifest(missing_manifest),
        encoding="utf-8",
    )

    summary = payload["summary"]
    print()
    print(f"Rapport Markdown : {markdown_path}")
    print(f"Rapport JSON     : {json_path}")
    print(f"Manifeste MD     : {missing_markdown_path}")
    print(f"Manifeste JSON   : {missing_json_path}")
    print(
        f"Résumé : {summary['errors']} erreur(s), {summary['warnings']} avertissement(s), "
        f"{summary['exact']} exact(s), {summary['estimated']} estimé(s)."
    )
    print(
        "Durées : "
        f"{summary['routing_seconds']:.1f} s de routage "
        f"(moyenne {summary['routing_average_seconds']:.1f} s), "
        f"{summary['toll_pricing_seconds']:.2f} s de calcul des péages."
    )
    return 1 if summary["errors"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Valider Routeco sur plusieurs trajets français.")
    parser.add_argument(
        "--scenarios",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "validation" / "scenarios.json",
    )
    parser.add_argument("--only", action="append", help="Identifiant d'un scénario à exécuter.")
    parser.add_argument(
        "--gold",
        action="store_true",
        help="Activer les montants attendus des trajets de référence vérifiés.",
    )
    parser.add_argument(
        "--random",
        type=int,
        default=0,
        metavar="N",
        help="Tester N couples de villes tirés de façon déterministe.",
    )
    parser.add_argument("--seed", type=int, default=20260729)
    parser.add_argument(
        "--cities",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "validation" / "cities.json",
    )
    parser.add_argument("--strict", action="store_true", help="Traiter tout péage estimé comme une erreur.")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--fuel-price", type=float, default=1.82)
    parser.add_argument("--motorway-consumption", type=float, default=6.5)
    parser.add_argument("--road-consumption", type=float, default=5.5)
    parser.add_argument("--timeout", type=float, default=120.0)
    raise SystemExit(asyncio.run(run(parser.parse_args())))


if __name__ == "__main__":
    main()

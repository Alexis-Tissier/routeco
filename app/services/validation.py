from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import Coordinate
from app.services.costs import calculate_costs
from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService, normalize_name, physical_label_key


@dataclass(slots=True)
class ValidationIssue:
    level: str
    message: str


@dataclass(slots=True)
class ValidatedRoute:
    id: str
    duration_minutes: int
    distance_km: float
    motorway_km: float
    road_km: float
    tolled_km: float
    toll_cost: float
    toll_confidence: str
    fuel_cost: float
    total_cost: float
    toll_message: str
    toll_segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ScenarioResult:
    id: str
    name: str
    engine: str
    engine_message: str
    routes: list[ValidatedRoute]
    issues: list[ValidationIssue]
    retried_profiles: list[str] = field(default_factory=list)
    failed_profiles: list[str] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(issue.level == "error" for issue in self.issues)

    @property
    def warnings(self) -> int:
        return sum(issue.level == "warning" for issue in self.issues)


def is_material_estimate(route: ValidatedRoute) -> bool:
    if route.toll_confidence != "estimated":
        return False
    estimated_km = sum(
        float(segment.get("distance_km") or 0.0)
        for segment in route.toll_segments
        if segment.get("confidence") == "estimated"
    )
    estimated_cost = sum(
        float(segment.get("cost") or 0.0)
        for segment in route.toll_segments
        if segment.get("confidence") == "estimated"
    )
    return estimated_km >= 5.0 or estimated_cost >= 1.0


async def validate_scenario(
    scenario: dict[str, Any],
    routing: GraphHopperClient,
    tolls: TollPricingService,
    *,
    fuel_price: float = 1.82,
    motorway_consumption: float = 6.5,
    road_consumption: float = 5.5,
    strict: bool = False,
    enforce_gold: bool = False,
) -> ScenarioResult:
    start = Coordinate(**scenario["start"])
    end = Coordinate(**scenario["end"])
    engine_result = await routing.candidates(start, end)
    issues: list[ValidationIssue] = []
    routes: list[ValidatedRoute] = []

    if engine_result.engine != "graphhopper":
        issues.append(ValidationIssue("error", "GraphHopper indisponible : scénario calculé en démo."))
    if engine_result.retried_profiles:
        issues.append(
            ValidationIssue(
                "info",
                "Profils GraphHopper ayant nécessité une relance : "
                + ", ".join(engine_result.retried_profiles)
                + ".",
            )
        )
    if engine_result.failed_profiles:
        issues.append(
            ValidationIssue(
                "warning",
                "Profils GraphHopper indisponibles après relance : "
                + ", ".join(engine_result.failed_profiles)
                + ".",
            )
        )

    for candidate in engine_result.candidates:
        quote = tolls.quote(
            geometry=candidate["geometry"],
            tolled_km=candidate.get("tolled_km", 0.0),
            toll_ranges=candidate.get("toll_ranges"),
            demo_toll=candidate.get("demo_toll"),
        )
        costs = calculate_costs(
            candidate["motorway_km"],
            candidate["road_km"],
            motorway_consumption,
            road_consumption,
            fuel_price,
            quote.cost,
        )
        segments = [asdict(segment) for segment in quote.segments]
        segment_sum = round(sum(float(segment["cost"]) for segment in segments), 2)
        if segments and abs(segment_sum - quote.cost) > 0.02:
            issues.append(
                ValidationIssue(
                    "error",
                    f"{candidate['id']} : somme des segments ({segment_sum:.2f} €) "
                    f"différente du péage total ({quote.cost:.2f} €).",
                )
            )
        if abs(round(costs.fuel_cost + quote.cost, 2) - costs.total_cost) > 0.01:
            issues.append(ValidationIssue("error", f"{candidate['id']} : total incohérent."))
        if quote.cost < 0 or costs.total_cost < 0:
            issues.append(ValidationIssue("error", f"{candidate['id']} : coût négatif."))

        tolled_km = float(candidate.get("tolled_km", 0.0))
        if quote.confidence == "exact" and quote.cost > 0:
            if tolled_km <= 0.5:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{candidate['id']} : tarif exact {quote.cost:.2f} € incohérent "
                        f"avec seulement {tolled_km:.1f} km marqués payants.",
                    )
                )
            matrix_distance = sum(
                float(segment.get("distance_km") or 0.0)
                for segment in segments
                if segment.get("confidence") == "exact"
            )
            if matrix_distance and matrix_distance > max(tolled_km * 1.8, tolled_km + 80.0):
                issues.append(
                    ValidationIssue(
                        "error",
                        f"{candidate['id']} : distance tarifaire exacte {matrix_distance:.1f} km "
                        f"incohérente avec {tolled_km:.1f} km payants OSM.",
                    )
                )
        if quote.confidence == "exact" and quote.cost > 0:
            if not segments:
                issues.append(
                    ValidationIssue(
                        "error", f"{candidate['id']} : tarif exact sans segment explicatif."
                    )
                )
            for segment in segments:
                if segment.get("confidence") != "exact":
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : total exact contenant un segment non exact.",
                        )
                    )
                if segment.get("exit") is None and not segment.get("entry"):
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : péage ouvert exact sans station identifiée.",
                        )
                    )
                if segment.get("exit") is not None and not segment.get("entry"):
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : matrice exacte sans gare d'entrée.",
                        )
                    )

            exact_segments = [
                segment for segment in segments if segment.get("confidence") == "exact"
            ]
            seen_entry_positions: dict[str, list[float]] = {}
            seen_exit_positions: dict[str, list[float]] = {}
            seen_entry_labels: set[str] = set()
            seen_exit_labels: set[str] = set()
            previous_closed_end: float | None = None
            for segment in exact_segments:
                entry_key = normalize_name(str(segment.get("entry") or ""))
                exit_key = normalize_name(str(segment.get("exit") or ""))
                entry_label = physical_label_key(str(segment.get("entry") or ""))
                exit_label = physical_label_key(str(segment.get("exit") or ""))

                start_km = segment.get("route_start_km")
                end_km = segment.get("route_end_km")
                if start_km is None or end_km is None:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : segment exact sans position sur le tracé.",
                        )
                    )
                    continue
                start_km = float(start_km)
                end_km = float(end_km)
                duplicate_entry = (
                    bool(entry_label and entry_label in seen_entry_labels)
                    or bool(
                        entry_key
                        and any(
                            abs(start_km - position) <= 1.0
                            for position in seen_entry_positions.get(entry_key, [])
                        )
                    )
                )
                duplicate_exit = (
                    bool(exit_label and exit_label in seen_exit_labels)
                    or bool(
                        exit_key
                        and any(
                            abs(end_km - position) <= 1.0
                            for position in seen_exit_positions.get(exit_key, [])
                        )
                    )
                )
                if duplicate_entry:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : gare d'entrée exacte facturée plusieurs fois "
                            f"({segment.get('entry')}).",
                        )
                    )
                if duplicate_exit:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : gare de sortie exacte facturée plusieurs fois "
                            f"({segment.get('exit')}).",
                        )
                    )
                if entry_key:
                    seen_entry_positions.setdefault(entry_key, []).append(start_km)
                if exit_key:
                    seen_exit_positions.setdefault(exit_key, []).append(end_km)
                if entry_label:
                    seen_entry_labels.add(entry_label)
                if exit_label:
                    seen_exit_labels.add(exit_label)
                if end_km + 0.05 < start_km:
                    issues.append(
                        ValidationIssue(
                            "error",
                            f"{candidate['id']} : segment exact dans le mauvais ordre "
                            f"({start_km:.1f} → {end_km:.1f} km).",
                        )
                    )
                if segment.get("exit") is not None:
                    if previous_closed_end is not None and start_km < previous_closed_end - 1.0:
                        issues.append(
                            ValidationIssue(
                                "error",
                                f"{candidate['id']} : sections de péage exactes qui se chevauchent.",
                            )
                        )
                    previous_closed_end = max(previous_closed_end or end_km, end_km)

        if len(candidate.get("geometry", [])) < 2:
            issues.append(ValidationIssue("error", f"{candidate['id']} : géométrie vide."))
        if strict and candidate.get("tolled_km", 0.0) > 0.05 and quote.confidence != "exact":
            issues.append(
                ValidationIssue(
                    "error",
                    f"{candidate['id']} : péage {quote.confidence} en mode strict.",
                )
            )

        routes.append(
            ValidatedRoute(
                id=candidate["id"],
                duration_minutes=int(candidate["duration_minutes"]),
                distance_km=float(candidate["distance_km"]),
                motorway_km=float(candidate["motorway_km"]),
                road_km=float(candidate["road_km"]),
                tolled_km=float(candidate.get("tolled_km", 0.0)),
                toll_cost=float(quote.cost),
                toll_confidence=quote.confidence,
                fuel_cost=float(costs.fuel_cost),
                total_cost=float(costs.total_cost),
                toll_message=quote.message,
                toll_segments=segments,
            )
        )

    routes.sort(key=lambda route: route.duration_minutes)
    minimum = int(scenario.get("min_routes", 1))
    if len(routes) < minimum:
        issues.append(
            ValidationIssue(
                "error",
                f"Seulement {len(routes)} itinéraire(s), minimum attendu : {minimum}.",
            )
        )

    if len({route.id for route in routes}) != len(routes):
        issues.append(ValidationIssue("error", "Identifiants d'itinéraires dupliqués."))

    # Origin/destination examples are coverage probes, not production rules.
    # Numerical expectations are enforced only in explicit gold mode. This
    # avoids tuning the engine to a handful of city pairs while still keeping a
    # separate regression suite for independently verified reference routes.
    if routes and enforce_gold:
        fastest = routes[0]
        allowed_confidences = scenario.get("expected_fastest_confidence")
        if allowed_confidences and fastest.toll_confidence not in allowed_confidences:
            issues.append(
                ValidationIssue(
                    "error",
                    f"Péage du plus rapide : {fastest.toll_confidence}, "
                    f"attendu : {', '.join(allowed_confidences)}.",
                )
            )
        expected_toll = scenario.get("expected_fastest_toll_eur")
        if expected_toll:
            minimum_toll = float(expected_toll["min"])
            maximum_toll = float(expected_toll["max"])
            if not minimum_toll <= fastest.toll_cost <= maximum_toll:
                issues.append(
                    ValidationIssue(
                        "error",
                        f"Péage du plus rapide {fastest.toll_cost:.2f} € hors plage "
                        f"[{minimum_toll:.2f}; {maximum_toll:.2f}] €.",
                    )
                )

    estimated_count = sum(is_material_estimate(route) for route in routes)
    minor_count = sum(
        route.toll_confidence == "estimated" and not is_material_estimate(route) for route in routes
    )
    if estimated_count and not strict:
        issues.append(
            ValidationIssue(
                "warning",
                f"{estimated_count} itinéraire(s) conservent une estimation de péage significative.",
            )
        )
    if minor_count:
        issues.append(
            ValidationIssue(
                "info",
                f"{minor_count} estimation(s) résiduelle(s) négligeable(s) (< 1 € et < 5 km).",
            )
        )

    return ScenarioResult(
        id=scenario["id"],
        name=scenario["name"],
        engine=engine_result.engine,
        engine_message=engine_result.message,
        routes=routes,
        issues=issues,
        retried_profiles=list(engine_result.retried_profiles),
        failed_profiles=list(engine_result.failed_profiles),
    )


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))


def report_payload(results: list[ScenarioResult], *, strict: bool) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "strict": strict,
        "summary": {
            "scenarios": len(results),
            "errors": sum(result.errors for result in results),
            "warnings": sum(result.warnings for result in results),
            "routes": sum(len(result.routes) for result in results),
            "exact": sum(
                route.toll_confidence == "exact" for result in results for route in result.routes
            ),
            "estimated": sum(
                is_material_estimate(route) for result in results for route in result.routes
            ),
            "estimated_minor": sum(
                route.toll_confidence == "estimated" and not is_material_estimate(route)
                for result in results for route in result.routes
            ),
            "none": sum(
                route.toll_confidence == "none" for result in results for route in result.routes
            ),
            "routing_retries": sum(len(result.retried_profiles) for result in results),
            "routing_failures": sum(len(result.failed_profiles) for result in results),
        },
        "results": [
            {
                "id": result.id,
                "name": result.name,
                "engine": result.engine,
                "engine_message": result.engine_message,
                "issues": [asdict(issue) for issue in result.issues],
                "retried_profiles": result.retried_profiles,
                "failed_profiles": result.failed_profiles,
                "routes": [asdict(route) for route in result.routes],
            }
            for result in results
        ],
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Rapport de validation Routeco",
        "",
        f"Généré le `{payload['generated_at']}`.",
        "",
        "## Résumé",
        "",
        f"- Scénarios : **{summary['scenarios']}**",
        f"- Itinéraires : **{summary['routes']}**",
        f"- Péages exacts : **{summary['exact']}**",
        f"- Péages estimés significatifs : **{summary['estimated']}**",
        f"- Estimations résiduelles mineures : **{summary.get('estimated_minor', 0)}**",
        f"- Sans péage : **{summary['none']}**",
        f"- Profils GraphHopper relancés : **{summary.get('routing_retries', 0)}**",
        f"- Profils GraphHopper perdus : **{summary.get('routing_failures', 0)}**",
        f"- Erreurs : **{summary['errors']}**",
        f"- Avertissements : **{summary['warnings']}**",
        "",
        "## Vue d'ensemble",
        "",
        "| Scénario | Routes | Plus rapide | Péage rapide | Exact / estimé / aucun | État |",
        "|---|---:|---:|---:|---:|---|",
    ]

    for result in payload["results"]:
        routes = result["routes"]
        fastest = routes[0] if routes else None
        counts = {
            "exact": sum(route["toll_confidence"] == "exact" for route in routes),
            "estimated": sum(route["toll_confidence"] == "estimated" for route in routes),
            "none": sum(route["toll_confidence"] == "none" for route in routes),
        }
        errors = sum(issue["level"] == "error" for issue in result["issues"])
        warnings = sum(issue["level"] == "warning" for issue in result["issues"])
        state = "OK" if not errors and not warnings else (f"ERREUR ×{errors}" if errors else f"À vérifier ×{warnings}")
        fastest_duration = f"{fastest['duration_minutes']} min" if fastest else "—"
        fastest_toll = f"{fastest['toll_cost']:.2f} €" if fastest else "—"
        lines.append(
            f"| {result['name']} | {len(routes)} | {fastest_duration} | {fastest_toll} | "
            f"{counts['exact']} / {counts['estimated']} / {counts['none']} | {state} |"
        )

    for result in payload["results"]:
        lines.extend(["", f"## {result['name']}", ""])
        for issue in result["issues"]:
            marker = "❌" if issue["level"] == "error" else ("ℹ️" if issue["level"] == "info" else "⚠️")
            lines.append(f"- {marker} {issue['message']}")
        if not result["issues"]:
            lines.append("- Aucun problème détecté.")
        lines.extend(
            [
                "",
                "| # | Durée | Distance | Autoroute | Péage | Confiance | Total |",
                "|---:|---:|---:|---:|---:|---|---:|",
            ]
        )
        for index, route in enumerate(result["routes"], start=1):
            lines.append(
                f"| {index} | {route['duration_minutes']} min | {route['distance_km']:.1f} km | "
                f"{route['motorway_km']:.1f} km | {route['toll_cost']:.2f} € | "
                f"{route['toll_confidence']} | {route['total_cost']:.2f} € |"
            )
            for segment in route["toll_segments"]:
                entry = segment.get("entry") or "segment non identifié"
                exit_ = segment.get("exit")
                label = f"{entry} → {exit_}" if exit_ else entry
                lines.append(
                    f"  - Péage : {label} — {segment['cost']:.2f} € "
                    f"({segment['confidence']})."
                )

    lines.append("")
    return "\n".join(lines)

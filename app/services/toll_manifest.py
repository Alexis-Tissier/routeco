from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any

from app.services.toll_gap_classifier import (
    CAUSE_ACTION,
    CAUSE_PRIORITY,
    classify_unresolved_interval,
)

# ROUTECO_V034_GAP_CLASSIFIER


def _key(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(
        char
        for char in text
        if not unicodedata.combining(char)
    )
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text.casefold(),
    ).strip()


def _candidate_kind(station: dict[str, Any]) -> str:
    system_type = str(
        station.get("system_type") or ""
    ).lower()
    physical_type = str(
        station.get("physical_type") or ""
    ).lower()
    open_price = station.get("open_price")
    lateral_km = float(
        station.get("lateral_km") or 999.0
    )

    if (
        system_type == "open"
        and open_price is None
        and lateral_km <= 0.12
    ):
        return "missing_open_tariff"

    if (
        system_type in {"mainline", "barrier"}
        or physical_type in {"mainline", "barrier"}
    ) and open_price is None and lateral_km <= 0.12:
        return "station_tariff_review"

    return ""


def build_missing_toll_manifest(
    validation_payload: dict[str, Any],
) -> dict[str, Any]:
    intervals: list[dict[str, Any]] = []
    station_groups: dict[
        tuple[str, str, str],
        dict[str, Any],
    ] = {}
    corridor_groups: dict[
        tuple[str, str, str],
        dict[str, Any],
    ] = {}
    affected_routes: set[tuple[str, str]] = set()
    cause_counts: Counter[str] = Counter()

    for scenario in validation_payload.get("results", []):
        scenario_id = str(scenario.get("id") or "")
        scenario_name = str(scenario.get("name") or "")
        for route in scenario.get("routes", []):
            route_id = str(route.get("id") or "")
            diagnostics = route.get(
                "toll_diagnostics",
                [],
            )
            for diagnostic in diagnostics:
                if diagnostic.get("kind") not in {
                    "unresolved_toll_interval",
                    "unresolved_toll_range",
                }:
                    continue

                affected_routes.add(
                    (scenario_id, route_id)
                )
                start_km = float(
                    diagnostic.get(
                        "route_start_km",
                        0.0,
                    )
                    or 0.0
                )
                end_km = float(
                    diagnostic.get(
                        "route_end_km",
                        0.0,
                    )
                    or 0.0
                )
                nearby = list(
                    diagnostic.get(
                        "nearby_stations",
                        [],
                    )
                )

                occurrence = {
                    "scenario_id": scenario_id,
                    "scenario_name": scenario_name,
                    "route_id": route_id,
                    "route_start_km": start_km,
                    "route_end_km": end_km,
                    "unresolved_km": float(
                        diagnostic.get(
                            "unresolved_km",
                            0.0,
                        )
                        or 0.0
                    ),
                    "event_only": bool(
                        diagnostic.get(
                            "event_only",
                            False,
                        )
                    ),
                    "toll_states": list(
                        diagnostic.get(
                            "toll_states",
                            [],
                        )
                    ),
                    "nearby_stations": nearby,
                    "exact_segments": list(
                        diagnostic.get(
                            "exact_segments",
                            [],
                        )
                    ),
                    "closed_topology": dict(
                        diagnostic.get(
                            "closed_topology",
                            {},
                        )
                        or {}
                    ),
                }
                cause = classify_unresolved_interval(occurrence)
                occurrence["cause"] = cause
                occurrence["priority"] = CAUSE_PRIORITY[cause]
                occurrence["recommended_action"] = CAUSE_ACTION[cause]
                cause_counts[cause] += 1
                intervals.append(occurrence)

                for station in nearby:
                    kind = _candidate_kind(station)
                    if not kind:
                        continue
                    station_name = str(
                        station.get("name") or ""
                    )
                    operator = str(
                        station.get("operator") or ""
                    )
                    group_key = (
                        kind,
                        _key(station_name),
                        operator.upper(),
                    )
                    group = station_groups.setdefault(
                        group_key,
                        {
                            "kind": kind,
                            "station": station_name,
                            "operator": operator,
                            "system_type": station.get(
                                "system_type"
                            ),
                            "physical_type": station.get(
                                "physical_type"
                            ),
                            "occurrences": 0,
                            "affected_routes": [],
                            "positions": [],
                        },
                    )
                    group["occurrences"] += 1
                    route_ref = {
                        "scenario_id": scenario_id,
                        "route_id": route_id,
                    }
                    if route_ref not in group[
                        "affected_routes"
                    ]:
                        group["affected_routes"].append(
                            route_ref
                        )
                    position = {
                        "route_km": station.get(
                            "route_km"
                        ),
                        "lateral_km": station.get(
                            "lateral_km"
                        ),
                    }
                    if position not in group["positions"]:
                        group["positions"].append(position)

                start_candidates = sorted(
                    nearby,
                    key=lambda station: (
                        abs(
                            float(
                                station.get(
                                    "route_km",
                                    0.0,
                                )
                                or 0.0
                            )
                            - start_km
                        ),
                        float(
                            station.get(
                                "lateral_km",
                                999.0,
                            )
                            or 999.0
                        ),
                    ),
                )[:3]
                end_candidates = sorted(
                    nearby,
                    key=lambda station: (
                        abs(
                            float(
                                station.get(
                                    "route_km",
                                    0.0,
                                )
                                or 0.0
                            )
                            - end_km
                        ),
                        float(
                            station.get(
                                "lateral_km",
                                999.0,
                            )
                            or 999.0
                        ),
                    ),
                )[:3]

                start_labels = sorted(
                    {
                        str(item.get("name") or "")
                        for item in start_candidates
                        if str(item.get("name") or "")
                    }
                )
                end_labels = sorted(
                    {
                        str(item.get("name") or "")
                        for item in end_candidates
                        if str(item.get("name") or "")
                    }
                )
                if start_labels or end_labels:
                    start_key = "|".join(
                        _key(item) for item in start_labels
                    )
                    end_key = "|".join(
                        _key(item) for item in end_labels
                    )
                else:
                    start_key = f"{scenario_id}:{route_id}"
                    end_key = f"{start_km:.1f}:{end_km:.1f}"
                corridor_key = (
                    cause,
                    start_key,
                    end_key,
                )
                corridor = corridor_groups.setdefault(
                    corridor_key,
                    {
                        "cause": cause,
                        "priority": CAUSE_PRIORITY[cause],
                        "recommended_action": CAUSE_ACTION[cause],
                        "start_candidates": start_labels,
                        "end_candidates": end_labels,
                        "occurrences": 0,
                        "affected_routes": [],
                        "intervals": [],
                    },
                )
                corridor["occurrences"] += 1
                route_ref = {
                    "scenario_id": scenario_id,
                    "route_id": route_id,
                }
                if route_ref not in corridor[
                    "affected_routes"
                ]:
                    corridor["affected_routes"].append(
                        route_ref
                    )
                corridor["intervals"].append(
                    {
                        "route_start_km": start_km,
                        "route_end_km": end_km,
                        "unresolved_km": occurrence[
                            "unresolved_km"
                        ],
                    }
                )

    station_candidates = sorted(
        station_groups.values(),
        key=lambda item: (
            -int(item["occurrences"]),
            item["kind"],
            _key(str(item["station"])),
        ),
    )
    corridors = sorted(
        corridor_groups.values(),
        key=lambda item: (
            -int(item["occurrences"]),
            "|".join(item["start_candidates"]),
            "|".join(item["end_candidates"]),
        ),
    )

    verification_queue = sorted(
        [
            {
                "priority": item["priority"],
                "cause": item["cause"],
                "recommended_action": item["recommended_action"],
                "scenario_id": item["scenario_id"],
                "route_id": item["route_id"],
                "route_start_km": item["route_start_km"],
                "route_end_km": item["route_end_km"],
                "unresolved_km": item["unresolved_km"],
            }
            for item in intervals
        ],
        key=lambda item: (
            int(item["priority"]),
            -float(item["unresolved_km"]),
            item["scenario_id"],
            item["route_id"],
        ),
    )

    return {
        "generated_at": validation_payload.get(
            "generated_at"
        ),
        "source_summary": validation_payload.get(
            "summary",
            {},
        ),
        "summary": {
            "unresolved_intervals": len(intervals),
            "affected_routes": len(affected_routes),
            "station_review_candidates": len(
                station_candidates
            ),
            "corridor_review_candidates": len(
                corridors
            ),
            "cause_counts": dict(sorted(cause_counts.items())),
        },
        "verification_queue": verification_queue,
        "station_review_candidates": station_candidates,
        "corridor_review_candidates": corridors,
        "unresolved_intervals": intervals,
    }


def render_missing_toll_manifest(
    manifest: dict[str, Any],
) -> str:
    summary = manifest["summary"]
    lines = [
        "# Manifeste des données tarifaires à examiner",
        "",
        "Ce fichier contient des candidats de diagnostic, "
        "pas des tarifs officiels validés.",
        "",
        "## Résumé",
        "",
        f"- Intervalles non résolus : **{summary['unresolved_intervals']}**",
        f"- Itinéraires affectés : **{summary['affected_routes']}**",
        f"- Gares/portiques à examiner : **{summary['station_review_candidates']}**",
        f"- Corridors à examiner : **{summary['corridor_review_candidates']}**",
        "",
        "### Causes probables",
        "",
    ]
    for cause, count in summary.get("cause_counts", {}).items():
        lines.append(f"- `{cause}` : **{count}**")
    if not summary.get("cause_counts"):
        lines.append("- Aucun intervalle non résolu.")
    lines.extend(
        [
            "",
            "## File de vérification",
            "",
        ]
    )
    for item in manifest.get("verification_queue", []):
        lines.append(
            f"- P{item['priority']} `{item['cause']}` — "
            f"{item['scenario_id']} / {item['route_id']} — "
            f"{item['route_start_km']:.1f}→"
            f"{item['route_end_km']:.1f} km : "
            f"{item['recommended_action']}"
        )
    if not manifest.get("verification_queue"):
        lines.append("- Aucune vérification en attente.")
    lines.extend(
        [
            "",
            "## Gares et portiques à examiner",
            "",
        ]
    )

    candidates = manifest.get(
        "station_review_candidates",
        [],
    )
    if not candidates:
        lines.append("- Aucun candidat rapproché automatiquement.")
    for item in candidates:
        lines.append(
            "- "
            f"`{item['kind']}` — {item['station']} "
            f"({item.get('operator') or 'opérateur inconnu'}) : "
            f"{item['occurrences']} occurrence(s)."
        )

    lines.extend(
        [
            "",
            "## Corridors non résolus",
            "",
        ]
    )
    corridors = manifest.get(
        "corridor_review_candidates",
        [],
    )
    if not corridors:
        lines.append("- Aucun corridor non résolu.")
    for item in corridors:
        start = ", ".join(
            item.get("start_candidates", [])
        ) or "borne de départ inconnue"
        end = ", ".join(
            item.get("end_candidates", [])
        ) or "borne d'arrivée inconnue"
        lines.append(
            f"- {start} → {end} : "
            f"{item['occurrences']} occurrence(s)."
        )

    lines.extend(
        [
            "",
            "## Intervalles détaillés",
            "",
        ]
    )
    for item in manifest.get(
        "unresolved_intervals",
        [],
    ):
        lines.append(
            "- "
            f"{item['scenario_name']} / {item['route_id']} : "
            f"{item['route_start_km']:.1f}→"
            f"{item['route_end_km']:.1f} km, "
            f"{item['unresolved_km']:.1f} km non résolus."
        )

    return "\n".join(lines) + "\n"

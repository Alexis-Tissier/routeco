from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.models import Coordinate
from app.services.demo import demo_candidates
from app.services.geo import haversine_km, polyline_distance_km

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineResult:
    engine: str
    message: str
    candidates: list[dict]
    retried_profiles: list[str] = field(default_factory=list)
    failed_profiles: list[str] = field(default_factory=list)
    routing_seconds: float = 0.0
    native_alternatives_skipped: bool = False


@dataclass(slots=True)
class ProfileResult:
    name: str
    candidates: list[dict]
    attempts: int
    last_error: str = ""

    @property
    def retried(self) -> bool:
        # A failed profile can still have been retried several times. Reporting
        # the attempt is useful for diagnostics even when recovery failed.
        return self.attempts > 1

    @property
    def failed(self) -> bool:
        return not self.candidates


class GraphHopperRequestError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail.strip().replace("\n", " ")[:300]
        super().__init__(f"HTTP {status_code}: {self.detail or 'réponse GraphHopper invalide'}")

    @property
    def retryable(self) -> bool:
        return self.status_code in {400, 408, 409, 429, 500, 502, 503, 504}


class GraphHopperClient:
    PATH_DETAILS = (
        "road_class",
        "road_class_link",
        "street_name",
        "street_ref",
        "toll",
    )

    def __init__(self, base_url: str, timeout_seconds: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    async def available(self) -> bool:
        try:
            # GraphHopper is a local Routeco dependency. Environment proxies
            # must not intercept localhost health checks or route requests.
            async with httpx.AsyncClient(
                timeout=2.5,
                trust_env=False,
            ) as client:
                response = await client.get(f"{self.base_url}/info")
                return response.is_success
        except httpx.HTTPError:
            return False

    async def candidates(self, start: Coordinate, end: Coordinate) -> EngineResult:
        routing_started = time.perf_counter()
        if not await self.available():
            return EngineResult(
                "demo",
                "GraphHopper local n'est pas démarré : résultats de démonstration.",
                demo_candidates(start, end),
                routing_seconds=round(time.perf_counter() - routing_started, 3),
            )

        profiles = [
            ("fastest", 1.0, 1.0, 0),
            ("light", 0.88, 0.72, 1),
            ("balanced", 0.70, 0.42, 2),
            ("economy", 0.48, 0.12, 3),
            ("free", 0.30, 0.05, 4),
        ]
        profile_tasks = [
            asyncio.create_task(
                self._request_profile(start, end, name, motorway, toll, rank)
            )
            for name, motorway, toll, rank in profiles
        ]
        # GraphHopper has a native alternative-route algorithm that is far less
        # prone to the maximum-nodes failures triggered by very aggressive custom
        # models. It provides a robust baseline of genuinely different routes,
        # while the five custom profiles still search for economical variants.
        native_task = asyncio.create_task(
            self._request_native_alternatives(start, end)
        )
        try:
            responses = await asyncio.gather(
                *profile_tasks,
                return_exceptions=True,
            )
        except BaseException:
            native_task.cancel()
            await asyncio.gather(
                native_task,
                return_exceptions=True,
            )
            raise

        candidates: list[dict] = []
        retried_profiles: list[str] = []
        failed_profile_results: list[ProfileResult] = []
        for result in responses:
            if isinstance(result, Exception):
                logger.warning("Unexpected GraphHopper profile failure: %s", result)
                continue
            candidates.extend(result.candidates)
            if result.retried:
                retried_profiles.append(result.name)
            if result.failed:
                failed_profile_results.append(result)
                logger.warning(
                    "GraphHopper profile %s unavailable after %s attempt(s): %s",
                    result.name,
                    result.attempts,
                    result.last_error,
                )

        # Native alternatives are supplemental. When the five custom profiles
        # already produced at least four genuinely distinct routes, waiting for
        # the native request to hit its 25-second ceiling only adds latency. Keep
        # it whenever it has already completed, or whenever custom coverage is
        # sparse enough that it can still improve resilience.
        native_alternatives_skipped = False
        distinct_custom = self._deduplicate(candidates)
        if (
            not native_task.done()
            and len(distinct_custom) >= 4
        ):
            native_task.cancel()
            try:
                await native_task
            except asyncio.CancelledError:
                pass
            native_result: list[dict] | Exception = []
            native_alternatives_skipped = True
        else:
            native_response = await asyncio.gather(
                native_task,
                return_exceptions=True,
            )
            native_result = native_response[0]

        # Native alternatives are usable even when every custom profile fails.
        # Add them before choosing a fallback geometry so a bounded native path can
        # seed segmented recovery instead of silently losing all economic profiles.
        if isinstance(native_result, Exception):
            # A native alternative-route failure is expected on some very long
            # searches. Do not print it as a warning when custom profiles already
            # produced usable routes; it remains visible at INFO level.
            log_native_failure = logger.info if candidates else logger.warning
            log_native_failure(
                "GraphHopper native alternatives unavailable: %s", native_result
            )
        else:
            candidates.extend(native_result)

        # A France-wide low-toll search can still hit the server's visited-node
        # ceiling even with landmarks. Re-run only the failed profiles through
        # one or two waypoints sampled from the fastest geometry. GraphHopper
        # then solves several shorter legs in one request, preserving a general
        # A-to-B algorithm without encoding any city pair or corridor.
        fastest_geometry = next(
            (
                item.get("geometry", [])
                for item in candidates
                if item.get("profile") == "fastest" and len(item.get("geometry", [])) >= 2
            ),
            [],
        )
        if not fastest_geometry and candidates:
            baseline = min(
                candidates,
                key=lambda item: (
                    item.get("duration_minutes", float("inf")),
                    item.get("distance_km", float("inf")),
                ),
            )
            candidate_geometry = baseline.get("geometry", [])
            if len(candidate_geometry) >= 2:
                fastest_geometry = candidate_geometry
        recovered_names: set[str] = set()
        if fastest_geometry and failed_profile_results:
            profile_by_name = {name: (motorway, toll, rank) for name, motorway, toll, rank in profiles}
            fallback_tasks = []
            fallback_names = []
            for result in failed_profile_results:
                config = profile_by_name.get(result.name)
                if config is None or result.name == "fastest":
                    continue
                motorway, toll, rank = config
                fallback_names.append(result.name)
                fallback_tasks.append(
                    self._request_segmented_profile(
                        start,
                        end,
                        result.name,
                        motorway,
                        toll,
                        rank,
                        fastest_geometry,
                    )
                )
            if fallback_tasks:
                fallback_responses = await asyncio.gather(
                    *fallback_tasks, return_exceptions=True
                )
                for name, fallback in zip(fallback_names, fallback_responses):
                    if isinstance(fallback, Exception):
                        logger.warning(
                            "GraphHopper segmented fallback %s unavailable: %s",
                            name,
                            fallback,
                        )
                        continue
                    if fallback:
                        candidates.extend(fallback)
                        recovered_names.add(name)
                        if name not in retried_profiles:
                            retried_profiles.append(name)

        failed_profiles = [
            result.name
            for result in failed_profile_results
            if result.name not in recovered_names
        ]

        candidates = self._deduplicate(candidates)
        if not candidates:
            return EngineResult(
                "demo",
                "GraphHopper a répondu sans itinéraire exploitable : mode démonstration.",
                demo_candidates(start, end),
                retried_profiles=retried_profiles,
                failed_profiles=failed_profiles,
                routing_seconds=round(
                    time.perf_counter() - routing_started,
                    3,
                ),
                native_alternatives_skipped=(
                    native_alternatives_skipped
                ),
            )

        message = f"{len(candidates)} itinéraires candidats calculés localement."
        if retried_profiles:
            message += f" {len(retried_profiles)} profil(s) relancé(s)."
        if recovered_names:
            message += f" {len(recovered_names)} profil(s) récupéré(s) par segmentation."
        if failed_profiles:
            message += f" {len(failed_profiles)} profil(s) indisponible(s)."
        if native_alternatives_skipped:
            message += " Variante native devenue inutile, annulée."
        return EngineResult(
            "graphhopper",
            message,
            candidates,
            retried_profiles=retried_profiles,
            failed_profiles=failed_profiles,
            routing_seconds=round(
                time.perf_counter() - routing_started,
                3,
            ),
            native_alternatives_skipped=(
                native_alternatives_skipped
            ),
        )

    async def _request_native_alternatives(
        self, start: Coordinate, end: Coordinate
    ) -> list[dict]:
        """Ask GraphHopper for native alternatives using its bounded algorithm.

        This request deliberately uses the server profile without a request-time
        custom model. It can therefore use the prepared landmarks efficiently and
        remains usable on long France-wide journeys where low motorway/toll
        priorities can exceed the flexible-search node limit.
        """
        direct_km = haversine_km(
            (start.lon, start.lat),
            (end.lon, end.lat),
        )
        # Three native alternatives are sufficient for regional journeys. Restore
        # a fourth one only on France-scale routes, where diversity matters most.
        # The supplemental request remains bounded by the 25-second timeout below.
        native_max_paths = 4 if direct_km >= 450.0 else 3
        body: dict[str, Any] = {
            "points": [[start.lon, start.lat], [end.lon, end.lat]],
            "profile": "car",
            "locale": "fr",
            "instructions": False,
            "points_encoded": False,
            "details": list(self.PATH_DETAILS),
            "algorithm": "alternative_route",
            "alternative_route.max_paths": native_max_paths,
            "alternative_route.max_weight_factor": 1.55,
            "alternative_route.max_share_factor": 0.80,
        }
        try:
            # Native alternatives are supplemental: custom profiles must not wait
            # up to the global 120/180 s ceiling for them. The request already runs
            # concurrently with the custom profiles, so this is a wall-clock cap.
            payload = await asyncio.wait_for(
                self._post_route(body),
                timeout=min(self.timeout, 25.0),
            )
        except TimeoutError as exc:
            raise GraphHopperRequestError(
                408,
                "native alternative-route timeout after 25 seconds",
            ) from exc
        return self._paths_to_candidates(payload, "native", 0)

    async def _request_profile(
        self,
        start: Coordinate,
        end: Coordinate,
        name: str,
        motorway_priority: float,
        toll_priority: float,
        rank: int,
    ) -> ProfileResult:
        attempts = self._retry_plan(motorway_priority, toll_priority)
        last_error = ""
        for attempt_number, (motorway, toll, distance_influence) in enumerate(
            attempts, start=1
        ):
            try:
                candidates = await self._request_once(
                    start,
                    end,
                    name,
                    motorway,
                    toll,
                    rank,
                    distance_influence,
                )
                return ProfileResult(name, candidates, attempt_number, last_error)
            except GraphHopperRequestError as exc:
                last_error = str(exc)
                if not exc.retryable or attempt_number == len(attempts):
                    break
                logger.info(
                    "GraphHopper profile %s failed on attempt %s; retrying with a "
                    "less aggressive custom model (%s)",
                    name,
                    attempt_number,
                    exc,
                )
            except httpx.HTTPError as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt_number == len(attempts):
                    break
                logger.info(
                    "GraphHopper profile %s transport error on attempt %s; retrying: %s",
                    name,
                    attempt_number,
                    exc,
                )
        return ProfileResult(name, [], len(attempts), last_error)

    @staticmethod
    def _retry_plan(
        motorway_priority: float, toll_priority: float
    ) -> list[tuple[float, float, float]]:
        """Return increasingly bounded custom models.

        Very low motorway/toll priorities can make GraphHopper explore millions
        of nodes on long journeys. Retrying with a less aggressive model retains
        a useful alternative while avoiding a silent candidate loss. The plan is
        purely numerical and independent from any origin or destination.
        """
        raw = [
            (motorway_priority, toll_priority, 90.0),
            (max(motorway_priority, 0.58), max(toll_priority, 0.24), 130.0),
            (max(motorway_priority, 0.78), max(toll_priority, 0.50), 180.0),
        ]
        output: list[tuple[float, float, float]] = []
        for item in raw:
            rounded = (round(item[0], 3), round(item[1], 3), round(item[2], 1))
            if rounded not in output:
                output.append(rounded)
        return output

    async def _request_segmented_profile(
        self,
        start: Coordinate,
        end: Coordinate,
        name: str,
        motorway_priority: float,
        toll_priority: float,
        rank: int,
        baseline_geometry: list[list[float]],
    ) -> list[dict]:
        """Recover a failed long-distance custom profile using via points.

        The via points are sampled by travelled distance from the already-known
        fastest route. They merely divide the search space; the custom model is
        still applied to every leg, so the resulting path can leave the fastest
        corridor to avoid motorways or tolls.
        """
        total_km = polyline_distance_km(baseline_geometry)
        if total_km < 450.0:
            plans = ((0.5,), (1 / 3, 2 / 3))
        elif total_km < 800.0:
            plans = ((0.5,), (1 / 3, 2 / 3), (0.25, 0.5, 0.75))
        else:
            plans = ((0.25, 0.5, 0.75), (0.2, 0.4, 0.6, 0.8))

        retry_models = self._retry_plan(motorway_priority, toll_priority)
        models = [retry_models[0]]
        if retry_models[-1] != retry_models[0]:
            models.append(retry_models[-1])

        last_error: Exception | None = None
        attempt_index = 0
        for motorway, toll, distance_influence in models:
            for fractions in plans:
                attempt_index += 1
                vias = [
                    self._point_at_fraction(baseline_geometry, value)
                    for value in fractions
                ]
                points = [[start.lon, start.lat], *vias, [end.lon, end.lat]]
                body: dict[str, Any] = {
                    "points": points,
                    "profile": "car",
                    "locale": "fr",
                    "instructions": False,
                    "points_encoded": False,
                    "details": list(self.PATH_DETAILS),
                    "pass_through": True,
                    "custom_model": {
                        "priority": [
                            {
                                "if": "road_class == MOTORWAY",
                                "multiply_by": motorway,
                            },
                            {"if": "toll == ALL", "multiply_by": toll},
                        ],
                        "distance_influence": distance_influence,
                    },
                }
                try:
                    payload = await self._post_route(body)
                    routes = self._paths_to_candidates(
                        payload, f"{name}-seg{attempt_index}", rank
                    )
                    if routes:
                        return routes
                except (GraphHopperRequestError, httpx.HTTPError) as exc:
                    last_error = exc
                    logger.info(
                        "GraphHopper segmented fallback %s/%s failed: %s",
                        name,
                        attempt_index,
                        exc,
                    )
        if last_error is not None:
            logger.warning("GraphHopper segmented fallback %s exhausted: %s", name, last_error)
        return []

    @staticmethod
    def _point_at_fraction(
        geometry: list[list[float]], fraction: float
    ) -> list[float]:
        if len(geometry) < 2:
            return list(geometry[0]) if geometry else [0.0, 0.0]
        fraction = min(1.0, max(0.0, fraction))
        lengths = [
            polyline_distance_km([geometry[index - 1], geometry[index]])
            for index in range(1, len(geometry))
        ]
        total = sum(lengths)
        if total <= 0:
            return list(geometry[round((len(geometry) - 1) * fraction)])
        target = total * fraction
        travelled = 0.0
        for index, length in enumerate(lengths, start=1):
            if travelled + length >= target and length > 0:
                ratio = (target - travelled) / length
                start = geometry[index - 1]
                end = geometry[index]
                return [
                    start[0] + (end[0] - start[0]) * ratio,
                    start[1] + (end[1] - start[1]) * ratio,
                ]
            travelled += length
        return list(geometry[-1])

    async def _request_once(
        self,
        start: Coordinate,
        end: Coordinate,
        name: str,
        motorway_priority: float,
        toll_priority: float,
        rank: int,
        distance_influence: float,
    ) -> list[dict]:
        body: dict[str, Any] = {
            "points": [[start.lon, start.lat], [end.lon, end.lat]],
            "profile": "car",
            "locale": "fr",
            "instructions": False,
            "points_encoded": False,
            "details": list(self.PATH_DETAILS),
            "custom_model": {
                "priority": [
                    {
                        "if": "road_class == MOTORWAY",
                        "multiply_by": motorway_priority,
                    },
                    {"if": "toll == ALL", "multiply_by": toll_priority},
                ],
                "distance_influence": distance_influence,
            },
        }
        payload = await self._post_route(body)
        return self._paths_to_candidates(payload, name, rank)

    def _paths_to_candidates(
        self, payload: dict[str, Any], name: str, rank: int
    ) -> list[dict]:
        output: list[dict] = []
        for path_index, path in enumerate(payload.get("paths", [])):
            geometry = path.get("points", {}).get("coordinates", [])
            if len(geometry) < 2:
                continue
            road_class_details = path.get("details", {}).get("road_class", [])
            road_class_link_details = path.get("details", {}).get(
                "road_class_link", []
            )
            street_name_details = path.get("details", {}).get(
                "street_name", []
            )
            street_ref_details = path.get("details", {}).get(
                "street_ref", []
            )
            toll_details = path.get("details", {}).get("toll", [])
            # ROUTECO_V034_TOLL_STATE_INTERVALS
            # Preserve every GraphHopper toll state. Routeco still derives the
            # passenger-car paid ranges from ALL, but no longer discards NO,
            # HGV or MISSING/unknown intervals needed for completeness proofs.
            toll_state_intervals = self._detail_intervals(
                geometry,
                toll_details,
            )
            motorway_km = self._detail_distance(
                geometry, road_class_details, {"MOTORWAY"}
            )
            # Routeco prices passenger vehicles (classe 1). GraphHopper's
            # HGV value means "toll for heavy goods vehicles only", not all cars.
            toll_ranges = self._detail_ranges(geometry, toll_details, {"ALL"})
            tolled_km = sum(item["distance_km"] for item in toll_ranges)
            total_km = float(path.get("distance", 0)) / 1000 or polyline_distance_km(
                geometry
            )
            motorway_km = min(total_km, motorway_km)
            route_hash = hashlib.sha1(
                json.dumps(
                    geometry[:: max(1, len(geometry) // 25)], separators=(",", ":")
                ).encode()
            ).hexdigest()[:12]
            output.append(
                {
                    "id": f"gh-{name}-{path_index}-{route_hash}",
                    "profile": name,
                    "profile_rank": rank + path_index,
                    "distance_km": round(total_km, 1),
                    "duration_minutes": round(float(path.get("time", 0)) / 60000),
                    "motorway_km": round(motorway_km, 1),
                    "road_km": round(max(0, total_km - motorway_km), 1),
                    "tolled_km": round(tolled_km, 1),
                    "toll_ranges": toll_ranges,
                    "toll_state_intervals": toll_state_intervals,
                    "road_class_link_details": road_class_link_details,
                    "street_name_details": street_name_details,
                    "street_ref_details": street_ref_details,
                    "geometry": geometry,
                    "source": "graphhopper",
                }
            )
        return output

    async def _post_route(self, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            timeout=self.timeout,
            trust_env=False,
        ) as client:
            response = await client.post(f"{self.base_url}/route", json=body)
        if not response.is_success:
            detail = response.text
            try:
                payload = response.json()
                detail = str(payload.get("message") or payload.get("hints") or detail)
            except (ValueError, TypeError, AttributeError):
                pass
            raise GraphHopperRequestError(response.status_code, detail)
        return response.json()

    @staticmethod
    def _detail_intervals(
        geometry: list[list[float]],
        details: list[list],
    ) -> list[dict]:
        # Return every GraphHopper toll state with classe-1 semantics.
        # ALL applies to cars. HGV applies only to heavy goods vehicles. NO is
        # explicit non-toll. MISSING remains unknown because an absent OSM tag
        # is not positive proof that a road is free.
        intervals: list[dict] = []
        for detail in details:
            if len(detail) != 3 or len(geometry) < 2:
                continue
            start_index = max(
                0,
                min(len(geometry) - 2, int(detail[0])),
            )
            end_index = max(
                start_index + 1,
                min(len(geometry) - 1, int(detail[1])),
            )
            distance = polyline_distance_km(
                geometry[start_index : end_index + 1]
            )
            if distance <= 0.01:
                continue

            value = str(detail[2]).upper()
            if value == "ALL":
                class1_status = "toll"
            elif value in {"NO", "HGV"}:
                class1_status = "free"
            else:
                class1_status = "unknown"

            intervals.append(
                {
                    "start_index": start_index,
                    "end_index": end_index,
                    "distance_km": round(distance, 3),
                    "value": value,
                    "class1_status": class1_status,
                }
            )
        return intervals

    @staticmethod
    def _detail_ranges(
        geometry: list[list[float]], details: list[list], accepted_values: set[str]
    ) -> list[dict]:
        ranges: list[dict] = []
        for detail in details:
            if len(detail) != 3 or str(detail[2]).upper() not in accepted_values:
                continue
            start_index = max(0, min(len(geometry) - 2, int(detail[0])))
            end_index = max(start_index + 1, min(len(geometry) - 1, int(detail[1])))
            distance = polyline_distance_km(geometry[start_index : end_index + 1])
            if distance <= 0.01:
                continue
            previous = ranges[-1] if ranges else None
            merge = False
            if previous is not None:
                if start_index <= previous["end_index"]:
                    merge = True
                else:
                    physical_gap = polyline_distance_km(
                        geometry[previous["end_index"] : start_index + 1]
                    )
                    merge = physical_gap <= 0.75

            if previous is not None and merge:
                old_end = previous["end_index"]
                previous["end_index"] = max(old_end, end_index)
                if start_index <= old_end:
                    previous["distance_km"] = round(
                        polyline_distance_km(
                            geometry[
                                previous["start_index"] : previous["end_index"] + 1
                            ]
                        ),
                        3,
                    )
                else:
                    previous["distance_km"] = round(
                        previous["distance_km"] + distance,
                        3,
                    )
            else:
                ranges.append(
                    {
                        "start_index": start_index,
                        "end_index": end_index,
                        "distance_km": round(distance, 3),
                    }
                )
        return ranges

    @staticmethod
    def _detail_distance(
        geometry: list[list[float]], details: list[list], accepted_values: set[str]
    ) -> float:
        distance = 0.0
        for detail in details:
            if len(detail) != 3 or str(detail[2]).upper() not in accepted_values:
                continue
            start_index = max(0, int(detail[0]))
            end_index = min(len(geometry) - 1, int(detail[1]))
            if end_index > start_index:
                distance += polyline_distance_km(
                    geometry[start_index : end_index + 1]
                )
        return distance

    @staticmethod
    def _deduplicate(candidates: list[dict]) -> list[dict]:
        kept: list[dict] = []
        for candidate in sorted(candidates, key=lambda item: item["duration_minutes"]):
            duplicate = any(
                abs(candidate["distance_km"] - other["distance_km"]) < 1.2
                and abs(candidate["duration_minutes"] - other["duration_minutes"]) < 3
                and abs(candidate["motorway_km"] - other["motorway_km"]) < 4
                and abs(
                    candidate.get("tolled_km", 0.0) - other.get("tolled_km", 0.0)
                ) < 2.0
                for other in kept
            )
            if not duplicate:
                kept.append(candidate)
        return kept[:24]

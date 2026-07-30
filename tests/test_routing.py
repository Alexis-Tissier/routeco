from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models import Coordinate
from app.services.routing import GraphHopperClient, GraphHopperRequestError


class RetryClient(GraphHopperClient):
    def __init__(self, failures: int) -> None:
        super().__init__("http://graphhopper.test")
        self.failures = failures
        self.bodies: list[dict] = []

    async def _post_route(self, body: dict) -> dict:
        self.bodies.append(body)
        if len(self.bodies) <= self.failures:
            raise GraphHopperRequestError(400, "maximum nodes exceeded")
        return {
            "paths": [
                {
                    "distance": 10_000,
                    "time": 600_000,
                    "points": {"coordinates": [[2.0, 48.0], [2.1, 48.1]]},
                    "details": {"road_class": [], "toll": []},
                }
            ]
        }


def test_graphhopper_profile_retries_with_less_aggressive_model() -> None:
    client = RetryClient(failures=1)
    result = asyncio.run(
        client._request_profile(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=45.0, lon=4.0),
            "free",
            0.30,
            0.05,
            4,
        )
    )

    assert result.retried is True
    assert result.attempts == 2
    assert len(result.candidates) == 1
    first = client.bodies[0]["custom_model"]
    second = client.bodies[1]["custom_model"]
    assert second["distance_influence"] > first["distance_influence"]
    assert second["priority"][0]["multiply_by"] > first["priority"][0]["multiply_by"]
    assert second["priority"][1]["multiply_by"] > first["priority"][1]["multiply_by"]


def test_graphhopper_profile_reports_permanent_failure() -> None:
    client = RetryClient(failures=10)
    result = asyncio.run(
        client._request_profile(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=45.0, lon=4.0),
            "economy",
            0.48,
            0.12,
            3,
        )
    )

    assert result.failed is True
    assert result.attempts == 3
    assert "maximum nodes exceeded" in result.last_error

class NativeAlternativeClient(GraphHopperClient):
    def __init__(self) -> None:
        super().__init__("http://graphhopper.test")
        self.body: dict = {}

    async def _post_route(self, body: dict) -> dict:
        self.body = body
        return {
            "paths": [
                {
                    "distance": 100_000,
                    "time": 3_600_000,
                    "points": {"coordinates": [[2.0, 48.0], [3.0, 47.0]]},
                    "details": {"road_class": [], "toll": []},
                },
                {
                    "distance": 112_000,
                    "time": 4_000_000,
                    "points": {"coordinates": [[2.0, 48.0], [2.4, 47.4], [3.0, 47.0]]},
                    "details": {"road_class": [], "toll": []},
                },
            ]
        }


def test_native_alternative_route_request_is_bounded() -> None:
    client = NativeAlternativeClient()
    routes = asyncio.run(
        client._request_native_alternatives(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=47.0, lon=3.0),
        )
    )

    assert len(routes) == 2
    assert client.body["algorithm"] == "alternative_route"
    assert client.body["alternative_route.max_paths"] == 3
    assert client.body["alternative_route.max_weight_factor"] == 1.55
    assert client.body["alternative_route.max_share_factor"] == 0.80


def test_fastest_profile_uses_prepared_strict_time_car_profile() -> None:
    class CapturingClient(GraphHopperClient):
        def __init__(self) -> None:
            super().__init__("http://graphhopper.test")
            self.body = {}

        async def _post_route(self, body):
            self.body = body
            return {"paths": []}

    client = CapturingClient()
    asyncio.run(
        client._request_once(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=43.0, lon=6.0),
            "fastest",
            1.0,
            1.0,
            0,
            90.0,
        )
    )

    assert client.body["profile"] == "car"
    assert "custom_model" not in client.body


def test_prepared_car_profile_is_a_strict_time_baseline() -> None:
    model_path = Path("infra/graphhopper/custom_models/routeco_car.json")
    model = json.loads(model_path.read_text(encoding="utf-8"))
    config = Path("infra/graphhopper/config.yml").read_text(encoding="utf-8")

    assert model["distance_influence"] == 0
    assert model["priority"] == [
        {"if": "!car_access", "multiply_by": "0"}
    ]
    assert model["speed"] == [
        {"if": "true", "limit_to": "car_average_speed"}
    ]
    assert "custom_model_files: [routeco_car.json]" in config
    assert "custom_model_files: [car.json]" not in config


def test_failed_profile_is_reported_as_retried() -> None:
    client = RetryClient(failures=10)
    result = asyncio.run(
        client._request_profile(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=45.0, lon=4.0),
            "free",
            0.30,
            0.05,
            4,
        )
    )

    assert result.failed is True
    assert result.retried is True


def test_native_alternatives_survive_failed_economy_profiles() -> None:
    from app.services.routing import ProfileResult

    class MergeClient(GraphHopperClient):
        async def available(self) -> bool:
            return True

        async def _request_profile(
            self, start, end, name, motorway_priority, toll_priority, rank
        ) -> ProfileResult:
            if name == "fastest":
                return ProfileResult(
                    name,
                    [
                        {
                            "id": "fastest",
                            "profile": name,
                            "profile_rank": rank,
                            "distance_km": 100.0,
                            "duration_minutes": 60,
                            "motorway_km": 90.0,
                            "road_km": 10.0,
                            "tolled_km": 80.0,
                            "toll_ranges": [],
                            "geometry": [[2.0, 48.0], [3.0, 47.0]],
                            "source": "graphhopper",
                        }
                    ],
                    1,
                )
            return ProfileResult(name, [], 3, "maximum nodes exceeded")

        async def _request_segmented_profile(self, *args, **kwargs) -> list[dict]:
            return []

        async def _request_native_alternatives(self, start, end) -> list[dict]:
            return [
                {
                    "id": "native-1",
                    "profile": "native",
                    "profile_rank": 1,
                    "distance_km": 112.0,
                    "duration_minutes": 70,
                    "motorway_km": 55.0,
                    "road_km": 57.0,
                    "tolled_km": 30.0,
                    "toll_ranges": [],
                    "geometry": [[2.0, 48.0], [2.5, 47.4], [3.0, 47.0]],
                    "source": "graphhopper",
                },
                {
                    "id": "native-2",
                    "profile": "native",
                    "profile_rank": 2,
                    "distance_km": 120.0,
                    "duration_minutes": 78,
                    "motorway_km": 20.0,
                    "road_km": 100.0,
                    "tolled_km": 0.0,
                    "toll_ranges": [],
                    "geometry": [[2.0, 48.0], [2.2, 47.2], [3.0, 47.0]],
                    "source": "graphhopper",
                },
            ]

    client = MergeClient("http://graphhopper.test")
    result = asyncio.run(
        client.candidates(
            Coordinate(lat=48.0, lon=2.0),
            Coordinate(lat=47.0, lon=3.0),
        )
    )

    assert len(result.candidates) == 3
    assert {item["id"] for item in result.candidates} == {
        "fastest",
        "native-1",
        "native-2",
    }
    assert result.failed_profiles == ["light", "balanced", "economy", "free"]
    assert result.retried_profiles == ["light", "balanced", "economy", "free"]


def test_redundant_pending_native_request_is_cancelled() -> None:
    from app.services.routing import ProfileResult

    class CompleteCustomClient(GraphHopperClient):
        def __init__(self) -> None:
            super().__init__("http://graphhopper.test")
            self.native_cancelled = False

        async def available(self) -> bool:
            return True

        async def _request_profile(
            self,
            start,
            end,
            name,
            motorway_priority,
            toll_priority,
            rank,
        ) -> ProfileResult:
            return ProfileResult(
                name,
                [
                    {
                        "id": f"custom-{name}",
                        "profile": name,
                        "profile_rank": rank,
                        "distance_km": 100.0 + rank * 8.0,
                        "duration_minutes": 60 + rank * 5,
                        "motorway_km": 90.0 - rank * 12.0,
                        "road_km": 10.0 + rank * 20.0,
                        "tolled_km": 80.0 - rank * 10.0,
                        "toll_ranges": [],
                        "geometry": [
                            [2.0, 48.0],
                            [2.2 + rank * 0.1, 47.5],
                            [3.0, 47.0],
                        ],
                        "source": "graphhopper",
                    }
                ],
                1,
            )

        async def _request_native_alternatives(
            self,
            start,
            end,
        ) -> list[dict]:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.native_cancelled = True
                raise
            return []

    client = CompleteCustomClient()
    result = asyncio.run(
        asyncio.wait_for(
            client.candidates(
                Coordinate(lat=48.0, lon=2.0),
                Coordinate(lat=47.0, lon=3.0),
            ),
            timeout=1.0,
        )
    )

    assert len(result.candidates) == 5
    assert client.native_cancelled is True
    assert result.native_alternatives_skipped is True
    assert result.message == "5 itinéraires trouvés."
    assert "annulée" not in result.message


class SegmentedFallbackClient(GraphHopperClient):
    def __init__(self) -> None:
        super().__init__("http://graphhopper.test")
        self.bodies: list[dict] = []

    async def _post_route(self, body: dict) -> dict:
        self.bodies.append(body)
        if len(self.bodies) == 1:
            raise GraphHopperRequestError(400, "maximum nodes exceeded")
        return {
            "paths": [
                {
                    "distance": 900_000,
                    "time": 36_000_000,
                    "points": {
                        "coordinates": [
                            body["points"][0],
                            *body["points"][1:-1],
                            body["points"][-1],
                        ]
                    },
                    "details": {"road_class": [], "toll": []},
                }
            ]
        }


def test_segmented_profile_uses_distance_sampled_via_points() -> None:
    client = SegmentedFallbackClient()
    baseline = [[2.0, 50.0], [3.0, 48.0], [5.0, 45.0]]

    routes = asyncio.run(
        client._request_segmented_profile(
            Coordinate(lat=50.0, lon=2.0),
            Coordinate(lat=45.0, lon=5.0),
            "free",
            0.30,
            0.05,
            4,
            baseline,
        )
    )

    assert len(client.bodies) == 2
    assert len(client.bodies[0]["points"]) == 3
    assert len(client.bodies[1]["points"]) == 4
    assert client.bodies[1]["pass_through"] is True
    assert routes
    assert routes[0]["profile"] == "free-seg2"

# ROUTECO_V034_RELIABILITY_PATCH
def test_passenger_toll_detection_ignores_hgv_only_segments() -> None:
    client = GraphHopperClient("http://graphhopper.test")
    payload = {
        "paths": [{
            "distance": 30_000,
            "time": 1_800_000,
            "points": {"coordinates": [[2.0, 48.0], [2.1, 47.9], [2.2, 47.8]]},
            "details": {"road_class": [], "toll": [[0, 1, "HGV"], [1, 2, "ALL"]]},
        }]
    }
    route = client._paths_to_candidates(payload, "passenger", 0)[0]
    assert len(route["toll_ranges"]) == 1
    assert route["toll_ranges"][0]["start_index"] == 1


def test_sparse_geometry_toll_ranges_are_not_merged_by_point_count() -> None:
    geometry = [[0.0, 45.0], [0.001, 45.0], [2.0, 45.0], [2.001, 45.0]]
    details = [[0, 1, "ALL"], [2, 3, "ALL"]]
    ranges = GraphHopperClient._detail_ranges(geometry, details, {"ALL"})
    assert len(ranges) == 2


def test_deduplication_keeps_materially_different_toll_usage() -> None:
    base = {
        "profile": "test", "profile_rank": 0, "distance_km": 300.0,
        "duration_minutes": 180, "motorway_km": 200.0, "road_km": 100.0,
        "toll_ranges": [], "geometry": [[2.0, 48.0], [3.0, 47.0]],
        "source": "graphhopper",
    }
    free = {**base, "id": "free", "tolled_km": 0.0}
    paid = {**base, "id": "paid", "tolled_km": 25.0}
    kept = GraphHopperClient._deduplicate([free, paid])
    assert {item["id"] for item in kept} == {"free", "paid"}


def test_native_geometry_can_seed_segmented_recovery_when_fastest_fails() -> None:
    from app.services.routing import ProfileResult

    class NativeSeedClient(GraphHopperClient):
        def __init__(self) -> None:
            super().__init__("http://graphhopper.test")
            self.segmented_baselines: list[list[list[float]]] = []

        async def available(self) -> bool:
            return True

        async def _request_profile(self, start, end, name, motorway_priority, toll_priority, rank) -> ProfileResult:
            return ProfileResult(name, [], 3, "maximum nodes exceeded")

        async def _request_native_alternatives(self, start, end) -> list[dict]:
            return [{
                "id": "native", "profile": "native", "profile_rank": 0,
                "distance_km": 900.0, "duration_minutes": 520,
                "motorway_km": 800.0, "road_km": 100.0, "tolled_km": 500.0,
                "toll_ranges": [], "geometry": [[2.0, 50.0], [3.0, 48.0], [5.0, 43.0]],
                "source": "graphhopper",
            }]

        async def _request_segmented_profile(self, start, end, name, motorway_priority, toll_priority, rank, baseline_geometry) -> list[dict]:
            self.segmented_baselines.append(baseline_geometry)
            if name != "free":
                return []
            return [{
                "id": "recovered-free", "profile": "free-seg", "profile_rank": rank,
                "distance_km": 930.0, "duration_minutes": 650,
                "motorway_km": 100.0, "road_km": 830.0, "tolled_km": 0.0,
                "toll_ranges": [], "geometry": [[2.0, 50.0], [2.4, 46.0], [5.0, 43.0]],
                "source": "graphhopper",
            }]

    client = NativeSeedClient()
    result = asyncio.run(client.candidates(Coordinate(lat=50.0, lon=2.0), Coordinate(lat=43.0, lon=5.0)))
    assert client.segmented_baselines
    assert "recovered-free" in {item["id"] for item in result.candidates}
    assert "free" not in result.failed_profiles

# ROUTECO_V034_PERFORMANCE_FOLLOWUP
class SlowNativeAlternativeClient(GraphHopperClient):
    def __init__(self) -> None:
        super().__init__("http://graphhopper.test", timeout_seconds=0.01)

    async def _post_route(self, body: dict) -> dict:
        await asyncio.sleep(0.05)
        return {"paths": []}


def test_native_alternative_route_has_a_short_supplemental_timeout() -> None:
    client = SlowNativeAlternativeClient()
    try:
        asyncio.run(
            client._request_native_alternatives(
                Coordinate(lat=48.0, lon=2.0),
                Coordinate(lat=47.0, lon=3.0),
            )
        )
    except GraphHopperRequestError as exc:
        assert exc.status_code == 408
        assert "native alternative-route timeout" in exc.detail
    else:
        raise AssertionError("La recherche native aurait dû expirer.")

# ROUTECO_V034_ADAPTIVE_NATIVE_PATHS
def test_native_alternative_route_uses_four_paths_on_long_distance() -> None:
    client = NativeAlternativeClient()
    asyncio.run(
        client._request_native_alternatives(
            Coordinate(lat=50.63, lon=3.06),
            Coordinate(lat=43.30, lon=5.37),
        )
    )

    assert client.body["alternative_route.max_paths"] == 4

# ROUTECO_V034_ROAD_CLASS_LINK_DETAILS
def test_candidate_preserves_road_class_link_details() -> None:
    client = GraphHopperClient("http://graphhopper.test")
    link_details = [[0, 1, False], [1, 2, True]]
    street_name_details = [[0, 2, "Autoroute du Test"]]
    street_ref_details = [[0, 2, "A42"]]
    payload = {
        "paths": [
            {
                "distance": 20_000,
                "time": 1_200_000,
                "points": {
                    "coordinates": [
                        [2.0, 48.0],
                        [2.1, 48.0],
                        [2.2, 48.0],
                    ]
                },
                "details": {
                    "road_class": [[0, 2, "MOTORWAY"]],
                    "road_class_link": link_details,
                    "street_name": street_name_details,
                    "street_ref": street_ref_details,
                    "toll": [[0, 2, "ALL"]],
                },
            }
        ]
    }

    route = client._paths_to_candidates(payload, "details", 0)[0]

    assert route["road_class_link_details"] == link_details
    assert route["street_name_details"] == street_name_details
    assert route["street_ref_details"] == street_ref_details


def test_graphhopper_config_encodes_road_class_link() -> None:
    from pathlib import Path

    config = Path("infra/graphhopper/config.yml").read_text(encoding="utf-8")

    assert "road_class_link" in config

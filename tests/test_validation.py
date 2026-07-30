from app.services.validation import (
    ScenarioResult,
    ValidatedRoute,
    ValidationIssue,
    render_markdown,
    report_payload,
)


def test_validation_report_contains_summary_and_toll_segments() -> None:
    result = ScenarioResult(
        id="sample",
        name="Exemple",
        engine="graphhopper",
        engine_message="1 route",
        issues=[ValidationIssue("warning", "À vérifier")],
        routing_seconds=3.25,
        toll_pricing_seconds=0.125,
        native_alternatives_skipped=True,
        routes=[
            ValidatedRoute(
                id="route-1",
                duration_minutes=100,
                distance_km=120.0,
                motorway_km=80.0,
                road_km=40.0,
                tolled_km=60.0,
                toll_cost=8.5,
                toll_confidence="exact",
                fuel_cost=12.0,
                total_cost=20.5,
                toll_message="Exact",
                toll_segments=[
                    {
                        "entry": "Entrée",
                        "exit": "Sortie",
                        "operator": "TEST",
                        "cost": 8.5,
                        "distance_km": 70.0,
                        "confidence": "exact",
                    }
                ],
            )
        ],
    )

    payload = report_payload([result], strict=False)
    markdown = render_markdown(payload)

    assert payload["summary"]["routes"] == 1
    assert payload["summary"]["exact"] == 1
    assert payload["summary"]["routing_seconds"] == 3.25
    assert payload["summary"]["toll_pricing_seconds"] == 0.125
    assert payload["summary"]["native_alternatives_skipped"] == 1
    assert "Entrée → Sortie" in markdown
    assert "8.50 €" in markdown
    assert "3.2 s" in markdown


def test_report_payload_counts_exact_routes_without_changing_totals() -> None:
    result = ScenarioResult(
        id="sample-2",
        name="Exemple 2",
        engine="graphhopper",
        engine_message="1 route",
        issues=[],
        routes=[
            ValidatedRoute(
                id="route-exact",
                duration_minutes=10,
                distance_km=20.0,
                motorway_km=10.0,
                road_km=10.0,
                tolled_km=8.0,
                toll_cost=3.0,
                toll_confidence="exact",
                fuel_cost=2.0,
                total_cost=5.0,
                toll_message="Exact",
                toll_segments=[],
            )
        ],
    )
    payload = report_payload([result], strict=False)
    assert payload["summary"]["exact"] == 1
    assert payload["summary"]["errors"] == 0


def test_coverage_validation_does_not_assume_city_pair_price() -> None:
    """Reference amounts are optional gold checks, never production matching rules."""
    # The production validator exposes the mode as an explicit argument. The
    # default must remain structural so arbitrary origins/destinations are not
    # forced into one of the reference examples.
    import inspect
    from app.services.validation import validate_scenario

    signature = inspect.signature(validate_scenario)
    assert signature.parameters["enforce_gold"].default is False

# ROUTECO_V034_CANDIDATE_PIPELINE_FIX
def test_validation_uses_canonical_candidate_pricing_adapter() -> None:
    import asyncio

    from app.services.routing import EngineResult
    from app.services.tolls import TollQuote
    from app.services.validation import validate_scenario

    candidate = {
        "id": "candidate-with-topology",
        "profile": "fastest",
        "profile_rank": 0,
        "duration_minutes": 60,
        "distance_km": 100.0,
        "motorway_km": 80.0,
        "road_km": 20.0,
        "tolled_km": 20.0,
        "toll_ranges": [
            {"start_index": 0, "end_index": 2, "distance_km": 20.0}
        ],
        "road_class_link_details": [[0, 2, False]],
        "geometry": [[2.0, 48.0], [2.1, 48.0], [2.2, 48.0]],
        "source": "graphhopper",
    }

    class FakeRouting:
        async def candidates(self, start, end) -> EngineResult:
            return EngineResult("graphhopper", "1 route", [candidate])

    class RecordingTolls:
        def __init__(self) -> None:
            self.received = None

        def quote_candidate(self, value) -> TollQuote:
            self.received = value
            return TollQuote(0.0, "none", [], "test")

    tolls = RecordingTolls()
    result = asyncio.run(
        validate_scenario(
            {
                "id": "pipeline",
                "name": "Pipeline",
                "start": {"lat": 48.0, "lon": 2.0},
                "end": {"lat": 47.0, "lon": 3.0},
                "min_routes": 1,
            },
            FakeRouting(),
            tolls,
        )
    )

    assert result.errors == 0
    assert tolls.received is candidate
    assert tolls.received["road_class_link_details"] == [[0, 2, False]]

# ROUTECO_V034_GLOBAL_TOLL_PLAN
def test_strict_mode_accepts_verified_no_toll_result() -> None:
    import asyncio

    from app.services.routing import EngineResult
    from app.services.tolls import TollQuote
    from app.services.validation import validate_scenario

    candidate = {
        "id": "micro-noise",
        "profile": "balanced",
        "profile_rank": 0,
        "duration_minutes": 60,
        "distance_km": 100.0,
        "motorway_km": 10.0,
        "road_km": 90.0,
        "tolled_km": 0.4,
        "toll_ranges": [{"start_index": 0, "end_index": 1, "distance_km": 0.4}],
        "road_class_link_details": [[0, 1, False]],
        "geometry": [[2.0, 48.0], [2.1, 48.0]],
        "source": "graphhopper",
    }

    class FakeRouting:
        async def candidates(self, start, end) -> EngineResult:
            return EngineResult("graphhopper", "1 route", [candidate])

    class FakeTolls:
        def quote_candidate(self, value) -> TollQuote:
            return TollQuote(0.0, "none", [], "Fragment OSM sans événement tarifaire.")

    result = asyncio.run(
        validate_scenario(
            {
                "id": "strict-none",
                "name": "Strict none",
                "start": {"lat": 48.0, "lon": 2.0},
                "end": {"lat": 47.0, "lon": 3.0},
                "min_routes": 1,
            },
            FakeRouting(),
            FakeTolls(),
            strict=True,
        )
    )

    assert result.errors == 0

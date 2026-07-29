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
    assert "Entrée → Sortie" in markdown
    assert "8.50 €" in markdown


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

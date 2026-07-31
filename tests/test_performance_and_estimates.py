from __future__ import annotations

import asyncio
import csv
from pathlib import Path

from app.config import load_settings
from app.models import Coordinate
from app.services.routing import EngineResult, GraphHopperClient
from app.services.tolls import TollPricingService


class CountingRoutingClient(GraphHopperClient):
    def __init__(self) -> None:
        super().__init__(
            "http://graphhopper.test",
            cache_ttl_seconds=60,
            cache_max_entries=2,
            max_concurrent_calculations=1,
        )
        self.computations = 0

    async def _compute_candidates(
        self,
        start: Coordinate,
        end: Coordinate,
    ) -> EngineResult:
        self.computations += 1
        await asyncio.sleep(0.01)
        return EngineResult(
            "graphhopper",
            "1 itinéraire trouvé.",
            [
                {
                    "id": f"{start.lat}-{end.lat}",
                    "geometry": [
                        [start.lon, start.lat],
                        [end.lon, end.lat],
                    ],
                }
            ],
            routing_seconds=0.01,
            profile_metrics=[
                {
                    "name": "fastest",
                    "seconds": 0.01,
                    "attempts": 1,
                    "candidates": 1,
                    "status": "ok",
                    "fallback_seconds": 0.0,
                }
            ],
        )


def test_routing_cache_reuses_geometry_without_sharing_mutations() -> None:
    async def scenario() -> None:
        client = CountingRoutingClient()
        start = Coordinate(lat=48.8566, lon=2.3522)
        end = Coordinate(lat=45.7640, lon=4.8357)

        first = await client.candidates(start, end)
        first.candidates[0]["id"] = "mutated-by-caller"
        second = await client.candidates(start, end)

        assert client.computations == 1
        assert first.cache_hit is False
        assert second.cache_hit is True
        assert second.candidates[0]["id"] != "mutated-by-caller"
        assert second.profile_metrics == []
        assert client.cache_info()["hits"] == 1
        await client.close()

    asyncio.run(scenario())


def test_identical_concurrent_requests_share_one_heavy_calculation() -> None:
    async def scenario() -> None:
        client = CountingRoutingClient()
        start = Coordinate(lat=43.6584, lon=6.9210)
        end = Coordinate(lat=45.8567, lon=6.6178)

        first, second = await asyncio.gather(
            client.candidates(start, end),
            client.candidates(start, end),
        )

        assert client.computations == 1
        assert {first.cache_hit, second.cache_hit} == {False, True}
        assert client.cache_info()["shared_waits"] == 1
        await client.close()

    asyncio.run(scenario())


def test_routing_cache_is_directional() -> None:
    async def scenario() -> None:
        client = CountingRoutingClient()
        start = Coordinate(lat=48.8566, lon=2.3522)
        end = Coordinate(lat=45.7640, lon=4.8357)

        await client.candidates(start, end)
        await client.candidates(end, start)

        assert client.computations == 2
        await client.close()

    asyncio.run(scenario())


def test_estimated_toll_rate_is_adjustable_and_exposes_a_range(
    tmp_path: Path,
) -> None:
    service = TollPricingService(tmp_path)

    quote = service.quote(
        geometry=[[2.0, 48.0], [3.0, 47.0]],
        tolled_km=100.0,
        fallback_eur_per_km=0.12,
    )

    assert quote.confidence == "estimated"
    assert quote.cost == 12.0
    assert quote.cost_low == 9.0
    assert quote.cost_high == 15.6
    assert quote.segments[0].cost_low == 9.0
    assert quote.segments[0].cost_high == 15.6
    assert "0.120 €/km" in quote.message


def test_exact_or_free_toll_never_receives_an_uncertainty_range(
    tmp_path: Path,
) -> None:
    service = TollPricingService(tmp_path)

    quote = service.quote(
        geometry=[[2.0, 48.0], [2.1, 48.1]],
        tolled_km=0.0,
        fallback_eur_per_km=0.30,
    )

    assert quote.confidence == "none"
    assert quote.cost_low == quote.cost == quote.cost_high == 0.0


def test_station_grid_preserves_latitude_aware_projection(
    tmp_path: Path,
) -> None:
    with (tmp_path / "stations.csv").open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "name",
                "osm_name",
                "operator",
                "lat",
                "lon",
                "type",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "name": "OFFSET",
                "osm_name": "Offset",
                "operator": "TEST",
                "lat": "50.050",
                "lon": "2.030",
                "type": "closed",
            }
        )
        for index in range(100):
            writer.writerow(
                {
                    "name": f"FAR-{index}",
                    "osm_name": f"Far {index}",
                    "operator": "TEST",
                    "lat": f"{42.0 + index * 0.001:.3f}",
                    "lon": "-4.000",
                    "type": "closed",
                }
            )

    service = TollPricingService(tmp_path)
    projections, _ = service._project_stations([[2.0, 50.0], [2.0, 50.1]])

    assert [item.station.name for item in projections] == ["OFFSET"]
    assert projections[0].lateral_km < 2.5


def test_runtime_limits_are_bounded_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("ROUTECO_ROUTING_CACHE_TTL", "999999")
    monkeypatch.setenv("ROUTECO_ROUTING_CACHE_ENTRIES", "-4")
    monkeypatch.setenv("ROUTECO_MAX_CONCURRENT_CALCULATIONS", "99")
    monkeypatch.setenv("ROUTECO_TOLL_ESTIMATE_EUR_PER_KM", "0,12")

    settings = load_settings()

    assert settings.routing_cache_ttl_seconds == 86400
    assert settings.routing_cache_max_entries == 0
    assert settings.max_concurrent_calculations == 8
    assert settings.toll_estimate_eur_per_km == 0.12

from __future__ import annotations

from collections import OrderedDict
from types import MethodType

from app.services.tolls import TollPricingService, TollQuote, TollSegmentQuote


def _service_with_fake_pricer() -> tuple[TollPricingService, list[float]]:
    service = object.__new__(TollPricingService)
    service._quote_cache = OrderedDict()
    service._quote_cache_hits = 0
    service._quote_cache_misses = 0
    calls: list[float] = []

    def fake(
        _self: TollPricingService,
        candidate: dict,
        *,
        fallback_eur_per_km: float | None = None,
    ) -> TollQuote:
        rate = float(fallback_eur_per_km or 0.0)
        calls.append(rate)
        return TollQuote(
            cost=round(10.0 + rate * 20.0, 2),
            confidence="estimated",
            stations=["A"],
            message="estimation",
            cost_low=round(10.0 + rate * 20.0 * 0.75, 2),
            cost_high=round(10.0 + rate * 20.0 * 1.30, 2),
            segments=[
                TollSegmentQuote(
                    entry="A",
                    exit="B",
                    operator="TEST",
                    cost=10.0,
                    distance_km=10.0,
                    confidence="exact",
                ),
                TollSegmentQuote(
                    entry=None,
                    exit=None,
                    operator="",
                    cost=round(rate * 20.0, 2),
                    distance_km=20.0,
                    confidence="estimated",
                ),
            ],
        )

    service._quote_candidate_uncached = MethodType(fake, service)
    return service, calls


def _candidate() -> dict:
    return {
        "id": "test-route",
        "geometry": [[2.0, 48.0], [3.0, 47.0]],
        "tolled_km": 20.0,
        "toll_ranges": [{"start_index": 0, "end_index": 1, "distance_km": 20.0}],
        "toll_state_intervals": [],
        "road_class_link_details": [],
        "street_name_details": [],
        "street_ref_details": [],
    }


def test_toll_quote_cache_reuses_same_geometry_and_rate() -> None:
    service, calls = _service_with_fake_pricer()

    first = service.quote_candidate(_candidate(), fallback_eur_per_km=0.105)
    first.stations.append("mutation locale")
    second = service.quote_candidate(_candidate(), fallback_eur_per_km=0.105)

    assert calls == [0.105]
    assert second.stations == ["A"]
    assert service.quote_cache_info() == {
        "entries": 1,
        "max_entries": service.QUOTE_CACHE_MAX_ENTRIES,
        "hits": 1,
        "misses": 1,
    }

    service.clear_quote_cache()
    assert service.quote_cache_info()["entries"] == 0


def test_estimated_quote_cache_separates_estimate_rates() -> None:
    service, calls = _service_with_fake_pricer()

    low = service.quote_candidate(_candidate(), fallback_eur_per_km=0.08)
    high = service.quote_candidate(_candidate(), fallback_eur_per_km=0.16)
    low_again = service.quote_candidate(_candidate(), fallback_eur_per_km=0.08)

    assert calls == [0.08]
    assert low.cost != high.cost
    assert low_again.cost == low.cost
    assert service.quote_cache_info()["entries"] == 1
    assert service.quote_cache_info()["hits"] == 2
    assert service.quote_cache_info()["misses"] == 1

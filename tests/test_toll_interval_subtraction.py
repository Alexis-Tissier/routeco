from __future__ import annotations

import pytest

from app.services.tolls import (
    TollPricingService,
    TollRange,
    TollStateInterval,
)


def test_interval_subtraction_handles_overlapping_ranges() -> None:
    residuals = TollPricingService._subtract_km_intervals(
        [
            (54.1, 68.7),
            (87.4, 112.1),
        ],
        [
            (54.3, 96.4),
        ],
    )

    assert residuals == pytest.approx(
        [
            (54.1, 54.3),
            (96.4, 112.1),
        ]
    )


def test_overlapping_covered_spans_are_not_counted_twice() -> None:
    residuals = TollPricingService._subtract_km_intervals(
        [(0.0, 100.0)],
        [
            (10.0, 60.0),
            (40.0, 80.0),
        ],
    )

    assert residuals == pytest.approx(
        [
            (0.0, 10.0),
            (80.0, 100.0),
        ]
    )


def test_free_graphhopper_interval_is_not_chargeable() -> None:
    toll_range = TollRange(
        0,
        4,
        0.0,
        20.0,
        20.0,
    )
    intervals = [
        TollStateInterval(
            0,
            1,
            0.0,
            5.0,
            5.0,
            "ALL",
            "toll",
        ),
        TollStateInterval(
            1,
            3,
            5.0,
            15.0,
            10.0,
            "NO",
            "free",
        ),
        TollStateInterval(
            3,
            4,
            15.0,
            20.0,
            5.0,
            "MISSING",
            "unknown",
        ),
    ]

    assert (
        TollPricingService._class1_chargeable_intervals_for_range(
            toll_range,
            intervals,
        )
        == pytest.approx(
            [
                (0.0, 5.0),
                (15.0, 20.0),
            ]
        )
    )


def test_missing_toll_states_preserve_declared_range_distance() -> None:
    toll_range = TollRange(
        0,
        2,
        0.0,
        81.6,
        100.0,
    )

    assert (
        TollPricingService._range_has_detailed_toll_states(
            toll_range,
            [],
        )
        is False
    )


def test_detailed_toll_states_enable_physical_interval_measurement() -> None:
    toll_range = TollRange(
        0,
        2,
        0.0,
        81.6,
        100.0,
    )
    intervals = [
        TollStateInterval(
            0,
            2,
            0.0,
            81.6,
            81.6,
            "ALL",
            "toll",
        )
    ]

    assert (
        TollPricingService._range_has_detailed_toll_states(
            toll_range,
            intervals,
        )
        is True
    )


def test_missing_toll_states_keep_conservative_fallback() -> None:
    toll_range = TollRange(
        0,
        2,
        0.0,
        20.0,
        20.0,
    )

    residuals = (
        TollPricingService._unresolved_class1_toll_intervals(
            toll_range,
            [],
            [(5.0, 15.0)],
        )
    )

    assert residuals == pytest.approx(
        [
            (0.0, 5.0),
            (15.0, 20.0),
        ]
    )

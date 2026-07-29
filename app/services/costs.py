from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CostBreakdown:
    fuel_liters: float
    fuel_cost: float
    total_cost: float


def calculate_costs(
    motorway_km: float,
    road_km: float,
    motorway_consumption: float,
    road_consumption: float,
    fuel_price: float,
    toll_cost: float,
) -> CostBreakdown:
    fuel_liters = (
        motorway_km * motorway_consumption / 100 + road_km * road_consumption / 100
    )
    fuel_cost = fuel_liters * fuel_price
    return CostBreakdown(
        fuel_liters=round(fuel_liters, 2),
        fuel_cost=round(fuel_cost, 2),
        total_cost=round(fuel_cost + toll_cost, 2),
    )

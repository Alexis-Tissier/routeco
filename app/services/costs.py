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
    rounded_fuel_cost = round(fuel_cost, 2)
    rounded_toll_cost = round(toll_cost, 2)
    return CostBreakdown(
        fuel_liters=round(fuel_liters, 2),
        fuel_cost=rounded_fuel_cost,
        # The displayed components must add up to the displayed total.
        total_cost=round(rounded_fuel_cost + rounded_toll_cost, 2),
    )

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class Coordinate(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RouteRequest(BaseModel):
    start: Coordinate
    end: Coordinate
    start_label: str = "Départ"
    end_label: str = "Arrivée"
    fuel_type: Literal["SP95-E10", "SP98"] = "SP95-E10"
    fuel_price: float = Field(default=1.82, gt=0, le=5)
    max_extra_minutes: int | None = Field(default=45, ge=0, le=720)
    min_savings: float = Field(default=5.0, ge=0, le=500)
    show_all: bool = False
    motorway_consumption: float = Field(default=6.5, gt=0, le=30)
    road_consumption: float = Field(default=5.5, gt=0, le=30)

    @field_validator("start_label", "end_label")
    @classmethod
    def clean_label(cls, value: str) -> str:
        return value.strip()[:160] or "Adresse"


class GeocodeResult(BaseModel):
    label: str
    city: str = ""
    postcode: str = ""
    lat: float
    lon: float
    source: Literal["ban", "commune", "demo"]
    kind: Literal["address", "municipality", "demo"] = "address"
    code: str = ""
    department_code: str = ""
    population: int = 0


class TollSegmentResult(BaseModel):
    entry: str | None = None
    exit: str | None = None
    operator: str = ""
    cost: float = 0.0
    distance_km: float | None = None
    confidence: Literal["exact", "estimated", "none", "missing"] = "missing"
    route_start_km: float | None = None
    route_end_km: float | None = None


class RouteResult(BaseModel):
    id: str
    label: str
    description: str
    distance_km: float
    duration_minutes: int
    extra_minutes: int = 0
    motorway_km: float
    road_km: float
    fuel_liters: float
    fuel_cost: float
    toll_cost: float
    total_cost: float
    savings: float = 0
    toll_confidence: Literal["exact", "estimated", "none", "missing"] = "missing"
    toll_stations: list[str] = Field(default_factory=list)
    toll_message: str = ""
    toll_segments: list[TollSegmentResult] = Field(default_factory=list)
    within_limit: bool = True
    tags: list[str] = Field(default_factory=list)
    geometry: list[list[float]] = Field(default_factory=list, description="[lon, lat]")
    source: Literal["graphhopper", "demo"]


class RouteResponse(BaseModel):
    engine: Literal["graphhopper", "demo"]
    engine_message: str
    fastest_minutes: int
    max_extra_minutes: int | None
    candidate_count: int
    distinct_count: int
    eligible_count: int
    merged_count: int = 0
    hidden_count: int = 0
    routes: list[RouteResult]

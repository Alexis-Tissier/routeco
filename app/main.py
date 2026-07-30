from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import RouteRequest, RouteResponse, RouteResult, TollSegmentResult
from app.services.costs import calculate_costs
from app.services.geocoder import (
    AmbiguousLocationError,
    LocalGeocoder,
    LocationNotFoundError,
)
from app.services.pareto import (
    decorate_routes,
    select_economically_distinct_routes,
    select_representative_routes,
)
from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService

app = FastAPI(title="Routeco", version="0.3.8")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

geocoder = LocalGeocoder(
    settings.ban_database,
    settings.demo_places,
    settings.communes_database,
)
routing = GraphHopperClient(settings.graphhopper_url)
tolls = TollPricingService(settings.tolls_dir)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/api/config")
def public_config() -> dict:
    return {
        "map": {
            "mode": "openstreetmap",
            "style_url": settings.map_style_url,
            "interactive": True,
        },
        "vehicle": {
            "name": "Renault Twingo 2",
            "toll_class": 1,
            "motorway_consumption": 6.5,
            "road_consumption": 5.5,
            "fuel_types": ["SP95-E10", "SP98"],
        },
        "geocoding": {
            "communes": geocoder.commune_count,
            "detailed_addresses": settings.ban_database.exists(),
        },
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "graphhopper": await routing.available(),
        "ban": settings.ban_database.exists(),
        "communes": geocoder.commune_count,
        "tolls": tolls.ready,
        "toll_stations": len(tolls.stations),
        "toll_closed_pairs": len(tolls.closed_prices),
        "toll_open_prices": len(tolls.open_prices),
        "toll_official_sources": (settings.tolls_dir / "official" / "sources.json").exists(),
        "map_mode": "openstreetmap",
        "map_interactive": True,
    }


@app.get("/api/geocode")
def search_address(q: str = Query(min_length=2, max_length=160)) -> list[dict]:
    return [result.model_dump() for result in geocoder.search(q)]


@app.get("/api/geocode/resolve")
def resolve_address(q: str = Query(min_length=2, max_length=160)) -> dict:
    try:
        return geocoder.resolve(q).model_dump()
    except AmbiguousLocationError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "choices": [choice.model_dump() for choice in exc.choices],
            },
        ) from exc
    except LocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/routes", response_model=RouteResponse)
async def calculate_routes(request: RouteRequest) -> RouteResponse:
    if request.start == request.end:
        raise HTTPException(status_code=400, detail="Le départ et l'arrivée doivent être différents.")

    engine_result = await routing.candidates(request.start, request.end)
    results: list[RouteResult] = []
    for candidate in engine_result.candidates:
        quote = tolls.quote_candidate(candidate)
        costs = calculate_costs(
            candidate["motorway_km"],
            candidate["road_km"],
            request.motorway_consumption,
            request.road_consumption,
            request.fuel_price,
            quote.cost,
        )
        results.append(
            RouteResult(
                id=candidate["id"],
                label="Alternative",
                description=quote.message,
                distance_km=candidate["distance_km"],
                duration_minutes=max(1, candidate["duration_minutes"]),
                motorway_km=candidate["motorway_km"],
                road_km=candidate["road_km"],
                fuel_liters=costs.fuel_liters,
                fuel_cost=costs.fuel_cost,
                toll_cost=quote.cost,
                total_cost=costs.total_cost,
                toll_confidence=quote.confidence,  # type: ignore[arg-type]
                toll_stations=quote.stations,
                toll_message=quote.message,
                toll_segments=[
                    TollSegmentResult(
                        entry=segment.entry,
                        exit=segment.exit,
                        operator=segment.operator,
                        cost=segment.cost,
                        distance_km=segment.distance_km,
                        confidence=segment.confidence,  # type: ignore[arg-type]
                        route_start_km=segment.route_start_km,
                        route_end_km=segment.route_end_km,
                    )
                    for segment in quote.segments
                ],
                geometry=candidate["geometry"],
                source=candidate["source"],
            )
        )

    if not results:
        raise HTTPException(status_code=502, detail="Aucun itinéraire exploitable n'a été calculé.")

    # Preserve the pure fastest route, then keep alternatives that create a
    # meaningful new saving step. This prevents several penny-apart no-toll
    # routes from crowding out genuinely different compromises.
    decorated = decorate_routes(results, request.max_extra_minutes)
    if not request.show_all:
        fastest = min(decorated, key=lambda route: route.duration_minutes)
        visible = [
            route
            for route in decorated
            if route.within_limit
            and (route.id == fastest.id or route.savings >= request.min_savings)
        ]
        decorated = visible

    eligible_count = len(decorated)
    decorated = select_economically_distinct_routes(
        decorated,
        request.min_savings,
    )
    distinct_count = len(decorated)
    decorated = select_representative_routes(decorated, max_routes=7)
    decorated = decorate_routes(decorated, request.max_extra_minutes)
    fastest_minutes = min(route.duration_minutes for route in results)
    return RouteResponse(
        engine=engine_result.engine,  # type: ignore[arg-type]
        engine_message=engine_result.message,
        fastest_minutes=fastest_minutes,
        max_extra_minutes=request.max_extra_minutes,
        candidate_count=len(results),
        distinct_count=distinct_count,
        eligible_count=eligible_count,
        merged_count=max(0, eligible_count - distinct_count),
        hidden_count=max(0, len(results) - len(decorated)),
        routes=decorated,
    )

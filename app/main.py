from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.models import RouteRequest, RouteResponse, RouteResult, TollSegmentResult
from app.services.costs import calculate_costs
from app.services.geocoder import LocalGeocoder
from app.services.pareto import decorate_routes, select_representative_routes
from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService

app = FastAPI(title="Routeco", version="0.3.3")
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

geocoder = LocalGeocoder(settings.ban_database, settings.demo_places)
routing = GraphHopperClient(settings.graphhopper_url)
tolls = TollPricingService(settings.tolls_dir)


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(settings.static_dir / "index.html")


@app.get("/api/config")
def public_config() -> dict:
    return {
        "map": {
            "mode": "schematic",
            "style_url": settings.map_style_url,
            "maplibre_ready": bool(settings.map_style_url),
        },
        "vehicle": {
            "name": "Renault Twingo 2",
            "toll_class": 1,
            "motorway_consumption": 6.5,
            "road_consumption": 5.5,
            "fuel_types": ["SP95-E10", "SP98"],
        },
    }


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "graphhopper": await routing.available(),
        "ban": settings.ban_database.exists(),
        "tolls": tolls.ready,
        "toll_stations": len(tolls.stations),
        "toll_closed_pairs": len(tolls.closed_prices),
        "toll_open_prices": len(tolls.open_prices),
        "toll_official_sources": (settings.tolls_dir / "official" / "sources.json").exists(),
        "map_mode": "schematic",
        "maplibre_ready": bool(settings.map_style_url),
    }


@app.get("/api/geocode")
def search_address(q: str = Query(min_length=2, max_length=160)) -> list[dict]:
    return [result.model_dump() for result in geocoder.search(q)]


@app.post("/api/routes", response_model=RouteResponse)
async def calculate_routes(request: RouteRequest) -> RouteResponse:
    if request.start == request.end:
        raise HTTPException(status_code=400, detail="Le départ et l'arrivée doivent être différents.")

    engine_result = await routing.candidates(request.start, request.end)
    results: list[RouteResult] = []
    for candidate in engine_result.candidates:
        quote = tolls.quote(
            geometry=candidate["geometry"],
            tolled_km=candidate.get("tolled_km", 0),
            toll_ranges=candidate.get("toll_ranges"),
            road_class_link_details=candidate.get("road_class_link_details"),
            demo_toll=candidate.get("demo_toll"),
        )
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

    # GraphHopper has already removed near-duplicates. Keep the remaining route
    # variants instead of applying a strict Pareto filter: the product is meant
    # to expose useful trade-offs, not only mathematically non-dominated paths.
    decorated = decorate_routes(results, request.max_extra_minutes)
    if not request.show_all:
        visible = [route for route in decorated if route.within_limit]
        fastest = min(decorated, key=lambda route: route.duration_minutes)
        if all(route.id != fastest.id for route in visible):
            visible.insert(0, fastest)
        decorated = visible

    decorated = select_representative_routes(decorated, max_routes=5)
    fastest_minutes = min(route.duration_minutes for route in results)
    return RouteResponse(
        engine=engine_result.engine,  # type: ignore[arg-type]
        engine_message=engine_result.message,
        fastest_minutes=fastest_minutes,
        max_extra_minutes=request.max_extra_minutes,
        routes=decorated,
    )

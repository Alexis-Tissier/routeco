#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio

from app.config import settings
from app.models import Coordinate
from app.services.geocoder import LocalGeocoder
from app.services.routing import GraphHopperClient
from app.services.tolls import TollPricingService


def fmt_station(item) -> str:
    station = item.station
    marker = "BARRIÈRE" if station.is_mainline_barrier else "gare"
    return (
        f"{station.display_name} [{marker}, {station.operator or '?'}] "
        f"route={item.route_km:.1f} km, écart={item.lateral_km:.2f} km"
    )


def resolve(geocoder: LocalGeocoder, query: str) -> Coordinate:
    results = geocoder.search(query, limit=5)
    if not results:
        raise SystemExit(f"Adresse introuvable dans la BAN : {query}")
    print(f"{query} -> {results[0].label} ({results[0].lat}, {results[0].lon})")
    return Coordinate(lat=results[0].lat, lon=results[0].lon)


async def run(start_query: str, end_query: str) -> None:
    geocoder = LocalGeocoder(settings.ban_database, settings.demo_places)
    routing = GraphHopperClient(settings.graphhopper_url)
    tolls = TollPricingService(settings.tolls_dir)

    start = resolve(geocoder, start_query)
    end = resolve(geocoder, end_query)

    result = await routing.candidates(start, end)
    print(f"\nMoteur : {result.engine} — {result.message}")
    print(
        f"Données péage : {len(tolls.stations)} gares, "
        f"{len(tolls.closed_prices)} tarifs fermés\n"
    )

    for index, candidate in enumerate(result.candidates, 1):
        geometry = candidate["geometry"]
        projections, cumulative = tolls._project_stations(geometry)
        ranges = tolls._prepare_ranges(geometry, cumulative, candidate.get("toll_ranges", []))
        quote = tolls.quote_candidate(candidate)

        print("=" * 100)
        print(
            f"ITINÉRAIRE {index}: {candidate['id']}\n"
            f"durée={candidate['duration_minutes']} min | distance={candidate['distance_km']} km | "
            f"autoroute={candidate['motorway_km']} km | payant={candidate['tolled_km']} km | "
            f"plages payantes={len(ranges)}"
        )
        print(
            f"RÉSULTAT: {quote.cost:.2f} € | {quote.confidence} | "
            f"{quote.message} | gares={quote.stations}"
        )
        for segment in quote.segments:
            label = segment.entry or "partie estimée"
            if segment.exit:
                label += f" -> {segment.exit}"
            print(
                f"  SEGMENT: {label} | {segment.cost:.2f} € | "
                f"{segment.confidence} | opérateur={segment.operator or '?'}"
            )
        print(f"Gares projetées à moins de 2,5 km du tracé : {len(projections)}")

        for range_index, toll_range in enumerate(ranges, 1):
            print("-" * 100)
            print(
                f"PLAGE {range_index}: route {toll_range.start_km:.1f} -> "
                f"{toll_range.end_km:.1f} km "
                f"(distance GraphHopper={toll_range.distance_km:.1f} km)"
            )

            starts = tolls._boundary_candidates(
                projections, toll_range.start_km, progress_window=22.0, lateral_limit=2.5
            )[:12]
            ends = tolls._boundary_candidates(
                projections, toll_range.end_km, progress_window=22.0, lateral_limit=2.5
            )[:12]

            print("Candidats près du DÉBUT :")
            if starts:
                for score, item in starts:
                    print(f"  score={score:.2f} | {fmt_station(item)}")
            else:
                print("  aucun")

            print("Candidats près de la FIN :")
            if ends:
                for score, item in ends:
                    print(f"  score={score:.2f} | {fmt_station(item)}")
            else:
                print("  aucun")

            pair = tolls._best_closed_pair(projections, toll_range)
            if pair is None:
                print("Paire locale retenue : AUCUNE")
            else:
                record, entry, exit_ = pair
                print(
                    f"Paire locale retenue : {entry.station.display_name} -> "
                    f"{exit_.station.display_name} = {record.price:.2f} € "
                    f"(distance matrice={record.distance_km}, opérateur={record.operator})"
                )

        if len(ranges) == 1:
            wide = tolls._route_wide_pair(projections, ranges[0], candidate.get("tolled_km", 0.0))
            if wide is None:
                print("Paire globale route : AUCUNE")
            else:
                record, entry, exit_ = wide
                print(
                    f"Paire globale route : {entry.station.display_name} -> "
                    f"{exit_.station.display_name} = {record.price:.2f} € "
                    f"(distance matrice={record.distance_km}, opérateur={record.operator})"
                )

        print("Gares proches du tracé, dans l'ordre :")
        for item in projections:
            if item.lateral_km <= 1.3:
                print(f"  {fmt_station(item)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnostiquer l'appariement des péages.")
    parser.add_argument("start", nargs="?", default="Paris, 75001")
    parser.add_argument("end", nargs="?", default="Lyon, 69001")
    args = parser.parse_args()
    asyncio.run(run(args.start, args.end))


if __name__ == "__main__":
    main()

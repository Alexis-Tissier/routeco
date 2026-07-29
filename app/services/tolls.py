from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.geo import haversine_km, point_segment_projection_km, polyline_distance_km


def normalize_name(value: str) -> str:
    """Return a conservative key shared by tariff matrices and station datasets."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().strip()
    text = re.sub(r"\bn[°o]?\s*\d+(?:[.,]\d+)?\b", " ", text)
    text = re.sub(r"\ba\s*\d+[a-z]?\b", " ", text)
    text = re.sub(r"\b(?:entree|sortie|sens\s*[12]|bpv|principale|annexe)\b", " ", text)
    text = re.sub(r"\bsainte?\b", lambda match: "ste" if match.group(0).startswith("sainte") else "st", text)
    text = re.sub(r"\b(peage|gare|barriere|de|du|des|la|le|les|d)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()



def physical_label_key(value: str) -> str:
    """Normalize a station label while preserving principal/annex distinctions."""
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().strip()
    text = re.sub(r"\bn[°o]?\s*\d+(?:[.,]\d+)?\b", " ", text)
    text = re.sub(r"\ba\s*\d+[a-z]?\b", " ", text)
    text = re.sub(r"\b(?:entree|sortie|sens\s*[12]|bpv)\b", " ", text)
    text = re.sub(r"\bsainte?\b", lambda match: "ste" if match.group(0).startswith("sainte") else "st", text)
    text = re.sub(r"\b(peage|gare|barriere|de|du|des|la|le|les|d)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()

def name_aliases(value: str) -> set[str]:
    """Build useful aliases without hard-coding a particular journey.

    Official tariff PDFs often label a mainline barrier as
    ``PARIS / ROISSY (péage de Chamant)`` while the national station dataset
    simply calls it ``Chamant``. Both forms are indexed here.
    """
    raw = value or ""
    aliases = {normalize_name(raw)}
    for marker in re.findall(r"\((?:peage|péage|barriere|barrière)\s+(?:de|d['’])?\s*([^)]*)\)", raw, re.I):
        aliases.add(normalize_name(marker))
    for part in re.split(r"[/|]", raw):
        aliases.add(normalize_name(part))
    # Matrix groups such as "X à Y" may be represented by either endpoint in
    # the geographic station file. Keep both endpoint aliases.
    for part in re.split(r"\s+à\s+", raw, flags=re.I):
        aliases.add(normalize_name(part))
    return {alias for alias in aliases if alias}


@dataclass(slots=True)
class TollSegmentQuote:
    entry: str | None
    exit: str | None
    operator: str
    cost: float
    distance_km: float | None
    confidence: str
    route_start_km: float | None = None
    route_end_km: float | None = None


@dataclass(slots=True)
class TollQuote:
    cost: float
    confidence: str
    stations: list[str]
    message: str
    segments: list[TollSegmentQuote] = field(default_factory=list)


@dataclass(slots=True)
class TollStation:
    name: str
    operator: str
    lat: float
    lon: float
    system_type: str
    osm_name: str = ""

    @property
    def display_name(self) -> str:
        return self.osm_name.strip() or self.name.title()

    @property
    def is_mainline_barrier(self) -> bool:
        """True for named full-width barriers rather than interchange plazas.

        OpenTollData names major barriers with prefixes such as ``PEAGE DE`` or
        ``BARRIERE``. Interchange stations (Fontainebleau, Nemours, etc.) can sit
        close to the motorway geometry without actually being crossed. For a
        long closed-system journey, a physical mainline barrier is therefore a
        much stronger candidate than a nearby ramp plaza.
        """
        def marker_text(value: str) -> str:
            text = unicodedata.normalize("NFKD", value or "")
            text = "".join(char for char in text if not unicodedata.combining(char))
            return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

        if self.system_type in {"mainline", "barrier"}:
            return True
        raw = marker_text(self.name)
        osm = marker_text(self.osm_name)
        return bool(re.search(r"\b(peage|barriere)\b", raw)) or bool(
            re.search(r"\b(peage|barriere)\b", osm)
        )


@dataclass(frozen=True, slots=True)
class ClosedPrice:
    price: float
    distance_km: float | None
    operator: str


@dataclass(slots=True)
class StationProjection:
    station: TollStation
    route_km: float
    lateral_km: float
    segment_index: int


@dataclass(slots=True)
class TollRange:
    start_index: int
    end_index: int
    start_km: float
    end_km: float
    distance_km: float


@dataclass(slots=True)
class ClosedMatch:
    range_index: int
    toll_range: TollRange
    record: ClosedPrice
    entry: StationProjection
    exit: StationProjection
    coverage_km: float = 0.0
    full_range: bool = False

    @property
    def span_start_km(self) -> float:
        return self.entry.route_km

    @property
    def span_end_km(self) -> float:
        return self.exit.route_km

    @property
    def span_km(self) -> float:
        return max(0.0, self.span_end_km - self.span_start_km)


class TollPricingService:
    """Price French tolls from local OpenTollData matrices.

    Exact matching is driven by GraphHopper's tolled path ranges. For each range,
    the service identifies the physical entry and exit plazas near the range
    boundaries, then looks up their class-1 price in the local matrix. It only
    claims an exact price when every tolled range has been resolved.
    """

    FALLBACK_EUR_PER_KM = 0.105
    MINOR_RESIDUAL_KM = 5.0
    MINOR_RESIDUAL_EUR = 1.0

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.stations: list[TollStation] = []
        self.closed_prices: dict[tuple[str, str, str], ClosedPrice] = {}
        self.closed_prices_any: dict[tuple[str, str], list[ClosedPrice]] = {}
        self.open_prices: dict[tuple[str, str], float] = {}
        self.open_prices_any: dict[str, list[tuple[str, float]]] = {}
        self._load()

    @property
    def ready(self) -> bool:
        return bool(self.stations and (self.closed_prices or self.open_prices))

    @staticmethod
    def _parse_float(value: str | None) -> float | None:
        if value is None or not value.strip():
            return None
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None

    def _load(self) -> None:
        station_files = sorted(self.data_dir.glob("stations*.csv"))
        station_files.extend(sorted((self.data_dir / "official").glob("stations*.csv")))
        closed_files = sorted(self.data_dir.glob("closed_prices*.csv"))
        closed_files.extend(sorted((self.data_dir / "official").glob("closed_prices*.csv")))
        open_files = sorted(self.data_dir.glob("open_prices*.csv"))
        open_files.extend(sorted((self.data_dir / "official").glob("open_prices*.csv")))

        seen_stations: set[tuple[str, int, int, str]] = set()
        for stations_file in station_files:
            with stations_file.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        station_type = row.get("type", "closed").lower()
                        if station_type == "close":
                            station_type = "closed"
                        station = TollStation(
                            name=row["name"],
                            osm_name=row.get("osm_name", ""),
                            operator=row.get("operator", "").upper(),
                            lat=float(row["lat"]),
                            lon=float(row["lon"]),
                            system_type=station_type,
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
                    dedupe_key = (
                        normalize_name(station.name),
                        round(station.lat * 10000),
                        round(station.lon * 10000),
                        station.system_type,
                    )
                    if dedupe_key in seen_stations:
                        continue
                    seen_stations.add(dedupe_key)
                    self.stations.append(station)

        for closed_file in closed_files:
            with closed_file.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        operator = row.get("operator", "").upper()
                        price = self._parse_float(row.get("price1"))
                        if price is None:
                            continue
                        record = ClosedPrice(
                            price=price,
                            distance_km=self._parse_float(row.get("distance")),
                            operator=operator,
                        )
                        aliases_a = name_aliases(row["name_from"])
                        aliases_b = name_aliases(row["name_to"])
                        for a in aliases_a:
                            for b in aliases_b:
                                if not a or not b or a == b:
                                    continue
                                self.closed_prices[(operator, a, b)] = record
                                bucket = self.closed_prices_any.setdefault((a, b), [])
                                if record not in bucket:
                                    bucket.append(record)
                    except (KeyError, TypeError, ValueError):
                        continue

        for open_file in open_files:
            with open_file.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    try:
                        operator = row.get("operator", "").upper()
                        price = self._parse_float(row.get("price1"))
                        if price is None:
                            continue
                        for name in name_aliases(row["name"]):
                            self.open_prices[(operator, name)] = price
                            bucket = self.open_prices_any.setdefault(name, [])
                            item = (operator, price)
                            if item not in bucket:
                                bucket.append(item)
                    except (KeyError, TypeError, ValueError):
                        continue

        # Open-system prices and station coordinates often come from different
        # sources. Build explicit open-station twins only when a station name
        # unambiguously matches an open-toll tariff. This keeps the production
        # algorithm data-driven: no journey, city pair or route name is encoded
        # here.
        self._materialize_open_stations()

    def _materialize_open_stations(self) -> None:
        existing = {
            (
                normalize_name(station.name),
                round(station.lat * 10000),
                round(station.lon * 10000),
                station.system_type,
            )
            for station in self.stations
        }
        additions: list[TollStation] = []
        for station in list(self.stations):
            if station.system_type == "open":
                continue
            aliases = name_aliases(station.name) | name_aliases(station.osm_name)
            matches: set[tuple[str, float]] = set()
            for alias in aliases:
                direct = self.open_prices.get((station.operator, alias))
                if direct is not None:
                    matches.add((station.operator, direct))
                matches.update(self.open_prices_any.get(alias, []))
            values = {(operator, price) for operator, price in matches if price >= 0}
            if not values:
                continue
            preferred = [item for item in values if item[0] == station.operator]
            if preferred:
                operator, _ = sorted(preferred)[0]
            else:
                operators = {operator for operator, _ in values if operator}
                prices = {price for _, price in values}
                if len(operators) != 1 or len(prices) != 1:
                    continue
                operator = next(iter(operators))
            key = (
                normalize_name(station.name),
                round(station.lat * 10000),
                round(station.lon * 10000),
                "open",
            )
            if key in existing:
                continue
            existing.add(key)
            additions.append(
                TollStation(
                    name=station.name,
                    osm_name=station.osm_name,
                    operator=operator or station.operator,
                    lat=station.lat,
                    lon=station.lon,
                    system_type="open",
                )
            )
        self.stations.extend(additions)

    def quote(
        self,
        geometry: list[list[float]],
        tolled_km: float,
        toll_ranges: list[dict[str, Any]] | None = None,
        demo_toll: float | None = None,
    ) -> TollQuote:
        if demo_toll is not None:
            return TollQuote(round(demo_toll, 2), "exact", [], "Tarif de démonstration.")
        if tolled_km <= 0.05:
            return TollQuote(0.0, "none", [], "Aucun tronçon payant détecté.")

        # Very short OSM toll fragments are usually ramp/service-lane tagging
        # noise. Before ignoring them, still allow an official open-system gantry
        # that lies on the route to provide an exact fixed price. Closed-system
        # matrix pairs are never credible for only a few hundred metres.
        if tolled_km <= 0.5:
            if self.ready and len(geometry) >= 2:
                exact_open = self._quote_open_only(geometry, toll_ranges or [])
                if exact_open is not None:
                    return exact_open
            return TollQuote(
                0.0,
                "none",
                [],
                "Micro-segment de péage OSM ignoré : aucun tarif ouvert correspondant.",
            )

        if self.ready and len(geometry) >= 2:
            exact = self._quote_from_ranges(geometry, tolled_km, toll_ranges or [])
            if exact is not None:
                return exact

        estimate = round(tolled_km * self.FALLBACK_EUR_PER_KM, 2)
        return TollQuote(
            estimate,
            "estimated",
            [],
            "Estimation provisoire à 0,105 €/km payant : aucune paire entrée-sortie fiable.",
            segments=[
                TollSegmentQuote(
                    entry=None,
                    exit=None,
                    operator="",
                    cost=estimate,
                    distance_km=round(tolled_km, 1),
                    confidence="estimated",
                )
            ],
        )

    def _quote_open_only(
        self, geometry: list[list[float]], raw_ranges: list[dict[str, Any]]
    ) -> TollQuote | None:
        projections, cumulative = self._project_stations(geometry)
        if not projections:
            return None
        ranges = self._prepare_ranges(geometry, cumulative, raw_ranges)
        if not ranges:
            ranges = [
                TollRange(
                    start_index=0,
                    end_index=len(geometry) - 1,
                    start_km=0.0,
                    end_km=cumulative[-1],
                    distance_km=cumulative[-1],
                )
            ]

        used: list[tuple[StationProjection, float]] = []
        names: list[str] = []
        segments: list[TollSegmentQuote] = []
        total = 0.0
        for toll_range in ranges:
            for projection in self._open_stations_in_range(projections, toll_range):
                price = self._lookup_open(projection.station)
                if price is None:
                    continue
                if self._same_open_charge_already_used(projection, price, used):
                    continue
                used.append((projection, price))
                total += price
                names.append(projection.station.display_name)
                segments.append(
                    TollSegmentQuote(
                        entry=projection.station.display_name,
                        exit=None,
                        operator=projection.station.operator,
                        cost=round(price, 2),
                        distance_km=None,
                        confidence="exact",
                        route_start_km=round(projection.route_km, 1),
                        route_end_km=round(projection.route_km, 1),
                    )
                )
        if not segments:
            return None
        names = self._dedupe_names(names)
        return TollQuote(
            round(total, 2),
            "exact",
            names,
            f"Tarif exact classe 1 (péage ouvert) : {' + '.join(names)}.",
            segments=segments,
        )

    def _quote_from_ranges(
        self,
        geometry: list[list[float]],
        tolled_km: float,
        raw_ranges: list[dict[str, Any]],
    ) -> TollQuote | None:
        projections, cumulative = self._project_stations(geometry)
        if not projections:
            return None

        ranges = self._prepare_ranges(geometry, cumulative, raw_ranges)
        if not ranges:
            route_wide = self._route_wide_pair(projections, None, tolled_km)
            if route_wide is None:
                return None
            record, entry, exit_ = route_wide
            return self._closed_quote(record, entry, exit_)

        # Closed-system matches are proposed for every GraphHopper toll range,
        # then selected globally. The previous range-by-range greedy approach
        # could reuse one physical entry twice or accept overlapping matrix
        # journeys. Global selection makes those states impossible.
        proposals: list[ClosedMatch] = []
        multiple_ranges = len(ranges) > 1
        for range_index, toll_range in enumerate(ranges):
            pair = None
            if toll_range.distance_km >= 5.0:
                if not multiple_ranges and toll_range.distance_km >= 80.0:
                    pair = self._route_wide_pair(
                        projections, toll_range, toll_range.distance_km
                    )
                if pair is None:
                    pair = self._best_closed_pair(projections, toll_range)
            elif toll_range.distance_km > 0.5:
                # A short but material range may still correspond to a local
                # closed-system entry/exit. Micro-ranges are handled in quote().
                pair = self._best_closed_pair(projections, toll_range)

            if pair is not None:
                record, entry, exit_ = pair
                proposals.append(
                    ClosedMatch(
                        range_index,
                        toll_range,
                        record,
                        entry,
                        exit_,
                        coverage_km=toll_range.distance_km,
                        full_range=True,
                    )
                )
            else:
                chain, chain_is_complete = self._best_closed_chain(
                    projections, toll_range, range_index
                )
                if chain:
                    if chain_is_complete:
                        chain[0].full_range = True
                    proposals.extend(chain)

        accepted = self._select_closed_matches(proposals)
        resolved_ranges: set[int] = set()
        range_covered_km: dict[int, float] = {}
        used_station_keys: set[str] = set()
        used_open: list[tuple[StationProjection, float]] = []
        total = 0.0
        station_names: list[str] = []
        segments: list[TollSegmentQuote] = []
        closed_spans: list[tuple[float, float]] = []

        for match in accepted:
            range_covered_km[match.range_index] = min(
                ranges[match.range_index].distance_km,
                range_covered_km.get(match.range_index, 0.0)
                + max(0.0, match.coverage_km or match.span_km),
            )
            if match.full_range:
                resolved_ranges.add(match.range_index)
                # Nested/duplicated OSM ranges are considered explained by the same
                # official journey only when the ranges themselves substantially
                # overlap. Separated paid corridors are never merged implicitly.
                for other_index, other_range in enumerate(ranges):
                    if other_index in resolved_ranges:
                        continue
                    if self._ranges_substantially_overlap(match.toll_range, other_range):
                        resolved_ranges.add(other_index)

            total += match.record.price
            entry_name = match.entry.station.display_name
            exit_name = match.exit.station.display_name
            station_names.extend([entry_name, exit_name])
            used_station_keys.update(self._station_identity_keys(match.entry.station))
            used_station_keys.update(self._station_identity_keys(match.exit.station))
            closed_spans.append((match.span_start_km, match.span_end_km))
            segments.append(
                TollSegmentQuote(
                    entry=entry_name,
                    exit=exit_name,
                    operator=match.record.operator,
                    cost=round(match.record.price, 2),
                    distance_km=match.record.distance_km,
                    confidence="exact",
                    route_start_km=round(match.span_start_km, 1),
                    route_end_km=round(match.span_end_km, 1),
                )
            )

        # Resolve remaining ranges with explicit open/free-flow gantries. A
        # physical gantry can only be charged once, regardless of aliases or
        # duplicate station files. Open points located inside an accepted closed
        # matrix span are ignored because that matrix already prices the journey.
        for range_index, toll_range in enumerate(ranges):
            if range_index in resolved_ranges:
                continue
            open_matches = self._open_stations_in_range(projections, toll_range)
            accepted_open: list[tuple[StationProjection, float]] = []
            for projection in open_matches:
                if any(
                    start_km - 0.5 <= projection.route_km <= end_km + 0.5
                    for start_km, end_km in closed_spans
                ):
                    continue
                keys = self._station_identity_keys(projection.station)
                if keys & used_station_keys:
                    continue
                price = self._lookup_open(projection.station)
                if price is None:
                    continue
                if self._same_open_charge_already_used(projection, price, used_open):
                    continue
                used_station_keys.update(keys)
                used_open.append((projection, price))
                accepted_open.append((projection, price))

            if not accepted_open:
                continue

            # A pure open-system range is priced by the crossed gantry itself.
            # When closed matrix spans already cover part of the same OSM range,
            # the gantry is added but the remaining distance still has to be
            # explained instead of declaring the entire range resolved.
            if range_covered_km.get(range_index, 0.0) <= 0.05:
                resolved_ranges.add(range_index)
            for projection, price in accepted_open:
                name = projection.station.display_name
                total += price
                station_names.append(name)
                segments.append(
                    TollSegmentQuote(
                        entry=name,
                        exit=None,
                        operator=projection.station.operator,
                        cost=round(price, 2),
                        distance_km=None,
                        confidence="exact",
                        route_start_km=round(projection.route_km, 1),
                        route_end_km=round(projection.route_km, 1),
                    )
                )

        segments.sort(
            key=lambda item: (
                float("inf") if item.route_start_km is None else item.route_start_km,
                float("inf") if item.route_end_km is None else item.route_end_km,
            )
        )
        station_names = self._dedupe_names(station_names)
        unresolved_indexes = [
            index for index in range(len(ranges)) if index not in resolved_ranges
        ]
        unresolved_km_by_range = {
            index: max(
                0.0,
                ranges[index].distance_km - range_covered_km.get(index, 0.0),
            )
            for index in unresolved_indexes
        }
        unresolved_km = sum(unresolved_km_by_range.values())

        if not unresolved_indexes or unresolved_km <= 0.05:
            if segments and self._segments_are_integral(segments):
                details = " → ".join(station_names)
                message = "Tarif exact classe 1 issu des matrices locales."
                if details:
                    message = f"Tarif exact classe 1 : {details}."
                return TollQuote(
                    round(total, 2), "exact", station_names, message, segments=segments
                )
            # A fully resolved-looking result that violates ordering, uniqueness
            # or overlap constraints is discarded. quote() will return the honest
            # per-kilometre estimate instead of publishing a false exact fare.
            return None

        # OSM can split one continuous closed corridor into several nearby toll
        # ranges. A single route-wide matrix is allowed to replace the partial
        # result only when all ranges are contiguous enough and the resulting
        # pair is itself geometrically credible.
        if unresolved_indexes:
            combined = self._combined_range_if_contiguous(ranges, tolled_km)
            if combined is not None:
                route_wide = self._route_wide_pair(projections, combined, tolled_km)
                if route_wide is not None:
                    record, entry, exit_ = route_wide
                    route_quote = self._closed_quote(record, entry, exit_)
                    if route_quote.cost + 0.01 >= total:
                        return route_quote

        if total > 0:
            estimated_part = round(unresolved_km * self.FALLBACK_EUR_PER_KM, 2)
            # A few kilometres of residual OSM toll tagging around a known plaza
            # must not downgrade an otherwise complete official tariff. These
            # fragments are explicitly ignored only below both distance and cost
            # thresholds; significant gaps remain honestly estimated.
            if (
                unresolved_km <= self.MINOR_RESIDUAL_KM
                and estimated_part < self.MINOR_RESIDUAL_EUR
                and segments
                and self._segments_are_integral(segments)
            ):
                details = " → ".join(station_names)
                message = "Tarif exact classe 1"
                if details:
                    message += f" : {details}"
                message += " (micro-fragment OSM ignoré)."
                return TollQuote(
                    round(total, 2), "exact", station_names, message, segments=segments
                )
            if estimated_part > 0:
                segments.append(
                    TollSegmentQuote(
                        entry=None,
                        exit=None,
                        operator="",
                        cost=estimated_part,
                        distance_km=round(unresolved_km, 1),
                        confidence="estimated",
                    )
                )
            return TollQuote(
                round(total + estimated_part, 2),
                "estimated",
                station_names,
                "Tarif partiellement apparié ; le solde reste estimé à 0,105 €/km payant.",
                segments=segments,
            )

        return None

    def _best_closed_chain(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        range_index: int,
    ) -> tuple[list[ClosedMatch], bool]:
        """Find several non-overlapping exact matrix journeys inside one OSM range.

        A single GraphHopper toll range can cross multiple concession systems or
        be split by a free urban connector. Boundary-only matching cannot explain
        such a range. This fallback builds all credible matrix intervals along
        the route, then uses weighted interval scheduling to maximize the exact
        distance covered without overlaps or reused stations.
        """
        if toll_range.distance_km < 40.0:
            return [], False

        relevant = [
            item
            for item in projections
            if item.station.system_type != "open"
            and toll_range.start_km - 25.0 <= item.route_km <= toll_range.end_km + 25.0
            and (
                item.lateral_km <= 0.45
                or (item.station.is_mainline_barrier and item.lateral_km <= 1.2)
            )
        ]
        candidates: list[tuple[float, ClosedMatch]] = []
        for position, entry in enumerate(relevant):
            for exit_ in relevant[position + 1 :]:
                span = exit_.route_km - entry.route_km
                if span < 8.0:
                    continue
                record = self._lookup_closed(entry.station, exit_.station)
                if record is None:
                    continue
                overlap_start = max(entry.route_km, toll_range.start_km)
                overlap_end = min(exit_.route_km, toll_range.end_km)
                coverage = max(0.0, overlap_end - overlap_start)
                if coverage < 8.0:
                    continue
                mismatch = 0.0
                if record.distance_km is not None:
                    mismatch = abs(record.distance_km - span)
                    if mismatch > max(20.0, span * 0.18):
                        continue
                boundary_bonus = 0.0
                if abs(entry.route_km - toll_range.start_km) <= 25.0:
                    boundary_bonus += 4.0
                if abs(exit_.route_km - toll_range.end_km) <= 25.0:
                    boundary_bonus += 4.0
                quality = (
                    coverage
                    + boundary_bonus
                    - (entry.lateral_km + exit_.lateral_km) * 3.0
                    - mismatch * 0.15
                )
                candidates.append(
                    (
                        quality,
                        ClosedMatch(
                            range_index,
                            toll_range,
                            record,
                            entry,
                            exit_,
                            coverage_km=coverage,
                            full_range=False,
                        ),
                    )
                )

        if not candidates:
            return [], False

        candidates.sort(key=lambda item: (item[1].span_end_km, item[1].span_start_km))
        previous: list[int] = []
        for _, candidate in candidates:
            index = -1
            # Number of candidates is small (projected stations near one route),
            # so a backwards scan is clearer and fast enough.
            for previous_index in range(len(previous) - 1, -1, -1):
                if candidates[previous_index][1].span_end_km <= candidate.span_start_km + 1.0:
                    index = previous_index
                    break
            previous.append(index)

        scores: list[float] = [0.0] * (len(candidates) + 1)
        paths: list[list[int]] = [[] for _ in range(len(candidates) + 1)]
        for index, (quality, _) in enumerate(candidates, start=1):
            predecessor = previous[index - 1] + 1
            include_score = quality + scores[predecessor]
            exclude_score = scores[index - 1]
            if include_score > exclude_score + 0.01:
                scores[index] = include_score
                paths[index] = paths[predecessor] + [index - 1]
            else:
                scores[index] = exclude_score
                paths[index] = list(paths[index - 1])

        selected = [candidates[index][1] for index in paths[-1]]
        selected.sort(key=lambda item: item.span_start_km)
        if not selected:
            return [], False

        # Reject station reuse that could survive tariff aliases.
        filtered: list[ClosedMatch] = []
        used_keys: set[str] = set()
        for item in selected:
            keys = self._station_identity_keys(item.entry.station) | self._station_identity_keys(
                item.exit.station
            )
            if keys & used_keys:
                continue
            used_keys.update(keys)
            filtered.append(item)
        selected = filtered
        if not selected:
            return [], False

        covered = sum(item.coverage_km for item in selected)
        start_gap = max(0.0, selected[0].span_start_km - toll_range.start_km)
        end_gap = max(0.0, toll_range.end_km - selected[-1].span_end_km)
        internal_gaps = [
            max(0.0, current.span_start_km - previous_item.span_end_km)
            for previous_item, current in zip(selected, selected[1:])
        ]
        unexplained = max(0.0, toll_range.distance_km - covered)
        complete = (
            start_gap <= 25.0
            and end_gap <= 25.0
            and all(gap <= 35.0 for gap in internal_gaps)
            and unexplained <= max(10.0, toll_range.distance_km * 0.12)
        )
        return selected, complete

    def _closed_quote(
        self,
        record: ClosedPrice,
        entry: StationProjection,
        exit_: StationProjection,
    ) -> TollQuote:
        names = [entry.station.display_name, exit_.station.display_name]
        return TollQuote(
            round(record.price, 2),
            "exact",
            names,
            f"Tarif exact classe 1 : {names[0]} → {names[1]}.",
            segments=[
                TollSegmentQuote(
                    entry=names[0],
                    exit=names[1],
                    operator=record.operator,
                    cost=round(record.price, 2),
                    distance_km=record.distance_km,
                    confidence="exact",
                    route_start_km=round(entry.route_km, 1),
                    route_end_km=round(exit_.route_km, 1),
                )
            ],
        )

    def _select_closed_matches(self, proposals: list[ClosedMatch]) -> list[ClosedMatch]:
        # Long/material ranges are selected first. This lets a credible complete
        # matrix journey win over a shorter nested proposal that reuses the same
        # entry or exit. No destination-specific information is involved.
        ordered = sorted(
            proposals,
            key=lambda item: (
                -item.toll_range.distance_km,
                -item.span_km,
                item.entry.lateral_km + item.exit.lateral_km,
                item.span_start_km,
            ),
        )
        accepted: list[ClosedMatch] = []
        used_entries: set[str] = set()
        used_exits: set[str] = set()

        for proposal in ordered:
            if proposal.span_end_km <= proposal.span_start_km + 0.05:
                continue
            entry_keys = self._station_identity_keys(proposal.entry.station)
            exit_keys = self._station_identity_keys(proposal.exit.station)
            if entry_keys & used_entries or exit_keys & used_exits:
                continue
            if any(self._closed_spans_conflict(proposal, current) for current in accepted):
                continue
            accepted.append(proposal)
            used_entries.update(entry_keys)
            used_exits.update(exit_keys)

        accepted.sort(key=lambda item: item.span_start_km)
        return accepted

    @staticmethod
    def _closed_spans_conflict(first: ClosedMatch, second: ClosedMatch) -> bool:
        overlap = min(first.span_end_km, second.span_end_km) - max(
            first.span_start_km, second.span_start_km
        )
        return overlap > 1.0

    @staticmethod
    def _ranges_substantially_overlap(first: TollRange, second: TollRange) -> bool:
        overlap = min(first.end_km, second.end_km) - max(first.start_km, second.start_km)
        if overlap <= 0:
            return False
        shorter = min(
            max(0.1, first.end_km - first.start_km),
            max(0.1, second.end_km - second.start_km),
        )
        return overlap >= shorter * 0.75

    @staticmethod
    def _station_identity_keys(station: TollStation) -> set[str]:
        name = normalize_name(station.display_name or station.name)
        lat = round(station.lat, 3)
        lon = round(station.lon, 3)
        keys = {f"coord:{lat:.3f}:{lon:.3f}"}
        if name:
            keys.add(f"namecoord:{name}:{lat:.3f}:{lon:.3f}")
        return keys

    @staticmethod
    def _same_open_charge_already_used(
        projection: StationProjection,
        price: float,
        used: list[tuple[StationProjection, float]],
    ) -> bool:
        """Detect aliases of one physical open-system charge.

        National and concessionaire datasets can describe the same gantry with
        slightly different names and coordinates (for example ``Ancenis`` and
        ``Ancenis Péage``). A name-only key would incorrectly merge distinct
        plazas such as a principal/annex pair, while a coordinate-only key misses
        aliases shifted by a few hundred metres. We therefore require the same
        tariff plus geographic/route proximity, and either a shared normalized
        alias or near-identical coordinates.
        """
        aliases = name_aliases(projection.station.name) | name_aliases(
            projection.station.osm_name
        )
        for previous, previous_price in used:
            route_gap = abs(previous.route_km - projection.route_km)
            geo_gap = haversine_km(
                (previous.station.lon, previous.station.lat),
                (projection.station.lon, projection.station.lat),
            )
            previous_aliases = name_aliases(previous.station.name) | name_aliases(
                previous.station.osm_name
            )
            same_alias = bool(aliases & previous_aliases)
            nearly_same_point = geo_gap <= 0.8 and route_gap <= 1.0
            same_tariff_alias = abs(previous_price - price) <= 0.01 and same_alias
            if (same_tariff_alias and (route_gap <= 1.0 or geo_gap <= 1.0)) or nearly_same_point:
                return True
        return False

    @staticmethod
    def _segments_are_integral(segments: list[TollSegmentQuote]) -> bool:
        exact = [segment for segment in segments if segment.confidence == "exact"]
        if len(exact) != len(segments):
            return False

        entry_positions: dict[str, list[float]] = {}
        exit_positions: dict[str, list[float]] = {}
        entry_labels: set[str] = set()
        exit_labels: set[str] = set()
        previous_end = -1.0
        for segment in exact:
            if segment.route_start_km is None or segment.route_end_km is None:
                return False
            if segment.route_end_km + 0.05 < segment.route_start_km:
                return False
            entry_key = normalize_name(segment.entry or "")
            exit_key = normalize_name(segment.exit or "")
            entry_label = physical_label_key(segment.entry or "")
            exit_label = physical_label_key(segment.exit or "")
            # The exact same label cannot be charged twice anywhere on an A-to-B
            # route. Broader aliases are rejected only when they occur at almost
            # the same route position, preserving legitimate principal/annex
            # plazas that share a base locality name.
            if entry_label and entry_label in entry_labels:
                return False
            if exit_label and exit_label in exit_labels:
                return False
            if entry_key and any(
                abs(segment.route_start_km - position) <= 1.0
                for position in entry_positions.get(entry_key, [])
            ):
                return False
            if exit_key and any(
                abs(segment.route_end_km - position) <= 1.0
                for position in exit_positions.get(exit_key, [])
            ):
                return False
            if entry_key:
                entry_positions.setdefault(entry_key, []).append(segment.route_start_km)
            if exit_key:
                exit_positions.setdefault(exit_key, []).append(segment.route_end_km)
            if entry_label:
                entry_labels.add(entry_label)
            if exit_label:
                exit_labels.add(exit_label)
            # Open gantries are points. Closed journeys must not overlap a
            # previously selected exact journey by more than one kilometre.
            if segment.exit is not None and segment.route_start_km < previous_end - 1.0:
                return False
            previous_end = max(previous_end, segment.route_end_km)
        return True

    @staticmethod
    def _combined_range_if_contiguous(
        ranges: list[TollRange], tolled_km: float
    ) -> TollRange | None:
        if len(ranges) < 2:
            return ranges[0] if ranges else None
        gap_km = sum(
            max(0.0, current.start_km - previous.end_km)
            for previous, current in zip(ranges, ranges[1:])
        )
        # OSM may split a single charged corridor around junctions or gantries.
        # A genuinely mixed itinerary such as Avallon→Chalon has a much larger
        # free gap and must remain segmented.
        if gap_km > max(35.0, tolled_km * 0.25):
            return None
        return TollRange(
            start_index=ranges[0].start_index,
            end_index=ranges[-1].end_index,
            start_km=ranges[0].start_km,
            end_km=ranges[-1].end_km,
            distance_km=tolled_km,
        )

    def _prepare_ranges(
        self,
        geometry: list[list[float]],
        cumulative: list[float],
        raw_ranges: list[dict[str, Any]],
    ) -> list[TollRange]:
        prepared: list[TollRange] = []
        for item in raw_ranges:
            try:
                start = max(0, min(len(geometry) - 2, int(item["start_index"])))
                end = max(start + 1, min(len(geometry) - 1, int(item["end_index"])))
            except (KeyError, TypeError, ValueError):
                continue
            distance = self._parse_float(str(item.get("distance_km", "")))
            if distance is None or distance <= 0:
                distance = polyline_distance_km(geometry[start : end + 1])
            prepared.append(
                TollRange(
                    start_index=start,
                    end_index=end,
                    start_km=cumulative[start],
                    end_km=cumulative[end],
                    distance_km=distance,
                )
            )

        prepared.sort(key=lambda item: item.start_index)
        merged: list[TollRange] = []
        for item in prepared:
            if not merged or item.start_index > merged[-1].end_index + 2:
                merged.append(item)
                continue
            previous = merged[-1]
            previous.end_index = max(previous.end_index, item.end_index)
            previous.end_km = max(previous.end_km, item.end_km)
            previous.distance_km = max(previous.distance_km, previous.end_km - previous.start_km)
        return merged

    def _project_stations(
        self, geometry: list[list[float]]
    ) -> tuple[list[StationProjection], list[float]]:
        cumulative = [0.0]
        segment_lengths: list[float] = []
        for index in range(1, len(geometry)):
            length = haversine_km(
                (geometry[index - 1][0], geometry[index - 1][1]),
                (geometry[index][0], geometry[index][1]),
            )
            segment_lengths.append(length)
            cumulative.append(cumulative[-1] + length)

        min_lon = min(point[0] for point in geometry) - 0.05
        max_lon = max(point[0] for point in geometry) + 0.05
        min_lat = min(point[1] for point in geometry) - 0.05
        max_lat = max(point[1] for point in geometry) + 0.05

        projections: list[StationProjection] = []
        for station in self.stations:
            if not (min_lon <= station.lon <= max_lon and min_lat <= station.lat <= max_lat):
                continue
            best_distance = float("inf")
            best_route_km = 0.0
            best_segment = -1
            for index in range(1, len(geometry)):
                start = geometry[index - 1]
                end = geometry[index]
                # Cheap rejection before doing the planar projection.
                margin = 0.025
                if station.lon < min(start[0], end[0]) - margin or station.lon > max(start[0], end[0]) + margin:
                    continue
                if station.lat < min(start[1], end[1]) - margin or station.lat > max(start[1], end[1]) + margin:
                    continue
                lateral, fraction = point_segment_projection_km(
                    (station.lon, station.lat),
                    (start[0], start[1]),
                    (end[0], end[1]),
                )
                if lateral < best_distance:
                    best_distance = lateral
                    best_route_km = cumulative[index - 1] + fraction * segment_lengths[index - 1]
                    best_segment = index
            if best_segment >= 0 and best_distance <= 2.5:
                projections.append(
                    StationProjection(
                        station=station,
                        route_km=best_route_km,
                        lateral_km=best_distance,
                        segment_index=best_segment,
                    )
                )
        projections.sort(key=lambda item: item.route_km)
        return projections, cumulative

    def _best_closed_pair(
        self, projections: list[StationProjection], toll_range: TollRange
    ) -> tuple[ClosedPrice, StationProjection, StationProjection] | None:
        # First pass is strict enough to avoid neighboring exits. The second pass
        # tolerates GraphHopper toll tags that begin/end well beyond the physical
        # plaza (observed gap: ~16.4 km at Villefranche-Limas), while still requiring
        # tariff-matrix distance agreement and preferring named mainline barriers.
        for progress_window, lateral_limit in ((7.0, 1.3), (22.0, 2.2)):
            starts = self._boundary_candidates(
                projections, toll_range.start_km, progress_window, lateral_limit
            )[:10]
            ends = self._boundary_candidates(
                projections, toll_range.end_km, progress_window, lateral_limit
            )[:10]
            best: tuple[float, ClosedPrice, StationProjection, StationProjection] | None = None
            has_start_barrier = any(item.station.is_mainline_barrier for _, item in starts)
            has_end_barrier = any(item.station.is_mainline_barrier for _, item in ends)
            for start_score, entry in starts:
                for end_score, exit_ in ends:
                    if exit_.route_km <= entry.route_km + 0.05:
                        continue
                    record = self._lookup_closed(entry.station, exit_.station)
                    if record is None:
                        continue
                    mismatch = 0.0
                    if record.distance_km is not None:
                        mismatch = abs(record.distance_km - toll_range.distance_km)
                        allowed = max(15.0, toll_range.distance_km * 0.12)
                        if progress_window > 7.0 and mismatch > allowed:
                            continue

                    # A side-ramp plaza may be only a few hundred metres from
                    # the motorway and can otherwise beat the barrier actually
                    # crossed by the route. Prefer named mainline barriers when
                    # one is available near the same boundary.
                    plaza_penalty = 0.0
                    if toll_range.distance_km >= 80.0:
                        if has_start_barrier and not entry.station.is_mainline_barrier:
                            plaza_penalty += 24.0
                        if has_end_barrier and not exit_.station.is_mainline_barrier:
                            plaza_penalty += 24.0
                    score = start_score + end_score + mismatch / 12.0 + plaza_penalty
                    if best is None or score < best[0]:
                        best = (score, record, entry, exit_)
            if best is not None:
                return best[1], best[2], best[3]
        return None

    @staticmethod
    def _boundary_candidates(
        projections: list[StationProjection],
        boundary_km: float,
        progress_window: float,
        lateral_limit: float,
    ) -> list[tuple[float, StationProjection]]:
        candidates: list[tuple[float, StationProjection]] = []
        for projection in projections:
            if projection.station.system_type == "open":
                continue
            progress_delta = abs(projection.route_km - boundary_km)
            if progress_delta > progress_window or projection.lateral_km > lateral_limit:
                continue
            score = projection.lateral_km * 4.0 + progress_delta * 0.22
            candidates.append((score, projection))
        candidates.sort(key=lambda item: item[0])
        return candidates

    def _open_stations_in_range(
        self, projections: list[StationProjection], toll_range: TollRange
    ) -> list[StationProjection]:
        matches = [
            projection
            for projection in projections
            if projection.station.system_type == "open"
            and projection.lateral_km <= 0.12
            and toll_range.start_km - 1.5 <= projection.route_km <= toll_range.end_km + 1.5
            and self._lookup_open(projection.station) is not None
        ]
        matches.sort(key=lambda item: item.route_km)
        if not matches:
            return []

        # Several datasets can expose a mainline gantry and its two directional
        # ramps as three tariffs within a few hundred metres. A vehicle crosses
        # only one physical branch. Cluster these candidates and retain the point
        # that lies closest to the actual route geometry; a named mainline toll
        # wins only when the lateral distances are virtually tied.
        clusters: list[list[StationProjection]] = []
        for projection in matches:
            placed = False
            for cluster in clusters:
                anchor = cluster[0]
                if (
                    abs(anchor.route_km - projection.route_km) <= 1.0
                    and haversine_km(
                        (anchor.station.lon, anchor.station.lat),
                        (projection.station.lon, projection.station.lat),
                    )
                    <= 0.8
                ):
                    cluster.append(projection)
                    placed = True
                    break
            if not placed:
                clusters.append([projection])

        def mainline_hint(item: StationProjection) -> int:
            raw = f"{item.station.name} {item.station.osm_name}".casefold()
            directional = bool(re.search(r"\b(dir|direction|sens|bretelle|entree|sortie)\b", raw))
            mainline = bool(re.search(r"\b(peage|péage|barriere|barrière)\b", raw))
            return 0 if mainline and not directional else 1

        selected: list[StationProjection] = []
        for cluster in clusters:
            best_lateral = min(item.lateral_km for item in cluster)
            close = [item for item in cluster if item.lateral_km <= best_lateral + 0.03]
            selected.append(
                min(
                    close,
                    key=lambda item: (
                        mainline_hint(item),
                        item.lateral_km,
                        abs(item.route_km - (toll_range.start_km + toll_range.end_km) / 2),
                    ),
                )
            )
        selected.sort(key=lambda item: item.route_km)
        return selected

    def _route_wide_pair(
        self,
        projections: list[StationProjection],
        toll_range: TollRange | None = None,
        tolled_km: float | None = None,
    ) -> tuple[ClosedPrice, StationProjection, StationProjection] | None:
        # Mainline barriers normally sit almost exactly on the route. A side-ramp
        # plaza can still be less than 1 km from the motorway while not being
        # traversed at all. Keep a tight limit for ordinary interchange plazas,
        # and only allow a wider tolerance for explicitly named barriers.
        close = [
            projection
            for projection in projections
            if projection.station.system_type != "open"
            and (
                projection.lateral_km <= 0.32
                or (
                    projection.station.is_mainline_barrier
                    and projection.lateral_km <= 1.15
                )
            )
        ]
        if len(close) < 2:
            return None

        target_km = max(0.0, tolled_km or (toll_range.distance_km if toll_range else 0.0))
        best: tuple[float, ClosedPrice, StationProjection, StationProjection] | None = None

        for entry in close:
            for exit_ in close:
                span_km = exit_.route_km - entry.route_km
                if span_km <= 5.0:
                    continue

                record = self._lookup_closed(entry.station, exit_.station)
                if record is None:
                    continue

                # Avoid selecting a short interchange-to-interchange fare for a
                # long tolled motorway section.
                if target_km > 40.0 and span_km < target_km * 0.68:
                    continue
                if target_km and span_km > target_km + max(35.0, target_km * 0.35):
                    continue

                boundary_gap = 0.0
                if toll_range is not None:
                    boundary_gap = abs(entry.route_km - toll_range.start_km) + abs(
                        exit_.route_km - toll_range.end_km
                    )
                    # The OSM toll tag can start/end well outside the plazas, but
                    # a candidate hundreds of kilometres away is not credible.
                    if entry.route_km > toll_range.start_km + 110.0:
                        continue
                    if exit_.route_km < toll_range.end_km - 110.0:
                        continue

                tariff_mismatch = 0.0
                if record.distance_km is not None:
                    tariff_mismatch = abs(record.distance_km - span_km)
                    # Tariff distance is not always the exact driven distance.
                    allowed_tariff_mismatch = max(30.0, span_km * 0.45)
                    if target_km >= 80.0:
                        allowed_tariff_mismatch = max(160.0, span_km * 0.45)
                    if tariff_mismatch > allowed_tariff_mismatch:
                        continue

                target_mismatch = abs(span_km - target_km) if target_km else 0.0
                # For long motorway sections, the physical barriers actually
                # crossed are more trustworthy than the OSM `toll` range length:
                # that tag frequently starts after the entry barrier. Without
                # this preference, nearby exits such as Fontainebleau/Nemours can
                # be selected instead of the Fleury-en-Bière mainline barrier.
                plaza_penalty = 0.0
                if target_km >= 80.0:
                    if not entry.station.is_mainline_barrier:
                        plaza_penalty += 32.0
                    if not exit_.station.is_mainline_barrier:
                        plaza_penalty += 32.0

                score = (
                    entry.lateral_km * 24.0
                    + exit_.lateral_km * 24.0
                    + boundary_gap * 0.008
                    + tariff_mismatch * 0.012
                    + target_mismatch * 0.006
                    + plaza_penalty
                )
                if best is None or score < best[0]:
                    best = (score, record, entry, exit_)

        if best is None:
            return None
        return best[1], best[2], best[3]

    def _lookup_closed(self, entry: TollStation, exit_: TollStation) -> ClosedPrice | None:
        aliases_a = name_aliases(entry.name) | name_aliases(entry.osm_name)
        aliases_b = name_aliases(exit_.name) | name_aliases(exit_.osm_name)
        operators = [entry.operator, exit_.operator]

        direct: list[ClosedPrice] = []
        for operator in operators:
            if not operator:
                continue
            for a in aliases_a:
                for b in aliases_b:
                    record = self.closed_prices.get((operator, a, b))
                    if record is not None:
                        direct.append(record)
        chosen = self._unique_record(direct, preferred_operators=set(operators))
        if chosen is not None:
            return chosen

        candidates: list[ClosedPrice] = []
        for a in aliases_a:
            for b in aliases_b:
                candidates.extend(self.closed_prices_any.get((a, b), []))
        return self._unique_record(candidates, preferred_operators=set(operators))

    @staticmethod
    def _unique_record(
        candidates: list[ClosedPrice], preferred_operators: set[str]
    ) -> ClosedPrice | None:
        unique: dict[tuple[float, float | None, str], ClosedPrice] = {}
        for candidate in candidates:
            unique[(candidate.price, candidate.distance_km, candidate.operator)] = candidate
        if not unique:
            return None

        # The same official price may be present in OpenTollData and in a
        # concessionaire matrix under different operator labels. Collapse those
        # duplicates before declaring the match ambiguous.
        by_value: dict[tuple[float, float | None], list[ClosedPrice]] = {}
        for candidate in unique.values():
            by_value.setdefault((candidate.price, candidate.distance_km), []).append(candidate)
        if len(by_value) == 1:
            records = next(iter(by_value.values()))
            preferred = [item for item in records if item.operator in preferred_operators]
            return preferred[0] if preferred else records[0]

        preferred = [
            candidate
            for candidate in unique.values()
            if candidate.operator in preferred_operators
        ]
        preferred_values = {(item.price, item.distance_km) for item in preferred}
        if len(preferred_values) == 1 and preferred:
            return preferred[0]
        return None

    def _lookup_open(self, station: TollStation) -> float | None:
        aliases = name_aliases(station.name) | name_aliases(station.osm_name)
        direct = {
            self.open_prices[(station.operator, name)]
            for name in aliases
            if (station.operator, name) in self.open_prices
        }
        if len(direct) == 1:
            return next(iter(direct))
        candidates = {
            price
            for name in aliases
            for _, price in self.open_prices_any.get(name, [])
        }
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    @staticmethod
    def _dedupe_names(names: list[str]) -> list[str]:
        output: list[str] = []
        seen: set[str] = set()
        for name in names:
            key = normalize_name(name)
            if key and key not in seen:
                seen.add(key)
                output.append(name)
        return output

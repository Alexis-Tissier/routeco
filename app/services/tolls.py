from __future__ import annotations

import csv
import math
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
    # Physical topology from the station dataset. It stays available when a
    # closed interchange or a mainline barrier receives an open-tariff twin.
    physical_type: str = ""

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

        if (
            self.system_type in {"mainline", "barrier"}
            or self.physical_type in {"mainline", "barrier"}
        ):
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


# ROUTECO_V034_TOLL_PLAN_PROOF
@dataclass(slots=True)
class TollPlan:
    # Facturation candidate avant décision finale de confiance.
    exact_cost: float
    station_names: list[str]
    segments: list[TollSegmentQuote]
    ranges: list[TollRange]
    unresolved_indexes: list[int]
    unresolved_km_by_range: dict[int, float]
    unresolved_event_ranges: set[int]
    ignored_noise_indexes: set[int]

    @property
    def unresolved_km(self) -> float:
        return sum(max(0.0, value) for value in self.unresolved_km_by_range.values())

    @property
    def has_unresolved_events(self) -> bool:
        return bool(
            self.unresolved_event_ranges.intersection(self.unresolved_indexes)
        )

    @property
    def is_complete(self) -> bool:
        distance_complete = (
            not self.unresolved_indexes
            or self.unresolved_km <= 0.05
        )
        return distance_complete and not self.has_unresolved_events
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
    USER_VISIBLE_RESIDUAL_KM = 6.0
    # Budget transitoire : le routage ne prouve pas encore positivement qu'un
    # intervalle entre une sortie fermée et l'entrée suivante est gratuit.
    MAX_UNVERIFIED_CLOSED_CONNECTOR_KM = 5.0

    # ROUTECO_V034_GLOBAL_TOLL_PLAN
    # Isolated OSM toll tags below this size are non-billable unless a real
    # mainline barrier or an exact open-system charge is physically crossed.
    OSM_NOISE_RANGE_KM = 2.0
    # A slightly longer tag can still be boundary padding around an already
    # resolved tariff event. It is ignored only when no billing event exists.
    OSM_BOUNDARY_FRAGMENT_KM = 10.0
    OSM_BOUNDARY_EVENT_GAP_KM = 25.0

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
                            physical_type=station_type,
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
                    physical_type=station.physical_type or station.system_type,
                )
            )
        self.stations.extend(additions)

    def quote_candidate(self, candidate: dict[str, Any]) -> TollQuote:
        # One canonical adapter keeps every routing metadata field synchronized
        # between the API, validation scripts and diagnostics.
        return self.quote(
            geometry=candidate["geometry"],
            tolled_km=candidate.get("tolled_km", 0.0),
            toll_ranges=candidate.get("toll_ranges"),
            road_class_link_details=candidate.get("road_class_link_details"),
            demo_toll=candidate.get("demo_toll"),
        )

    def quote(
        self,
        geometry: list[list[float]],
        tolled_km: float,
        toll_ranges: list[dict[str, Any]] | None = None,
        road_class_link_details: list[list] | None = None,
        demo_toll: float | None = None,
    ) -> TollQuote:
        if demo_toll is not None:
            return TollQuote(
                round(demo_toll, 2),
                "estimated",
                [],
                "Tarif de démonstration synthétique, non issu de données tarifaires.",
            )
        if tolled_km <= 0.05:
            return TollQuote(0.0, "none", [], "Aucun tronçon payant détecté.")

        # Very short OSM toll fragments are usually ramp/service-lane tagging
        # noise. Before ignoring them, still allow an official open-system gantry
        # that lies on the route to provide an exact fixed price. Closed-system
        # matrix pairs are never credible for only a few hundred metres.
        if tolled_km <= 0.5:
            if self.ready and len(geometry) >= 2:
                exact_open = self._quote_open_only(
                    geometry,
                    toll_ranges or [],
                    road_class_link_details or [],
                )
                if exact_open is not None:
                    return exact_open
            return TollQuote(
                0.0,
                "none",
                [],
                "Micro-segment de péage OSM ignoré : aucun tarif ouvert correspondant.",
            )

        if self.ready and len(geometry) >= 2:
            exact = self._quote_from_ranges(
                geometry,
                tolled_km,
                toll_ranges or [],
                road_class_link_details or [],
            )
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
        self,
        geometry: list[list[float]],
        raw_ranges: list[dict[str, Any]],
        road_class_link_details: list[list],
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

        has_unpriced_event = any(
            self._unpriced_billing_events_in_range(
                projections,
                toll_range,
                road_class_link_details,
                [],
                set(),
            )
            for toll_range in ranges
        )

        used: list[tuple[StationProjection, float]] = []
        names: list[str] = []
        segments: list[TollSegmentQuote] = []
        total = 0.0
        for toll_range in ranges:
            for projection in self._open_stations_in_range(
                projections,
                toll_range,
                road_class_link_details,
            ):
                price = self._lookup_open(projection.station)
                if price is None:
                    continue
                if self._same_open_charge_already_used(
                    projection,
                    price,
                    used,
                ):
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

        if not segments and not has_unpriced_event:
            return None

        unresolved_indexes = (
            list(range(len(ranges)))
            if has_unpriced_event
            else []
        )
        plan = TollPlan(
            exact_cost=total,
            station_names=names,
            segments=segments,
            ranges=ranges,
            unresolved_indexes=unresolved_indexes,
            unresolved_km_by_range={
                index: 0.0
                for index in unresolved_indexes
            },
            unresolved_event_ranges=set(unresolved_indexes),
            ignored_noise_indexes=set(),
        )
        return self._finalize_toll_plan(plan)

    def _closed_match_from_pair(
        self,
        range_index: int,
        toll_range: TollRange,
        pair: tuple[ClosedPrice, StationProjection, StationProjection] | None,
    ) -> ClosedMatch | None:
        if pair is None:
            return None
        record, entry, exit_ = pair
        if exit_.route_km <= entry.route_km + 0.05:
            return None

        physical_coverage = max(
            0.0,
            min(exit_.route_km, toll_range.end_km)
            - max(entry.route_km, toll_range.start_km),
        )
        start_gap = max(0.0, entry.route_km - toll_range.start_km)
        end_gap = max(0.0, toll_range.end_km - exit_.route_km)

        matrix_consistent = (
            record.distance_km is not None
            and abs(record.distance_km - toll_range.distance_km)
            <= max(30.0, toll_range.distance_km * 0.18)
        )
        matrix_resolves_range = (
            matrix_consistent
            and physical_coverage
            >= max(5.0, toll_range.distance_km * 0.60)
        )

        boundary_padding = min(start_gap, 25.0) + min(end_gap, 25.0)
        boundary_coverage = min(
            toll_range.distance_km,
            physical_coverage + boundary_padding,
        )
        boundary_residual = max(
            0.0,
            toll_range.distance_km - boundary_coverage,
        )
        # A matrix with an official distance can explain generous OSM boundary
        # padding. Without a matrix distance, only a small combined padding is
        # credible; otherwise a short sub-matrix could hide a later tariff group.
        distance_less_padding_budget = min(
            12.0,
            max(3.0, toll_range.distance_km * 0.18),
        )
        boundary_resolves_range = (
            start_gap <= 25.0
            and end_gap <= 25.0
            and boundary_residual <= self.MINOR_RESIDUAL_KM
            and boundary_residual * self.FALLBACK_EUR_PER_KM
            < self.MINOR_RESIDUAL_EUR
            and (
                record.distance_km is not None
                or start_gap + end_gap <= distance_less_padding_budget
            )
        )

        full_range = matrix_resolves_range or boundary_resolves_range
        if full_range:
            coverage = toll_range.distance_km
        else:
            credible_matrix_coverage = (
                record.distance_km
                if matrix_consistent and record.distance_km is not None
                else physical_coverage
            )
            coverage = min(
                toll_range.distance_km,
                max(physical_coverage, credible_matrix_coverage),
            )

        return ClosedMatch(
            range_index=range_index,
            toll_range=toll_range,
            record=record,
            entry=entry,
            exit=exit_,
            coverage_km=coverage,
            full_range=full_range,
        )

    # ROUTECO_V034_LONG_MATRIX_PRIORITY_FIX
    def _route_wide_candidates(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
    ) -> list[tuple[ClosedPrice, StationProjection, StationProjection]]:
        """Return every credible long closed-system interpretation.

        Returning only the single lowest geometric score is not sufficient:
        a short local sub-matrix can lie closer to the polyline than the official
        tariff group that actually covers the full tolled range.
        """
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
        target_km = max(0.0, toll_range.distance_km)
        found: dict[
            tuple[str, str, int, int, int],
            tuple[float, ClosedPrice, StationProjection, StationProjection],
        ] = {}

        for entry in close:
            for exit_ in close:
                span_km = exit_.route_km - entry.route_km
                if span_km <= 5.0:
                    continue

                record = self._lookup_closed(entry.station, exit_.station)
                if record is None:
                    continue

                if target_km > 40.0 and span_km < target_km * 0.55:
                    continue
                if span_km > target_km + max(45.0, target_km * 0.28):
                    continue
                if entry.route_km > toll_range.start_km + 90.0:
                    continue
                if exit_.route_km < toll_range.end_km - 90.0:
                    continue

                tariff_mismatch = 0.0
                if record.distance_km is not None:
                    tariff_mismatch = abs(record.distance_km - target_km)
                    if tariff_mismatch > max(30.0, target_km * 0.18):
                        continue

                boundary_gap = (
                    abs(entry.route_km - toll_range.start_km)
                    + abs(exit_.route_km - toll_range.end_km)
                )
                target_mismatch = abs(span_km - target_km)
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
                key = (
                    physical_label_key(entry.station.display_name),
                    physical_label_key(exit_.station.display_name),
                    round(entry.route_km * 10),
                    round(exit_.route_km * 10),
                    round(record.price * 100),
                )
                current = found.get(key)
                if current is None or score < current[0]:
                    found[key] = (score, record, entry, exit_)

        ordered = sorted(
            found.values(),
            key=lambda item: (
                abs((item[3].route_km - item[2].route_km) - target_km),
                item[0],
            ),
        )
        return [
            (record, entry, exit_)
            for _, record, entry, exit_ in ordered[:64]
        ]

    # ROUTECO_V034_BILLING_SEMANTICS_FIX
    def _normalize_closed_proposals(
        self,
        proposals: list[ClosedMatch],
        projections: list[StationProjection],
        toll_range: TollRange,
    ) -> list[ClosedMatch]:
        # ROUTECO_V034_BILLING_SEMANTICS_FIX
        # Keep maximal exact journeys and absorb only boundary-only OSM padding.
        if not proposals:
            return []

        for item in proposals:
            containers = [
                other
                for other in proposals
                if other is not item
                and other.range_index == item.range_index
                and other.span_start_km <= item.span_start_km + 0.5
                and other.span_end_km >= item.span_end_km - 0.5
                and other.span_km >= item.span_km + 1.0
            ]
            if containers and item.full_range:
                item.full_range = False
                item.coverage_km = max(
                    0.0,
                    min(item.span_end_km, toll_range.end_km)
                    - max(item.span_start_km, toll_range.start_km),
                )

        for item in proposals:
            if item.full_range:
                continue
            if any(
                other is not item
                and other.range_index == item.range_index
                and other.span_start_km <= item.span_start_km + 0.5
                and other.span_end_km >= item.span_end_km - 0.5
                and other.span_km >= item.span_km + 1.0
                for other in proposals
            ):
                continue

            start_gap = max(0.0, item.span_start_km - toll_range.start_km)
            end_gap = max(0.0, toll_range.end_km - item.span_end_km)
            if start_gap > 25.0 or end_gap > 25.0:
                continue

            blocked = False
            for projection in projections:
                if not (
                    toll_range.start_km - 1.5
                    <= projection.route_km
                    <= toll_range.end_km + 1.5
                ):
                    continue
                if (
                    item.span_start_km - 0.5
                    <= projection.route_km
                    <= item.span_end_km + 0.5
                ):
                    continue
                station = projection.station
                if not station.is_mainline_barrier:
                    continue
                if projection.lateral_km > 0.12:
                    continue
                if self._lookup_open(station) is None:
                    blocked = True
                    break

            if blocked:
                continue

            item.full_range = True
            item.coverage_km = toll_range.distance_km

        return proposals

    def _unpriced_billing_events_in_range(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        road_class_link_details: list[list],
        closed_spans: list[tuple[float, float]],
        used_station_keys: set[str],
    ) -> list[StationProjection]:
        # Return physical billing events crossed without a local exact tariff.
        unresolved: list[StationProjection] = []
        seen: set[str] = set()

        for projection in projections:
            if not (
                toll_range.start_km - 1.5
                <= projection.route_km
                <= toll_range.end_km + 1.5
            ):
                continue
            if any(
                start_km - 0.5 <= projection.route_km <= end_km + 0.5
                for start_km, end_km in closed_spans
            ):
                continue

            station = projection.station
            keys = self._station_identity_keys(station)
            if keys & used_station_keys:
                continue

            is_event = False
            if station.system_type == "open":
                ramp_station = self._is_open_ramp_station(station)
                lateral_limit = (
                    0.05
                    if ramp_station
                    else 0.12
                    if station.is_mainline_barrier
                    else 0.06
                )
                if projection.lateral_km > lateral_limit:
                    continue
                if ramp_station:
                    boundary_gap = min(
                        abs(projection.route_km - toll_range.start_km),
                        abs(projection.route_km - toll_range.end_km),
                    )
                    if boundary_gap > 4.0:
                        continue
                    is_link = self._road_class_link_at_projection(
                        projection,
                        road_class_link_details,
                    )
                    if is_link is False:
                        continue
                is_event = True
            elif station.is_mainline_barrier and projection.lateral_km <= 0.12:
                is_event = True

            if not is_event or self._lookup_open(station) is not None:
                continue

            identity = sorted(keys)[0] if keys else (
                f"{round(station.lat, 4)}:{round(station.lon, 4)}"
            )
            if identity in seen:
                continue
            seen.add(identity)
            unresolved.append(projection)

        return unresolved

    def _closed_proposals_for_range(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        range_index: int,
    ) -> list[ClosedMatch]:
        proposals: list[ClosedMatch] = []

        if toll_range.distance_km > 0.5:
            boundary_match = self._closed_match_from_pair(
                range_index,
                toll_range,
                self._best_closed_pair(projections, toll_range),
            )
            if boundary_match is not None:
                proposals.append(boundary_match)

        if toll_range.distance_km >= 20.0:
            route_wide_pairs: list[
                tuple[
                    ClosedPrice,
                    StationProjection,
                    StationProjection,
                ]
            ] = []
            canonical = self._route_wide_pair(
                projections,
                toll_range,
                toll_range.distance_km,
            )
            if canonical is not None:
                route_wide_pairs.append(canonical)

            route_wide_pairs.extend(
                self._route_wide_candidates(
                    projections,
                    toll_range,
                )
            )
            for pair in route_wide_pairs:
                route_wide_match = self._closed_match_from_pair(
                    range_index,
                    toll_range,
                    pair,
                )
                if route_wide_match is not None:
                    proposals.append(route_wide_match)

        chain, chain_is_complete = self._best_closed_chain(
            projections,
            toll_range,
            range_index,
        )
        if chain:
            if chain_is_complete:
                missing = max(
                    0.0,
                    toll_range.distance_km
                    - sum(
                        max(0.0, item.coverage_km)
                        for item in chain
                    ),
                )
                if missing > 0.0:
                    start_padding = min(
                        missing,
                        max(
                            0.0,
                            chain[0].span_start_km
                            - toll_range.start_km,
                        ),
                        25.0,
                    )
                    chain[0].coverage_km += start_padding
                    missing -= start_padding
                if missing > 0.0:
                    end_padding = min(
                        missing,
                        max(
                            0.0,
                            toll_range.end_km
                            - chain[-1].span_end_km,
                        ),
                        25.0,
                    )
                    chain[-1].coverage_km += end_padding
                    missing -= end_padding
                if missing > 0.0 and len(chain) == 1:
                    chain[0].coverage_km = min(
                        toll_range.distance_km,
                        chain[0].coverage_km + missing,
                    )
            proposals.extend(chain)

        deduped = self._dedupe_closed_proposals(proposals)
        return self._normalize_closed_proposals(
            deduped,
            projections,
            toll_range,
        )

    def _dedupe_closed_proposals(
        self,
        proposals: list[ClosedMatch],
    ) -> list[ClosedMatch]:
        unique: dict[
            tuple[int, str, str, int, int, int],
            ClosedMatch,
        ] = {}
        for item in proposals:
            key = (
                item.range_index,
                physical_label_key(item.entry.station.display_name),
                physical_label_key(item.exit.station.display_name),
                round(item.entry.route_km * 10),
                round(item.exit.route_km * 10),
                round(item.record.price * 100),
            )
            current = unique.get(key)
            current_score = (
                int(current.full_range),
                current.coverage_km,
                current.span_km,
                -(current.entry.lateral_km + current.exit.lateral_km),
            ) if current is not None else None
            item_score = (
                int(item.full_range),
                item.coverage_km,
                item.span_km,
                -(item.entry.lateral_km + item.exit.lateral_km),
            )
            if current_score is None or item_score > current_score:
                unique[key] = item
        return list(unique.values())

    def _quote_from_ranges(
        self,
        geometry: list[list[float]],
        tolled_km: float,
        raw_ranges: list[dict[str, Any]],
        road_class_link_details: list[list],
    ) -> TollQuote | None:
        projections, cumulative = self._project_stations(geometry)

        ranges = self._prepare_ranges(geometry, cumulative, raw_ranges)
        if not ranges:
            route_wide = self._route_wide_pair(projections, None, tolled_km)
            if route_wide is None:
                return None
            record, entry, exit_ = route_wide
            return self._closed_quote(record, entry, exit_)

        # Every exact interpretation is generated before selection. A long matrix,
        # a boundary pair and a multi-matrix chain therefore compete on coverage.
        proposals: list[ClosedMatch] = []
        for range_index, toll_range in enumerate(ranges):
            proposals.extend(
                self._closed_proposals_for_range(
                    projections,
                    toll_range,
                    range_index,
                )
            )

        accepted = self._select_closed_matches(proposals)
        resolved_ranges: set[int] = set()
        range_covered_km: dict[int, float] = {}
        used_station_keys: set[str] = set()
        used_open: list[tuple[StationProjection, float]] = []
        unresolved_event_ranges: set[int] = set()
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
            # Exact open/free-flow events remain chargeable even when a
            # closed matrix has already resolved the surrounding OSM range.
            open_matches = self._open_stations_in_range(
                projections,
                toll_range,
                road_class_link_details,
            )
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

            unpriced_events = self._unpriced_billing_events_in_range(
                projections,
                toll_range,
                road_class_link_details,
                closed_spans,
                used_station_keys,
            )
            if unpriced_events:
                unresolved_event_ranges.add(range_index)
                resolved_ranges.discard(range_index)

            if not accepted_open:
                continue

            # A pure open-system range is priced by the crossed gantry itself.
            # When closed matrix spans already cover part of the same OSM range,
            # the gantry is added but the remaining distance still has to be
            # explained instead of declaring the entire range resolved.
            if range_covered_km.get(range_index, 0.0) <= 0.05:
                # In an open system, the crossed gantry is the tariff event: its
                # official fixed charge prices the range even when OSM marks a long
                # approach. The station has already passed a very tight on-route
                # projection test and an exact local tariff lookup.
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

        # Isolated OSM toll tags are not billing events. Resolve them as zero only
        # when no mainline barrier or exact open charge is physically crossed.
        exact_boundaries = [
            value
            for start_km, end_km in closed_spans
            for value in (start_km, end_km)
        ]
        exact_boundaries.extend(
            projection.route_km
            for projection, _ in used_open
        )
        ignored_noise_indexes: set[int] = set()
        for range_index, toll_range in enumerate(ranges):
            if range_index in resolved_ranges:
                continue
            if range_covered_km.get(range_index, 0.0) > 0.05:
                continue
            if self._is_non_billable_osm_fragment(
                projections,
                toll_range,
                road_class_link_details,
                exact_boundaries,
            ):
                ignored_noise_indexes.add(range_index)
                resolved_ranges.add(range_index)

        # Une chaîne de plusieurs voyages fermés se prouve par ses événements :
        # chaque matrice possède une entrée et une sortie. La portion comprise
        # entre une sortie et l'entrée suivante est donc hors facturation, même
        # si GraphHopper l'a incluse dans une grande plage toll=yes.
        accepted_by_range: dict[int, list[ClosedMatch]] = {}
        for match in accepted:
            accepted_by_range.setdefault(
                match.range_index,
                [],
            ).append(match)

        for range_index, matches in accepted_by_range.items():
            if range_index in unresolved_event_ranges:
                continue
            if self._closed_chain_has_complete_event_topology(matches):
                resolved_ranges.add(range_index)

        unresolved_indexes = [
            index
            for index in range(len(ranges))
            if index not in resolved_ranges
        ]
        unresolved_km_by_range = {
            index: max(
                0.0,
                ranges[index].distance_km
                - range_covered_km.get(index, 0.0),
            )
            for index in unresolved_indexes
        }
        plan = TollPlan(
            exact_cost=total,
            station_names=station_names,
            segments=segments,
            ranges=ranges,
            unresolved_indexes=unresolved_indexes,
            unresolved_km_by_range=unresolved_km_by_range,
            unresolved_event_ranges=unresolved_event_ranges,
            ignored_noise_indexes=ignored_noise_indexes,
        )

        if plan.is_complete:
            return self._finalize_toll_plan(plan)

        if plan.unresolved_indexes and not plan.has_unresolved_events:
            combined = self._combined_range_if_contiguous(
                ranges,
                tolled_km,
            )
            if combined is not None:
                route_wide = self._route_wide_pair(
                    projections,
                    combined,
                    tolled_km,
                )
                route_match = self._closed_match_from_pair(
                    -1,
                    combined,
                    route_wide,
                )
                if (
                    route_match is not None
                    and self._route_wide_match_confirms_same_closed_journey(
                        route_match,
                        plan,
                    )
                ):
                    return self._closed_quote(
                        route_match.record,
                        route_match.entry,
                        route_match.exit,
                    )

        return self._finalize_toll_plan(plan)

    # ROUTECO_V034_TOLL_PLAN_PROOF
    def _finalize_toll_plan(self, plan: TollPlan) -> TollQuote | None:
        # Seule cette méthode produit un TollQuote de niveau route exact.
        segments = sorted(
            list(plan.segments),
            key=lambda item: (
                float("inf")
                if item.route_start_km is None
                else item.route_start_km,
                float("inf")
                if item.route_end_km is None
                else item.route_end_km,
            ),
        )
        station_names = self._dedupe_names(plan.station_names)

        if plan.is_complete:
            if segments and self._segments_are_integral(segments):
                details = " → ".join(station_names)
                message = "Tarif exact classe 1 issu des matrices locales."
                if details:
                    message = f"Tarif exact classe 1 : {details}."
                if plan.ignored_noise_indexes:
                    message = (
                        message.rstrip(".")
                        + " (fragments OSM sans événement tarifaire ignorés)."
                    )
                return TollQuote(
                    round(plan.exact_cost, 2),
                    "exact",
                    station_names,
                    message,
                    segments=segments,
                )

            if plan.ignored_noise_indexes and not segments:
                return TollQuote(
                    0.0,
                    "none",
                    [],
                    "Fragments OSM isolés ignorés : "
                    "aucun événement de paiement traversé.",
                )
            return None

        estimated_part = round(
            plan.unresolved_km * self.FALLBACK_EUR_PER_KM,
            2,
        )

        if (
            plan.exact_cost <= 0
            and not plan.ignored_noise_indexes
            and not plan.has_unresolved_events
            and estimated_part <= 0
        ):
            return None

        if estimated_part > 0:
            segments.append(
                TollSegmentQuote(
                    entry=None,
                    exit=None,
                    operator="",
                    cost=estimated_part,
                    distance_km=round(plan.unresolved_km, 1),
                    confidence="estimated",
                )
            )

        message = (
            "Tarif partiellement apparié ; "
            "le solde réel reste sans tarif officiel."
            if plan.exact_cost > 0
            else "Tronçon payant réel détecté, mais aucun tarif officiel "
            "fiable n'est associé."
        )
        if plan.ignored_noise_indexes:
            message += (
                " Les fragments OSM sans événement tarifaire ont été exclus."
            )

        return TollQuote(
            round(plan.exact_cost + estimated_part, 2),
            "estimated",
            station_names,
            message,
            segments=segments,
        )

    def _closed_chain_has_complete_event_topology(
        self,
        matches: list[ClosedMatch],
    ) -> bool:
        # Deux voyages fermés ou plus peuvent former un plan complet lorsque
        # chaque trajet possède une entrée et une sortie officielles, dans le
        # bon ordre et sans chevauchement.
        #
        # Le routage actuel ne fournit toutefois pas encore une preuve positive
        # du statut gratuit de chaque intervalle sortie -> entrée suivante.
        # On conserve donc un budget transitoire, nommé explicitement et séparé
        # des résidus OSM et des marges de recherche de 25 km. Au-delà de ce
        # budget, le connecteur reste non prouvé et le plan doit être estimé.
        if len(matches) < 2:
            return False

        ordered = sorted(matches, key=lambda item: item.span_start_km)
        previous_end: float | None = None
        used_stations: set[tuple[str, int]] = set()

        for match in ordered:
            if match.span_end_km <= match.span_start_km + 0.05:
                return False

            entry_label = physical_label_key(
                match.entry.station.display_name
            )
            exit_label = physical_label_key(
                match.exit.station.display_name
            )
            if not entry_label or not exit_label:
                return False

            entry_key = (
                entry_label,
                round(match.span_start_km * 10),
            )
            exit_key = (
                exit_label,
                round(match.span_end_km * 10),
            )
            if entry_key in used_stations or exit_key in used_stations:
                return False
            used_stations.update((entry_key, exit_key))

            if previous_end is not None:
                connector_km = match.span_start_km - previous_end
                if connector_km < -1.0:
                    return False
                if (
                    connector_km
                    > self.MAX_UNVERIFIED_CLOSED_CONNECTOR_KM
                ):
                    return False

            previous_end = (
                match.span_end_km
                if previous_end is None
                else max(previous_end, match.span_end_km)
            )

        return True

    @staticmethod
    def _route_wide_match_confirms_same_closed_journey(
        match: ClosedMatch,
        plan: TollPlan,
    ) -> bool:
        # Une matrice globale ne remplace un plan partiel que lorsqu'elle
        # confirme exactement le même voyage fermé déjà identifié. La distance
        # OSM et le montant ne constituent jamais la preuve.
        if plan.has_unresolved_events:
            return False

        exact_segments = [
            segment
            for segment in plan.segments
            if segment.confidence == "exact"
        ]
        if len(exact_segments) != len(plan.segments):
            return False
        if len(exact_segments) != 1:
            # Une matrice unique ne doit pas absorber plusieurs voyages fermés.
            return False

        segment = exact_segments[0]
        if segment.exit is None:
            # Un portique ouvert ne peut pas être absorbé par une matrice
            # fermée entrée-sortie.
            return False
        if (
            segment.route_start_km is None
            or segment.route_end_km is None
        ):
            return False

        entry_label = physical_label_key(segment.entry or "")
        exit_label = physical_label_key(segment.exit or "")
        match_entry_label = physical_label_key(
            match.entry.station.display_name
        )
        match_exit_label = physical_label_key(
            match.exit.station.display_name
        )
        if not entry_label or entry_label != match_entry_label:
            return False
        if not exit_label or exit_label != match_exit_label:
            return False

        if abs(segment.route_start_km - match.span_start_km) > 1.0:
            return False
        if abs(segment.route_end_km - match.span_end_km) > 1.0:
            return False

        segment_operator = (segment.operator or "").upper()
        matrix_operator = (match.record.operator or "").upper()
        if (
            segment_operator
            and matrix_operator
            and segment_operator != "UNKNOWN"
            and matrix_operator != "UNKNOWN"
            and segment_operator != matrix_operator
        ):
            return False

        return True

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
        # Gaps before the first physical plaza and after the last one are
        # ordinary OSM boundary padding. Only internal holes can represent an
        # unpriced toll. Keep those internal holes at the strict 5 km / 1 euro
        # threshold introduced by the reliability patch.
        boundary_padding = min(start_gap, 25.0) + min(end_gap, 25.0)
        unexplained_after_boundaries = max(
            0.0, toll_range.distance_km - covered - boundary_padding
        )
        estimated_unexplained = (
            unexplained_after_boundaries * self.FALLBACK_EUR_PER_KM
        )
        complete = (
            start_gap <= 25.0
            and end_gap <= 25.0
            and all(gap <= self.MINOR_RESIDUAL_KM for gap in internal_gaps)
            and unexplained_after_boundaries <= self.MINOR_RESIDUAL_KM
            and estimated_unexplained < self.MINOR_RESIDUAL_EUR
        )
        return selected, complete

    def _closed_quote(
        self,
        record: ClosedPrice,
        entry: StationProjection,
        exit_: StationProjection,
    ) -> TollQuote:
        names = [
            entry.station.display_name,
            exit_.station.display_name,
        ]
        segment = TollSegmentQuote(
            entry=names[0],
            exit=names[1],
            operator=record.operator,
            cost=round(record.price, 2),
            distance_km=record.distance_km,
            confidence="exact",
            route_start_km=round(entry.route_km, 1),
            route_end_km=round(exit_.route_km, 1),
        )
        quote = self._finalize_toll_plan(
            TollPlan(
                exact_cost=record.price,
                station_names=names,
                segments=[segment],
                ranges=[],
                unresolved_indexes=[],
                unresolved_km_by_range={},
                unresolved_event_ranges=set(),
                ignored_noise_indexes=set(),
            )
        )
        if quote is None:
            raise RuntimeError(
                "Une matrice fermée valide n'a pas produit de TollQuote."
            )
        return quote

    # ROUTECO_V034_MATRIX_SELECTION_HOTFIX
    def _select_closed_matches(
        self,
        proposals: list[ClosedMatch],
    ) -> list[ClosedMatch]:
        candidates = [
            item
            for item in proposals
            if item.span_end_km > item.span_start_km + 0.05
            and max(item.coverage_km, item.span_km) > 0.05
        ]
        if not candidates:
            return []

        def potential(item: ClosedMatch) -> float:
            return min(
                item.toll_range.distance_km,
                item.toll_range.distance_km
                if item.full_range
                else max(item.coverage_km, item.span_km),
            )

        def item_mainline_score(item: ClosedMatch) -> int:
            return (
                int(item.entry.station.is_mainline_barrier)
                + int(item.exit.station.is_mainline_barrier)
            )

        candidates.sort(
            key=lambda item: (
                -potential(item),
                -int(item.full_range),
                abs(
                    item.span_km
                    - item.toll_range.distance_km
                ),
                -item_mainline_score(item),
                -int(item.record.distance_km is not None),
                item.entry.lateral_km
                + item.exit.lateral_km,
                item.span_start_km,
            )
        )

        if len(candidates) > 22:
            accepted: list[ClosedMatch] = []
            used_keys: set[str] = set()
            covered: dict[int, float] = {}
            for item in candidates:
                keys = (
                    self._station_identity_keys(item.entry.station)
                    | self._station_identity_keys(item.exit.station)
                )
                if keys & used_keys:
                    continue
                if any(
                    self._closed_spans_conflict(item, current)
                    for current in accepted
                ):
                    continue
                current = covered.get(item.range_index, 0.0)
                new = min(
                    item.toll_range.distance_km,
                    current + potential(item),
                )
                if new <= current + 0.05:
                    continue
                accepted.append(item)
                used_keys.update(keys)
                covered[item.range_index] = new
            accepted.sort(key=lambda item: item.span_start_km)
            return accepted

        suffix = [0.0] * (len(candidates) + 1)
        for index in range(len(candidates) - 1, -1, -1):
            suffix[index] = (
                suffix[index + 1]
                + potential(candidates[index])
            )

        range_lengths = {
            item.range_index: item.toll_range.distance_km
            for item in candidates
        }
        best_key = (
            -1.0,
            -1,
            -1e12,
            -1,
            -1,
            -10_000,
            -1e12,
        )
        best_selection: list[ClosedMatch] = []

        def selection_quality(
            accepted: list[ClosedMatch],
            covered: dict[int, float],
            exact_km: float,
            lateral_sum: float,
        ) -> tuple[
            float,
            int,
            float,
            int,
            int,
            int,
            float,
        ]:
            full_ranges = sum(
                covered.get(range_index, 0.0)
                >= distance - 0.05
                for range_index, distance
                in range_lengths.items()
            )

            grouped: dict[int, list[ClosedMatch]] = {}
            for item in accepted:
                grouped.setdefault(
                    item.range_index,
                    [],
                ).append(item)

            span_fit = 0.0
            mainline_boundaries = 0
            matrix_distance_evidence = 0
            for range_index, items in grouped.items():
                first = min(
                    items,
                    key=lambda item: item.span_start_km,
                )
                last = max(
                    items,
                    key=lambda item: item.span_end_km,
                )
                envelope = max(
                    0.0,
                    last.span_end_km
                    - first.span_start_km,
                )
                span_fit -= abs(
                    envelope
                    - range_lengths[range_index]
                )
                mainline_boundaries += int(
                    first.entry.station.is_mainline_barrier
                )
                mainline_boundaries += int(
                    last.exit.station.is_mainline_barrier
                )
                matrix_distance_evidence += sum(
                    item.record.distance_km is not None
                    for item in items
                )

            return (
                round(exact_km, 6),
                full_ranges,
                round(span_fit, 6),
                mainline_boundaries,
                matrix_distance_evidence,
                -len(accepted),
                -lateral_sum,
            )

        def visit(
            index: int,
            accepted: list[ClosedMatch],
            used_keys: set[str],
            covered: dict[int, float],
            exact_km: float,
            lateral_sum: float,
        ) -> None:
            nonlocal best_key, best_selection

            if (
                exact_km
                + suffix[index]
                + 0.01
                < best_key[0]
            ):
                return

            if index >= len(candidates):
                key = selection_quality(
                    accepted,
                    covered,
                    exact_km,
                    lateral_sum,
                )
                if key > best_key:
                    best_key = key
                    best_selection = list(accepted)
                return

            item = candidates[index]
            visit(
                index + 1,
                accepted,
                used_keys,
                covered,
                exact_km,
                lateral_sum,
            )

            keys = (
                self._station_identity_keys(item.entry.station)
                | self._station_identity_keys(item.exit.station)
            )
            if keys & used_keys:
                return
            if any(
                self._closed_spans_conflict(item, current)
                for current in accepted
            ):
                return

            current_coverage = covered.get(
                item.range_index,
                0.0,
            )
            new_coverage = min(
                item.toll_range.distance_km,
                current_coverage + potential(item),
            )
            increment = new_coverage - current_coverage
            if increment <= 0.05:
                return

            accepted.append(item)
            next_used = set(used_keys)
            next_used.update(keys)
            next_covered = dict(covered)
            next_covered[item.range_index] = new_coverage
            visit(
                index + 1,
                accepted,
                next_used,
                next_covered,
                exact_km + increment,
                lateral_sum
                + item.entry.lateral_km
                + item.exit.lateral_km,
            )
            accepted.pop()

        visit(
            0,
            [],
            set(),
            {},
            0.0,
            0.0,
        )
        best_selection.sort(
            key=lambda item: item.span_start_km
        )
        return best_selection

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


    def _range_has_physical_billing_event(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        road_class_link_details: list[list],
    ) -> bool:
        for projection in projections:
            if not (
                toll_range.start_km - 1.5
                <= projection.route_km
                <= toll_range.end_km + 1.5
            ):
                continue
            station = projection.station
            if station.system_type == "open":
                ramp_station = self._is_open_ramp_station(station)
                lateral_limit = (
                    0.05
                    if ramp_station
                    else 0.12
                    if station.is_mainline_barrier
                    else 0.06
                )
                if projection.lateral_km > lateral_limit:
                    continue
                if ramp_station:
                    boundary_gap = min(
                        abs(projection.route_km - toll_range.start_km),
                        abs(projection.route_km - toll_range.end_km),
                    )
                    if boundary_gap > 4.0:
                        continue
                    is_link = self._road_class_link_at_projection(
                        projection,
                        road_class_link_details,
                    )
                    if is_link is False:
                        continue
                # Physical traversal is evidence even when the local tariff
                # is missing. It must never be discarded as OSM noise.
                return True
            if station.is_mainline_barrier and projection.lateral_km <= 0.12:
                return True
        return False

    def _is_non_billable_osm_fragment(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        road_class_link_details: list[list],
        exact_boundaries: list[float],
    ) -> bool:
        if self._range_has_physical_billing_event(
            projections,
            toll_range,
            road_class_link_details,
        ):
            return False

        if toll_range.distance_km <= self.OSM_NOISE_RANGE_KM:
            return True

        if (
            toll_range.distance_km <= self.OSM_BOUNDARY_FRAGMENT_KM
            and exact_boundaries
        ):
            boundary_gap = min(
                min(abs(toll_range.start_km - boundary) for boundary in exact_boundaries),
                min(abs(toll_range.end_km - boundary) for boundary in exact_boundaries),
            )
            return boundary_gap <= self.OSM_BOUNDARY_EVENT_GAP_KM

        return False

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
            if not merged:
                merged.append(item)
                continue

            previous = merged[-1]
            physical_gap = max(0.0, item.start_km - previous.end_km)
            overlaps = item.start_index <= previous.end_index
            if not overlaps and physical_gap > 0.75:
                merged.append(item)
                continue

            previous_end_index = previous.end_index
            previous.end_index = max(previous.end_index, item.end_index)
            previous.end_km = max(previous.end_km, item.end_km)
            if item.start_index <= previous_end_index:
                previous.distance_km = max(
                    previous.distance_km,
                    item.distance_km,
                    previous.end_km - previous.start_km,
                )
            else:
                previous.distance_km += item.distance_km
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
                # A fixed longitude margin loses valid stations in northern France,
                # where one degree of longitude is shorter than at the equator.
                mean_lat = (start[1] + end[1]) / 2.0
                margin_lat = 2.7 / 111.32
                margin_lon = 2.7 / (
                    111.32 * max(0.20, abs(math.cos(math.radians(mean_lat))))
                )
                if (
                    station.lon < min(start[0], end[0]) - margin_lon
                    or station.lon > max(start[0], end[0]) + margin_lon
                ):
                    continue
                if (
                    station.lat < min(start[1], end[1]) - margin_lat
                    or station.lat > max(start[1], end[1]) + margin_lat
                ):
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
                        if mismatch > allowed:
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

    @staticmethod
    def _is_open_ramp_station(station: TollStation) -> bool:
        # A fixed open tariff can be joined to a station originally classified
        # as a closed interchange. That physical type is stronger evidence than
        # the label: a locality name may not contain "sortie" even though the
        # tariff applies only when taking the branch.
        if station.physical_type == "closed" and not station.is_mainline_barrier:
            return True

        # Keep label detection for datasets that directly declare open stations
        # but encode the direction or branch in their name.
        raw = f"{station.name} {station.osm_name}"
        text = unicodedata.normalize("NFKD", raw)
        text = "".join(char for char in text if not unicodedata.combining(char))
        text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
        return bool(
            re.search(
                r"\b(?:entree|sortie|bretelle|diffuseur|echangeur|exit)\b"
                r"|\bfl\s*e\b",
                text,
            )
        )

    @staticmethod
    def _road_class_link_at_projection(
        projection: StationProjection,
        details: list[list] | None,
    ) -> bool | None:
        # GraphHopper path details use point-index intervals [from, to, value].
        # StationProjection.segment_index identifies the interval ending at that
        # point, hence the -1 conversion below.
        if not details:
            return None
        segment_start = max(0, projection.segment_index - 1)
        for detail in details:
            if len(detail) != 3:
                continue
            try:
                start = int(detail[0])
                end = int(detail[1])
            except (TypeError, ValueError):
                continue
            if not (start <= segment_start < end):
                continue
            value = detail[2]
            if isinstance(value, bool):
                return value
            if value is None:
                return None
            normalized = str(value).strip().casefold()
            if normalized in {"true", "1", "yes"}:
                return True
            if normalized in {"false", "0", "no"}:
                return False
            return None
        return None

    def _open_stations_in_range(
        self,
        projections: list[StationProjection],
        toll_range: TollRange,
        road_class_link_details: list[list] | None = None,
    ) -> list[StationProjection]:
        matches: list[StationProjection] = []
        for projection in projections:
            station = projection.station
            if station.system_type != "open":
                continue

            ramp_station = self._is_open_ramp_station(station)
            if ramp_station:
                lateral_limit = 0.05
            elif station.is_mainline_barrier:
                lateral_limit = 0.12
            else:
                lateral_limit = 0.06
            if projection.lateral_km > lateral_limit:
                continue

            if not (
                toll_range.start_km - 1.5
                <= projection.route_km
                <= toll_range.end_km + 1.5
            ):
                continue

            # An interchange tariff is charged only when the tolled OSM range
            # starts or ends at that branch. Merely passing nearby is not enough.
            if ramp_station:
                boundary_gap = min(
                    abs(projection.route_km - toll_range.start_km),
                    abs(projection.route_km - toll_range.end_km),
                )
                if boundary_gap > 4.0:
                    continue

                # A tariff attached to an interchange is only crossed when the
                # route itself uses a link road. A toll-range boundary alone is
                # insufficient because OSM toll tags can start/end at a nearby
                # junction while the vehicle remains on the motorway.
                is_link = self._road_class_link_at_projection(
                    projection,
                    road_class_link_details,
                )
                if is_link is False:
                    continue

            if self._lookup_open(station) is None:
                continue
            matches.append(projection)
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
                if target_km > 40.0 and span_km < target_km * 0.72:
                    continue
                if target_km and span_km > target_km + max(45.0, target_km * 0.28):
                    continue

                boundary_gap = 0.0
                if toll_range is not None:
                    boundary_gap = abs(entry.route_km - toll_range.start_km) + abs(
                        exit_.route_km - toll_range.end_km
                    )
                    # The OSM toll tag can start/end well outside the plazas, but
                    # a candidate hundreds of kilometres away is not credible.
                    if entry.route_km > toll_range.start_km + 90.0:
                        continue
                    if exit_.route_km < toll_range.end_km - 90.0:
                        continue

                tariff_mismatch = 0.0
                if record.distance_km is not None:
                    # On sparse/simplified polylines, the projected station-to-station
                    # span can be much shorter than the driven motorway distance. For a
                    # route-wide match, compare the tariff matrix with GraphHopper's
                    # measured tolled range; keep the projected span for geometry/order.
                    comparison_km = target_km or span_km
                    tariff_mismatch = abs(record.distance_km - comparison_km)
                    allowed_tariff_mismatch = max(30.0, comparison_km * 0.18)
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
        preferred = set(operators)

        def collect(
            from_aliases: set[str],
            to_aliases: set[str],
        ) -> tuple[list[ClosedPrice], list[ClosedPrice]]:
            by_operator: list[ClosedPrice] = []
            for operator in operators:
                if not operator:
                    continue
                for from_alias in from_aliases:
                    for to_alias in to_aliases:
                        record = self.closed_prices.get(
                            (operator, from_alias, to_alias)
                        )
                        if record is not None:
                            by_operator.append(record)

            any_operator: list[ClosedPrice] = []
            for from_alias in from_aliases:
                for to_alias in to_aliases:
                    any_operator.extend(
                        self.closed_prices_any.get(
                            (from_alias, to_alias),
                            [],
                        )
                    )
            return by_operator, any_operator

        # An explicitly published fare in the travelled direction always wins.
        direct_operator, direct_any = collect(aliases_a, aliases_b)
        if direct_operator:
            return self._unique_record(
                direct_operator,
                preferred_operators=preferred,
            )
        if direct_any:
            return self._unique_record(
                direct_any,
                preferred_operators=preferred,
            )

        # Closed motorway matrices are commonly published as one triangular
        # table: A→B exists while B→A is omitted even though the class-1 fare is
        # the same. Use the reverse cell only as a fallback, never over an
        # explicit directional record. Ambiguous reverse records remain rejected.
        reverse_operator, reverse_any = collect(aliases_b, aliases_a)
        if reverse_operator:
            return self._unique_record(
                reverse_operator,
                preferred_operators=preferred,
            )
        if reverse_any:
            return self._unique_record(
                reverse_any,
                preferred_operators=preferred,
            )
        return None

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

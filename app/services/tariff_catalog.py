from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class TariffSource:
    source_id: str
    publisher: str
    title: str
    url: str
    effective_from: date | None
    effective_to: date | None
    retrieved_at: date | None


@dataclass(frozen=True, slots=True)
class OpenTariffRecord:
    operator: str
    name: str
    vehicle_class: int
    price: float
    effective_from: date | None
    effective_to: date | None
    season_start: tuple[int, int] | None
    season_end: tuple[int, int] | None
    source_id: str
    additive_to_closed: bool = False

    def applies_on(self, day: date) -> bool:
        return _applies_on(
            day,
            effective_from=self.effective_from,
            effective_to=self.effective_to,
            season_start=self.season_start,
            season_end=self.season_end,
        )


@dataclass(frozen=True, slots=True)
class ClosedTariffRecord:
    operator: str
    name_from: str
    name_to: str
    vehicle_class: int
    price: float
    distance_km: float | None
    effective_from: date | None
    effective_to: date | None
    season_start: tuple[int, int] | None
    season_end: tuple[int, int] | None
    source_id: str

    def applies_on(self, day: date) -> bool:
        return _applies_on(
            day,
            effective_from=self.effective_from,
            effective_to=self.effective_to,
            season_start=self.season_start,
            season_end=self.season_end,
        )


@dataclass(frozen=True, slots=True)
class PhysicalTariffAlias:
    operator: str
    physical_name: str
    tariff_name: str
    lat: float
    lon: float
    max_distance_km: float
    source_id: str


def _parse_date(value: object) -> date | None:
    text = str(value or "").strip()
    return date.fromisoformat(text) if text else None


def _parse_month_day(value: object) -> tuple[int, int] | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split("-")
    if len(parts) != 2:
        raise ValueError(f"Format saison invalide : {text!r}")
    month, day = int(parts[0]), int(parts[1])
    date(2000, month, day)
    return month, day


def _parse_optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    return float(text.replace(",", ".")) if text else None


def _parse_bool(value: object) -> bool:
    text = str(value or "").strip().casefold()
    if not text:
        return False
    if text in {"1", "true", "yes", "oui"}:
        return True
    if text in {"0", "false", "no", "non"}:
        return False
    raise ValueError(f"Booléen invalide : {value!r}")


def _applies_on(
    day: date,
    *,
    effective_from: date | None,
    effective_to: date | None,
    season_start: tuple[int, int] | None,
    season_end: tuple[int, int] | None,
) -> bool:
    if effective_from is not None and day < effective_from:
        return False
    if effective_to is not None and day > effective_to:
        return False
    if season_start is None and season_end is None:
        return True
    if season_start is None or season_end is None:
        return False

    current = (day.month, day.day)
    if season_start <= season_end:
        return season_start <= current <= season_end
    return current >= season_start or current <= season_end


def load_tariff_sources(
    paths: Iterable[Path],
) -> dict[str, TariffSource]:
    output: dict[str, TariffSource] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        items = payload.get("sources", [])
        if not isinstance(items, list):
            raise ValueError(f"Registre de sources invalide : {path}")
        for raw in items:
            source = TariffSource(
                source_id=str(raw["source_id"]).strip(),
                publisher=str(raw["publisher"]).strip(),
                title=str(raw["title"]).strip(),
                url=str(raw["url"]).strip(),
                effective_from=_parse_date(raw.get("effective_from")),
                effective_to=_parse_date(raw.get("effective_to")),
                retrieved_at=_parse_date(raw.get("retrieved_at")),
            )
            if not source.source_id or not source.url.startswith("https://"):
                raise ValueError(f"Source tarifaire invalide : {raw!r}")
            previous = output.get(source.source_id)
            if previous is not None and previous != source:
                raise ValueError(
                    f"Source tarifaire contradictoire : {source.source_id}"
                )
            output[source.source_id] = source
    return output


def load_open_tariff_records(
    paths: Iterable[Path],
    sources: dict[str, TariffSource],
) -> list[OpenTariffRecord]:
    output: list[OpenTariffRecord] = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    source_id = str(row.get("source_id") or "").strip()
                    if source_id not in sources:
                        raise ValueError(
                            f"source_id inconnu : {source_id or '<vide>'}"
                        )
                    record = OpenTariffRecord(
                        operator=str(row.get("operator") or "").strip().upper(),
                        name=str(row["name"]).strip(),
                        vehicle_class=int(row.get("vehicle_class") or 1),
                        price=float(str(row["price"]).replace(",", ".")),
                        effective_from=_parse_date(row.get("effective_from")),
                        effective_to=_parse_date(row.get("effective_to")),
                        season_start=_parse_month_day(row.get("season_start")),
                        season_end=_parse_month_day(row.get("season_end")),
                        source_id=source_id,
                        additive_to_closed=_parse_bool(
                            row.get("additive_to_closed")
                        ),
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path}:{line_number}: tarif daté invalide : {exc}"
                    ) from exc
                if record.price < 0:
                    raise ValueError(
                        f"{path}:{line_number}: prix négatif interdit"
                    )
                output.append(record)
    return output


def load_closed_tariff_records(
    paths: Iterable[Path],
    sources: dict[str, TariffSource],
) -> list[ClosedTariffRecord]:
    output: list[ClosedTariffRecord] = []
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    source_id = str(row.get("source_id") or "").strip()
                    if source_id not in sources:
                        raise ValueError(
                            f"source_id inconnu : {source_id or '<vide>'}"
                        )
                    record = ClosedTariffRecord(
                        operator=str(
                            row.get("operator") or ""
                        ).strip().upper(),
                        name_from=str(row["name_from"]).strip(),
                        name_to=str(row["name_to"]).strip(),
                        vehicle_class=int(row.get("vehicle_class") or 1),
                        price=float(
                            str(row["price"]).replace(",", ".")
                        ),
                        distance_km=_parse_optional_float(
                            row.get("distance")
                        ),
                        effective_from=_parse_date(
                            row.get("effective_from")
                        ),
                        effective_to=_parse_date(
                            row.get("effective_to")
                        ),
                        season_start=_parse_month_day(
                            row.get("season_start")
                        ),
                        season_end=_parse_month_day(
                            row.get("season_end")
                        ),
                        source_id=source_id,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path}:{line_number}: matrice datée invalide : {exc}"
                    ) from exc
                if (
                    not record.operator
                    or not record.name_from
                    or not record.name_to
                    or record.price < 0
                    or (
                        record.distance_km is not None
                        and record.distance_km < 0
                    )
                ):
                    raise ValueError(
                        f"{path}:{line_number}: matrice datée invalide"
                    )
                output.append(record)
    return output


def load_physical_tariff_aliases(
    paths: Iterable[Path],
    sources: dict[str, TariffSource],
) -> list[PhysicalTariffAlias]:
    output: list[PhysicalTariffAlias] = []
    seen: dict[
        tuple[str, str, int, int],
        PhysicalTariffAlias,
    ] = {}
    for path in paths:
        with path.open(encoding="utf-8", newline="") as handle:
            for line_number, row in enumerate(csv.DictReader(handle), start=2):
                try:
                    source_id = str(row.get("source_id") or "").strip()
                    if source_id not in sources:
                        raise ValueError(
                            f"source_id inconnu : {source_id or '<vide>'}"
                        )
                    alias = PhysicalTariffAlias(
                        operator=str(
                            row.get("operator") or ""
                        ).strip().upper(),
                        physical_name=str(
                            row["physical_name"]
                        ).strip(),
                        tariff_name=str(row["tariff_name"]).strip(),
                        lat=float(row["lat"]),
                        lon=float(row["lon"]),
                        max_distance_km=float(
                            str(
                                row.get("max_distance_km") or "1.0"
                            ).replace(",", ".")
                        ),
                        source_id=source_id,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError(
                        f"{path}:{line_number}: alias tarifaire invalide : {exc}"
                    ) from exc
                if (
                    not alias.operator
                    or not alias.physical_name
                    or not alias.tariff_name
                    or not -90.0 <= alias.lat <= 90.0
                    or not -180.0 <= alias.lon <= 180.0
                    or not 0.0 < alias.max_distance_km <= 5.0
                ):
                    raise ValueError(
                        f"{path}:{line_number}: alias tarifaire invalide"
                    )
                key = (
                    alias.operator,
                    alias.physical_name.casefold(),
                    round(alias.lat * 10000),
                    round(alias.lon * 10000),
                )
                previous = seen.get(key)
                if previous is not None and previous != alias:
                    raise ValueError(
                        f"{path}:{line_number}: alias contradictoire"
                    )
                if previous is None:
                    seen[key] = alias
                    output.append(alias)
    return output

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable


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

    def applies_on(self, day: date) -> bool:
        if self.effective_from is not None and day < self.effective_from:
            return False
        if self.effective_to is not None and day > self.effective_to:
            return False
        if self.season_start is None and self.season_end is None:
            return True
        if self.season_start is None or self.season_end is None:
            return False

        current = (day.month, day.day)
        start = self.season_start
        end = self.season_end
        if start <= end:
            return start <= current <= end
        return current >= start or current <= end


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

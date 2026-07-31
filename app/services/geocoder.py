from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.models import GeocodeResult


def normalize_location(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(character for character in value if not unicodedata.combining(character))
    return " ".join(re.findall(r"[a-z0-9]+", value))


def fts_expression(query: str) -> str:
    tokens = normalize_location(query).split()
    return " AND ".join(f'"{token}"*' for token in tokens)


@dataclass(slots=True)
class AmbiguousLocationError(ValueError):
    query: str
    choices: list[GeocodeResult]

    def __str__(self) -> str:
        return f"Plusieurs lieux correspondent à « {self.query} »."


class LocationNotFoundError(ValueError):
    pass


class LocalGeocoder:
    def __init__(
        self,
        database_path: Path,
        demo_path: Path,
        communes_database_path: Path | None = None,
    ) -> None:
        self.database_path = database_path
        self.communes_database_path = communes_database_path
        self.demo_places = json.loads(demo_path.read_text(encoding="utf-8"))

    @property
    def commune_count(self) -> int:
        path = self.communes_database_path
        if path is None or not path.exists():
            return 0
        try:
            with sqlite3.connect(path) as connection:
                return int(connection.execute("SELECT COUNT(*) FROM communes").fetchone()[0])
        except sqlite3.Error:
            return 0

    @staticmethod
    def _looks_like_address(query: str) -> bool:
        normalized = normalize_location(query)
        if re.search(r"\b\d{1,5}\b", normalized):
            return True
        street_words = {
            "allee",
            "avenue",
            "boulevard",
            "chemin",
            "cours",
            "impasse",
            "place",
            "quai",
            "route",
            "rue",
            "square",
            "voie",
        }
        return bool(street_words.intersection(normalized.split()))

    def search(self, query: str, limit: int = 10) -> list[GeocodeResult]:
        clean = " ".join(query.strip().split())
        if len(clean) < 2:
            return []

        communes = self._search_communes(clean, max(limit * 4, 30))
        exact_communes = [
            result for result in communes if self._matches_commune_query(clean, result)
        ]
        other_communes = [result for result in communes if result not in exact_communes]
        addresses = self._search_ban(clean, max(limit * 3, 20))

        # Une saisie contenant un numéro ou un type de voie doit proposer les
        # adresses BAN avant le centre de la commune. Un simple nom de ville
        # conserve au contraire la commune comme premier choix.
        if self._looks_like_address(clean):
            ordered = [*addresses, *exact_communes, *other_communes]
        else:
            ordered = [*exact_communes, *addresses, *other_communes]

        combined = self._deduplicate(ordered)
        if combined:
            return combined[:limit]
        return self._search_demo(clean, limit)

    def resolve(self, query: str, limit: int = 12) -> GeocodeResult:
        clean = " ".join(query.strip().split())
        results = self.search(clean, limit=limit)
        if not results:
            raise LocationNotFoundError(f"Adresse ou commune introuvable : {clean}")

        commune_matches = [
            result
            for result in results
            if result.kind == "municipality" and self._matches_commune_query(clean, result)
        ]
        unique_communes = self._deduplicate(commune_matches)
        if len(unique_communes) == 1:
            return unique_communes[0]
        if len(unique_communes) > 1:
            raise AmbiguousLocationError(clean, unique_communes[:limit])

        exact_addresses = [
            result
            for result in results
            if result.kind == "address"
            and normalize_location(result.label) == normalize_location(clean)
        ]
        if len(exact_addresses) == 1:
            return exact_addresses[0]
        if len(results) == 1:
            return results[0]
        raise AmbiguousLocationError(clean, results[:limit])

    def _search_ban(self, query: str, limit: int) -> list[GeocodeResult]:
        if not self.database_path.exists():
            return []
        expression = fts_expression(query)
        if not expression:
            return []
        try:
            with sqlite3.connect(self.database_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT a.label, a.city, a.postcode, a.lat, a.lon
                    FROM addresses_fts f
                    JOIN addresses a ON a.id = f.rowid
                    WHERE addresses_fts MATCH ?
                    ORDER BY bm25(addresses_fts)
                    LIMIT ?
                    """,
                    (expression, limit),
                ).fetchall()
        except sqlite3.Error:
            return []
        return [
            GeocodeResult(
                label=row["label"],
                city=row["city"],
                postcode=row["postcode"],
                lat=row["lat"],
                lon=row["lon"],
                source="ban",
                kind="address",
            )
            for row in rows
        ]

    def _search_communes(self, query: str, limit: int) -> list[GeocodeResult]:
        path = self.communes_database_path
        if path is None or not path.exists():
            return []
        expression = fts_expression(query)
        if not expression:
            return []
        normalized_query = normalize_location(query)
        try:
            with sqlite3.connect(path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(
                    """
                    SELECT c.code, c.name, c.normalized_name, c.postcodes,
                           c.department_code, c.population, c.lat, c.lon
                    FROM communes_fts f
                    JOIN communes c ON c.id = f.rowid
                    WHERE communes_fts MATCH ?
                    ORDER BY bm25(communes_fts), c.population DESC
                    LIMIT ?
                    """,
                    (expression, max(limit * 3, 40)),
                ).fetchall()
        except sqlite3.Error:
            return []

        def score(row: sqlite3.Row) -> tuple[int, int, str]:
            postcodes = row["postcodes"].split()
            exact_name = row["normalized_name"] == normalized_query
            exact_postcode = normalized_query in postcodes
            name_and_postcode = any(
                normalized_query
                in {
                    f"{row['normalized_name']} {postcode}",
                    f"{postcode} {row['normalized_name']}",
                }
                for postcode in postcodes
            )
            priority = 0 if name_and_postcode else 1 if exact_name else 2 if exact_postcode else 3
            return (priority, -int(row["population"]), row["name"])

        ordered = sorted(rows, key=score)[:limit]
        return [self._commune_result(row) for row in ordered]

    @staticmethod
    def _commune_result(row: sqlite3.Row) -> GeocodeResult:
        postcode = row["postcodes"].split()[0] if row["postcodes"] else ""
        qualifiers = [postcode, row["department_code"]]
        suffix = " · ".join(value for value in qualifiers if value)
        label = f"{row['name']} ({suffix})" if suffix else row["name"]
        return GeocodeResult(
            label=label,
            city=row["name"],
            postcode=postcode,
            lat=row["lat"],
            lon=row["lon"],
            source="commune",
            kind="municipality",
            code=row["code"],
            department_code=row["department_code"],
            population=row["population"],
        )

    @staticmethod
    def _matches_commune_query(query: str, result: GeocodeResult) -> bool:
        normalized_query = normalize_location(query)
        normalized_city = normalize_location(result.city)
        candidates = {normalized_city}
        if result.postcode:
            candidates.update(
                {
                    result.postcode,
                    f"{normalized_city} {result.postcode}",
                    f"{result.postcode} {normalized_city}",
                }
            )
        if result.department_code:
            candidates.update(
                {
                    f"{normalized_city} {result.department_code}",
                    f"{result.department_code} {normalized_city}",
                }
            )
        return normalized_query in candidates

    @staticmethod
    def _deduplicate(results: list[GeocodeResult]) -> list[GeocodeResult]:
        output: list[GeocodeResult] = []
        seen: set[tuple] = set()
        for result in results:
            key = (
                result.kind,
                result.code or normalize_location(result.label),
                round(result.lat, 5),
                round(result.lon, 5),
            )
            if key in seen:
                continue
            seen.add(key)
            output.append(result)
        return output

    def _search_demo(self, query: str, limit: int) -> list[GeocodeResult]:
        normalized = normalize_location(query)
        matches = [
            place
            for place in self.demo_places
            if normalized in normalize_location(place["label"])
            or normalized in normalize_location(place["city"])
        ]
        return [GeocodeResult(**place, source="demo", kind="demo") for place in matches[:limit]]

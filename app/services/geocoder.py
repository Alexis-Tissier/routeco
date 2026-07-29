from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.models import GeocodeResult


class LocalGeocoder:
    def __init__(self, database_path: Path, demo_path: Path) -> None:
        self.database_path = database_path
        self.demo_places = json.loads(demo_path.read_text(encoding="utf-8"))

    def search(self, query: str, limit: int = 7) -> list[GeocodeResult]:
        clean = " ".join(query.strip().split())
        if len(clean) < 2:
            return []
        if self.database_path.exists():
            results = self._search_ban(clean, limit)
            if results:
                return results
        return self._search_demo(clean, limit)

    def _search_ban(self, query: str, limit: int) -> list[GeocodeResult]:
        safe_tokens = [token.replace('"', "") for token in query.split() if token]
        expression = " ".join(f'"{token}"*' for token in safe_tokens)
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
            )
            for row in rows
        ]

    def _search_demo(self, query: str, limit: int) -> list[GeocodeResult]:
        normalized = query.casefold()
        matches = [
            place
            for place in self.demo_places
            if normalized in place["label"].casefold() or normalized in place["city"].casefold()
        ]
        return [GeocodeResult(**place, source="demo") for place in matches[:limit]]

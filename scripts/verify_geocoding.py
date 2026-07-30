#!/usr/bin/env python3
from __future__ import annotations

from app.config import settings
from app.services.geocoder import AmbiguousLocationError, LocalGeocoder


def verify() -> None:
    geocoder = LocalGeocoder(
        settings.ban_database,
        settings.demo_places,
        settings.communes_database,
    )
    if geocoder.commune_count < 30_000:
        raise RuntimeError(
            f"Index national incomplet : {geocoder.commune_count} communes."
        )

    versailles = geocoder.resolve("Versailles")
    if versailles.source != "commune" or versailles.code != "78646":
        raise RuntimeError(f"Versailles mal résolu : {versailles.model_dump()}")

    try:
        geocoder.resolve("Saint-Aubin")
    except AmbiguousLocationError as exc:
        if len(exc.choices) < 2:
            raise RuntimeError("Les homonymes Saint-Aubin ne sont pas tous proposés.") from exc
    else:
        raise RuntimeError("Saint-Aubin a été choisi silencieusement malgré ses homonymes.")

    print(
        f"Géocodage national validé : {geocoder.commune_count} communes, "
        f"{versailles.label}, homonymes protégés."
    )


if __name__ == "__main__":
    verify()

from __future__ import annotations

from pathlib import Path


def test_ui_polish_markers_present_in_app_js() -> None:
    content = Path("static/app.js").read_text(encoding="utf-8")
    assert "routecoApplyUiPolish()" in content
    assert "routecoInstallMiniViaToggle" in content
    assert "routecoInstallCompactSettings" in content
    assert "map-icon-button" in content
    assert "segmented-location-field" in content
    assert "segmented-location-button" in content


def test_ui_polish_markers_present_in_css() -> None:
    content = Path("static/app.css").read_text(encoding="utf-8")
    assert "Routeco 0.4.4 — contrôles de localisation segmentés" in content
    assert ".segmented-location-field" in content
    assert ".segmented-location-button" in content
    assert ".via-toggle-mini" in content
    assert ".compact-settings" in content

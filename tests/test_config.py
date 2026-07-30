from pathlib import Path

from app.config import load_settings


def test_external_data_paths_are_supported(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "data"
    ban = tmp_path / "windows" / "ban.sqlite"
    communes = tmp_path / "windows" / "communes.sqlite"
    tolls = tmp_path / "tolls"
    reports = tmp_path / "reports"
    monkeypatch.setenv("ROUTECO_DATA_DIR", str(data))
    monkeypatch.setenv("ROUTECO_BAN_DB", str(ban))
    monkeypatch.setenv("ROUTECO_COMMUNES_DB", str(communes))
    monkeypatch.setenv("ROUTECO_TOLLS_DIR", str(tolls))
    monkeypatch.setenv("ROUTECO_REPORTS_DIR", str(reports))
    monkeypatch.setenv("GRAPHHOPPER_URL", "http://localhost:9999/")

    settings = load_settings()

    assert settings.data_dir == data.resolve()
    assert settings.ban_database == ban.resolve()
    assert settings.communes_database == communes.resolve()
    assert settings.tolls_dir == tolls.resolve()
    assert settings.reports_dir == reports.resolve()
    assert settings.graphhopper_url == "http://localhost:9999"

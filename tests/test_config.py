"""Tests for the configuration helper functions."""


import config


def test_load_settings_creates_file(tmp_path, monkeypatch):
    """``load_settings`` should create a new file with defaults."""

    settings_file = tmp_path / "settings.json"
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)

    settings = config.load_settings()

    assert settings_file.exists()
    assert settings_file.read_text(encoding="utf-8") == "{}"
    assert isinstance(settings, config.AppSettings)


def test_load_settings_handles_invalid_json(tmp_path, monkeypatch):
    """An invalid JSON file should be reset and not raise an error."""

    settings_file = tmp_path / "settings.json"
    settings_file.write_text("bad json", encoding="utf-8")
    monkeypatch.setattr(config, "SETTINGS_FILE", settings_file)

    settings = config.load_settings()

    assert settings_file.read_text(encoding="utf-8") == "{}"
    assert isinstance(settings, config.AppSettings)


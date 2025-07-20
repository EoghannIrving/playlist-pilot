import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config


def test_determine_settings_file_env(monkeypatch):
    monkeypatch.setenv("SETTINGS_FILE", "/tmp/custom.json")
    path = config.determine_settings_file([])
    assert path == Path("/tmp/custom.json")


def test_determine_settings_file_cli(monkeypatch):
    monkeypatch.delenv("SETTINGS_FILE", raising=False)
    path = config.determine_settings_file(["--settings-file", "/tmp/cli.json"])
    assert path == Path("/tmp/cli.json")


def test_determine_settings_file_default(monkeypatch):
    monkeypatch.delenv("SETTINGS_FILE", raising=False)
    path = config.determine_settings_file([])
    assert path == Path("/app/settings.json")

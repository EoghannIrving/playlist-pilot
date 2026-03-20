"""Unit tests for the :class:`SettingsForm` helper functions."""

import inspect
import json

from fastapi import HTTPException
from fastapi.params import Form
import pytest

from config import AppSettings
from api.forms import SettingsForm


def _default_form_data():
    data = AppSettings().model_dump()
    data["cache_ttls"] = json.dumps(data["cache_ttls"])
    data["getsongbpm_headers"] = json.dumps(data["getsongbpm_headers"])
    return data


def test_as_form_invalid_cache_ttls():
    """Invalid JSON for cache_ttls should raise HTTPException."""
    defaults = _default_form_data()
    with pytest.raises(HTTPException) as excinfo:
        SettingsForm.as_form(**{**defaults, "cache_ttls": "{bad json"})
    assert excinfo.value.status_code == 400
    assert "cache_ttls" in excinfo.value.detail


def test_as_form_invalid_getsongbpm_headers():
    """Invalid JSON for getsongbpm_headers should raise HTTPException."""
    defaults = _default_form_data()
    with pytest.raises(HTTPException) as excinfo:
        SettingsForm.as_form(**{**defaults, "getsongbpm_headers": "{bad"})
    assert excinfo.value.status_code == 400
    assert "getsongbpm_headers" in excinfo.value.detail


def test_as_form_lyrics_enabled_default():
    """The lyrics_enabled field should default to ``True`` for missing input."""
    sig = inspect.signature(SettingsForm.as_form)
    param = sig.parameters["lyrics_enabled"]

    assert isinstance(param.default, Form)
    assert param.default.default is True


def test_integration_failure_limit_default():
    """integration_failure_limit should have a default of 3."""
    sig = inspect.signature(SettingsForm.as_form)
    param = sig.parameters["integration_failure_limit"]

    assert isinstance(param.default, Form)
    assert param.default.default == 3


def test_as_form_prefers_generic_media_fields():
    """Generic media-server fields should populate the returned form model."""
    defaults = _default_form_data()
    form = SettingsForm.as_form(
        **{
            **defaults,
            "media_backend": "jellyfin",
            "media_url": "http://media",
            "media_api_key": "media-key",
            "media_user_id": "media-user",
            "jellyfin_url": "http://legacy",
            "jellyfin_api_key": "legacy-key",
            "jellyfin_user_id": "legacy-user",
        }
    )

    assert form.media_backend == "jellyfin"
    assert form.media_url == "http://media"
    assert form.media_api_key == "media-key"
    assert form.media_user_id == "media-user"


def test_as_form_accepts_navidrome_fields():
    """Navidrome settings should populate the generic media fields."""
    defaults = _default_form_data()
    form = SettingsForm.as_form(
        **{
            **defaults,
            "media_backend": "navidrome",
            "media_url": "http://nav",
            "media_username": "nav-user",
            "media_password": "nav-pass",
        }
    )

    assert form.media_backend == "navidrome"
    assert form.media_url == "http://nav"
    assert form.media_username == "nav-user"
    assert form.media_password == "nav-pass"

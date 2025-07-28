"""Unit tests for the :class:`SettingsForm` helper functions."""

import json
import inspect
from fastapi import HTTPException
from fastapi.params import Form
import pytest
from config import AppSettings
from api.forms import SettingsForm


def _default_form_data():
    data = AppSettings().dict()
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

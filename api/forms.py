"""Form utilities for validating settings updates through FastAPI."""

import json
from json import JSONDecodeError
from fastapi import Form, HTTPException
from config import AppSettings


class SettingsForm(AppSettings):
    """Pydantic model for updating application settings via form."""

    @classmethod
    def as_form(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        cls,
        jellyfin_url: str = Form(""),
        jellyfin_api_key: str = Form(""),
        jellyfin_user_id: str = Form(""),
        openai_api_key: str = Form(""),
        lastfm_api_key: str = Form(""),
        model: str = Form("gpt-4o-mini"),
        getsongbpm_api_key: str = Form(""),
        global_min_lfm: int = Form(10000),
        global_max_lfm: int = Form(15000000),
        cache_ttls: str = Form(""),
        getsongbpm_base_url: str = Form("https://api.getsongbpm.com/search/"),
        getsongbpm_headers: str = Form(""),
        http_timeout_short: int = Form(5),
        http_timeout_long: int = Form(10),
        youtube_min_duration: int = Form(120),
        youtube_max_duration: int = Form(360),
        library_scan_limit: int = Form(1000),
        music_library_root: str = Form("Movies/Music"),
        lyrics_enabled: bool = Form(True),
        lyrics_weight: float = Form(1.5),
        bpm_weight: float = Form(1.0),
        tags_weight: float = Form(0.7),
    ) -> "SettingsForm":
        """Create a SettingsForm instance from submitted form data."""

        def _safe_json(value: str, default: dict, field_name: str) -> dict:
            """Parse a JSON string or raise a ``HTTPException`` with details."""
            if not value:
                return default
            try:
                return json.loads(value)
            except JSONDecodeError as exc:  # nosec B003 - informative error
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid JSON for {field_name}: {exc.msg}",
                ) from exc

        return cls(
            jellyfin_url=jellyfin_url,
            jellyfin_api_key=jellyfin_api_key,
            jellyfin_user_id=jellyfin_user_id,
            openai_api_key=openai_api_key,
            lastfm_api_key=lastfm_api_key,
            model=model,
            getsongbpm_api_key=getsongbpm_api_key,
            global_min_lfm=global_min_lfm,
            global_max_lfm=global_max_lfm,
            cache_ttls=_safe_json(cache_ttls, AppSettings().cache_ttls, "cache_ttls"),
            getsongbpm_base_url=getsongbpm_base_url,
            getsongbpm_headers=_safe_json(
                getsongbpm_headers,
                AppSettings().getsongbpm_headers,
                "getsongbpm_headers",
            ),
            http_timeout_short=http_timeout_short,
            http_timeout_long=http_timeout_long,
            youtube_min_duration=youtube_min_duration,
            youtube_max_duration=youtube_max_duration,
            library_scan_limit=library_scan_limit,
            music_library_root=music_library_root,
            lyrics_enabled=lyrics_enabled,
            lyrics_weight=lyrics_weight,
            bpm_weight=bpm_weight,
            tags_weight=tags_weight,
        )

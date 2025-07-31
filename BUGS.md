# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).



## 56. `_duration_from_ticks` may crash on non-numeric BPM data
The helper casts the BPM API's ``duration`` field directly to ``int`` without validating its type.
```
bpm_duration = bpm_data.get("duration")
return int(bpm_duration) if bpm_duration is not None else duration
```
【F:core/playlist.py†L287-L291】

## 57. `parse_gpt_line` ignores em dashes
Only en dashes are normalized, so lines using an em dash (`—`) fail to parse.
```
line = line.replace("\u2013", "-").strip()  # normalize en dash
```
【F:services/gpt.py†L181-L201】

## 58. `_extract_remaining` splits on every dash
When titles or artists contain dashes, the remaining text is truncated because the helper splits on ``" - "`` without limit.
```
parts = [p.strip() for p in normalized.split(" - ")]
return " - ".join(parts[2:]).strip()
```
【F:services/gpt.py†L304-L315】

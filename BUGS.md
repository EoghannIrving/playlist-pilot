# Known Issues

This file documents outstanding bugs discovered during a code audit.
Fixed issues have been moved to [FIXED_BUGS.md](FIXED_BUGS.md).



## 58. `_extract_remaining` splits on every dash
When titles or artists contain dashes, the remaining text is truncated because the helper splits on ``" - "`` without limit.
```
parts = [p.strip() for p in normalized.split(" - ")]
return " - ".join(parts[2:]).strip()
```
【F:services/gpt.py†L304-L315】

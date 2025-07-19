"""FastAPI template configuration and custom Jinja filters."""

from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")


def duration_human(seconds: int) -> str:
    """Return ``MM:SS`` style duration strings for template rendering."""
    if not isinstance(seconds, int):
        return "?:??"
    return f"{seconds // 60}:{seconds % 60:02d}"


templates.env.filters["duration_human"] = duration_human

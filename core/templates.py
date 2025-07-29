"""FastAPI template configuration and custom Jinja filters."""

from pathlib import Path

from fastapi.templating import Jinja2Templates

# Use an absolute path so running the app from another working directory
# still finds the HTML templates bundled with the package.
TEMPLATES_DIR = (Path(__file__).resolve().parent.parent / "templates").resolve()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def duration_human(seconds: int) -> str:
    """Return ``MM:SS`` style duration strings for template rendering."""
    if not isinstance(seconds, int):
        return "?:??"
    return f"{seconds // 60}:{seconds % 60:02d}"


templates.env.filters["duration_human"] = duration_human

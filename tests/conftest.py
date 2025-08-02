"""Pytest configuration and fixtures."""

import sys
from pathlib import Path

# Ensure repository root is on PYTHONPATH for direct test execution
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

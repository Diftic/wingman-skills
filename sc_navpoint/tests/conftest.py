"""Pytest setup for sc_navpoint tests.

The sc_navpoint runtime modules (database.py, scanner.py, navigation.py)
import each other flat, as top-level modules (see main.py:
`from database import ...`). To match that, the skill directory is placed
on sys.path so `import database` resolves to skills/sc_navpoint/database.py.

Importing the modules flat (not as `sc_navpoint.database`) deliberately
avoids triggering sc_navpoint/__init__.py, which pulls in the Wingman
runtime (api.enums, api.interface) that is not importable in a bare test
environment.
"""

from __future__ import annotations

import sys
from pathlib import Path


_SKILL_DIR = Path(__file__).resolve().parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))

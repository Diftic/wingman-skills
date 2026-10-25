"""Put the skill's dependencies folder on sys.path, as Core does when it loads the skill."""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent / "dependencies"
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

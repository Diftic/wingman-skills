"""Put the skill directory on sys.path so pure modules import directly."""

from __future__ import annotations

import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

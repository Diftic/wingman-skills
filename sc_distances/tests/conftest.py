"""Put the skill's dependencies (as Core does when it loads the skill) and tools folders on sys.path."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (ROOT / "dependencies", ROOT / "tools"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

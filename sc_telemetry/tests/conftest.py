"""Test setup: the skill's pure-logic package `sc_telemetry_core` is imported directly, without Wingman."""
import json
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
for folder in (SKILL_DIR / "dependencies", SKILL_DIR / "tools", Path(__file__).resolve().parent):
    sys.path.insert(0, str(folder))


def load_frames(name: str) -> list[tuple[float, dict]]:
    """A recorded moment: (unix time, frame dict as the probe logged it)."""
    with (FIXTURES / name).open(encoding="utf-8") as handle:
        return [(row["t"], row["frame"]) for row in map(json.loads, handle)]


@pytest.fixture
def frames():
    return load_frames

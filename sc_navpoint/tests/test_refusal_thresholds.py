"""The two refusal thresholds are pinned so lowering one is a deliberate act.

A cell is refused when its decode cost exceeds `REFUSE_COST` OR its margin over
the runner-up falls below `REFUSE_MARGIN`, and a row is trusted only when every
cell in it was read. That is why a scene with three or four bad cells loses a
whole capture, and it is the obvious thing to "fix" while the diagnosis is
still open.

It would not be a fix. High cost means nothing in the glyph bank matched, low
margin means two glyphs matched almost equally, and neither is repaired by
accepting the result anyway: the outcome is a waypoint with a wrong digit in
it, which is the failure this skill exists to refuse. The 2026-07-20 and
2026-07-26 incidents are what a confident wrong read costs.

So: anyone changing either number has to change this test in the same commit,
with a reason. That is the whole purpose. It is not a claim that 15.0 and 8.0
are optimal, only that they may not drift silently.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import overlay_reader  # noqa: E402


def test_the_cost_threshold_is_unchanged():
    assert overlay_reader.REFUSE_COST == 15.0


def test_the_margin_threshold_is_unchanged():
    assert overlay_reader.REFUSE_MARGIN == 8.0


def test_refusal_is_still_a_disjunction_of_the_two():
    """Either condition alone refuses the cell. They mean opposite things, so
    a change that made it a conjunction would quietly halve the guard."""
    source = Path(overlay_reader.__file__).read_text(encoding="utf-8")
    assert "cost > REFUSE_COST or margin < REFUSE_MARGIN" in source

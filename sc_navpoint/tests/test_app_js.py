"""JavaScript syntax guard for the SPA (spec Item C).

The deflection-ring rewrite is not unit-tested (its mapping math mirrors
calcBearing outputs already covered in test_navigation). What this guards is
that the rewritten static/app.js still parses: a `node --check` catches the
kind of brace/paren slip a large canvas rewrite can introduce. If node is not
on PATH the check skips cleanly rather than failing the suite.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


_APP_JS = Path(__file__).resolve().parent.parent / "navpoint_ui" / "static" / "app.js"


def test_app_js_parses_with_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node not on PATH; skipping JS syntax check")
    assert _APP_JS.exists(), f"app.js not found at {_APP_JS}"
    result = subprocess.run(
        [node, "--check", str(_APP_JS)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"node --check reported a syntax error in app.js:\n"
        f"{result.stdout}\n{result.stderr}"
    )

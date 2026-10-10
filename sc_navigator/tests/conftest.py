"""Shared fixtures for sc_navigator tests.

Inserts the skill directory on sys.path so `import sc_nav_route_optimizer` and
`import build_locations` resolve by bare name, matching how the wingman host
loads the skill. main.py is never imported here; it needs the wingman runtime.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))


@pytest.fixture
def loc():
    """Return a factory for a single location dict."""

    def _loc(
        name: str,
        system: str,
        x: float = 0.0,
        y: float = 0.0,
        z: float = 0.0,
        type: str = "POI",
    ) -> dict:
        return {"name": name, "system": system, "type": type, "x": x, "y": y, "z": z}

    return _loc


@pytest.fixture
def build_optimizer(tmp_path):
    """Return a factory building a RouteOptimizer from in-memory data."""

    def _build(
        locations: list[dict],
        gateway_links: list[dict] | None = None,
        aliases: dict[str, str] | None = None,
    ):
        from sc_nav_route_optimizer import RouteOptimizer

        data = {
            "metadata": {"units": "meters", "location_count": len(locations)},
            "locations": locations,
            "gateway_links": gateway_links or [],
            "aliases": aliases or {},
        }
        path = tmp_path / "dataset.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return RouteOptimizer(str(path))

    return _build

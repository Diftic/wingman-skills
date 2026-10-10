"""Smoke tests against the built data/sc_locations.json."""

from __future__ import annotations

import math
from collections import Counter

import pytest

from sc_nav_route_optimizer import MATCHED, RouteOptimizer


@pytest.fixture(scope="module")
def opt() -> RouteOptimizer:
    return RouteOptimizer()


def test_metadata_counts_are_consistent(opt):
    meta = opt.metadata
    assert 500 <= meta["location_count"] <= 540
    assert meta["location_count"] == len(opt._locations)

    actual = Counter(location.system for location in opt._locations)
    for system, count in meta["system_counts"].items():
        assert count == actual.get(system, 0)


def test_exactly_three_gateway_links(opt):
    pairs = {frozenset(transit) for transit in _system_pairs(opt)}
    assert pairs == {
        frozenset({"Stanton", "Pyro"}),
        frozenset({"Stanton", "Nyx"}),
        frozenset({"Pyro", "Nyx"}),
    }


def _system_pairs(opt) -> list[tuple[str, str]]:
    seen = set()
    for (system, name), targets in opt._transit.items():
        for target_system, _ in targets:
            seen.add(frozenset({system, target_system}))
    return [tuple(pair) for pair in seen]


def test_resolves_key_locations(opt):
    for spoken in ("Lorville", "area 18", "Grim HEX"):
        result = opt.resolve_location(spoken)
        assert result.status == MATCHED, spoken


def test_same_system_distance_positive_no_via(opt):
    lorville = opt.resolve_location("Lorville").location.display_key
    area18 = opt.resolve_location("area 18").location.display_key
    distance, via = opt.get_distance(lorville, area18)
    assert distance is not None and math.isfinite(distance) and distance > 0.0
    assert via == []


def test_cross_system_distance_has_stanton_gateway(opt):
    lorville = opt.resolve_location("Lorville").location.display_key
    ruin = opt.resolve_location("Ruin Station").location.display_key
    distance, via = opt.get_distance(lorville, ruin)
    assert distance is not None and distance > 0.0
    assert via
    via_systems = {opt.get_system(key) for key in via}
    assert "Stanton" in via_systems


def test_ten_waypoint_mixed_system_route(opt):
    keys = _pick_display_keys(opt, {"Stanton": 6, "Pyro": 2, "Nyx": 2})
    assert len(keys) == 10
    result = opt.optimize_route(keys)
    assert result["algorithm"] == "nearest_neighbor_2opt"
    assert "warnings" not in result
    for leg in result["legs"]:
        assert not leg.get("unreachable")
        assert leg["distance_gm"] is not None
        assert leg["distance_gm"] >= 0.0


def _pick_display_keys(opt, wanted: dict[str, int]) -> list[str]:
    picked: list[str] = []
    for system, count in wanted.items():
        keys = sorted(
            loc.display_key for loc in opt._locations if loc.system == system
        )
        picked.extend(keys[:count])
    return picked

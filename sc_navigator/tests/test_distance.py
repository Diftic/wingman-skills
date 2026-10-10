"""Distance computation: Euclidean, zero, cross-system, unreachable."""

from __future__ import annotations

import math


# One Gigameter in meters; coordinates below read as <Gm> * GM.
GM = 1_000_000_000.0


def test_same_system_euclidean(loc, build_optimizer):
    opt = build_optimizer(
        [
            loc("Origin", "Stanton", x=0.0, y=0.0, z=0.0),
            loc("Target", "Stanton", x=3.0 * GM, y=4.0 * GM, z=0.0),
        ]
    )
    distance, via = opt.get_distance("Origin", "Target")
    assert math.isclose(distance, 5.0)
    assert via == []


def test_colocated_points_are_zero_not_missing(loc, build_optimizer):
    opt = build_optimizer(
        [
            loc("A", "Stanton", x=7.0 * GM, y=0.0, z=0.0),
            loc("B", "Stanton", x=7.0 * GM, y=0.0, z=0.0),
        ]
    )
    distance, via = opt.get_distance("A", "B")
    assert distance == 0.0
    assert distance is not None


def test_unknown_key_returns_none(loc, build_optimizer):
    opt = build_optimizer([loc("A", "Stanton")])
    distance, via = opt.get_distance("A", "Nowhere")
    assert distance is None
    assert via == []


def _two_system(loc):
    locations = [
        loc("Alpha", "Stanton", x=0.0, y=0.0, z=0.0),
        loc("Pyro Gateway", "Stanton", x=10.0 * GM, y=0.0, z=0.0),
        loc("Stanton Gateway", "Pyro", x=0.0, y=0.0, z=0.0),
        loc("Beta", "Pyro", x=3.0 * GM, y=0.0, z=0.0),
    ]
    links = [
        {
            "system_a": "Pyro",
            "gateway_a": "Stanton Gateway",
            "system_b": "Stanton",
            "gateway_b": "Pyro Gateway",
        }
    ]
    return locations, links


def test_cross_system_leg_composition_and_via(loc, build_optimizer):
    locations, links = _two_system(loc)
    opt = build_optimizer(locations, gateway_links=links)
    distance, via = opt.get_distance("Alpha", "Beta")
    # Alpha -> Pyro Gateway (10) + jump (0) + Stanton Gateway -> Beta (3).
    assert math.isclose(distance, 13.0)
    assert via == ["Pyro Gateway", "Stanton Gateway"]


def test_cross_system_reverse_direction(loc, build_optimizer):
    locations, links = _two_system(loc)
    opt = build_optimizer(locations, gateway_links=links)
    distance, via = opt.get_distance("Beta", "Alpha")
    assert math.isclose(distance, 13.0)
    assert via == ["Stanton Gateway", "Pyro Gateway"]


def test_three_system_chain_multi_hop(loc, build_optimizer):
    # Stanton <-> Pyro <-> Nyx, with no direct Stanton <-> Nyx link.
    locations = [
        loc("A1", "Stanton", x=0.0, y=0.0, z=0.0),
        loc("Pyro Gateway", "Stanton", x=1.0 * GM, y=0.0, z=0.0),
        loc("Stanton Gateway", "Pyro", x=0.0, y=0.0, z=0.0),
        loc("Nyx Gateway", "Pyro", x=2.0 * GM, y=0.0, z=0.0),
        loc("Pyro Gateway", "Nyx", x=0.0, y=0.0, z=0.0),
        loc("C1", "Nyx", x=5.0 * GM, y=0.0, z=0.0),
    ]
    links = [
        {
            "system_a": "Pyro",
            "gateway_a": "Stanton Gateway",
            "system_b": "Stanton",
            "gateway_b": "Pyro Gateway",
        },
        {
            "system_a": "Nyx",
            "gateway_a": "Pyro Gateway",
            "system_b": "Pyro",
            "gateway_b": "Nyx Gateway",
        },
    ]
    opt = build_optimizer(locations, gateway_links=links)
    distance, via = opt.get_distance("A1", "C1")
    # 1 (to Pyro Gateway) + 0 + 2 (across Pyro) + 0 + 5 (across Nyx).
    assert math.isclose(distance, 8.0)
    assert via == [
        "Pyro Gateway (Stanton)",
        "Stanton Gateway",
        "Nyx Gateway",
        "Pyro Gateway (Nyx)",
    ]


def test_unreachable_systems_return_none(loc, build_optimizer):
    opt = build_optimizer(
        [
            loc("A1", "Stanton", x=0.0),
            loc("B1", "Pyro", x=0.0),
        ]
    )
    distance, via = opt.get_distance("A1", "B1")
    assert distance is None
    assert via == []

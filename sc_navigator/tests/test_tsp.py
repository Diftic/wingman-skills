"""TSP behaviour: brute force, multi-start NN, open/closed 2-opt, warnings."""

from __future__ import annotations

import math


# One Gigameter in meters; coordinates below read as <Gm> * GM.
GM = 1_000_000_000.0


def _line(loc, positions: dict[str, float], system: str = "Stanton") -> list[dict]:
    return [loc(name, system, x=x * GM, y=0.0, z=0.0) for name, x in positions.items()]


def test_brute_force_finds_known_best_order(loc, build_optimizer):
    # Positions 0, 10, 1, 11: optimal open path is by ascending x.
    opt = build_optimizer(
        _line(loc, {"A": 0.0, "B": 10.0, "C": 1.0, "D": 11.0})
    )
    result = opt.optimize_route(["A", "B", "C", "D"])
    assert result["algorithm"] == "brute_force"
    assert math.isclose(result["total_distance_gm"], 11.0)
    assert result["route"] in (["A", "C", "B", "D"], ["D", "B", "C", "A"])


def test_open_route_2opt_no_phantom_closing_edge(loc, build_optimizer):
    # Ten colinear points with strictly increasing gaps force the NN + 2-opt
    # path (>8 free waypoints). The optimal OPEN order is monotonic; a phantom
    # closing edge would reorder to shorten a non-existent return leg.
    positions = {
        "P0": 0.0,
        "P1": 1.0,
        "P2": 3.0,
        "P3": 6.0,
        "P4": 10.0,
        "P5": 15.0,
        "P6": 21.0,
        "P7": 28.0,
        "P8": 36.0,
        "P9": 45.0,
    }
    opt = build_optimizer(_line(loc, positions))
    result = opt.optimize_route(list(positions.keys()))
    assert result["algorithm"] == "nearest_neighbor_2opt"
    monotonic = list(positions.keys())
    assert result["route"] in (monotonic, list(reversed(monotonic)))
    assert math.isclose(result["total_distance_gm"], 45.0)


def test_closed_route_cycle_semantics(loc, build_optimizer):
    # Same colinear points, but returning to the pinned start: the optimal
    # cycle runs to the far end and back, so the total is twice the span.
    positions = {
        "P0": 0.0,
        "P1": 1.0,
        "P2": 3.0,
        "P3": 6.0,
        "P4": 10.0,
        "P5": 15.0,
        "P6": 21.0,
        "P7": 28.0,
        "P8": 36.0,
        "P9": 45.0,
    }
    opt = build_optimizer(_line(loc, positions))
    result = opt.optimize_route(
        list(positions.keys()), start_location="P0", return_to_start=True
    )
    assert result["route"][0] == "P0"
    assert result["route"][-1] == "P0"
    assert math.isclose(result["total_distance_gm"], 90.0)


def test_multi_start_nn_beats_first_waypoint_start(loc, build_optimizer):
    # waypoints[0] sits in the middle of the line, so a first-waypoint NN
    # zigzags outward; multi-start NN finds the endpoint start and runs clean.
    positions = {
        "M": 4.0,
        "P0": 0.0,
        "P1": 1.0,
        "P2": 2.0,
        "P3": 3.0,
        "P5": 5.0,
        "P6": 6.0,
        "P7": 7.0,
        "P8": 8.0,
    }
    order = list(positions.keys())
    opt = build_optimizer(_line(loc, positions))

    first_wp_order = [order[0], *opt._nn_order(order[1:], order[0])]
    first_wp_route = opt._assemble(first_wp_order, "", "", False)
    first_wp_total = opt._route_distance(first_wp_route)

    result = opt.optimize_route(order)
    assert math.isclose(result["total_distance_gm"], 8.0)
    assert result["total_distance_gm"] < first_wp_total


def test_unreachable_leg_flagged_and_excluded(loc, build_optimizer):
    # Two unlinked systems: any leg between them is unreachable.
    opt = build_optimizer(
        [
            loc("A1", "Stanton", x=0.0),
            loc("A2", "Stanton", x=2.0 * GM),
            loc("B1", "Pyro", x=0.0),
        ]
    )
    result = opt.optimize_route(["A1", "A2", "B1"], start_location="A1")
    unreachable = [leg for leg in result["legs"] if leg.get("unreachable")]
    assert unreachable
    assert "warnings" in result
    # The reachable A1 -> A2 leg (2 Gm) is the only priced distance.
    assert math.isclose(result["total_distance_gm"], 2.0)


def test_ambiguous_waypoint_reports_error(loc, build_optimizer):
    opt = build_optimizer(
        [
            loc("Gate", "Stanton", x=0.0),
            loc("Gate", "Pyro", x=0.0),
            loc("Lorville", "Stanton", x=1.0 * GM),
        ]
    )
    result = opt.optimize_route(["Gate", "Lorville"])
    assert "error" in result
    assert "Ambiguous" in result["error"]

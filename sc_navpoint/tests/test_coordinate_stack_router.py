"""The routing state machine, exercised without the game, OCR, Wingman or a HUD.

Every boundary is tested from both sides, and equality is tested explicitly:
`>= 3 Mm` belongs to Root, in both the Root test and the local test, and a
single `<` turned into `<=` is a silent one-metre widening that nothing else
would notice.

The name-independence tests are the point of the whole rework. `select_route`
must reach the same decision when every `raw_name` and `raw` value in both
stacks is replaced with nonsense, because a zone name is a token a patch may
rename and OCR may mangle.
"""

from __future__ import annotations

import dataclasses

import pytest

import coordinate_stack as cs


LIMIT = cs.LOCAL_TRACKING_MAX_M


def _row(x=0.0, y=0.0, z=0.0, name="zone", depth=None) -> cs.StackRow:
    return cs.StackRow(x_m=x, y_m=y, z_m=z, raw_name=name,
                       raw=f"Zone: {name} Pos: ...", depth=depth)


def _stack(root=(0.0, 0.0, 0.0), nested=((0.0, 0.0, 0.0),),
           candidate=True) -> cs.CoordinateStack:
    rows = tuple(
        _row(x, y, z, name=f"zone_{i}", depth=i)
        for i, (x, y, z) in enumerate(nested)
    )
    depth = (len(rows) - 1) if (rows and candidate) else None
    return cs.CoordinateStack(
        root=_row(*root, name="Root"),
        solar=_row(*root, name="SolarSystem_753098466557"),
        nested=rows,
        candidate_depth=depth,
    )


def _pair(d_root: float, d_local: float):
    """A (target, current) pair separated by exactly these two distances."""
    target = _stack(root=(0.0, 0.0, 0.0), nested=((0.0, 0.0, 0.0),))
    current = _stack(root=(d_root, 0.0, 0.0), nested=((d_local, 0.0, 0.0),))
    return target, current


def _route(d_root, d_local, allow_local=True):
    target, current = _pair(d_root, d_local)
    return cs.select_route(target, current, allow_local=allow_local)


# --------------------------------------------------------------------------- #
# Refusal
# --------------------------------------------------------------------------- #

def test_no_target_stack_refuses() -> None:
    decision = cs.select_route(None, _stack())
    assert decision.mode == cs.MODE_REFUSED
    assert decision.reason == cs.REASON_NO_TARGET_STACK
    assert decision.distance_m is None
    assert decision.clear_local is True


def test_no_current_stack_refuses() -> None:
    decision = cs.select_route(_stack(), None)
    assert decision.mode == cs.MODE_REFUSED
    assert decision.reason == cs.REASON_NO_CURRENT_STACK
    assert decision.distance_m is None


def test_a_refusal_draws_nothing_and_announces_nothing() -> None:
    for decision in (cs.select_route(None, _stack()), cs.select_route(_stack(), None)):
        assert decision.allow_direction is False
        assert decision.allow_arrival is False
        assert decision.current is None
        assert decision.target is None


# --------------------------------------------------------------------------- #
# The Root ceiling
# --------------------------------------------------------------------------- #

def test_root_beyond_the_limit_selects_root() -> None:
    decision = _route(LIMIT + 1.0, 0.0)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_ROOT_AT_OR_BEYOND_LIMIT


def test_root_exactly_at_the_limit_belongs_to_root() -> None:
    """Equality is Root's, in both ceilings. A `<` turned `<=` is a silent
    widening that no other test would notice."""
    decision = _route(LIMIT, 0.0)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_ROOT_AT_OR_BEYOND_LIMIT


def test_root_just_inside_the_limit_can_reach_local() -> None:
    decision = _route(LIMIT - 1.0, 0.0)
    assert decision.mode == cs.MODE_LOCAL_TRACKING


def test_the_limit_is_three_million_metres() -> None:
    assert cs.LOCAL_TRACKING_MAX_M == 3_000_000.0


def test_root_distance_is_reported_in_root_mode() -> None:
    """Root mode reports the ROOT separation, never the local one it declined."""
    decision = _route(2_500_000.0, 2_999_999.0, allow_local=False)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.distance_m == pytest.approx(2_500_000.0)
    assert decision.current == (2_500_000.0, 0.0, 0.0)
    assert decision.target == (0.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# The local ceiling
# --------------------------------------------------------------------------- #

def test_local_beyond_the_limit_falls_back_to_root() -> None:
    decision = _route(1_000.0, LIMIT + 1.0)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_LOCAL_AT_OR_BEYOND_LIMIT


def test_local_exactly_at_the_limit_falls_back_to_root() -> None:
    decision = _route(1_000.0, LIMIT)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_LOCAL_AT_OR_BEYOND_LIMIT


def test_both_distances_strictly_inside_selects_local() -> None:
    decision = _route(LIMIT - 1.0, LIMIT - 1.0)
    assert decision.mode == cs.MODE_LOCAL_TRACKING
    assert decision.reason == cs.REASON_LOCAL_IN_RANGE
    assert decision.distance_m == pytest.approx(LIMIT - 1.0)


def test_root_is_computed_before_local_is_considered() -> None:
    """No local reading may influence a decision taken outside the envelope."""
    decision = _route(LIMIT + 1.0, 0.0)
    assert decision.distance_m == pytest.approx(LIMIT + 1.0)
    assert decision.current == (LIMIT + 1.0, 0.0, 0.0)


# --------------------------------------------------------------------------- #
# Missing candidates
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("which", ["target", "current"])
def test_a_missing_local_candidate_falls_back_to_root(which) -> None:
    target, current = _pair(1_000.0, 1_000.0)
    if which == "target":
        target = dataclasses.replace(target, candidate_depth=None)
    else:
        current = dataclasses.replace(current, candidate_depth=None)
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_NO_LOCAL_CANDIDATE


def test_a_deep_space_stack_with_no_nested_row_is_root_only() -> None:
    target = _stack(root=(0.0, 0.0, 0.0), nested=())
    current = _stack(root=(1_000.0, 0.0, 0.0), nested=())
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_NO_LOCAL_CANDIDATE


def test_the_final_pre_solar_row_is_selected_never_an_inner_seat() -> None:
    """The row-index rule keyed waypoints to furniture. The seat row sits first
    and must never be the one compared."""
    target = _stack(root=(0.0, 0.0, 0.0),
                    nested=((0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (100.0, 0.0, 0.0)))
    current = _stack(root=(10.0, 0.0, 0.0),
                     nested=((0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (400.0, 0.0, 0.0)))
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_LOCAL_TRACKING
    # 400 - 100, the outermost pair. The seat pair would give 0 and the middle
    # pair would give 0 as well, so a wrong selection is unmistakable.
    assert decision.distance_m == pytest.approx(300.0)


# --------------------------------------------------------------------------- #
# The evidence gate
# --------------------------------------------------------------------------- #

def test_local_tracking_ships_disabled() -> None:
    """The outermost-row hypothesis has never been checked against paired live
    captures, so the whole local path is off until it is."""
    assert cs.LOCAL_TRACKING_ENABLED is False


def test_the_module_default_is_used_when_no_override_is_given() -> None:
    target, current = _pair(1_000.0, 1_000.0)
    decision = cs.select_route(target, current)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_LOCAL_DISABLED


def test_the_gate_says_plainly_that_the_gate_and_not_the_geometry_chose_root() -> None:
    decision = _route(1_000.0, 1_000.0, allow_local=False)
    assert decision.reason == cs.REASON_LOCAL_DISABLED
    assert decision.mode == cs.MODE_ROOT_APPROACH


def test_the_gate_does_not_rescue_a_geometry_that_already_refused_local() -> None:
    """Turning the gate on must never widen the envelope."""
    for d_root, d_local in ((LIMIT, 0.0), (0.0, LIMIT)):
        off = cs.select_route(*_pair(d_root, d_local), allow_local=False)
        on = cs.select_route(*reversed(list(reversed(_pair(d_root, d_local)))),
                             allow_local=True)
        assert off.mode == cs.MODE_ROOT_APPROACH
        assert on.mode == cs.MODE_ROOT_APPROACH
        assert on.reason != cs.REASON_LOCAL_DISABLED


# --------------------------------------------------------------------------- #
# Presentation flags
# --------------------------------------------------------------------------- #

def test_root_mode_draws_no_direction_and_announces_no_arrival() -> None:
    decision = _route(2_000_000.0, 0.0, allow_local=False)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.allow_direction is False
    assert decision.allow_arrival is False


def test_root_fallback_clears_any_stale_local_state() -> None:
    for decision in (
        _route(LIMIT + 1.0, 0.0, allow_local=True),
        _route(1_000.0, LIMIT, allow_local=True),
        _route(1_000.0, 1_000.0, allow_local=False),
        cs.select_route(None, _stack()),
    ):
        assert decision.clear_local is True


def test_local_mode_keeps_its_own_state_and_may_draw() -> None:
    decision = _route(1_000.0, 1_000.0, allow_local=True)
    assert decision.mode == cs.MODE_LOCAL_TRACKING
    assert decision.allow_direction is True
    assert decision.allow_arrival is True
    assert decision.clear_local is False


# --------------------------------------------------------------------------- #
# Names have no authority
# --------------------------------------------------------------------------- #

def _scramble(stack: cs.CoordinateStack, tag: str) -> cs.CoordinateStack:
    """Every name and raw line replaced. Nothing about the geometry changes."""
    def blank(row, i):
        return dataclasses.replace(row, raw_name=f"{tag}{i}", raw=f"{tag}-line-{i}")
    return dataclasses.replace(
        stack,
        root=blank(stack.root, "r"),
        solar=blank(stack.solar, "s"),
        nested=tuple(blank(row, i) for i, row in enumerate(stack.nested)),
    )


@pytest.mark.parametrize("d_root, d_local, allow", [
    (LIMIT + 1.0, 0.0, True),
    (LIMIT, 0.0, True),
    (1_000.0, LIMIT, True),
    (1_000.0, 1_000.0, True),
    (1_000.0, 1_000.0, False),
])
def test_scrambling_every_label_changes_no_decision(d_root, d_local, allow) -> None:
    target, current = _pair(d_root, d_local)
    plain = cs.select_route(target, current, allow_local=allow)
    scrambled = cs.select_route(
        _scramble(target, "xx"), _scramble(current, "yy"), allow_local=allow
    )
    assert (plain.mode, plain.reason) == (scrambled.mode, scrambled.reason)
    assert plain.distance_m == pytest.approx(scrambled.distance_m)
    assert plain.current == scrambled.current
    assert plain.target == scrambled.target


def test_a_changed_solarsystem_id_does_not_block_a_stack_route() -> None:
    """The system frame is per session; Root is not. A schema-1 waypoint stays
    addressable across sessions even when the opaque suffix changed."""
    target, current = _pair(1_000.0, 1_000.0)
    current = dataclasses.replace(
        current,
        solar=dataclasses.replace(current.solar, raw_name="SolarSystem_000000000001"),
    )
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_LOCAL_TRACKING


def test_the_candidate_is_found_by_depth_not_by_list_position() -> None:
    """When a middle row refused, the surviving rows keep their true depths, so
    the last element of `nested` is NOT automatically the candidate."""
    stack = cs.CoordinateStack(
        root=_row(name="Root"),
        solar=_row(name="SolarSystem_1"),
        nested=(_row(1.0, 0.0, 0.0, depth=0), _row(2.0, 0.0, 0.0, depth=1)),
        candidate_depth=2,
    )
    # Depth 2 is not present, which is exactly what a refused outer row leaves.
    assert stack.local_candidate is None


# --------------------------------------------------------------------------- #
# Distance
# --------------------------------------------------------------------------- #

def test_distance_is_euclidean_in_three_axes() -> None:
    assert cs.distance_m((0.0, 0.0, 0.0), (3.0, 4.0, 0.0)) == pytest.approx(5.0)
    assert cs.distance_m((1.0, 2.0, 3.0), (1.0, 2.0, 3.0)) == 0.0
    assert cs.distance_m((0.0, 0.0, 0.0), (0.0, 0.0, -7.5)) == pytest.approx(7.5)


def test_all_three_axes_reach_the_decision() -> None:
    """A distance that dropped an axis would read short and could select local
    from outside the envelope."""
    far = LIMIT / 1.5
    target = _stack(root=(0.0, 0.0, 0.0))
    current = _stack(root=(far, far, far))
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_ROOT_AT_OR_BEYOND_LIMIT


MODES = (cs.MODE_ROOT_APPROACH, cs.MODE_LOCAL_TRACKING, cs.MODE_REFUSED)

# An extreme coordinate is reachable from a corrupt `coordinate_stack` column,
# and the naive sum-of-squares distance OVERFLOWS there long before the distance
# itself would. This runs on the poll thread, where a raise is a dead navigation
# loop rather than a visible error.
EXTREME = cs.CoordinateStack(
    root=_row(1e308, -1e308, 1e308, name="Root"),
    solar=_row(1e308, -1e308, 1e308, name="SolarSystem_1"),
    nested=(_row(-1e308, 1e308, -1e308, depth=0),),
    candidate_depth=0,
)


@pytest.mark.parametrize("target, current", [
    (EXTREME, EXTREME),
    (EXTREME, _stack()),
    (_stack(), EXTREME),
    (_stack(root=(0.0, 0.0, 0.0)), _stack(root=(-0.0, 0.0, 0.0))),
])
def test_select_route_never_raises_on_extreme_input(target, current) -> None:
    for allow in (True, False):
        decision = cs.select_route(target, current, allow_local=allow)
        assert decision.mode in MODES


def test_an_extreme_separation_is_root_and_not_a_crash() -> None:
    decision = cs.select_route(EXTREME, _stack(), allow_local=True)
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.reason == cs.REASON_ROOT_AT_OR_BEYOND_LIMIT

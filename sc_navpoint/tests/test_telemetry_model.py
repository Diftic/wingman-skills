"""The telemetry observation model, exercised without the game, OCR, or a
producer thread.

Wave 2 of `Supercalifragilistic.md` builds this model before any consumer
reads it, so every proof here is about the model's own invariants: that the
ten outcome states from section 7 stay distinct, that a refused attempt can
never refresh a retained timestamp or become authoritative (section 12.4),
that a hard-gate failure can never be rescued by a temporal pass (section
12.1), and that the module stays pure (no Wingman runtime, no OCR, no
database, no logging, no threading, no clock reads), matching
`coordinate_stack.py`.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from types import MappingProxyType

import pytest

import coordinate_stack as cs
import telemetry as tm


def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _epoch(width=1920, height=1080, origin=100.0) -> tm.AlignmentEpoch:
    return tm.AlignmentEpoch(
        screen_resolution=(width, height),
        block_geometry=(0, 0, 667, 175),
        vertical_origin=origin,
        row_mapping=(("camdir", 0), ("root", 7), ("solar", 6)),
    )


def _stack() -> cs.CoordinateStack:
    root = cs.StackRow(x_m=1.0, y_m=2.0, z_m=3.0, raw_name="Root", raw="Zone: Root Pos: 1m 2m 3m")
    solar = cs.StackRow(x_m=1.0, y_m=2.0, z_m=3.0, raw_name="SolarSystem_1", raw="Zone: SolarSystem_1 Pos: 1m 2m 3m")
    return cs.CoordinateStack(root=root, solar=solar)


def _accepted(
    seq=1, wall=100.0, mono=10.0, epoch=None, lane=tm.LANE_STRUCTURAL, freshness=None
) -> tm.Observation:
    return tm.Observation(
        capture_seq=seq,
        wall_clock_ts=wall,
        monotonic_ts=mono,
        epoch=epoch or _epoch(),
        lane=lane,
        stack=_stack(),
        cam_dir=(0.0, 0.0, 0.0),
        hard_gate_result=tm.HARD_GATE_PASSED,
        temporal_result=tm.TEMPORAL_PASSED,
        reason_code="",
        freshness=freshness,
    )


def _refused(
    seq=1,
    wall=100.0,
    mono=10.0,
    epoch=None,
    hard_gate_result=tm.OUTCOME_UNUSABLE_IMAGE,
    temporal_result=tm.TEMPORAL_NOT_EVALUATED,
    reason_code="",
) -> tm.Observation:
    return tm.Observation(
        capture_seq=seq,
        wall_clock_ts=wall,
        monotonic_ts=mono,
        epoch=epoch or _epoch(),
        lane=tm.LANE_STRUCTURAL,
        stack=None,
        cam_dir=None,
        hard_gate_result=hard_gate_result,
        temporal_result=temporal_result,
        reason_code=reason_code,
    )


def _temporally_rejected(seq=1, wall=100.0, mono=10.0, epoch=None) -> tm.Observation:
    return tm.Observation(
        capture_seq=seq,
        wall_clock_ts=wall,
        monotonic_ts=mono,
        epoch=epoch or _epoch(),
        lane=tm.LANE_FAST,
        stack=None,
        cam_dir=None,
        hard_gate_result=tm.HARD_GATE_PASSED,
        temporal_result=tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION,
        reason_code="frame_transition",
    )


# --------------------------------------------------------------------------- #
# The ten outcome constants
# --------------------------------------------------------------------------- #

_OUTCOME_CONSTANTS = (
    tm.OUTCOME_NO_CAPTURE_ATTEMPTED,
    tm.OUTCOME_CAPTURE_IN_PROGRESS,
    tm.OUTCOME_FRESH_AUTHORITATIVE_FIX,
    tm.OUTCOME_STALE_RETAINED_FIX,
    tm.OUTCOME_DISPLAY_ONLY_INTERPOLATION,
    tm.OUTCOME_OVERLAY_ABSENT,
    tm.OUTCOME_UNUSABLE_IMAGE,
    tm.OUTCOME_DECODE_REFUSAL,
    tm.OUTCOME_PARSER_OR_SCANNER_REJECTION,
    tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION,
)


def test_every_outcome_constant_is_distinct() -> None:
    assert len(_OUTCOME_CONSTANTS) == 10
    assert len(set(_OUTCOME_CONSTANTS)) == 10


def test_the_auxiliary_state_constants_never_collide_with_an_outcome() -> None:
    """HARD_GATE_PASSED and the TEMPORAL_* sentinels are a different
    vocabulary (intermediate gate results, not terminal outcomes) and must
    never accidentally share a string with one of the ten."""
    auxiliary = {tm.HARD_GATE_PASSED, tm.TEMPORAL_NOT_EVALUATED, tm.TEMPORAL_PASSED}
    assert auxiliary.isdisjoint(_OUTCOME_CONSTANTS)
    assert len(auxiliary) == 3


def test_freshness_constants_are_distinct_from_outcomes_and_each_other() -> None:
    freshness = {
        tm.FRESHNESS_FRESH_AUTHORITATIVE,
        tm.FRESHNESS_STALE_RETAINED,
        tm.FRESHNESS_NONE_YET,
    }
    assert len(freshness) == 3
    assert freshness.isdisjoint(_OUTCOME_CONSTANTS)


# --------------------------------------------------------------------------- #
# Observation construction invariants
# --------------------------------------------------------------------------- #

def test_an_accepted_attempt_constructs_cleanly() -> None:
    obs = _accepted()
    assert obs.stack is not None
    assert tm.outcome_of(obs) == tm.OUTCOME_FRESH_AUTHORITATIVE_FIX


@pytest.mark.parametrize(
    "outcome",
    [
        tm.OUTCOME_OVERLAY_ABSENT,
        tm.OUTCOME_UNUSABLE_IMAGE,
        tm.OUTCOME_DECODE_REFUSAL,
        tm.OUTCOME_PARSER_OR_SCANNER_REJECTION,
    ],
)
def test_every_hard_gate_failure_constructs_cleanly_and_carries_nothing(outcome) -> None:
    obs = _refused(hard_gate_result=outcome)
    assert obs.stack is None
    assert obs.freshness is None
    assert tm.outcome_of(obs) == outcome


def test_a_temporal_rejection_after_a_passed_hard_gate_constructs_cleanly() -> None:
    obs = _temporally_rejected()
    assert obs.stack is None
    assert obs.freshness is None
    assert tm.outcome_of(obs) == tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION


def test_a_hard_gate_failure_cannot_be_rescued_by_a_temporal_pass() -> None:
    """Section 12.1: temporal logic may reject, never rescue. Attempting to
    construct the rescued state -- a failed hard gate paired with a passed
    temporal check -- must be impossible, not merely unused."""
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=_stack(),
            cam_dir=None,
            hard_gate_result=tm.OUTCOME_UNUSABLE_IMAGE,
            temporal_result=tm.TEMPORAL_PASSED,
            reason_code="",
        )


def test_a_hard_gate_failure_must_report_temporal_not_evaluated() -> None:
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=None,
            cam_dir=None,
            hard_gate_result=tm.OUTCOME_DECODE_REFUSAL,
            temporal_result=tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION,
            reason_code="",
        )


def test_a_failed_hard_gate_cannot_carry_a_stack() -> None:
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=_stack(),
            cam_dir=None,
            hard_gate_result=tm.OUTCOME_OVERLAY_ABSENT,
            temporal_result=tm.TEMPORAL_NOT_EVALUATED,
            reason_code="",
        )


def test_a_temporal_rejection_cannot_carry_a_stack() -> None:
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=_stack(),
            cam_dir=None,
            hard_gate_result=tm.HARD_GATE_PASSED,
            temporal_result=tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION,
            reason_code="",
        )


def test_an_accepted_fix_must_carry_a_stack() -> None:
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=None,
            cam_dir=None,
            hard_gate_result=tm.HARD_GATE_PASSED,
            temporal_result=tm.TEMPORAL_PASSED,
            reason_code="",
        )


def test_a_refused_attempt_can_never_be_constructed_as_authoritative() -> None:
    """No combination of a failed hard gate or a temporal rejection may carry
    a non-None `freshness`: the type itself forbids the "refused but
    authoritative" state, rather than relying on every caller to check."""
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_STRUCTURAL,
            stack=None,
            cam_dir=None,
            hard_gate_result=tm.OUTCOME_DECODE_REFUSAL,
            temporal_result=tm.TEMPORAL_NOT_EVALUATED,
            reason_code="",
            freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE,
        )


def test_a_temporal_rejection_can_never_be_constructed_as_authoritative() -> None:
    """M4 (QA finding): distinct from the hard-gate case above. A passed hard
    gate followed by a temporal rejection (OUTCOME_INCOMPATIBLE_FRAME_TRANSITION)
    must ALSO be unable to carry a non-None freshness -- this exercises the
    second, separate guard in `__post_init__`, not the first one."""
    with pytest.raises(ValueError):
        tm.Observation(
            capture_seq=1,
            wall_clock_ts=100.0,
            monotonic_ts=10.0,
            epoch=_epoch(),
            lane=tm.LANE_FAST,
            stack=None,
            cam_dir=None,
            hard_gate_result=tm.HARD_GATE_PASSED,
            temporal_result=tm.OUTCOME_INCOMPATIBLE_FRAME_TRANSITION,
            reason_code="",
            freshness=tm.FRESHNESS_STALE_RETAINED,
        )


def test_an_unknown_lane_refuses_construction() -> None:
    with pytest.raises(ValueError):
        _accepted(lane="fastest-ever")


def test_outcome_of_a_stale_retained_observation_is_stale_not_fresh() -> None:
    """M11 (QA finding): a stale-retained observation still has
    hard_gate_result == HARD_GATE_PASSED and temporal_result ==
    TEMPORAL_PASSED (only `freshness` changed), so `outcome_of` must check
    `freshness` explicitly rather than inferring fresh from the gates alone."""
    obs = _accepted(freshness=tm.FRESHNESS_STALE_RETAINED)
    assert tm.outcome_of(obs) == tm.OUTCOME_STALE_RETAINED_FIX
    assert tm.outcome_of(obs) != tm.OUTCOME_FRESH_AUTHORITATIVE_FIX


# --------------------------------------------------------------------------- #
# diagnostics immutability (QA finding: `Mapping` was typed but defaulted to a
# real mutable dict, so a caller holding the reference could mutate a
# supposedly frozen observation).
# --------------------------------------------------------------------------- #

def test_diagnostics_defaults_to_an_immutable_mapping() -> None:
    obs = _accepted()
    assert isinstance(obs.diagnostics, MappingProxyType)
    with pytest.raises(TypeError):
        obs.diagnostics["cost"] = 12.3


def test_diagnostics_passed_at_construction_is_coerced_to_immutable_too() -> None:
    obs = tm.Observation(
        capture_seq=1,
        wall_clock_ts=100.0,
        monotonic_ts=10.0,
        epoch=_epoch(),
        lane=tm.LANE_STRUCTURAL,
        stack=_stack(),
        cam_dir=None,
        hard_gate_result=tm.HARD_GATE_PASSED,
        temporal_result=tm.TEMPORAL_PASSED,
        reason_code="",
        diagnostics={"cost": 7.1, "margin": 3.2},
    )
    assert isinstance(obs.diagnostics, MappingProxyType)
    assert obs.diagnostics["cost"] == 7.1
    with pytest.raises(TypeError):
        obs.diagnostics["cost"] = 0.0


def test_mutating_the_callers_own_diagnostics_dict_afterward_does_not_reach_in() -> None:
    """The observation must hold a COPY, not a view over the caller's dict:
    otherwise a caller mutating their own reference after construction could
    still change a "frozen" observation's diagnostics."""
    caller_dict = {"cost": 1.0}
    obs = tm.Observation(
        capture_seq=1,
        wall_clock_ts=100.0,
        monotonic_ts=10.0,
        epoch=_epoch(),
        lane=tm.LANE_STRUCTURAL,
        stack=_stack(),
        cam_dir=None,
        hard_gate_result=tm.HARD_GATE_PASSED,
        temporal_result=tm.TEMPORAL_PASSED,
        reason_code="",
        diagnostics=caller_dict,
    )
    caller_dict["cost"] = 999.0
    assert obs.diagnostics["cost"] == 1.0


# --------------------------------------------------------------------------- #
# is_authoritative
# --------------------------------------------------------------------------- #

def test_none_is_not_authoritative() -> None:
    assert tm.is_authoritative(None, now=0.0, stale_bound_s=1.0) is False


def test_a_fresh_observation_within_the_bound_is_authoritative() -> None:
    obs = _accepted(mono=10.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    assert tm.is_authoritative(obs, now=10.5, stale_bound_s=1.0) is True


def test_a_stale_retained_observation_is_not_authoritative() -> None:
    """Wave 6's exit gate: stale data cannot reach authoritative consumers."""
    obs = _accepted(freshness=tm.FRESHNESS_STALE_RETAINED)
    assert tm.is_authoritative(obs, now=10.1, stale_bound_s=100.0) is False


def test_is_authoritative_ages_out_past_the_stale_bound_even_without_a_new_attempt() -> None:
    """Design fix (QA finding): `is_authoritative` must not report `True`
    forever on a snapshot nobody re-evaluated. A producer that dies silently
    leaves its last observation tagged FRESH_AUTHORITATIVE in
    `observation.freshness`, but enough elapsed time must still revoke
    authority here, exactly as `freshness_state` reports it stale."""
    obs = _accepted(mono=10.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    assert tm.is_authoritative(obs, now=20.0, stale_bound_s=1.0) is False


@pytest.mark.parametrize(
    "mono, freshness, now, stale_bound_s",
    [
        (10.0, tm.FRESHNESS_FRESH_AUTHORITATIVE, 10.5, 1.0),
        (10.0, tm.FRESHNESS_FRESH_AUTHORITATIVE, 20.0, 1.0),
        (10.0, tm.FRESHNESS_STALE_RETAINED, 10.1, 100.0),
    ],
)
def test_is_authoritative_agrees_with_freshness_state_by_construction(
    mono, freshness, now, stale_bound_s
) -> None:
    """Design fix (QA finding): `is_authoritative` must not be a second,
    independently-maintained classifier that can drift from
    `freshness_state`. Proven here as an explicit equivalence across several
    (freshness, age) combinations, on top of `is_authoritative` calling
    `freshness_state` directly in the implementation."""
    obs = _accepted(mono=mono, freshness=freshness)
    expected = tm.freshness_state(obs, now, stale_bound_s) == tm.FRESHNESS_FRESH_AUTHORITATIVE
    assert tm.is_authoritative(obs, now, stale_bound_s) == expected


# --------------------------------------------------------------------------- #
# transition(): the refusal-cannot-refresh-timestamp and
# refusal-cannot-become-authoritative invariants
# --------------------------------------------------------------------------- #

def test_an_accepted_attempt_becomes_the_new_fresh_state() -> None:
    attempt = _accepted(seq=5, wall=500.0, mono=50.0)
    result = tm.transition(previous=None, attempt=attempt, now=999.0)
    assert result is not None
    assert result.freshness == tm.FRESHNESS_FRESH_AUTHORITATIVE
    assert result.capture_seq == 5
    assert result.monotonic_ts == 50.0


def test_a_refused_attempt_with_no_previous_observation_produces_nothing() -> None:
    result = tm.transition(previous=None, attempt=_refused(), now=999.0)
    assert result is None


def test_a_refused_attempt_retains_the_previous_observation_as_stale() -> None:
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    result = tm.transition(previous=previous, attempt=_refused(seq=2, wall=200.0, mono=20.0), now=999.0)
    assert result is not None
    assert result.freshness == tm.FRESHNESS_STALE_RETAINED


def test_a_refused_attempt_never_refreshes_the_retained_timestamp() -> None:
    """Section 12.4, the load-bearing rule of this whole module: a refused
    frame must never refresh the timestamp on the retained fix."""
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    later_refusal = _refused(seq=2, wall=99999.0, mono=99999.0)
    result = tm.transition(previous=previous, attempt=later_refusal, now=999.0)
    assert result.wall_clock_ts == 100.0
    assert result.monotonic_ts == 10.0
    assert result.capture_seq == 1


def test_a_refused_attempt_never_becomes_authoritative() -> None:
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    result = tm.transition(previous=previous, attempt=_refused(seq=2), now=999.0)
    assert tm.is_authoritative(result, now=10.0, stale_bound_s=1.0) is False


def test_a_temporally_rejected_attempt_also_retains_the_previous_as_stale_without_touching_it() -> None:
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    result = tm.transition(
        previous=previous, attempt=_temporally_rejected(seq=2, wall=777.0, mono=777.0), now=999.0
    )
    assert result.freshness == tm.FRESHNESS_STALE_RETAINED
    assert result.monotonic_ts == 10.0
    assert tm.is_authoritative(result, now=10.0, stale_bound_s=1.0) is False


def test_feeding_a_previously_retained_observation_back_in_as_attempt_raises() -> None:
    """Design fix (QA finding): `transition()` used to accept anything with a
    non-None `freshness` as proof of acceptance, so passing the retained
    STALE observation back in as `attempt` re-tagged that same object
    FRESH_AUTHORITATIVE using its own ORIGINAL, possibly very old timestamps
    -- silently resurrecting stale data as if it had just been captured. That
    misuse must now raise instead of succeeding quietly."""
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    stale = tm.transition(previous=previous, attempt=_refused(seq=2), now=999.0)
    assert stale.freshness == tm.FRESHNESS_STALE_RETAINED
    with pytest.raises(ValueError):
        tm.transition(previous=previous, attempt=stale, now=9999.0)


def test_feeding_a_previously_accepted_fresh_observation_back_in_as_attempt_also_raises() -> None:
    """The same guard must fire for a FRESH (not just stale) retained
    observation: `attempt` must always be an unretained record."""
    fresh = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    assert fresh.freshness == tm.FRESHNESS_FRESH_AUTHORITATIVE
    with pytest.raises(ValueError):
        tm.transition(previous=None, attempt=fresh, now=999.0)


def test_a_second_accepted_attempt_replaces_the_stale_state_and_is_fresh_again() -> None:
    previous = tm.transition(
        previous=None, attempt=_accepted(seq=1, wall=100.0, mono=10.0), now=0.0
    )
    stale = tm.transition(previous=previous, attempt=_refused(seq=2), now=999.0)
    fresh_again = tm.transition(
        previous=stale, attempt=_accepted(seq=3, wall=300.0, mono=30.0), now=999.0
    )
    assert fresh_again.freshness == tm.FRESHNESS_FRESH_AUTHORITATIVE
    assert fresh_again.monotonic_ts == 30.0
    assert fresh_again.capture_seq == 3


# --------------------------------------------------------------------------- #
# freshness_state and age_s
# --------------------------------------------------------------------------- #

def test_age_s_is_now_minus_monotonic_ts() -> None:
    obs = _accepted(mono=10.0)
    assert tm.age_s(obs, now=15.0) == 5.0


def test_no_observation_is_none_yet() -> None:
    assert tm.freshness_state(None, now=0.0, stale_bound_s=1.0) == tm.FRESHNESS_NONE_YET


def test_a_fresh_observation_within_the_bound_stays_fresh() -> None:
    obs = _accepted(mono=10.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    assert tm.freshness_state(obs, now=10.5, stale_bound_s=1.0) == tm.FRESHNESS_FRESH_AUTHORITATIVE


def test_a_fresh_observation_past_the_bound_reads_as_stale_without_a_new_attempt() -> None:
    """A stalled producer (no new attempts at all) must still be caught by
    age alone, not only by an active refusal."""
    obs = _accepted(mono=10.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    assert tm.freshness_state(obs, now=20.0, stale_bound_s=1.0) == tm.FRESHNESS_STALE_RETAINED


def test_an_already_stale_observation_stays_stale_regardless_of_age() -> None:
    obs = _accepted(mono=10.0, freshness=tm.FRESHNESS_STALE_RETAINED)
    assert tm.freshness_state(obs, now=10.1, stale_bound_s=100.0) == tm.FRESHNESS_STALE_RETAINED


# --------------------------------------------------------------------------- #
# AlignmentEpoch identity
#
# `same_epoch()` was deleted (QA finding: it was `return a == b` with no
# non-test caller and no behaviour plain `==` did not already give), so
# identity is proven directly through dataclass equality and hashing here.
# --------------------------------------------------------------------------- #

def test_two_epochs_with_identical_fields_share_one_identity() -> None:
    a = _epoch()
    b = _epoch()
    assert a is not b
    assert a == b
    assert hash(a) == hash(b)


@pytest.mark.parametrize(
    "changed",
    [
        {"width": 2560},
        {"height": 1440},
        {"origin": 101.0},
    ],
)
def test_any_changed_field_starts_a_new_identity(changed) -> None:
    a = _epoch()
    b = _epoch(**changed)
    assert a != b


def test_a_changed_row_mapping_starts_a_new_identity() -> None:
    a = _epoch()
    b = tm.AlignmentEpoch(
        screen_resolution=a.screen_resolution,
        block_geometry=a.block_geometry,
        vertical_origin=a.vertical_origin,
        row_mapping=(("camdir", 0), ("root", 8), ("solar", 6)),
    )
    assert a != b


# --------------------------------------------------------------------------- #
# DisplayEstimate: structurally distinct from Observation
# --------------------------------------------------------------------------- #

def test_a_display_estimate_is_not_an_observation() -> None:
    estimate = tm.DisplayEstimate(position_m=(1.0, 2.0, 3.0), wall_clock_ts=100.0)
    assert not isinstance(estimate, tm.Observation)
    assert estimate.outcome == tm.OUTCOME_DISPLAY_ONLY_INTERPOLATION


def test_a_display_estimate_carries_no_authority_fields_at_all() -> None:
    """No `freshness`, no gate results: there is nothing on this type a
    caller could (mis)read as authoritative."""
    estimate = tm.DisplayEstimate(position_m=(1.0, 2.0, 3.0), wall_clock_ts=100.0)
    assert not hasattr(estimate, "freshness")
    assert not hasattr(estimate, "hard_gate_result")
    assert not hasattr(estimate, "temporal_result")


# --------------------------------------------------------------------------- #
# current_status: the ten states from a consumer's point of view
# --------------------------------------------------------------------------- #

def test_no_observation_and_nothing_in_flight_is_no_capture_attempted() -> None:
    status = tm.current_status(
        latest=None, capture_in_progress=False, last_refusal_outcome=None,
        now=0.0, stale_bound_s=1.0,
    )
    assert status == tm.OUTCOME_NO_CAPTURE_ATTEMPTED


def test_a_capture_in_flight_always_wins_even_with_a_retained_observation() -> None:
    obs = _accepted(mono=0.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    status = tm.current_status(
        latest=obs, capture_in_progress=True, last_refusal_outcome=None,
        now=0.0, stale_bound_s=1.0,
    )
    assert status == tm.OUTCOME_CAPTURE_IN_PROGRESS


def test_a_refusal_before_anything_was_ever_accepted_surfaces_its_own_outcome() -> None:
    status = tm.current_status(
        latest=None, capture_in_progress=False,
        last_refusal_outcome=tm.OUTCOME_OVERLAY_ABSENT,
        now=0.0, stale_bound_s=1.0,
    )
    assert status == tm.OUTCOME_OVERLAY_ABSENT


def test_a_fresh_retained_observation_reports_fresh() -> None:
    obs = _accepted(mono=0.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    status = tm.current_status(
        latest=obs, capture_in_progress=False, last_refusal_outcome=None,
        now=0.5, stale_bound_s=1.0,
    )
    assert status == tm.OUTCOME_FRESH_AUTHORITATIVE_FIX


def test_a_retained_observation_past_the_stale_bound_reports_stale() -> None:
    obs = _accepted(mono=0.0, freshness=tm.FRESHNESS_FRESH_AUTHORITATIVE)
    status = tm.current_status(
        latest=obs, capture_in_progress=False, last_refusal_outcome=None,
        now=5.0, stale_bound_s=1.0,
    )
    assert status == tm.OUTCOME_STALE_RETAINED_FIX


# --------------------------------------------------------------------------- #
# Purity: no Wingman runtime, no OCR, no database, no logging, no threading,
# no clock reads
# --------------------------------------------------------------------------- #

_FORBIDDEN_MODULES = (
    "api",
    "api.enums",
    "api.interface",
    "skills",
    "skill_base",
    "logging",
    "mss",
    "numpy",
    "cv2",
    "PIL",
    "threading",
    "asyncio",
    "sqlite3",
    "database",
    "main",
    "scanner",
    "overlay_reader",
    "overlay_win32",
    "overlay_fields",
    "navigation",
    "ring_overlay",
    "win32api",
    "win32gui",
    "requests",
)


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_the_module_imports_nothing_impure() -> None:
    source = (_skill_dir() / "telemetry.py").read_text(encoding="utf-8")
    imported = _imported_module_roots(source)
    forbidden_hit = imported & set(_FORBIDDEN_MODULES)
    assert forbidden_hit == set(), f"telemetry.py imports impure module(s): {forbidden_hit}"


def test_the_module_reads_no_clock() -> None:
    """`now` must always arrive from the caller. `time.time`, `time.monotonic`,
    `datetime.now`, and a bare `import time`/`import datetime` are all
    disallowed, mirroring `coordinate_stack.py`'s own no-clock-reads design."""
    source = (_skill_dir() / "telemetry.py").read_text(encoding="utf-8")
    imported = _imported_module_roots(source)
    assert "time" not in imported
    assert "datetime" not in imported


def test_the_module_declares_no_threading_or_async_primitives() -> None:
    source = (_skill_dir() / "telemetry.py").read_text(encoding="utf-8")
    assert "async def" not in source
    assert "Thread(" not in source


# --------------------------------------------------------------------------- #
# Release manifests
# --------------------------------------------------------------------------- #

def test_telemetry_is_in_both_release_manifests() -> None:
    """This project has had three release omissions from updating only one
    manifest. `update_release.py` builds `release_version/` and
    `skill_installer_config.json` drives the installer; neither reads the
    other, so both must be checked explicitly."""
    release = (_skill_dir() / "update_release.py").read_text(encoding="utf-8")
    installer = json.loads(
        (_skill_dir() / "skill_installer_config.json").read_text(encoding="utf-8")
    )
    assert '"telemetry.py",' in release
    assert "telemetry.py" in installer["files"]


def test_the_two_release_manifests_still_agree() -> None:
    """The existing parity check (`test_coordinate_stack_navigation.py`)
    proves this generally; re-proving it here means this file alone is
    sufficient evidence that adding telemetry.py did not desynchronise the
    two manifests."""
    release_src = (_skill_dir() / "update_release.py").read_text(encoding="utf-8")
    files_block = release_src.split("RELEASE_FILES = [")[1].split("]")[0]
    dirs_block = release_src.split("RELEASE_DIRS = [")[1].split("]")[0]
    listed = set(re.findall(r'"([^"]+)"', files_block))
    listed_dirs = set(re.findall(r'"([^"]+)"', dirs_block))
    installer = json.loads(
        (_skill_dir() / "skill_installer_config.json").read_text(encoding="utf-8")
    )
    assert listed - set(installer["files"]) == {"installer.bat", "TESTER_README.md"}
    assert set(installer["files"]) - listed == set()
    assert listed_dirs == set(installer["dirs"])

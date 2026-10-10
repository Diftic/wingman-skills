"""The calibration switch for open-space direction.

System-frame direction is uncalibrated: measured 108.7 degrees out against a
known in-game marker on 2026-07-26. The ring therefore draws no bubble out
there. This switch draws one anyway, so a calibration flight can compare it
against a direction the pilot already knows.

The whole risk of this feature is that the wrong numbers escape the test. These
tests pin the containment: OFF by default, no effect on the spoken guidance or
the HUD page, and anything it does produce is flagged `uncalibrated`.
"""

from __future__ import annotations

import navigation
from navigation import ring_deflection, space_guidance


_HERE = (-1.89408e10, -2.61006e9, 627_710.0)
_THERE = (-1.89308e10, -2.61006e9, 627_710.0)
_CAMDIR = (0.0, 0.0, 0.0)


def _space_pos(**over) -> dict:
    pos = {
        "x": _HERE[0], "y": _HERE[1], "z": _HERE[2],
        "body": "", "system_frame": True,
        "frame_id": "729494885314", "camdir": _CAMDIR,
    }
    pos.update(over)
    return pos


def _space_target(**over) -> dict:
    target = {
        "x": _THERE[0], "y": _THERE[1], "z": _THERE[2],
        "body": "", "frame": "system", "frame_id": "729494885314",
    }
    target.update(over)
    return target


def test_the_convention_is_still_flagged_uncalibrated() -> None:
    """If this ever flips to True the switch has served its purpose and these
    tests need rewriting, which is the point of asserting it."""
    assert navigation.SPACE_DIRECTION_CALIBRATED is False


def test_the_gate_is_closed_by_default() -> None:
    assert ring_deflection(_space_pos(), _space_target(), 1.0) is None


def test_the_switch_opens_it() -> None:
    result = ring_deflection(
        _space_pos(), _space_target(), 1.0, allow_uncalibrated_space=True
    )
    assert result is not None
    yaw, pitch = result
    assert isinstance(yaw, float) and isinstance(pitch, float)


def test_the_switch_does_not_reach_the_spoken_guidance() -> None:
    """Voice keeps withholding. A wrong direction read aloud is what sent the
    user flying the wrong way; only the ring is allowed to show the test."""
    guidance = space_guidance(_CAMDIR, _HERE, _THERE)
    assert "horizontal_offset_deg" not in guidance
    assert guidance["turn_instruction"] == "Direction not available in open space"


def test_numbers_from_the_switch_carry_the_uncalibrated_flag() -> None:
    guidance = space_guidance(_CAMDIR, _HERE, _THERE, allow_uncalibrated=True)
    assert guidance["uncalibrated"] is True
    assert "horizontal_offset_deg" in guidance


def test_the_switch_does_not_weaken_any_other_refusal() -> None:
    """It opens exactly one gate. Stale readings, wrong-session frames and
    missing facing must still refuse with the switch on."""
    on = {"allow_uncalibrated_space": True}
    assert ring_deflection(_space_pos(), _space_target(), 999.0, **on) is None
    assert ring_deflection(_space_pos(), _space_target(), None, **on) is None
    assert ring_deflection(
        _space_pos(), _space_target(frame_id="111111111111"), 1.0, **on
    ) is None
    assert ring_deflection(_space_pos(camdir=None), _space_target(), 1.0, **on) is None


def test_the_switch_does_nothing_on_a_surface() -> None:
    """Surface bearings are validated and must behave identically either way."""
    pos = {"x": 100.0, "y": 0.0, "z": 295_000.0, "body": "Daymar", "heading": 0.0}
    target = {"x": 1100.0, "y": 0.0, "z": 295_000.0, "body": "Daymar", "frame": "local"}
    assert ring_deflection(pos, target, 1.0) == ring_deflection(
        pos, target, 1.0, allow_uncalibrated_space=True
    )


def test_the_skill_does_not_enable_experiments_from_saved_settings() -> None:
    from main import SC_NavPoint

    skill = SC_NavPoint.__new__(SC_NavPoint)
    skill.retrieve_custom_property_value = lambda *args: True
    assert skill._get_space_direction_test() is False


def test_the_config_omits_development_and_obsolete_settings() -> None:
    import pathlib

    cfg = (
        pathlib.Path(__file__).resolve().parent.parent / "default_config.yaml"
    ).read_text(encoding="utf-8")
    assert "id: space_direction_test" not in cfg
    assert "id: poll_interval" not in cfg
    assert "CALIBRATION ONLY" not in cfg

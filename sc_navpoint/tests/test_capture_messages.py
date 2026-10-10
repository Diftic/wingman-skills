"""What the player is told when a capture produces nothing, and who is told at all.

Three sites used to collapse a dozen distinct causes into two messages, and a
fourth said nothing whatever. `mark_location` answered every falsy capture with
"Could not extract position from screen" plus the `r_displayinfo 2` console
command, and answered a payload with no usable frame with a different error and
a byte-identical hint, even though that path had just READ the overlay it was
telling the player to switch on. `update_position` said something different
again. And `navigate_to` never emitted an instruction at all, which was worse
than a wrong one: both its refusal gates key on a truthy `pos_frame`, so a total
capture failure walked past them, set the target, started the poll thread and
reported a deferred state.

Every refusal here is TERMINAL, because there is no second reader. So three
rules govern the text and are asserted below: say what happened without
instrument-fault language, give exactly ONE action or say plainly there is none,
and say that nothing was saved.

`r_displayinfo 2` belongs to ONE kind: `absent`, meaning `overlay_is_present`
returned False. The skill never types it; the player does.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
from database import NavPointDatabase  # noqa: E402


_MAIN_SRC = (Path(main.__file__).with_name("main.py")).read_text(encoding="utf-8")

# Every kind that means "no waypoint came out of this".
_FAILURE_KINDS = [
    fields.KIND_NO_READER,
    fields.KIND_NO_GRAB,
    fields.KIND_UNUSABLE,
    fields.KIND_ABSENT,
    fields.KIND_DECODE_ERROR,
    fields.KIND_GATE,
    fields.KIND_REJECT,
    fields.KIND_UNEXPLAINED,
    fields.KIND_NO_FRAME,
]

_GATE_IDS = [
    fields.GATE_NO_SYSTEM_LINE,
    fields.GATE_REFUSED_ABOVE,
    fields.GATE_BODY_SCALE,
    fields.GATE_NO_COORDINATE,
    fields.GATE_NO_ROOT,
]


class _Printr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message, color=None, server_only=False):
        self.calls.append((message, color, server_only))


class _RecordingUI:
    def __init__(self) -> None:
        self.url = ""
        self.set_active_target_calls: list = []

    def set_position(self, pos_data: dict) -> None:
        pass

    def set_active_target(self, target) -> None:
        self.set_active_target_calls.append(target)

    def notify_update(self) -> None:
        pass


def _outcome(kind: str, **kwargs) -> fields.CaptureOutcome:
    return fields.CaptureOutcome(kind=kind, **kwargs)


def _skill(db=None) -> main.SC_NavPoint:
    """A skill whose capture is dictated, so the MESSAGE is what is under test."""
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = db
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._hud_opened = False
    skill._get_display = lambda: 1
    skill._get_poll_interval = lambda: 5
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._start_nav_polling = MagicMock()
    skill._stop_nav_polling = MagicMock()
    skill._sync_ring = lambda: None
    return skill


def _capturing(skill: main.SC_NavPoint, pos_data, outcome) -> None:
    """Wire a capture that returns `pos_data` and ends on `outcome`."""

    async def _capture(attempts: int = 1):
        skill._last_outcome = outcome
        return dict(pos_data) if pos_data else pos_data

    skill._capture_position = _capture
    skill._last_outcome = outcome


def _error_for(kind: str, **kwargs) -> dict:
    return _skill()._capture_error(_outcome(kind, **kwargs))


# --------------------------------------------------------------------- #
# The three rules
# --------------------------------------------------------------------- #


def test_every_failure_says_nothing_was_saved() -> None:
    """Every one of these paths stores nothing. The player should never have to
    infer that from the absence of a confirmation."""
    for kind in _FAILURE_KINDS:
        assert "Nothing was saved." in _error_for(kind)["error"], kind


def test_every_failure_names_an_action_or_says_there_is_none() -> None:
    """A refusal with no next step and no statement that there is none leaves
    the player guessing, and guessing here means flying somewhere unmarked."""
    for kind in _FAILURE_KINDS:
        result = _error_for(kind)
        has_action = "There is no action here" in result["error"] or any(
            verb in result["error"] for verb in
            ("Check ", "Look at ", "Ask again", "Point away", "Hold still")
        )
        # `absent` carries its action in the hint, which is relayed verbatim.
        assert has_action or "hint" in result, kind


def test_no_failure_message_blames_the_instrument() -> None:
    """A refusal is the reader correctly declining. "Malfunctioning" sends the
    player hunting a fault that does not exist, which is the reasoning already
    recorded for the ring strings."""
    for kind in _FAILURE_KINDS:
        text = _error_for(kind)["error"].lower()
        for word in ("malfunction", "broken", "error in", "bug"):
            assert word not in text, (kind, word)


def test_no_failure_message_names_a_reader_that_is_not_there() -> None:
    for kind in _FAILURE_KINDS:
        assert "vision" not in _error_for(kind)["error"].lower(), kind


# --------------------------------------------------------------------- #
# `r_displayinfo 2` is reserved for one kind, and one kind only
# --------------------------------------------------------------------- #


def test_only_an_absent_overlay_carries_a_hint(tmp_path) -> None:
    """AC-3. The hint is relayed word for word by the model, so a hint on a
    capture that just READ the overlay is a console command read out for no
    reason."""
    for kind in _FAILURE_KINDS:
        skill = _skill(db=NavPointDatabase(str(tmp_path)))
        _capturing(skill, None, _outcome(kind))
        result = json.loads(asyncio.run(skill.mark_location()))
        assert ("hint" in result) == (kind == fields.KIND_ABSENT), kind


def test_only_an_absent_overlay_mentions_the_console_command(tmp_path) -> None:
    """AC-4, on the whole result rather than the hint field, so the command
    cannot reappear inside the error text instead."""
    for kind in _FAILURE_KINDS:
        skill = _skill(db=NavPointDatabase(str(tmp_path)))
        _capturing(skill, None, _outcome(kind))
        raw = asyncio.run(skill.mark_location())
        assert ("r_displayinfo" in raw) == (kind == fields.KIND_ABSENT), kind


def test_the_absent_hint_is_the_wording_that_already_shipped() -> None:
    result = _error_for(fields.KIND_ABSENT)
    assert "r_displayinfo 2" in result["hint"]
    assert "the player must type it manually" in result["hint"]


def test_the_console_command_is_produced_in_exactly_one_place() -> None:
    """AC-2. Two survivors in the source: the module docstring, which is
    documentation, and the single hint. It was four."""
    assert _MAIN_SRC.count("r_displayinfo 2") == 2


# --------------------------------------------------------------------- #
# The five gates mean genuinely different things
# --------------------------------------------------------------------- #


def test_each_gate_produces_its_own_message_and_an_action() -> None:
    """AC-6. The four decode gates share one action deliberately: the single
    lever the player holds over an overlay that partly failed to read is what is
    rendered behind it. The MESSAGES still differ, because each carries its own
    gate's clause, so no two gates are reported as the same event."""
    seen = {}
    for gate_id in _GATE_IDS:
        result = _error_for(fields.KIND_GATE, gate=f"{gate_id}: clause for {gate_id}")
        assert f"clause for {gate_id}" in result["error"], gate_id
        assert result["error"] not in seen, (gate_id, seen.get(result["error"]))
        seen[result["error"]] = gate_id
        has_action = (
            "There is no action here" in result["error"]
            or main.SC_NavPoint._REDUCE_SCENERY in result["error"]
        )
        assert has_action, gate_id
    assert len(seen) == 5


def test_body_scale_says_there_is_no_action_rather_than_try_again() -> None:
    """It is a refusal by design on a body surface. Looking again produces the
    same reading, so "try again" would be a lie the player pays for in time."""
    text = _error_for(fields.KIND_GATE, gate="body_scale: a container reads 330km")["error"]
    assert "There is no action here" in text
    assert "try again" not in text.lower()
    assert "ask again" not in text.lower()


def test_the_repeatable_kinds_say_there_is_no_action() -> None:
    for kind in (fields.KIND_UNEXPLAINED, fields.KIND_NO_FRAME):
        text = _error_for(kind)["error"]
        assert "There is no action here" in text, kind
        assert "try again" not in text.lower(), kind
        assert "ask again" not in text.lower(), kind


def test_a_gate_that_named_nothing_still_produces_a_message() -> None:
    text = _error_for(fields.KIND_GATE, gate="")["error"]
    assert "Nothing was saved." in text


def test_a_gate_walk_that_raised_is_not_partitioned_into_a_clause() -> None:
    """`_refusal_gate` names itself "gate unknown (TypeError: ...)" when the
    diagnostic walk raises, and that note carries its OWN ": ". Partitioning it
    handed the player the exception message as if it were a gate's clause, so
    the sentence ended mid-thought on a stray paren. It is an unnamed gate, and
    it has to read like one.

    The gate string is produced by the real `_refusal_gate` rather than typed
    out here, so a change to its wording cannot leave this test passing against
    a shape production no longer emits."""
    skill = _skill()
    gate = skill._refusal_gate(["a row shape the walk was not built for"])
    # Precondition: the note really does contain the separator that mangled it.
    assert gate.startswith("gate unknown ("), gate
    assert ": " in gate, gate

    text = skill._capture_error(_outcome(fields.KIND_GATE, gate=gate))["error"]

    assert "no gate named itself" in text
    assert "Nothing was saved." in text
    # No fragment of the exception reaches the player, and nothing dangles.
    assert "TypeError" not in text
    assert "gate unknown" not in text
    assert ")." not in text


def test_a_scanner_reason_reaches_the_player_as_a_clause() -> None:
    text = _error_for(fields.KIND_REJECT, reject_reason="unreadable_units")["error"]
    assert "the unit on a coordinate could not be read" in text
    # The log vocabulary itself means nothing in a cockpit.
    assert "unreadable_units" not in text


def test_an_unknown_reason_still_produces_a_message_and_asks_for_a_look() -> None:
    """An unrecognised reason defaults to the frame-quality action, which is the
    safe direction: it asks for one more look rather than declaring nothing can
    be done about something that might be recoverable."""
    text = _error_for(fields.KIND_REJECT, reject_reason="something_new")["error"]
    assert "Nothing was saved." in text
    assert "something_new" not in text
    assert main.SC_NavPoint._HOLD_STILL in text


def test_a_repeatable_reject_reason_does_not_ask_for_a_retry() -> None:
    """A `body_token` that fails the plausibility gate is a property of the
    LOCATION, not of the frame: the same token reads the same way every time and
    fails the same gate every time. Asking again sends the player round a loop
    that cannot terminate."""
    text = _error_for(fields.KIND_REJECT, reject_reason="implausible_body")["error"]
    assert "There is no action here" in text
    assert "ask again" not in text.lower()
    assert "retry" not in text.lower()


def test_a_frame_quality_reject_reason_does_ask_for_a_second_look() -> None:
    """The other side of the same rule. These three genuinely can read
    differently on a steadier frame, so refusing to ask again would cost the
    player a waypoint they could have had."""
    for reason in ("unreadable_units", "frame_mismatch", "coord_mismatch"):
        text = _error_for(fields.KIND_REJECT, reject_reason=reason)["error"]
        assert main.SC_NavPoint._HOLD_STILL in text, reason
        assert "There is no action here" not in text, reason


def test_the_display_number_reaches_the_grab_failure_message() -> None:
    skill = _skill()
    skill._get_display = lambda: 3
    text = skill._capture_error(_outcome(fields.KIND_NO_GRAB))["error"]
    assert "display 3" in text


# --------------------------------------------------------------------- #
# One table, three tools
# --------------------------------------------------------------------- #


def test_all_three_tools_report_the_same_kind_identically(tmp_path) -> None:
    """AC-10. Three copies of a refusal message drift, and two of them already
    had before this table existed."""
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Cave", "", "Daymar", 0.0, 0.0, 0.0)
    for kind in _FAILURE_KINDS:
        errors = []
        for tool in ("mark_location", "update_position"):
            skill = _skill(db=db)
            _capturing(skill, None, _outcome(kind))
            errors.append(json.loads(asyncio.run(getattr(skill, tool)()))["error"])
        skill = _skill(db=db)
        _capturing(skill, None, _outcome(kind))
        errors.append(json.loads(asyncio.run(skill.navigate_to("Cave")))["error"])
        assert len(set(errors)) == 1, (kind, errors)


def test_update_position_no_longer_answers_with_a_flat_string(tmp_path) -> None:
    skill = _skill(db=NavPointDatabase(str(tmp_path)))
    _capturing(skill, None, _outcome(fields.KIND_UNUSABLE))
    result = json.loads(asyncio.run(skill.update_position()))
    assert result["capture_kind"] == fields.KIND_UNUSABLE
    assert "Look at darker ground" in result["error"]


def test_the_no_frame_mark_refusal_keeps_its_own_wording(tmp_path) -> None:
    """The kind the CALLER can prove wins: the returned payload carries no
    frame, which is a stronger fact than a field that may be from an earlier
    capture."""
    skill = _skill(db=NavPointDatabase(str(tmp_path)))
    _capturing(skill, {"body": "", "x": 1.0}, _outcome(fields.KIND_OK))
    result = json.loads(asyncio.run(skill.mark_location()))
    assert result["capture_kind"] == fields.KIND_NO_FRAME
    assert "No usable coordinate frame" in result["error"]
    assert "hint" not in result


# --------------------------------------------------------------------- #
# THE `navigate_to` SILENT ACCEPT
# --------------------------------------------------------------------- #


def _nav_skill(tmp_path, pos_data, outcome) -> main.SC_NavPoint:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Cave", "", "Daymar", 0.0, 0.0, 0.0)
    skill = _skill(db=db)
    _capturing(skill, pos_data, outcome)
    return skill


def test_navigate_to_refuses_every_failure_kind_and_sets_no_target(tmp_path) -> None:
    """AC-7. Before this gate a failed capture set the target, started the poll
    thread and came back as an ordinary deferred state."""
    for kind in _FAILURE_KINDS:
        skill = _nav_skill(tmp_path, None, _outcome(kind))
        result = json.loads(asyncio.run(skill.navigate_to("Cave")))
        assert "error" in result, kind
        assert result["target_not_set"] is True, kind
        assert skill._active_target is None, kind
        skill._start_nav_polling.assert_not_called()
        assert skill._ui_server.set_active_target_calls == [], kind


def test_navigate_to_refuses_a_station_interior(tmp_path) -> None:
    """AC-8, the exact silent-accept path. `parse_payload` returns a TRUTHY dict
    here, so `if not pos_data` never fired and neither frame gate did either."""
    skill = _nav_skill(
        tmp_path, {"body": "", "zone": "", "local_frame": False},
        _outcome(fields.KIND_NO_FRAME),
    )
    result = json.loads(asyncio.run(skill.navigate_to("Cave")))
    assert result["capture_kind"] == fields.KIND_NO_FRAME
    assert result["target_not_set"] is True
    assert skill._active_target is None
    skill._start_nav_polling.assert_not_called()


def test_navigate_to_never_opens_the_hud_on_a_failed_capture(tmp_path) -> None:
    class _Window:
        def __init__(self) -> None:
            self.opens = 0

        def open(self) -> None:
            self.opens += 1

    skill = _nav_skill(tmp_path, None, _outcome(fields.KIND_ABSENT))
    skill._ui_window = _Window()
    asyncio.run(skill.navigate_to("Cave"))
    assert skill._ui_window.opens == 0
    assert skill._hud_opened is False


def test_navigate_to_does_not_report_a_deferred_state_on_a_failure(tmp_path) -> None:
    """The exact sentence the bug produced. It described a normal wait for a
    frame that was never going to arrive."""
    skill = _nav_skill(tmp_path, None, _outcome(fields.KIND_ABSENT))
    raw = asyncio.run(skill.navigate_to("Cave"))
    assert "Bearing tracking begins once" not in raw
    assert "tracking" not in json.loads(raw)


def test_navigate_to_still_works_on_a_successful_local_capture(tmp_path) -> None:
    """AC-9. The gate must refuse failures and nothing else."""
    skill = _nav_skill(
        tmp_path,
        {"body": "Daymar", "x": 100.0, "y": 0.0, "z": 0.0, "heading": 0.0},
        _outcome(fields.KIND_OK),
    )
    result = json.loads(asyncio.run(skill.navigate_to("Cave")))
    assert result.get("success") is True
    assert skill._active_target is not None
    skill._start_nav_polling.assert_called()


# --------------------------------------------------------------------- #
# The badges: a SECOND channel, and it goes to chat as written
# --------------------------------------------------------------------- #


def _badge_skill(reason: str) -> main.SC_NavPoint:
    skill = _skill()
    skill._scanner = type("_S", (), {"last_reject_reason": reason})()
    skill._implausible_badge_shown = False
    skill._units_badge_shown = False
    skill._frame_badge_shown = False
    skill._mismatch_badge_shown = False
    skill._capture_position_local = lambda attempts=1: None
    return skill


def _badges(reason: str) -> list[str]:
    skill = _badge_skill(reason)
    asyncio.run(skill._capture_position())
    return [message for message, _, _ in skill.printr.calls]


def test_body_rejection_badge_does_not_blame_vision() -> None:
    """A body-frame rejection must describe the actual OCR validation failure."""
    for reason in ("implausible_body",):
        for message in _badges(reason):
            assert "Vision" not in message, reason


def test_body_rejection_badge_obeys_the_three_rules() -> None:
    for reason in ("implausible_body",):
        text = _badges(reason)[0]
        assert "Nothing was saved." in text, reason
        assert "malfunction" not in text.lower(), reason


def test_the_implausible_badge_no_longer_asks_for_a_retry() -> None:
    """A body token that fails the plausibility gate is not fixed by looking
    harder. That gate is the open `pyro3` item, and retrying refuses again."""
    text = _badges("implausible_body")[0]
    assert "There is no action here" in text
    assert "Retry" not in text


def test_the_three_correct_badges_are_byte_identical_to_baseline() -> None:
    """AC-13. They already name no reader, so they were left exactly alone."""
    for phrase in (
        "[NavPoint] Could not read the unit (m or km) on a coordinate, "
        "so the capture was refused rather than risk a waypoint 1000x "
        "off. Retry with the overlay clearly visible.",
        "[NavPoint] The overlay's SolarSystem and Root lines did not "
        "match, so the capture was discarded rather than risk a "
        "waypoint in the wrong place.",
        "[NavPoint] The overlay's two position readings disagreed, so "
        "the capture was discarded. Retry with a clear, still view of "
        "the overlay.",
    ):
        # Reassembled from the source's own string concatenation, so a reflow
        # that changed a word breaks this and a reflow that did not does not.
        joined = re.sub(r'"\s*\n\s*"', "", _MAIN_SRC)
        assert phrase in joined, phrase[:60]


def test_each_badge_fires_at_most_once_per_activation() -> None:
    """AC-15. The one-shot guards are what keep a per-tick refusal from filling
    the chat log, and they were not touched."""
    for reason in ("implausible_body", "unreadable_units",
                   "frame_mismatch", "coord_mismatch"):
        skill = _badge_skill(reason)
        for _ in range(4):
            asyncio.run(skill._capture_position())
        assert len(skill.printr.calls) == 1, reason


def test_every_reason_still_has_a_badge() -> None:
    for reason in ("implausible_body", "unreadable_units",
                   "frame_mismatch", "coord_mismatch"):
        assert len(_badges(reason)) == 1, reason


# --------------------------------------------------------------------- #
# The two channels must not tell the player opposite things
# --------------------------------------------------------------------- #
#
# A refusal reaches the player TWICE and by two different routes: the badge goes
# straight to the chat log exactly as written, and the tool result goes to the
# model, which paraphrases it. So the player can be told, about one capture,
# both "there is nothing you can do" and "try that again". That is worse than
# either message alone, and it is a defect CLASS rather than one instance: the
# two strings live in different places and nothing has made them agree until
# now. This is the guard for the next person who edits one side.


def _advice(text: str) -> str:
    """Classify what a message asks the player to do, in one of three ways."""
    lowered = text.lower()
    if "there is no action here" in lowered:
        return "none"
    if "ask again" in lowered or "retry" in lowered or "try again" in lowered:
        return "retry"
    return "silent"


def test_no_reject_reason_gives_contradictory_advice_on_its_two_channels() -> None:
    """SILENCE on one channel is fine: `frame_mismatch`'s badge describes what
    happened and asks for nothing, so it cannot contradict anything. What is
    forbidden is one channel saying there is no action while the other asks for
    a retry."""
    for reason in ("implausible_body", "unreadable_units",
                   "frame_mismatch", "coord_mismatch"):
        badge = _advice(_badges(reason)[0])
        tool = _advice(_error_for(fields.KIND_REJECT, reject_reason=reason)["error"])
        assert {badge, tool} != {"none", "retry"}, (reason, badge, tool)


def test_at_least_one_channel_tells_the_player_something() -> None:
    """The complement of the test above, so "make them agree" cannot be
    satisfied by silencing both."""
    for reason in ("implausible_body", "unreadable_units",
                   "frame_mismatch", "coord_mismatch"):
        badge = _advice(_badges(reason)[0])
        tool = _advice(_error_for(fields.KIND_REJECT, reject_reason=reason)["error"])
        assert {badge, tool} != {"silent"}, reason

"""Behavioral tests for main.py's capture hook (spec Items A1, B2, B3).

main.py imports the Wingman runtime at module scope (api.enums, api.interface,
skills.skill_base). The runtime packages are not importable in a bare test
environment, so this module injects minimal stand-ins into sys.modules BEFORE
importing main. Those stand-ins are used by no other test
(scanner/database/navigation stay real), so the injection is safe for the whole
suite. scanner still imports PIL/mss for real; if either is unavailable the
module skips cleanly.

The skill instance is built with __new__ (bypassing __init__/prepare, which
need a live Wingman) and its collaborators are hand-mocked: a fake scanner and
an async llm_call feed _capture_position a controlled position dict, a real
NavPointDatabase in tmp_path proves the wipe, and a recording printr/ui prove
the badge and the active-target teardown.

Written from the spec BEFORE implementation. Against the current code
_capture_position neither stamps captured_at nor wipes, so those assertions are
expected to fail; the list_navpoints signature check is expected to fail until
the server_id parameter is removed.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")


# ---------------------------------------------------------------------- #
# Wingman-runtime stand-ins (injected before importing main)
# ---------------------------------------------------------------------- #


class _LogType:
    POSITIVE = "POSITIVE"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NEGATIVE = "NEGATIVE"


def _install_runtime_stubs() -> None:
    if "api" not in sys.modules:
        api = types.ModuleType("api")
        enums = types.ModuleType("api.enums")
        enums.LogType = _LogType
        enums.LogSource = types.SimpleNamespace(WINGMAN='wingman')
        interface = types.ModuleType("api.interface")

        class WingmanInitializationError(Exception):
            pass

        interface.WingmanInitializationError = WingmanInitializationError
        api.enums = enums
        api.interface = interface
        sys.modules["api"] = api
        sys.modules["api.enums"] = enums
        sys.modules["api.interface"] = interface

    if "skills" not in sys.modules:
        skills = types.ModuleType("skills")
        skill_base = types.ModuleType("skills.skill_base")

        class Skill:
            def __init__(self, *args, **kwargs) -> None:
                pass

        def tool(*args, **kwargs):
            def _decorate(fn):
                return fn

            return _decorate

        skill_base.Skill = Skill
        skill_base.tool = tool
        skills.skill_base = skill_base
        sys.modules["skills"] = skills
        sys.modules["skills.skill_base"] = skill_base


_install_runtime_stubs()

import main  # noqa: E402
from database import NavPointDatabase  # noqa: E402


# ---------------------------------------------------------------------- #
# Fakes
# ---------------------------------------------------------------------- #


class _FakeScanner:
    """Returns a caller-supplied position dict, standing in for OCR + parse."""

    def __init__(self, pos: dict | None) -> None:
        self._pos = pos





class _RecordingPrintr:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def print(self, message: str, color=None, server_only: bool = False) -> None:
        self.calls.append((message, color, server_only))


class _RecordingUI:
    def __init__(self) -> None:
        self.set_position_calls: list = []
        self.set_active_target_calls: list = []
        self.notify_updates: int = 0

    def set_position(self, pos_data: dict) -> None:
        self.set_position_calls.append(pos_data)

    def set_active_target(self, target) -> None:
        self.set_active_target_calls.append(target)

    def notify_update(self) -> None:
        self.notify_updates += 1


def _make_skill(
    *, scanner_pos: dict | None, db: NavPointDatabase | None
) -> main.SC_NavPoint:
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._scanner = _FakeScanner(scanner_pos)
    skill._db = db
    skill._ui_server = _RecordingUI()
    skill._ui_window = None
    skill._active_target = None
    skill._nav_task = None
    skill._pending_server_change = None
    skill.printr = _RecordingPrintr()


    # _capture_position asks for the configured display; short-circuit the
    # custom-property lookup that needs a live Wingman.
    skill._get_display = lambda: 1
    # Since 2026-07-31 the position comes from the local reader, not Vision, so
    # the fixture is injected at THAT seam. Every assertion below is about what
    # happens downstream of a position dict; how pixels become one is
    # `test_overlay_reader.py`'s subject, tested there against real captures.
    skill._reader_state = ""
    skill._reader = None
    # Reads the scanner's CURRENT `_pos` on every call, exactly as the real
    # reader does: several tests mutate it mid-run to simulate the
    # next capture landing somewhere else, and a lambda closing over the
    # factory argument would silently freeze the fixture.
    # Takes `attempts` because the real read does: the mark path asks it for
    # several looks at the overlay (see test_capture_retry.py). This fixture
    # answers the same whatever it is given, since retrying is that module's
    # subject and every assertion here is about what one position dict causes.
    skill._capture_position_local = (
        lambda attempts=1: dict(skill._scanner._pos)
        if skill._scanner._pos is not None
        else None
    )
    # Teardown of the active target must be observable without a real task.
    skill._stop_nav_polling = MagicMock()
    return skill


# ---------------------------------------------------------------------- #
# A1: captured_at stamping
# ---------------------------------------------------------------------- #


def test_capture_stamps_captured_at() -> None:
    # No server_id, so the wipe branch (B2) never runs: this isolates A1.
    skill = _make_skill(
        scanner_pos={"x": 1.0, "y": 2.0, "z": 3.0, "body": "Daymar"},
        db=None,
    )
    before = time.time()
    result = asyncio.run(skill._capture_position())
    after = time.time()
    assert result is not None
    assert "captured_at" in result
    assert before <= result["captured_at"] <= after


def test_capture_none_position_stays_none() -> None:
    skill = _make_skill(scanner_pos=None, db=None)
    assert asyncio.run(skill._capture_position()) is None


# ---------------------------------------------------------------------- #
# B2: wipe-on-relog capture hook
#
# As of v4.9.0.4 the wipe requires TWO consecutive captures agreeing on the new
# server (a single hallucinated server_id must not destroy waypoints), so these
# tests capture twice before asserting the wipe. The full two-capture gate
# matrix lives in test_server_change.py.
# ---------------------------------------------------------------------- #


def test_capture_wipe_fires_on_new_server(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(
        scanner_pos={
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "body": "Daymar",
            "server_id": "pub-euw1b-sc-alpha-490-22222222-game-82",
        },
        db=db,
    )
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    # First capture only arms the confirmation; the waypoint survives.
    assert db.count_navpoints() == 1
    asyncio.run(skill._capture_position())
    # Two is no longer enough either: raised to three after two agreeing
    # misreads deleted six real waypoints (2026-07-26).
    assert db.count_navpoints() == 1
    asyncio.run(skill._capture_position())

    # A proven server change (two consecutive captures) wipes every waypoint.
    assert db.count_navpoints() == 0


def test_capture_wipe_emits_chat_badge(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(
        scanner_pos={
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "body": "Daymar",
            "server_id": "pub-euw1b-sc-alpha-490-22222222-game-82",
        },
        db=db,
    )
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    asyncio.run(skill._capture_position())
    asyncio.run(skill._capture_position())

    warnings = [c for c in skill.printr.calls if c[1] == _LogType.WARNING]
    assert warnings, "expected a WARNING chat badge on server change"
    # The badge must reach chat, not be server_only.
    assert all(c[2] is False for c in warnings)
    assert any("Server changed" in c[0] for c in warnings)


def test_capture_wipe_clears_active_target_and_polling(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Old", "pub-euw1b-sc-alpha-490-11111111-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(
        scanner_pos={
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "body": "Daymar",
            "server_id": "pub-euw1b-sc-alpha-490-22222222-game-82",
        },
        db=db,
    )
    skill._active_target = db.find_navpoint_by_name("Old")

    asyncio.run(skill._capture_position())
    asyncio.run(skill._capture_position())
    asyncio.run(skill._capture_position())

    assert skill._active_target is None
    skill._stop_nav_polling.assert_called()
    # The HUD is told the target is gone.
    assert None in skill._ui_server.set_active_target_calls


def test_capture_no_wipe_when_server_matches(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint("Keep", "pub-euw1b-sc-alpha-490-55555555-game-82", "Daymar", 1.0, 2.0, 3.0)
    skill = _make_skill(
        scanner_pos={
            "x": 1.0,
            "y": 2.0,
            "z": 3.0,
            "body": "Daymar",
            "server_id": "pub-euw1b-sc-alpha-490-55555555-game-82",
        },
        db=db,
    )
    keep = db.find_navpoint_by_name("Keep")
    skill._active_target = keep

    asyncio.run(skill._capture_position())

    # Same server: nothing wiped, target intact, no badge.
    assert db.count_navpoints() == 1
    assert skill._active_target is not None
    assert not [c for c in skill.printr.calls if c[1] == _LogType.WARNING]


# ---------------------------------------------------------------------- #
# B3: list_navpoints tool signature
# ---------------------------------------------------------------------- #


def test_list_navpoints_has_no_server_id_param() -> None:
    params = inspect.signature(main.SC_NavPoint.list_navpoints).parameters
    assert "server_id" not in params
    assert "body" in params


# ---------------------------------------------------------------------- #
# D: default waypoint name convention (spec Item D)
# ---------------------------------------------------------------------- #
#
# When mark_location is called with no name it generates "Location {N}, {body}"
# where N = 1 + the highest existing "Location <n>" across all bodies, scanned
# over get_navpoints() names. A user-supplied name is stored verbatim and never
# triggers the name prompt, even one that starts with "Location". No server_id
# is put on the captured position here, so the wipe hook (B2) never fires and
# the numbering scan is the only thing under test.


def _mark_skill(tmp_path: Path, body: str) -> main.SC_NavPoint:
    db = NavPointDatabase(str(tmp_path))
    return _make_skill(
        scanner_pos={"x": 1.0, "y": 2.0, "z": 3.0, "body": body},
        db=db,
    )


def test_mark_auto_name_empty_db_is_location_one(tmp_path: Path) -> None:
    skill = _mark_skill(tmp_path, "Daymar")
    result = json.loads(asyncio.run(skill.mark_location()))
    assert result["navpoint"]["name"] == "Location 1, Daymar"
    assert result["ask_for_name"] is True


def test_mark_auto_name_counter_is_global_across_bodies(tmp_path: Path) -> None:
    skill = _mark_skill(tmp_path, "Daymar")
    first = json.loads(asyncio.run(skill.mark_location()))
    assert first["navpoint"]["name"] == "Location 1, Daymar"
    # Same skill, next capture lands on a different body.
    skill._scanner._pos = {"x": 4.0, "y": 5.0, "z": 6.0, "body": "Cellin"}
    second = json.loads(asyncio.run(skill.mark_location()))
    # N is global, so the body change does not reset the counter.
    assert second["navpoint"]["name"] == "Location 2, Cellin"


def test_mark_auto_name_does_not_reuse_freed_number(tmp_path: Path) -> None:
    # Spec Item D: a deletion leaves a gap; the number is not recycled. The
    # unambiguous case under the get_navpoints() name-scan formula is deleting
    # a NON-max waypoint: the next mark increments past the surviving max
    # rather than refilling the gap. (Deleting the current max instead frees
    # its number under this formula; see the report's flagged spec ambiguity.)
    skill = _mark_skill(tmp_path, "Daymar")
    for _ in range(3):
        asyncio.run(skill.mark_location())
    db = skill._db
    names = {np.name for np in db.get_navpoints()}
    assert names == {
        "Location 1, Daymar",
        "Location 2, Daymar",
        "Location 3, Daymar",
    }
    middle = db.find_navpoint_by_name("Location 2, Daymar")
    db.delete_navpoint(middle.id)
    result = json.loads(asyncio.run(skill.mark_location()))
    assert result["navpoint"]["name"] == "Location 4, Daymar"


def test_mark_user_name_stored_verbatim(tmp_path: Path) -> None:
    skill = _mark_skill(tmp_path, "Daymar")
    result = json.loads(asyncio.run(skill.mark_location(name="Secret Cache")))
    assert result["navpoint"]["name"] == "Secret Cache"
    assert result["ask_for_name"] is False


def test_mark_user_name_starting_with_location_not_flagged(tmp_path: Path) -> None:
    # A user name that happens to start with "Location" must NOT trip the
    # auto-name prompt: ask_for_name tracks whether WE generated the name.
    skill = _mark_skill(tmp_path, "Daymar")
    result = json.loads(
        asyncio.run(skill.mark_location(name="Location of the wreck"))
    )
    assert result["navpoint"]["name"] == "Location of the wreck"
    assert result["ask_for_name"] is False


# ---------------------------------------------------------------------- #
# No-local-frame refusal message (v4.9.0.5 rewording)
# ---------------------------------------------------------------------- #


def test_mark_refused_when_no_frame_at_all(tmp_path: Path) -> None:
    # No body AND no readable system-frame position (a station or asteroid base
    # interior looks like this): there is nothing to record, so mark refuses.
    # The message no longer claims off-planet waypoints are unimplemented,
    # because as of v4.9.0.10 they are.
    skill = _mark_skill(tmp_path, "")
    result = json.loads(asyncio.run(skill.mark_location()))
    assert "error" in result
    assert "No usable coordinate frame" in result["error"]
    assert "off-planet waypoints are planned but not yet implemented" not in result["error"]
    # The SPECIFICATION changed here, not the implementation. `r_displayinfo 2`
    # is now reserved for the case where the overlay-presence check actually
    # fails. This is the opposite case: the overlay WAS on screen and WAS read,
    # and there is simply no usable frame at this location. Telling the player
    # to enable something already enabled is wrong on its own, and
    # `default_config.yaml` orders the model to relay a hint word for word, so
    # the wrong hint was read out as an instruction. The test's intent, that the
    # refusal suits the situation, is what survives.
    assert "hint" not in result


# ---------------------------------------------------------------------- #
# Space waypoints (v4.9.0.10)
# ---------------------------------------------------------------------- #


def _space_pos(**overrides) -> dict:
    """An open-space capture: no body, but a readable system-frame position."""
    data = {
        "local_frame": False,
        "body": "",
        "system_frame": True,
        "frame_id": "729494885314",
        "location": "StantonSolarSystem",
        "x": -1.89308e10,
        "y": -2.61006e9,
        "z": 627710.0,
        "camdir": (70.0, 0.0, -97.0),
        "server_id": "",
    }
    data.update(overrides)
    return data


def test_mark_in_open_space_now_succeeds(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    skill = _make_skill(scanner_pos=_space_pos(), db=db)
    result = json.loads(asyncio.run(skill.mark_location()))
    assert result.get("success") is True
    stored = db.find_navpoint_by_name(result["navpoint"]["name"])
    assert stored.frame == "system"
    assert stored.frame_id == "729494885314"
    assert stored.body == ""


def test_space_mark_auto_name_uses_the_location_token(tmp_path: Path) -> None:
    skill = _make_skill(scanner_pos=_space_pos(), db=NavPointDatabase(str(tmp_path)))
    result = json.loads(asyncio.run(skill.mark_location()))
    assert result["navpoint"]["name"] == "Location 1, StantonSolarSystem"


def test_space_mark_without_a_frame_id_is_refused(tmp_path: Path) -> None:
    """No frame id means a later session could not tell the frame apart."""
    skill = _make_skill(
        scanner_pos=_space_pos(frame_id=""), db=NavPointDatabase(str(tmp_path))
    )
    with pytest.raises(ValueError, match="frame_id is required"):
        asyncio.run(skill.mark_location())


# ---------------------------------------------------------------------- #
# Heading from CamDir (v4.9.0.9)
# ---------------------------------------------------------------------- #

# A real WolfPoint frame from the 2026-07-26 Daymar sweeps: this CamDir was
# captured while the game's own compass read 0 degrees at this position.
_WOLFPOINT = {
    "local_frame": True,
    "body": "Daymar",
    "system": "Stanton",
    "zone": "OOC_Stanton_2b_Daymar",
    "x": -4340.15,
    "y": 279089.8,
    "z": 95673.8,
    "camdir": (70.0, 0.0, -97.0),
    "server_id": "",
}


def test_capture_retains_camdir_without_inventing_a_compass_heading() -> None:
    skill = _make_skill(scanner_pos=dict(_WOLFPOINT), db=None)
    pos = asyncio.run(skill._capture_position())
    assert pos is not None
    assert "heading" not in pos
    assert pos["camdir"] == _WOLFPOINT["camdir"]


def test_capture_without_camdir_leaves_heading_unset() -> None:
    """No CamDir line means no heading, rather than a fabricated 0."""
    data = dict(_WOLFPOINT)
    del data["camdir"]
    skill = _make_skill(scanner_pos=data, db=None)
    pos = asyncio.run(skill._capture_position())
    assert "heading" not in pos


def test_capture_survives_a_position_with_no_local_basis() -> None:
    """At the body centre the basis is undefined; capture must not raise."""
    data = dict(_WOLFPOINT)
    data.update({"x": 0.0, "y": 0.0, "z": 0.0})
    skill = _make_skill(scanner_pos=data, db=None)
    pos = asyncio.run(skill._capture_position())
    assert pos is not None
    assert "heading" not in pos


def test_open_space_capture_gets_no_heading() -> None:
    """local_frame False carries no coordinates, so no heading is derivable."""
    skill = _make_skill(
        scanner_pos={"local_frame": False, "body": "", "camdir": (70.0, 0.0, -97.0)},
        db=None,
    )
    pos = asyncio.run(skill._capture_position())
    assert "heading" not in pos


def _nav_space_skill(tmp_path: Path, capture: dict):
    """A skill holding one space waypoint, with a controllable current capture."""
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint(
        name="wreck",
        server_id="",
        body="",
        x=-1.89308e10,
        y=-2.61006e9,
        z=627710.0,
        frame="system",
        frame_id="729494885314",
    )
    skill = _make_skill(scanner_pos=capture, db=db)
    # navigate_to starts the poll loop, which reads live config; short-circuit
    # the custom-property lookups that need a running Wingman.
    skill._get_poll_interval = lambda: 5
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._start_nav_polling = MagicMock()
    return skill


def test_navigate_to_space_waypoint_from_space_works(tmp_path: Path) -> None:
    # 1e7 m along x, which is 10 000 km: far enough to have a real direction.
    skill = _nav_space_skill(tmp_path, _space_pos(x=-1.89408e10))
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert result.get("success") is True
    assert result["bearing"]["frame"] == "system"
    # No compass exists in open space, so none is reported.
    assert "horizontal_bearing_deg" not in result["bearing"]
    # Direction is withheld until the system-frame CamDir convention is
    # calibrated: it measured 108.7 deg out against a known marker.
    assert "total_offset_deg" not in result["bearing"]
    assert result["bearing"]["distance_km"] == pytest.approx(1e4, rel=1e-3)


def test_navigate_to_a_space_waypoint_you_are_standing_on(tmp_path: Path) -> None:
    """Zero distance has no direction; guidance must degrade, not crash."""
    skill = _nav_space_skill(tmp_path, _space_pos())
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert result.get("success") is True
    assert result["bearing"]["distance_m"] == pytest.approx(0.0, abs=1.0)


def test_navigate_to_space_waypoint_from_a_surface_is_refused(tmp_path: Path) -> None:
    skill = _nav_space_skill(
        tmp_path, {"x": 1.0, "y": 2.0, "z": 3.0, "body": "Daymar"}
    )
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert "error" in result
    assert "deep-space waypoint" in result["error"]
    assert result["current_frame"] == "local"
    assert result["target_frame"] == "system"


def test_navigate_to_surface_waypoint_from_space_is_refused(tmp_path: Path) -> None:
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint(name="cave", server_id="", body="Daymar", x=1.0, y=2.0, z=3.0)
    skill = _make_skill(scanner_pos=_space_pos(), db=db)
    result = json.loads(asyncio.run(skill.navigate_to("cave")))
    assert "error" in result
    assert "open space" in result["error"]
    assert result["target_frame"] == "local"


def test_navigate_to_space_waypoint_from_a_different_frame_instance(tmp_path: Path) -> None:
    """Same frame TYPE, different frame INSTANCE: the coordinates do not carry."""
    skill = _nav_space_skill(tmp_path, _space_pos(frame_id="999999999999"))
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert "error" in result
    assert "different system frame" in result["error"]


# ---------------------------------------------------------------------- #
# Navigation provides a link without opening the browser.
# ---------------------------------------------------------------------- #


class _RecordingWindow:
    def __init__(self) -> None:
        self.opens = 0

    def open(self) -> None:
        self.opens += 1


def _nav_hud_skill(tmp_path: Path):
    db = NavPointDatabase(str(tmp_path))
    db.add_navpoint(
        name="wreck", server_id="", body="", x=-1.89308e10, y=-2.61006e9,
        z=627710.0, frame="system", frame_id="729494885314",
    )
    skill = _make_skill(scanner_pos=_space_pos(x=-1.89408e10), db=db)
    skill._get_poll_interval = lambda: 5
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._start_nav_polling = MagicMock()
    skill._ui_window = _RecordingWindow()
    skill._hud_opened = False
    return skill


def test_navigate_to_does_not_open_the_hud(tmp_path: Path) -> None:
    skill = _nav_hud_skill(tmp_path)
    asyncio.run(skill.navigate_to("wreck"))
    assert skill._ui_window.opens == 0


def test_navigate_to_does_not_reopen_on_every_call(tmp_path: Path) -> None:
    """Repeated navigation must not spawn a browser tab each time."""
    skill = _nav_hud_skill(tmp_path)
    asyncio.run(skill.navigate_to("wreck"))
    asyncio.run(skill.navigate_to("wreck"))
    asyncio.run(skill.navigate_to("wreck"))
    assert skill._ui_window.opens == 0


def test_navigate_to_survives_a_browser_that_will_not_open(tmp_path: Path) -> None:
    class _Broken:
        def open(self):
            raise OSError("no browser")

    skill = _nav_hud_skill(tmp_path)
    skill._ui_window = _Broken()
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert result.get("success") is True


def test_navigate_to_tells_the_user_where_the_ring_is(tmp_path: Path) -> None:
    skill = _nav_hud_skill(tmp_path)
    skill._ui_server.url = "http://127.0.0.1:7869"
    result = json.loads(asyncio.run(skill.navigate_to("wreck")))
    assert result["hud_url"] == "http://127.0.0.1:7869"
    assert "link" in result["hud_note"]
    assert "now opened" not in result["hud_note"]


@pytest.mark.parametrize('lan_available,qr_available', [(True, True), (False, False), (True, False)])
def test_prepare_posts_dashboard_link_to_wingman_chat(tmp_path, monkeypatch, lan_available, qr_available):
    from unittest.mock import AsyncMock
    import navpoint_ui.app as ui_app
    import navpoint_ui.window as ui_window
    import navpoint_ui.sharing as sharing
    server = MagicMock(url='http://127.0.0.1:7869', lan_url='http://192.168.1.20:7869' if lan_available else '')
    if not qr_available:
        monkeypatch.setattr(sharing, 'qr_png_base64', lambda url: None)
    window = MagicMock()
    monkeypatch.setattr(ui_app, 'NavPointServer', lambda **kw: server)
    monkeypatch.setattr(ui_window, 'NavPointWindow', lambda **kw: window)
    monkeypatch.setattr(main.Skill, 'prepare', AsyncMock(), raising=False)
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill._trace_build_identity = MagicMock()
    skill._start_background_calibration = MagicMock()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_arrival_alert_m = lambda: 1000
    skill._get_arrival_stop_m = lambda: 250
    skill._get_overlay_enabled = lambda: False
    skill._ring_overlay = None
    skill.wingman = types.SimpleNamespace(name='Alyssa', run_in_thread=MagicMock())
    skill.name = 'SC_NavPoint'
    skill.printr = types.SimpleNamespace(print=MagicMock(), print_async=AsyncMock())
    asyncio.run(skill.prepare())
    skill._start_background_calibration.assert_called_once()
    server.start.assert_called_once()
    window.open.assert_not_called()
    skill.printr.print_async.assert_not_awaited()
    skill.wingman.run_in_thread.assert_called_once()
    announcement, *arguments = skill.wingman.run_in_thread.call_args.args
    pause = AsyncMock()
    monkeypatch.setattr(main.asyncio, 'sleep', pause)
    asyncio.run(announcement(*arguments))
    pause.assert_awaited_once_with(15)
    skill.printr.print_async.assert_awaited_once()
    args, kwargs = skill.printr.print_async.call_args
    assert 'http://127.0.0.1:7869' in args[0]
    assert 'http://192.168.1.20:7869' not in args[0]
    assert args[0].count('http://') == 1
    assert len(args[0].splitlines()) == 3
    if qr_available:
        assert args[0] == 'NavPoint dashboard ready.\nScan with your phone, or open:\nhttp://127.0.0.1:7869'
        assert kwargs['additional_data']['image_base64']
    else:
        assert 'Scan' not in args[0]
        assert kwargs['additional_data'] is None
    assert kwargs['source_name'] == 'Alyssa'
    assert kwargs['skill_name'] == 'SC_NavPoint'
    assert kwargs['source'] == main.LogSource.WINGMAN
    assert not kwargs.get('server_only', False)


@pytest.mark.parametrize('replacement', [None, object()])
def test_delayed_dashboard_announcement_skips_unloaded_or_replaced_server(monkeypatch, replacement):
    from unittest.mock import AsyncMock
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    server = MagicMock()
    skill._ui_server = server
    skill.printr = types.SimpleNamespace(print_async=AsyncMock())
    async def pause(seconds):
        skill._ui_server = replacement
    monkeypatch.setattr(main.asyncio, 'sleep', pause)
    asyncio.run(skill._announce_ui_startup(server))
    skill.printr.print_async.assert_not_awaited()


def test_explicit_hud_request_can_still_open_browser(tmp_path):
    skill = _nav_hud_skill(tmp_path)
    skill._ui_server.url = 'http://127.0.0.1:7869'
    result = json.loads(skill.show_navpoint_hud())
    assert result['success']
    assert skill._ui_window.opens == 1

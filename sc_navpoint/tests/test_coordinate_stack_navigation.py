"""Marking, routing and presenting a coordinate-stack waypoint end to end.

Two properties carry most of the weight here. A schema-1 waypoint must be
routed by the pure selector and by nothing else, so the frame, body and
frame-id gates that govern legacy rows never see it. And legacy rows must
behave exactly as they did, because the user has waypoints stored under both of
the older frames and this rework is not allowed to re-address them.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import coordinate_stack as cs
import main
import overlay_fields as fields
from database import NavPointDatabase


# The motivating capture, as decoded rows. Innermost first, through Root.
KEEGER_ROWS = [
    {"row": 0, "trusted": True, "kind": "camdir",
     "text": "CamDir: 179 0 133 FOV: 55"},
    {"row": 1, "trusted": True, "kind": "zone",
     "text": "Zone: rs_int_layout_keeger_01 Pos: -386.02m 209.38m -437.00m"},
    {"row": 2, "trusted": True, "kind": "zone",
     "text": "Zone: keeger_segment_social_001 Pos: 21.5842km -23.2325km 22.6220km"},
    {"row": 3, "trusted": True, "kind": "zone",
     "text": "Zone: SolarSystem_753098466557 Pos: -45804302.9778km "
             "-14351319.5080km 29.3847km"},
    {"row": 4, "trusted": True, "kind": "zone",
     "text": "Zone: Root Pos: -45804302.9778km -14351319.5080km 29.3847km"},
]

# The Pyro 3 surface, which the legacy parser refuses through `body_scale`
# because Pyro names bodies without an `OOC_` prefix. This is the primary use
# case the user stated on 2026-08-02: mostly in a ship on a surface.
PYRO3_ROWS = [
    {"row": 0, "trusted": True, "kind": "zone",
     "text": "Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"},
    {"row": 1, "trusted": True, "kind": "zone",
     "text": "Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"},
    {"row": 2, "trusted": True, "kind": "zone",
     "text": "Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km"},
    {"row": 3, "trusted": True, "kind": "zone",
     "text": "Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"},
]


class _Printr:
    def print(self, *a, **k):
        pass

    async def print_async(self, *a, **k):
        pass


class _Server:
    def __init__(self):
        self.targets = []
        self.updates = 0
        self.positions = []

    def set_active_target(self, target):
        self.targets.append(target)

    def notify_update(self):
        self.updates += 1

    def set_position(self, pos):
        self.positions.append(pos)

    url = ""


def _skill(tmp_path: Path, capture: dict | None):
    """A skill wired to one fixed capture, with no screen and no Wingman."""
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._db = NavPointDatabase(str(tmp_path))
    skill._ui_server = _Server()
    skill._ui_window = None
    skill._ring_overlay = None
    skill._active_target = None
    skill._last_position = None
    skill._last_ring_state = ""
    skill._arrival_alert_done = False
    skill._arrival_stop_streak = 0
    skill._hud_opened = True
    skill.wingman = None
    skill._scanner = None
    skill.get_generated_files_dir = lambda: str(tmp_path)

    async def _capture(attempts: int = 1):
        return capture

    skill._capture_position = _capture
    skill._start_nav_polling = lambda: None
    skill._stop_nav_polling = lambda: None
    skill._get_arrival_alert_m = lambda: 1000.0
    skill._get_arrival_stop_m = lambda: 250.0
    skill._get_poll_interval = lambda: 1
    skill._sync_ring = lambda: None
    skill._get_space_direction_test = lambda: False
    return skill


def _capture_from(rows, scanner=None):
    """The position payload one capture of these rows produces."""
    from scanner import NavPointScanner

    payload, reason = fields.capture_payload(rows)
    assert payload is not None, reason
    return (scanner or NavPointScanner()).parse_payload(payload)


def _mark(skill, name=""):
    return json.loads(asyncio.run(skill.mark_location(name)))


def _navigate(skill, name):
    return json.loads(asyncio.run(skill.navigate_to(name)))


# --------------------------------------------------------------------------- #
# Marking
# --------------------------------------------------------------------------- #

def test_marking_stores_the_whole_stack_as_a_schema_1_waypoint(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    result = _mark(skill, "Keeger")
    assert result["success"] is True

    row = skill._db.find_navpoint_by_name("Keeger")
    assert row.frame == "stack"
    assert row.coordinate_schema == 1
    stack = cs.from_json(row.coordinate_stack)
    assert stack is not None
    assert len(stack.nested) == 2
    assert stack.local_candidate.raw_name == "keeger_segment_social_001"
    assert (row.root_x, row.root_y, row.root_z) == stack.root.xyz


def test_a_pyro_surface_can_now_be_marked_at_all(tmp_path) -> None:
    """The legacy parser refuses this capture outright and always has."""
    assert fields.payload_from_rows(PYRO3_ROWS) is None
    skill = _skill(tmp_path, _capture_from(PYRO3_ROWS))
    result = _mark(skill, "Landing site")
    assert result["success"] is True
    assert skill._db.find_navpoint_by_name("Landing site").frame == "stack"


def test_marking_returns_no_coordinates_labels_or_json_to_the_model(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    result = _mark(skill, "Keeger")
    blob = json.dumps(result)
    for forbidden in ("45804302", "coordinate_stack", "root_x", "keeger_segment",
                      "SolarSystem", "3000000", "LOCAL_TRACKING_MAX"):
        assert forbidden not in blob, forbidden
    assert result["coordinates"] == "logged"


def test_an_auto_named_stack_waypoint_carries_no_zone_text(tmp_path) -> None:
    """Zone text is OCR output that may carry the reader's `?` marker."""
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    result = _mark(skill)
    assert result["ask_for_name"] is True
    assert result["navpoint"]["name"].startswith("Location 1")
    assert "keeger" not in result["navpoint"]["name"].lower()


def test_marking_a_stack_waypoint_notifies_the_hud(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    assert skill._ui_server.updates == 1


def test_a_refused_capture_still_stores_nothing(tmp_path) -> None:
    skill = _skill(tmp_path, None)
    result = _mark(skill, "Nowhere")
    assert "error" in result
    assert skill._db.count_navpoints() == 0


def test_marking_never_wipes_waypoints_over_a_server_id(tmp_path) -> None:
    """The reader never emits one, and the three-agreeing-captures rule is
    REFUTED for a deterministic reader, so nothing here may drive a wipe."""
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "First")
    _mark(skill, "Second")
    assert skill._db.count_navpoints() == 2
    assert {n.server_id for n in skill._db.get_navpoints()} == {""}


def test_a_changed_solarsystem_suffix_does_not_disturb_stored_rows(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "First")

    moved = [dict(r) for r in KEEGER_ROWS]
    moved[3] = dict(moved[3])
    moved[3]["text"] = moved[3]["text"].replace("753098466557", "000000000001")
    skill._capture_position = lambda attempts=1: _async(_capture_from(moved))
    _mark(skill, "Second")
    assert skill._db.count_navpoints() == 2


async def _async(value):
    return value


# --------------------------------------------------------------------------- #
# Navigating
# --------------------------------------------------------------------------- #

def test_navigating_to_a_stack_waypoint_uses_the_pure_selector(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    result = _navigate(skill, "Keeger")
    assert result["success"] is True
    assert result["mode"] == "ROOT APPROACH"
    assert result["route_reason"] == cs.REASON_LOCAL_DISABLED
    assert skill._active_target.name == "Keeger"


def test_root_mode_says_coarse_and_offers_no_direction(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    result = _navigate(skill, "Keeger")
    assert "coarse" in result["guidance"]
    assert "bearing" not in json.dumps(result).lower()
    assert "direction" in result["note"].lower()


def test_a_capture_with_no_stack_refuses_and_sets_no_target(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    skill._capture_position = lambda attempts=1: _async(
        {"local_frame": True, "body": "Daymar", "x": 1.0, "y": 2.0, "z": 3.0}
    )
    result = _navigate(skill, "Keeger")
    assert result["target_not_set"] is True
    assert result["reason"] == "planet_frame_active"
    assert skill._active_target is None


def test_a_stack_waypoint_is_not_blocked_by_the_frame_id_gate(tmp_path) -> None:
    """The system frame is per session; Root is not."""
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    moved = [dict(r) for r in KEEGER_ROWS]
    moved[3] = dict(moved[3])
    moved[3]["text"] = moved[3]["text"].replace("753098466557", "000000000001")
    skill._capture_position = lambda attempts=1: _async(_capture_from(moved))
    result = _navigate(skill, "Keeger")
    assert result["success"] is True


def test_a_stack_waypoint_is_refused_when_planetary_frame_is_active(tmp_path) -> None:
    """Solar/Root may not route an old address while a planet frame is active."""
    skill = _skill(tmp_path, _capture_from(PYRO3_ROWS))
    _mark(skill, "Landing site")
    ooc_rows = [
        {"row": 0, "trusted": True, "kind": "zone",
         "text": "Zone: OOC_Stanton_4b_Clio Pos: 123.2375km -313.5352km 14.9327km"},
        {"row": 1, "trusted": True, "kind": "zone",
         "text": "Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
                 "7588008.0968km 119.0037km"},
        {"row": 2, "trusted": True, "kind": "zone",
         "text": "Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"},
    ]
    capture = _capture_from(ooc_rows)
    assert capture["body"] == "Clio"
    assert capture["coordinate_stack"] is not None
    skill._capture_position = lambda attempts=1: _async(capture)
    result = _navigate(skill, "Landing site")
    assert result["target_not_set"] is True
    assert result["reason"] == "planet_frame_active"


def test_a_distant_stack_target_reports_the_root_distance(tmp_path) -> None:
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    far = [dict(r) for r in KEEGER_ROWS]
    for index in (3, 4):
        far[index] = dict(far[index])
        far[index]["text"] = far[index]["text"].replace(
            "-45804302.9778km", "-45814302.9778km"
        )
    skill._capture_position = lambda attempts=1: _async(_capture_from(far))
    result = _navigate(skill, "Keeger")
    assert result["mode"] == "ROOT APPROACH"
    assert result["route_reason"] == cs.REASON_ROOT_AT_OR_BEYOND_LIMIT
    # Ten thousand kilometres out, reported as a distance rather than a fault.
    assert "10 megameters" in result["guidance"]


# --------------------------------------------------------------------------- #
# Legacy waypoints are untouched
# --------------------------------------------------------------------------- #

def test_a_legacy_local_waypoint_still_refuses_a_cross_body_capture(tmp_path) -> None:
    skill = _skill(tmp_path, None)
    skill._db.add_navpoint("Cave", "srv", "Daymar", 1.0, 2.0, 3.0)
    skill._capture_position = lambda attempts=1: _async(
        {"local_frame": True, "body": "Cellin", "x": 4.0, "y": 5.0, "z": 6.0}
    )
    result = _navigate(skill, "Cave")
    assert "cross-body" in result["error"]
    assert skill._active_target is None


def test_a_legacy_system_waypoint_still_refuses_a_changed_frame_id(tmp_path) -> None:
    skill = _skill(tmp_path, None)
    skill._db.add_navpoint("Deep", "srv", "", 1.0, 2.0, 3.0,
                           frame="system", frame_id="111")
    skill._capture_position = lambda attempts=1: _async(
        {"system_frame": True, "frame_id": "222", "x": 4.0, "y": 5.0, "z": 6.0}
    )
    result = _navigate(skill, "Deep")
    assert "different system frame" in result["error"]
    assert skill._active_target is None


def test_a_legacy_waypoint_never_takes_the_stack_branch(tmp_path) -> None:
    skill = _skill(tmp_path, None)
    skill._db.add_navpoint("Cave", "srv", "Daymar", 0.0, 0.0, 0.0)
    skill._capture_position = lambda attempts=1: _async(
        {"local_frame": True, "body": "Daymar", "x": 10.0, "y": 0.0, "z": 0.0,
         "heading": 0.0}
    )
    result = _navigate(skill, "Cave")
    assert result["success"] is True
    assert "mode" not in result
    assert "route_reason" not in result


# --------------------------------------------------------------------------- #
# The ring and the HUD
# --------------------------------------------------------------------------- #

def test_the_ring_draws_no_bubble_for_a_stack_target() -> None:
    import navigation

    position = {"x": 0.0, "y": 0.0, "z": 0.0, "coordinate_stack": {}}
    target = {"x": 1.0, "y": 0.0, "z": 0.0, "frame": "stack"}
    assert navigation.ring_deflection(position, target, 1.0) is None


def test_the_ring_says_no_bearing_rather_than_acquiring_for_a_stack_target() -> None:
    import navigation

    position = {"x": 0.0, "y": 0.0, "z": 0.0, "coordinate_stack": {}}
    target = {"x": 1.0, "y": 0.0, "z": 0.0, "frame": "stack"}
    deflection, message = navigation.ring_status(position, target, 1.0, "")
    assert deflection is None
    assert message == fields.RING_NO_BEARING


def test_a_reader_refusal_still_wins_on_the_ring_for_a_stack_target() -> None:
    import navigation

    position = {"x": 0.0, "y": 0.0, "z": 0.0, "coordinate_stack": {}}
    target = {"x": 1.0, "y": 0.0, "z": 0.0, "frame": "stack"}
    deflection, message = navigation.ring_status(
        position, target, 1.0, fields.RING_GLARE
    )
    assert deflection is None
    assert message == fields.RING_GLARE


def test_the_hud_page_clears_direction_for_distance_only_stack_fallback() -> None:
    js = (Path(__file__).resolve().parent.parent
          / "navpoint_ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "stackRoute" in js
    assert "ROOT APPROACH (coarse)" in js
    assert "NO BEARING (direction uncalibrated)" in js
    # Confirmed space guidance has its own branch; ambiguous stacks clear the dot.
    stack_branch = js.split("if (inStackRoute && !inSpaceFrame) {")[1].split("} else if")[0]
    assert "clearDeflection()" in stack_branch
    assert "setDeflection" not in stack_branch


def test_the_hud_server_uses_the_same_pure_selector() -> None:
    app = (Path(__file__).resolve().parent.parent
           / "navpoint_ui" / "app.py").read_text(encoding="utf-8")
    assert "coordinate_stack.select_route(" in app
    assert '"stack_route": stack_route' in app


# --------------------------------------------------------------------------- #
# Arrival
# --------------------------------------------------------------------------- #

def test_root_approach_can_never_announce_arrival(tmp_path) -> None:
    """A rotating surface target's saved Root position is deliberately stale
    within a body-sized envelope, so no Root distance may claim a landing."""
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    target = skill._db.find_navpoint_by_name("Keeger")
    decision = skill._stack_route(target, _capture_from(KEEGER_ROWS))
    # Standing exactly on it, and still no arrival.
    assert decision.distance_m == 0.0
    assert decision.mode == cs.MODE_ROOT_APPROACH
    assert decision.allow_arrival is False


def _run_one_poll(skill):
    """Drive `_nav_polling_loop` for exactly one tick, with no real sleeping."""
    ticks = iter([False, False, True])
    skill._poll_stopping = lambda: next(ticks, True)
    announced = []

    async def _announce(target, dist_m, alert_m, stop_m):
        announced.append((target.name, dist_m))
        return False

    skill._announce_arrival = _announce
    asyncio.run(skill._nav_polling_loop(0))
    return announced


def test_the_poll_loop_announces_nothing_in_root_approach(tmp_path) -> None:
    """The guard that matters is in the LOOP, not only in the decision object.

    Standing exactly on the stored Root position, distance zero, and still
    nothing is announced: a rotating surface target's saved Root position is
    stale within a body-sized envelope, so zero here does not mean arrived.
    """
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    skill._active_target = skill._db.find_navpoint_by_name("Keeger")
    assert _run_one_poll(skill) == []


def test_the_poll_loop_does_announce_once_local_tracking_is_live(tmp_path) -> None:
    """The positive control. Without it the test above would pass against a
    loop that had simply stopped calling the arrival policy at all."""
    skill = _skill(tmp_path, _capture_from(KEEGER_ROWS))
    _mark(skill, "Keeger")
    skill._active_target = skill._db.find_navpoint_by_name("Keeger")
    skill._stack_route = lambda target, pos: cs.RouteDecision(
        mode=cs.MODE_LOCAL_TRACKING,
        reason=cs.REASON_LOCAL_IN_RANGE,
        distance_m=42.0,
        allow_direction=True,
        allow_arrival=True,
        clear_local=False,
    )
    assert _run_one_poll(skill) == [("Keeger", 42.0)]


def test_local_tracking_would_announce_arrival_once_the_gate_opens() -> None:
    target, current = (
        cs.CoordinateStack(
            root=cs.StackRow(0.0, 0.0, 0.0, raw_name="Root"),
            solar=cs.StackRow(0.0, 0.0, 0.0, raw_name="SolarSystem_1"),
            nested=(cs.StackRow(0.0, 0.0, 0.0, depth=0),),
            candidate_depth=0,
        ),
    ) * 2
    decision = cs.select_route(target, current, allow_local=True)
    assert decision.mode == cs.MODE_LOCAL_TRACKING
    assert decision.allow_arrival is True


def test_one_arrival_policy_serves_both_routes() -> None:
    """Two arrival rules would be two rules to keep in step; the debounce is
    the part that stops a single flickering read announcing a landing."""
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(
        encoding="utf-8"
    )
    assert src.count("async def _announce_arrival") == 1
    assert src.count("_arrival_stop_streak >= 2") == 1
    assert src.count("self._announce_arrival(") == 2


# --------------------------------------------------------------------------- #
# Release manifests
# --------------------------------------------------------------------------- #

def _skill_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def test_the_new_runtime_module_is_in_both_release_manifests() -> None:
    """THERE ARE TWO MANIFESTS AND THEY ARE BOTH MANDATORY.

    A new runtime file has been omitted from one of them three times in this
    project's history, each time producing a release that imports a module the
    installer never copied. `update_release.py` builds `release_version/` and
    `skill_installer_config.json` drives the installer, and neither reads the
    other.
    """
    release = (_skill_dir() / "update_release.py").read_text(encoding="utf-8")
    installer = json.loads(
        (_skill_dir() / "skill_installer_config.json").read_text(encoding="utf-8")
    )
    assert '"coordinate_stack.py",' in release
    assert "coordinate_stack.py" in installer["files"]


def test_the_two_release_manifests_agree() -> None:
    """Only the batch launchers and tester readme are package-only files."""
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


def test_every_flat_runtime_import_of_main_is_released() -> None:
    """A module main.py imports at load time must reach the installed folder."""
    src = (_skill_dir() / "main.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^import (\w+)  # noqa: E402", src, re.MULTILINE))
    imported |= set(re.findall(r"^from (\w+) import", src, re.MULTILINE))
    local = {name for name in imported if (_skill_dir() / f"{name}.py").exists()}
    installer = json.loads(
        (_skill_dir() / "skill_installer_config.json").read_text(encoding="utf-8")
    )
    assert local, "the import scan found nothing, so it is not testing anything"
    assert {f"{name}.py" for name in local} <= set(installer["files"])


def test_no_new_tool_was_added() -> None:
    """The rework must stay token-neutral: no new schema on every API call."""
    src = (Path(__file__).resolve().parent.parent / "main.py").read_text(
        encoding="utf-8"
    )
    assert src.count("    @tool(") == 8

"""Version consistency for the v4.9.0.22 internal update (system-frame CamDir convention solved).

The bump is 4.9.0.21 -> 4.9.0.22 in main.py (the module docstring line and the
VERSION constant), __init__.py (__version__), and skill_installer_config.json.
This release draws the deflection ring over the game itself, in a click-through
layered window anchored to the top centre of the screen, instead of only on a
browser page that cannot appear over a game.

NOTE the version line: the fourth component is the WITHIN-PATCH counter, so this
is 4.9.0.22, not 4.9.1.0. A 4.9.1 would claim qualification against a Star
Citizen patch 4.9.1 that does not exist. See skills/Versioning.md. SC_TARGET_VERSION / __sc_target_version__ stay 4.9.0 (this
is not a requalification). Read as source text, since main.py imports the Wingman
runtime at module scope.

The no-game-input assertions from v4.9.0.18 are carried forward deliberately: that
was a standing user decision (CIG cheat-risk), not a one-release change, so it
stays regression-guarded. The overlay only draws, so it does not weaken that rule.

Every new runtime file must appear in BOTH release manifests. Omitting one has
shipped a broken skill three times (feedback_lesson_dual_release_manifests), so
that pairing is asserted here rather than remembered.
"""

from __future__ import annotations

from pathlib import Path


_SKILL_DIR = Path(__file__).resolve().parent.parent
_MAIN_SRC = (_SKILL_DIR / "main.py").read_text(encoding="utf-8")
_INIT_SRC = (_SKILL_DIR / "__init__.py").read_text(encoding="utf-8")
_INSTALLER_SRC = (_SKILL_DIR / "skill_installer_config.json").read_text(encoding="utf-8")
_SCANNER_SRC = (_SKILL_DIR / "scanner.py").read_text(encoding="utf-8")


def test_main_version_constant_is_49022() -> None:
    assert 'VERSION = "4.9.0.27"' in _MAIN_SRC


def test_main_docstring_version_is_49022() -> None:
    assert "Version: 4.9.0.27" in _MAIN_SRC


def test_main_has_two_49022_occurrences() -> None:
    # The docstring line and the VERSION constant.
    assert _MAIN_SRC.count("4.9.0.27") >= 2


def test_init_version_is_49022() -> None:
    assert '__version__ = "4.9.0.27"' in _INIT_SRC


def test_installer_config_version_is_49022() -> None:
    assert '"version": "4.9.0.27"' in _INSTALLER_SRC


def test_main_sc_target_stays_490() -> None:
    assert 'SC_TARGET_VERSION = "4.9.0"' in _MAIN_SRC


def test_init_sc_target_stays_490() -> None:
    assert '__sc_target_version__ = "4.9.0"' in _INIT_SRC


def test_main_has_no_stale_49021_version_declaration() -> None:
    # The declarations, not the word: main.py's comments cite earlier releases
    # by number on purpose, and that history must stay readable.
    assert 'VERSION = "4.9.0.21"' not in _MAIN_SRC
    assert "Version: 4.9.0.21" not in _MAIN_SRC


def test_init_has_no_stale_49021() -> None:
    assert "4.9.0.21" not in _INIT_SRC


def test_overlay_files_are_in_both_release_manifests() -> None:
    """A runtime file missing from either manifest ships a skill that cannot
    import itself. Three incidents; hence a test rather than a habit."""
    release_src = (_SKILL_DIR / "update_release.py").read_text(encoding="utf-8")
    for filename in ("overlay_win32.py", "ring_overlay.py"):
        assert f'"{filename}"' in _INSTALLER_SRC, filename
        assert f'"{filename}"' in release_src, filename


def test_overlay_never_sends_input_to_the_game() -> None:
    """The overlay draws over the game and must not grow an input path."""
    for filename in ("overlay_win32.py", "ring_overlay.py"):
        src = (_SKILL_DIR / filename).read_text(encoding="utf-8")
        assert "SendInput" not in src
        assert "keybd_event" not in src
        assert "pydirectinput" not in src


def test_overlay_window_is_click_through_and_topmost() -> None:
    """Anything less steals clicks from the game or sinks behind it."""
    src = (_SKILL_DIR / "overlay_win32.py").read_text(encoding="utf-8")
    for flag in (
        "WS_EX_LAYERED",
        "WS_EX_TRANSPARENT",
        "WS_EX_TOPMOST",
        "WS_EX_TOOLWINDOW",
        "WS_EX_NOACTIVATE",
    ):
        assert flag in src, flag
    assert "UpdateLayeredWindow" in src


def test_skill_wires_the_ring_through_one_place() -> None:
    assert "def _sync_ring" in _MAIN_SRC
    assert "def _set_position" in _MAIN_SRC
    # Exactly one call site, the one inside _set_position: any other would push
    # a position to the HUD page while leaving the ring showing the old fix.
    assert _MAIN_SRC.count("self._ui_server.set_position(") == 1
    assert "self._ui_server.set_position(" in _MAIN_SRC.split("def _set_position")[1]


def test_main_has_no_console_input_capability() -> None:
    # Standing decision from v4.9.0.18: the skill never sends input to the game.
    assert "pydirectinput" not in _MAIN_SRC
    assert "_send_console_command" not in _MAIN_SRC
    assert "def enable_displayinfo" not in _MAIN_SRC
    assert "def disable_displayinfo" not in _MAIN_SRC






def test_navigation_exposes_the_bearing_conversion() -> None:
    nav = (_SKILL_DIR / "navigation.py").read_text(encoding="utf-8")
    assert "def camdir_to_bearing" in nav
    assert "def local_basis" in nav
    assert "def surface_bearing" in nav


def test_space_waypoint_support_is_present() -> None:
    nav = (_SKILL_DIR / "navigation.py").read_text(encoding="utf-8")
    scan = (_SKILL_DIR / "scanner.py").read_text(encoding="utf-8")
    db = (_SKILL_DIR / "database.py").read_text(encoding="utf-8")
    assert "def space_guidance" in nav
    assert "def relative_deflection" in nav
    assert "system_pos_raw" in scan
    assert "_SCHEMA_VERSION = 4" in db


def test_version_line_stays_on_the_490_patch() -> None:
    # The fourth component is the within-patch counter; the first three must
    # remain the SC patch this is qualified against.
    assert 'SC_TARGET_VERSION = "4.9.0"' in _MAIN_SRC
    assert "4.9.1" not in _MAIN_SRC


def test_tool_results_do_not_carry_raw_coordinates() -> None:
    """Long numeric strings reaching the conversation model derailed the TTS."""
    assert '"x": np.x' not in _MAIN_SRC.split("_navpoint_to_result_dict")[1][:600]
    assert '"coordinates": "logged"' in _MAIN_SRC


def test_hud_payload_exposes_the_frame() -> None:
    db = (_SKILL_DIR / "database.py").read_text(encoding="utf-8")
    assert '"frame": np.frame' in db
    js = (_SKILL_DIR / "navpoint_ui" / "static" / "app.js").read_text(encoding="utf-8")
    assert "isSystemFrame" in js
    assert "spaceGuidance" in js


def test_open_space_reading_keeps_camdir() -> None:
    """Space guidance needs the facing direction alongside the position."""
    from scanner import NavPointScanner

    xyz = ["-60077861.1780km", "21737086.4624km", "19428930.4479km"]
    result = NavPointScanner().parse_payload({
        "local_frame": False,
        "system_zone_id": "729494885309",
        "system_pos_raw": xyz,
        "root_pos_raw": xyz,
        "camdir": [12, -23, 34],
    })
    assert result is not None
    assert tuple(result["camdir"]) == (12.0, -23.0, 34.0)


def test_polling_does_not_use_create_task() -> None:
    """A task on the caller's loop dies when that loop stops; proven live."""
    start = _MAIN_SRC.split("def _start_nav_polling")[1].split("def _stop_nav_polling")[0]
    # The CALL, not the word: the docstring names it to explain why it is wrong.
    assert "asyncio.create_task(self._nav_polling_loop" not in start
    assert "threading.Thread" in start
    assert "new_event_loop" in start

"""Source-level audit of main.py display-info wording.

main.py imports the Wingman runtime (api.enums, api.interface) at module
scope, so it is not importable in a bare test environment. These checks read
it as source text. As of v4.9.0.7 the skill sends no input to the game, so the
console-typing tools (enable_displayinfo / disable_displayinfo) were removed;
the remaining guarantee here is that main.py never references the wrong overlay
level r_displayinfo 4. The reworded guidance still points the player at
r_displayinfo 2 to type manually.
"""

from __future__ import annotations

from pathlib import Path


_SKILL_DIR = Path(__file__).resolve().parent.parent
_MAIN_SRC = (_SKILL_DIR / "main.py").read_text(encoding="utf-8")


def test_no_r_displayinfo_4_remains() -> None:
    assert "r_displayinfo 4" not in _MAIN_SRC


def test_player_guidance_still_names_level_2() -> None:
    # The skill no longer types the command, but its hints must still tell the
    # player the correct overlay level to type themselves.
    assert "r_displayinfo 2" in _MAIN_SRC

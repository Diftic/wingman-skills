"""default_config.yaml matches the code, and the tool answers stay short and read real states."""
import re
from pathlib import Path

import yaml
from sc_telemetry_core.describe import player_summary, ship_summary
from sc_telemetry_core.events import EVENTS
from test_handler import replay

SKILL_DIR = Path(__file__).resolve().parent.parent
MAX_ANSWER_CHARS = 800
"""Tool answers go into the conversation on every call; keep them small (Wingman's token rules)."""


def _config() -> dict:
    return yaml.safe_load((SKILL_DIR / "default_config.yaml").read_text(encoding="utf-8"))


def test_config_names_the_class_in_main():
    config = _config()
    assert config["api_version"] == 3 and config["platforms"] == ["windows"]
    assert re.search(rf"^class {config['name']}\(Skill\)", (SKILL_DIR / "main.py").read_text(), re.MULTILINE)


def test_config_shows_only_the_two_main_switches():
    """Everything else is on and hidden (user, 2026-10-29)."""
    props = _config()["custom_properties"]
    assert [p["id"] for p in props] == ["enable_telemetry", "proactive_notifications"]
    assert props[0]["value"] is False  # persistent config: only on the user's choice
    assert props[1]["value"] is True


def test_hint_lists_every_reaction_and_marks_the_untested():
    hint = _config()["hint"]["en"]
    for spec in EVENTS:
        assert spec.name.lower() + ("*" if not spec.tested else "") in hint, spec.id


def test_config_is_current():
    import build_config

    assert build_config.build() == (SKILL_DIR / "default_config.yaml").read_text(encoding="utf-8")


def test_answers_for_a_ship_in_combat_and_a_player(frames):
    handler, _, _ = replay(frames("combat_2026-10-28.jsonl"))
    ship = ship_summary(handler.state)
    player = player_summary(handler.state)
    assert ship.startswith("Ship: DRAK Cutter (Drake)") and "Warnings:" in ship
    assert "Wallet" in player and "aUEC" in player
    assert len(ship) < MAX_ANSWER_CHARS and len(player) < MAX_ANSWER_CHARS


def test_answer_for_a_ground_vehicle(frames):
    handler, _, _ = replay(frames("ursa_2026-10-28.jsonl"))
    assert "no ship telemetry" in ship_summary(handler.state)

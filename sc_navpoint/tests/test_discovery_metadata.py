"""Discovery metadata must get the skill ACTIVATED, or none of it exists.

sc_navpoint now auto-activates at Wingman startup at the user's request.
The discovery description still identifies its purpose and distinguishes saved
waypoints from the route planner when Wingman selects a tool.

On 2026-07-26 the skill was never activated across an entire session. The model
sent "log the current location" to the HUD Overlay skill's hud_add_info and
"navigate back to Space Location 1" to SC_Navigator's plan_route, because the
description said the skill worked "on planetary and moon surfaces" while the
player was in open space, and because an already-active tool beats paying for a
discovery step. These tests lock the wording that fixes both.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")


_CONFIG = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "default_config.yaml").read_text(
        encoding="utf-8"
    )
)
_DESC = _CONFIG["description"]["en"]
_KEYWORDS = [k.lower() for k in _CONFIG["discovery_keywords"]]


def _discovery_text() -> str:
    """Exactly what the model is shown, per get_discovery_description()."""
    return (
        _DESC
        + f". Keywords: {_CONFIG['discovery_keywords']}"
        + " ["
        + ", ".join(_CONFIG["tags"])
        + "]"
    )


def test_description_does_not_claim_surface_only() -> None:
    """The old wording told the model the skill did not apply in space."""
    text = _discovery_text().lower()
    assert "open space" in text
    assert "on planetary and moon surfaces in star citizen" not in text


def test_prompt_distinguishes_itself_from_the_route_planner() -> None:
    """SC_Navigator's plan_route stole 'navigate back to <my waypoint>'.

    Since 4.10.2.1 the description is one short sentence and this guidance
    lives in the prompt, which the model always sees: the skill auto-activates.
    """
    assert "route planner" in _CONFIG["prompt"].lower()


def test_prompt_distinguishes_itself_from_hud_info_cards() -> None:
    """HUD Overlay's hud_add_info stole 'log the current location'."""
    assert "hud information card" in _CONFIG["prompt"].lower()


@pytest.mark.parametrize(
    "phrase",
    [
        "log the current location",   # said live, went to hud_add_info
        "save the current location",  # said live, no tool call at all
        "navigate back",              # said live, went to plan_route
        "mark my position",
        "take me back",
        "space waypoint",
    ],
)
def test_natural_phrasings_are_covered(phrase: str) -> None:
    """The old keywords were 'save location' and 'navigate to', which do not
    appear in 'save THE CURRENT location' or 'navigate BACK to'."""
    assert phrase in _KEYWORDS


def test_auto_activate_starts_navpoint_with_wingman() -> None:
    """The user requested the dashboard and skill to be ready at startup."""
    assert _CONFIG["auto_activate"] is True

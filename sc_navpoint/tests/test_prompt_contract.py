"""The configured prompt must describe the behaviour the code actually has.

WHY THIS FILE EXISTS. The prompt is the only description of this skill the
language model ever sees, and nothing validates it. It drifted: it documented
`list_navpoints(server_id, body)` when the tool takes `body` alone, and it
promised surface waypoints give "distance AND direction" after schema-1 marks
had become coarse Root-addressed records with no bearing and no arrival. A model
reading that would invent a turn direction the skill deliberately withholds.

These tests derive their expectations from the CODE wherever possible, by
introspecting the real tool signatures, so they keep biting as the code moves
rather than pinning today's wording.

Note on where the prompt actually takes effect: the running Wingman reads the
INSTALLED skill's `default_config.yaml`, and the saved Wingman config persists
only `module` and `custom_properties` id/value pairs, with no prompt at all
(verified against the 2.1.1 config on 2026-08-10). So a prompt correction here
reaches the player at install time, not before.

Credit: Mallachi
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import yaml

from main import SC_NavPoint


SKILL_DIR = Path(__file__).resolve().parent.parent
CONFIG = SKILL_DIR / "default_config.yaml"

# Tools the prompt documents with an explicit argument list, as
# `name(args)`. Each is checked against the real signature.
_DOCUMENTED = re.compile(r"`(\w+)\(([^)]*)\)`")


def _prompt() -> str:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return data["prompt"]


def _flat() -> str:
    """The prompt with every run of whitespace collapsed to one space.

    Phrase assertions run against this. The prompt is a YAML block scalar that
    is hand-wrapped at about 85 columns, so a required sentence is routinely
    split across a newline; matching the raw text would make these tests fail
    on a rewrap that changed no meaning.
    """
    return re.sub(r"\s+", " ", _prompt()).lower()


def test_every_documented_tool_exists_on_the_skill() -> None:
    """A prompt naming a tool that does not exist teaches the model to fail."""
    missing = []
    for name, _ in _DOCUMENTED.findall(_prompt()):
        if not callable(getattr(SC_NavPoint, name, None)):
            missing.append(name)
    assert missing == [], f"prompt documents non-existent tools: {missing}"


def test_documented_arguments_match_the_real_signatures() -> None:
    """The defect that started this: `list_navpoints(server_id, body)`.

    Derived from `inspect.signature`, so renaming or removing a parameter fails
    here instead of silently teaching the model a call it cannot make.
    """
    wrong = []
    for name, args in _DOCUMENTED.findall(_prompt()):
        target = getattr(SC_NavPoint, name, None)
        if not callable(target):
            continue
        real = {
            p for p in inspect.signature(target).parameters
            if p not in ("self", "args", "kwargs")
        }
        documented = {a.strip() for a in args.split(",") if a.strip()}
        unknown = documented - real
        if unknown:
            wrong.append((name, sorted(unknown), sorted(real)))
    assert wrong == [], f"prompt documents parameters the tools do not take: {wrong}"


def test_the_prompt_does_not_promise_a_bearing_for_address_waypoints() -> None:
    """Direction is withheld, never guessed, and the prompt must say so.

    `navigation.SPACE_DIRECTION_CALIBRATED` is False and a stack route sets
    `allow_direction=False`, so any promise of a turn direction for a new mark
    would be a promise the runtime refuses to keep.
    """
    prompt = _flat()
    assert "no direction is available" in prompt
    assert "distance only" in prompt


def test_the_prompt_forbids_announcing_arrival_for_address_waypoints() -> None:
    """`RouteDecision.allow_arrival` is False in ROOT APPROACH, at any distance.

    Without this the model would helpfully announce a landing from a figure the
    runtime knows is stale within a body-sized envelope.
    """
    prompt = _flat()
    assert "do not announce or imply arrival" in prompt
    assert "coarse" in prompt


def test_the_prompt_still_forbids_reading_coordinates_aloud() -> None:
    """A pre-existing contract that the rewrite must not have dropped."""
    assert "never read coordinate numbers aloud" in _flat()


def test_the_prompt_no_longer_claims_surfaces_are_refused() -> None:
    """Marking now succeeds where the legacy body parser refused.

    Proven live on 2026-08-10: 90/90 stack accepts against 0/90 legacy on a
    Pyro 3 surface. A prompt still saying those are refused would talk the
    player out of the skill's newest capability.
    """
    assert "succeeds in places it used to refuse" in _flat()

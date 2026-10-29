"""main.py with minimal stand-ins for the Core modules it imports: frames in, switched events out, tool answers.

Only the facade members the skill uses are faked. A live check in Wingman is still needed (TESTER notes)."""
import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest
from sc_telemetry_core.events import EVENTS

SKILL_DIR = Path(__file__).resolve().parent.parent


def _install_core_stubs() -> None:
    api = types.ModuleType("api")
    interface = types.ModuleType("api.interface")
    interface.SettingsConfig = interface.SkillConfig = object
    skills = types.ModuleType("skills")
    skill_base = types.ModuleType("skills.skill_base")

    class Skill:
        def __init__(self, config, settings, wingman):
            self.config, self.settings, self.wingman = config, settings, wingman
            self.logged: list[str] = []
            self.log = types.SimpleNamespace(info=lambda msg, **kw: self.logged.append(msg),
                                             warning=lambda msg, **kw: self.logged.append(msg))

        async def prepare(self):
            return None

        async def unload(self):
            return None

    def tool(**_kwargs):
        return lambda function: function

    skill_base.Skill, skill_base.tool = Skill, tool
    services = types.ModuleType("services")
    local_ai = types.ModuleType("services.skill_local_ai")
    local_ai.SamplingPreset = types.SimpleNamespace(CREATIVE="creative")
    for name, module in {"api": api, "api.interface": interface, "skills": skills, "skills.skill_base": skill_base,
                         "services": services, "services.skill_local_ai": local_ai}.items():
        sys.modules.setdefault(name, module)


@pytest.fixture
def skill_class():
    _install_core_stubs()
    spec = importlib.util.spec_from_file_location("sc_telemetry_main", SKILL_DIR / "main.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.SC_Telemetry


def _skill(skill_class, settings: dict):
    skill = skill_class(types.SimpleNamespace(display_name="Star Citizen Telemetry"), None, None)
    skill.retrieve_custom_property_value = lambda key, errors: settings.get(key)
    return skill


def test_frames_become_events_and_answers(skill_class, frames):
    skill = _skill(skill_class, {})
    offered = []
    skill._offer = offered.extend
    skill._loop = types.SimpleNamespace(call_soon_threadsafe=lambda fn, events: fn(events))
    for t, frame in frames("combat_2026-10-28.jsonl"):
        skill._on_frame_thread(frame, t)
    found = {event.id for event in offered}
    assert {"shields_down", "under_fire", "powerplant_offline"} <= found
    skill._reader_status = "live"
    ship = asyncio.run(skill.get_ship_status())
    assert ship.startswith("Ship: DRAK Cutter")


def test_every_reaction_is_on_and_only_the_master_mutes(skill_class):
    """Only two settings are shown (user, 2026-10-29): all reactions on, the proactive master mutes them all."""
    skill = _skill(skill_class, {"react_ship": False, "react_under_fire": False})  # old switches are ignored
    assert all(skill._event_enabled(spec.id) for spec in EVENTS)
    assert not skill._event_enabled("no_such_event")
    muted = _skill(skill_class, {"proactive_notifications": False})
    assert not any(muted._event_enabled(spec.id) for spec in EVENTS)

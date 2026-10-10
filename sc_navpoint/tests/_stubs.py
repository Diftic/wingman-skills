"""Shared Wingman-runtime stand-ins for tests that import main.py.

main.py imports the Wingman runtime at module scope (api.enums, api.interface,
skills.skill_base). Those packages are not importable in a bare test
environment, so this helper injects minimal stand-ins into sys.modules BEFORE
main is imported. The stubs are used by no runtime test (scanner, database and
navigation stay real), so the injection is safe for the whole suite.

test_main_capture.py carries its own copy of this shimming for historical
reasons; the guards here are idempotent, so both installing them is harmless.
"""

from __future__ import annotations

import sys
import types


class LogType:
    """Mirror of api.enums.LogType, string-valued for easy comparison."""

    POSITIVE = "POSITIVE"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    NEGATIVE = "NEGATIVE"


def install_runtime_stubs() -> None:
    """Inject api.* and skills.skill_base stand-ins if the real ones are absent."""
    if "api" not in sys.modules:
        api = types.ModuleType("api")
        enums = types.ModuleType("api.enums")
        enums.LogType = LogType
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

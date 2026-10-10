"""Offline contract check using methods extracted from the installed v3 host.

Never starts Wingman, calls a real provider or reads/writes the live runtime.
Host configuration validation and hardware/providers are doubles, not qualified.
Run with the host-compatible Python and an isolated candidate directory.
"""

import ast
import asyncio
import hashlib
import importlib
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock


def load_class(file, name, namespace, methods=None):
    tree = ast.parse(file.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    if methods is not None:
        node.body = [n for n in node.body if getattr(n, "name", None) in methods]
    module = ast.Module(
        body=[
            ast.ImportFrom(
                module="__future__", names=[ast.alias(name="annotations")], level=0
            ),
            node,
        ],
        type_ignores=[],
    )
    exec(compile(ast.fix_missing_locations(module), str(file), "exec"), namespace)
    return namespace[name]


async def verify(host, candidate):
    NS = types.SimpleNamespace
    facade = types.ModuleType("wingmen.facade")
    facade.FacadeError = RuntimeError
    facade._wrap = lambda value: (
        facade.ReadOnlyConfigView(value) if isinstance(value, NS) else value
    )
    for name, methods in (
        ("ReadOnlyConfigView", None),
        ("SkillSettings", None),
        ("SkillAi", {"__init__", "generate", "converse", "_max_input_tokens"}),
        ("SkillTts", {"__init__", "speak"}),
        ("SkillConversation", None),
    ):
        load_class(host / "wingmen/facade.py", name, facade.__dict__, methods)
    sys.modules["wingmen"] = types.ModuleType("wingmen")
    sys.modules["wingmen.facade"] = facade
    spec = importlib.util.spec_from_file_location(
        "reader_host_context", host / "wingmen/wingman_context.py"
    )
    context_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(context_module)

    tokens = types.ModuleType("services.token_utils")
    tokens.count_tokens = lambda text: len(text)
    tokens.truncate_to_tokens = lambda text, budget: text[:budget]
    sys.modules["services"] = types.ModuleType("services")
    sys.modules["services.token_utils"] = tokens

    subscriptions = set()
    events = NS(
        subscribe=lambda event, cb: subscriptions.add(cb),
        unsubscribe=lambda event, cb: subscriptions.discard(cb),
    )
    base = types.ModuleType("skills.skill_base")
    base.SecretKeeper = lambda: NS(secret_events=events)
    base.SkillLog = lambda name: NS(
        info=lambda *a, **kw: None, warning=lambda *a, **kw: None
    )
    base.Printr = lambda: NS(print_async=AsyncMock())
    load_class(
        host / "skills/skill_base.py",
        "Skill",
        base.__dict__,
        {
            "__init__",
            "prepare",
            "unload",
            "get_prompt",
            "secret_changed",
            "_collect_decorated_tools",
            "_collect_command_actions",
        },
    )
    sys.modules["skills"] = types.ModuleType("skills")
    sys.modules["skills.skill_base"] = base

    namespace = dict(
        sys=sys,
        path=os.path,
        util=importlib.util,
        import_module=importlib.import_module,
        get_custom_skills_dir=lambda: str(candidate.parent),
        get_bundled_skills_dir=lambda: None,
    )
    manager = load_class(
        host / "services/module_manager.py",
        "ModuleManager",
        namespace,
        {
            "get_module_name_and_path",
            "resolve_skill_module",
            "probe_import",
            "load_skill",
        },
    )
    config = NS(
        module="skills.sc_log_reader.main", name="SCLogReader", prompt="Test prompt"
    )
    manager.probe_import(config)
    assert "sc_log_reader.main" not in sys.modules
    assert "regex" not in sys.modules

    history, requests, spoken = [], [], []

    async def add_user(text):
        history.append({"role": "user", "content": text})

    async def add_assistant(text):
        history.append({"role": "assistant", "content": text})

    async def generate(messages, tools=None):
        requests.append(messages)
        assert tools is None
        return NS(choices=[NS(message=NS(content="Welcome aboard."))])

    async def speak(text, **kwargs):
        spoken.append((text, kwargs))

    underlying = NS(
        name="Computer",
        config=NS(
            prompts=NS(backstory="Calm ship computer."),
            features=NS(condense_conversation=False),
        ),
        settings=NS(spoken_language="en"),
        add_user_message=add_user,
        conversation=NS(messages=history, add_assistant_message=add_assistant),
        actual_llm_call=generate,
        play_to_user=speak,
    )
    context = context_module.WingmanContext(underlying)
    # Demonstrate why the reader supplies explicit system instructions.
    await context.ai.converse("probe")
    assert not any(m["role"] == "system" for m in requests[-1])
    history.clear()
    requests.clear()
    with tempfile.TemporaryDirectory(prefix="sc-reader-v3-contract-") as tmp:
        root = Path(tmp)
        (root / "LIVE").mkdir()
        (root / "LIVE/Game.log").write_text(
            "User Login Success Handle[ContractPlayer]\n"
        )
        config.custom_properties = [
            NS(id=k, value=v)
            for k, v in {
                "sc_game_path": str(root),
                "runtime_directory": str(root / "runtime"),
                "instruction_url": "",
                "react_game_events": True,
            }.items()
        ]
        skill = manager.load_skill(config, underlying.settings, context)
        try:
            await skill.prepare()
            assert len(subscriptions) == 1
            assert len(skill.get_tools()) == 7
            for _ in range(100):
                if skill.service.state("LIVE")["player_name"] == "ContractPlayer":
                    break
                await asyncio.sleep(0.02)
            assert skill.service.state("LIVE")["player_name"] == "ContractPlayer"
            # Avoid GUI dependencies; the real public host facade remains in use.
            skill.notification_sink.display = None
            await skill.notification_sink.send("Player boarded ship: Pisces")
            await skill.notification_sink.task
            assert requests[-1][0]["role"] == "system"
            assert "Player names identify people" in requests[-1][0]["content"]
            assert "Calm ship computer" in requests[-1][0]["content"]
            assert spoken == [
                ("Welcome aboard.", {"no_interrupt": True, "sound_config": None})
            ]
            assert history[-2]["content"] == "[Game Event] Player boarded ship: Pisces"
            assert history[-1]["content"] == "Welcome aboard."
            for name, _ in skill.get_tools():
                result, _ = await skill.execute_tool(name, {}, None)
                assert result
        finally:
            await skill.unload()
        assert not subscriptions
        assert skill.service.closed
        from sc_log_reader.host_boundary import _registry

        for key in list(_registry.runtimes):
            if Path(key).is_relative_to(root):
                _registry.runtimes.pop(key)["stream"].close()
    files = [
        "wingmen/facade.py",
        "wingmen/wingman_context.py",
        "skills/skill_base.py",
        "services/module_manager.py",
    ]
    print(
        json.dumps(
            {
                "passed": True,
                "host_source_sha256": {
                    f: hashlib.sha256((host / f).read_bytes()).hexdigest()
                    for f in files
                },
                "checks": [
                    "actual module probe and load",
                    "actual closed facade",
                    "actual base init prepare unload",
                    "seven tool calls",
                    "isolated log ingestion",
                    "explicit reaction context",
                    "history append",
                    "non-interrupting TTS delegation",
                ],
                "limits": "Selected installed methods with configuration, provider, GUI and hardware doubles; no live Wingman launch or audible playback.",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(verify(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()))

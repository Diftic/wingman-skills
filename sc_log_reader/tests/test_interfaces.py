import asyncio
import importlib
import io
import json
import sys
import tempfile
import types
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.cli import main


class CliTests(unittest.TestCase):
    def test_replay_reports_state_without_wingman(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.log"
            path.write_text(
                "<2026-09-15T12:00:00Z> User Login Success Handle[Mallachi]\n"
            )
            out = io.StringIO()
            with redirect_stdout(out):
                result = main(["replay", str(path)])
            self.assertEqual(result, 0)
            self.assertEqual(
                json.loads(out.getvalue())["state"]["player_name"], "Mallachi"
            )

    def test_invalid_json_returns_error_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"run":"no"}')
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["validate", str(path)]), 2)


class HostAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifecycle_exposes_real_service_state_and_stops_cleanly(self):
        # Only the unavailable Wingman host is doubled. The reader/service and
        # filesystem watcher are the actual implementation.
        class FakeSkill:
            def __init__(self, config, settings, wingman):
                self.config = config
                self.settings = settings
                self.wingman = wingman
                self.printr = types.SimpleNamespace(toast_info=lambda *args, **kw: None)
                self.log = types.SimpleNamespace(
                    info=lambda *args, **kw: None, warning=lambda *args, **kw: None
                )

            async def prepare(self):
                pass

            async def unload(self):
                pass

        stub = types.ModuleType("skills.skill_base")
        stub.Skill = FakeSkill
        with patch.dict(
            sys.modules,
            {"skills": types.ModuleType("skills"), "skills.skill_base": stub},
        ):
            module = importlib.import_module("sc_log_reader.main")
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "LIVE").mkdir()
                (root / "LIVE/Game.log").write_text(
                    "<2026-09-15T12:00:00Z> User Login Success Handle[Mallachi]\n"
                )
                config = types.SimpleNamespace(
                    custom_properties=[
                        types.SimpleNamespace(id=k, value=v)
                        for k, v in {
                            "sc_game_path": str(root),
                            "runtime_directory": str(root / "runtime"),
                            "instruction_url": "",
                            "notify_game_events": False,
                        }.items()
                    ]
                )
                skill = module.SCLogReader(config, None, None)
                await skill.prepare()
                try:
                    for _ in range(50):
                        if skill.service.state("LIVE")["player_name"]:
                            break
                        await asyncio.sleep(0.02)
                    content, _ = await skill.execute_tool(
                        "get_current_game_state", {"environment": "LIVE"}, None
                    )
                    self.assertEqual(json.loads(content)["player_name"], "Mallachi")
                    self.assertNotIn(
                        "approve_update", [name for name, _ in skill.get_tools()]
                    )
                    real_poll = skill.tailer.poll
                    calls = 0

                    def fail_once():
                        nonlocal calls
                        calls += 1
                        if calls == 1:
                            raise RuntimeError("injected monitor failure")
                        return real_poll()

                    skill.tailer.poll = fail_once
                    for _ in range(150):
                        if calls > 1:
                            break
                        await asyncio.sleep(0.02)
                    self.assertGreater(
                        calls,
                        1,
                        "A monitor exception must not silently kill monitoring",
                    )
                finally:
                    await skill.unload()
                    # End this synthetic process; real runtime leases last
                    # until host process exit, not skill unload.
                    from sc_log_reader.host_boundary import _registry

                    for key in list(_registry.runtimes):
                        if Path(key).is_relative_to(root):
                            _registry.runtimes.pop(key)["stream"].close()
                self.assertTrue(skill.service.closed)
        sys.modules.pop("sc_log_reader.main", None)


if __name__ == "__main__":
    unittest.main()

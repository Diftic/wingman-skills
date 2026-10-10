"""The reader must work with a closed v3 facade, without raw Wingman access."""

import asyncio
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sc_log_reader.host_notifications import REACTION_PROMPT, WingmanReactionSink

ROOT = Path(__file__).resolve().parents[1]


def v3_host(generate=None):
    return types.SimpleNamespace(
        name="Computer",
        config=types.SimpleNamespace(
            prompts=types.SimpleNamespace(backstory="You are a calm ship computer.")
        ),
        settings=types.SimpleNamespace(spoken_language="en"),
        ai=types.SimpleNamespace(
            generate=generate or AsyncMock(return_value="Acknowledged.")
        ),
        conversation=types.SimpleNamespace(
            add_user=AsyncMock(), add_assistant=AsyncMock()
        ),
        tts=types.SimpleNamespace(speak=AsyncMock()),
    )


class V3Tests(unittest.IsolatedAsyncioTestCase):
    async def test_closed_facade_reaction_preserves_instructions_history_and_voice(
        self,
    ):
        host = v3_host()
        sink = WingmanReactionSink(host)
        await sink.send("Player boarded ship: Pisces")
        await sink.task
        host.conversation.add_user.assert_awaited_once_with(
            "[Game Event] Player boarded ship: Pisces"
        )
        args, kwargs = host.ai.generate.call_args
        self.assertEqual(args, ("[Game Event] Player boarded ship: Pisces",))
        self.assertIn(REACTION_PROMPT, kwargs["system"])
        self.assertIn(host.config.prompts.backstory, kwargs["system"])
        self.assertNotIn("tools", kwargs)
        host.conversation.add_assistant.assert_awaited_once_with("Acknowledged.")
        host.tts.speak.assert_awaited_once_with("Acknowledged.", interrupt=False)
        self.assertEqual(sink.stats["calls_returned"], 1)

    async def test_empty_provider_result_is_observable_and_never_spoken(self):
        host = v3_host(AsyncMock(return_value=""))
        sink = WingmanReactionSink(host)
        await sink.send("event")
        await sink.task
        host.tts.speak.assert_not_called()
        host.conversation.add_assistant.assert_not_called()
        self.assertEqual(sink.stats["empty_responses"], 1)

    async def test_voice_failure_is_observable_without_regenerating(self):
        host = v3_host()
        host.tts.speak.side_effect = RuntimeError("voice")
        sink = WingmanReactionSink(host)
        await sink.send("event")
        await sink.task
        host.ai.generate.assert_awaited_once()
        self.assertEqual(sink.stats["failures"], 1)

    async def test_busy_voice_is_owned_and_cancelled_on_unload(self):
        host = v3_host()
        speaking = asyncio.Event()

        async def speak(*args, **kwargs):
            speaking.set()
            await asyncio.Event().wait()

        host.tts.speak = speak
        sink = WingmanReactionSink(host)
        await sink.send("first")
        await speaking.wait()
        self.assertEqual(await sink.send("second"), 0)
        await sink.close()
        self.assertTrue(sink.task.done())

    async def test_disconnected_gui_does_not_abort_history_or_speech(self):
        host = v3_host()
        display = AsyncMock(side_effect=ConnectionError("disconnected"))
        sink = WingmanReactionSink(host, display=display)
        await sink.send("event")
        await sink.task
        self.assertEqual(sink.stats["display_failures"], 2)
        display.assert_any_await("user", "[Game Event] event")
        display.assert_any_await("assistant", "Acknowledged.")
        host.tts.speak.assert_awaited_once()

    def test_catalog_probe_does_not_load_core_or_touch_filesystem(self):
        wrapper = ROOT / "integrations/wingman_target/main.py"
        code = compile(wrapper.read_bytes(), str(wrapper), "exec")
        base = types.ModuleType("skills.skill_base")
        base.Skill = type("Skill", (), {})
        namespace = {"__file__": str(wrapper), "__name__": "reader_probe"}
        before = set(sys.modules)
        with (
            patch.dict(sys.modules, {"skills.skill_base": base}),
            patch.object(
                Path, "resolve", side_effect=AssertionError("catalog filesystem access")
            ),
        ):
            exec(code, namespace)
        self.assertTrue(issubclass(namespace["SCLogReader"], base.Skill))
        self.assertFalse(
            {"sc_log_reader.main", "regex"} & (set(sys.modules) - before)
        )

    def test_manifest_declares_v3_and_current_folder(self):
        config = (ROOT / "integrations/wingman_target/default_config.yaml").read_text()
        self.assertIn("api_version: 3\n", config)
        self.assertIn("module: skills.sc_log_reader.main\n", config)


if __name__ == "__main__":
    unittest.main()

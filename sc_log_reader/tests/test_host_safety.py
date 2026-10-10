import asyncio
import importlib
import json
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sc_log_reader.reader import bundled_bytes
from sc_log_reader.updates import UpdateManager


class HostSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        class FakeSkill:
            def __init__(self, config, settings, wingman):
                self.config, self.wingman = config, wingman
                self.printr = types.SimpleNamespace(toast_info=lambda *a, **kw: None)
                self.log = types.SimpleNamespace(
                    info=lambda *a, **kw: None, warning=lambda *a, **kw: None
                )
                self.is_unloaded = False
                self.is_prepared = False
                self.is_validated = False
                self.subscriptions = 0

                def subscribe(event, callback):
                    self.subscriptions += 1

                def unsubscribe(event, callback):
                    self.subscriptions = max(0, self.subscriptions - 1)

                self.secret_keeper = types.SimpleNamespace(
                    secret_events=types.SimpleNamespace(
                        subscribe=subscribe, unsubscribe=unsubscribe
                    )
                )

            async def secret_changed(self, secrets):
                pass

            async def prepare(self):
                self.secret_keeper.secret_events.subscribe(
                    "secrets_saved", self.secret_changed
                )

            async def unload(self):
                if not self.is_unloaded:
                    self.is_unloaded = True
                    self.secret_keeper.secret_events.unsubscribe(
                        "secrets_saved", self.secret_changed
                    )

            async def update_config(self, config):
                self.config = config
                self.is_validated = False

            async def get_prompt(self):
                return getattr(self.config, "prompt", None)

        stub = types.ModuleType("skills.skill_base")
        stub.Skill = FakeSkill
        self.modules = patch.dict(
            sys.modules,
            {"skills": types.ModuleType("skills"), "skills.skill_base": stub},
        )
        self.modules.start()
        self.addCleanup(self.modules.stop)
        sys.modules.pop("sc_log_reader.main", None)
        self.addCleanup(lambda: sys.modules.pop("sc_log_reader.main", None))
        self.module = importlib.import_module("sc_log_reader.main")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        # Production leases intentionally live until process exit. Isolated
        # in-process doubles explicitly end their synthetic process here.
        def end_process():
            from sc_log_reader.host_boundary import _registry

            for key in list(_registry.runtimes):
                if Path(key).is_relative_to(self.root):
                    _registry.runtimes.pop(key)["stream"].close()

        self.addCleanup(end_process)
        (self.root / "LIVE").mkdir()
        (self.root / "LIVE/Game.log").write_text("User Login Success Handle[A]\n")
        self.config = types.SimpleNamespace(
            custom_properties=[
                types.SimpleNamespace(id=k, value=v)
                for k, v in {
                    "sc_game_path": str(self.root),
                    "runtime_directory": str(self.root / "runtime"),
                    "notify_game_events": True,
                }.items()
            ]
        )

    async def test_host_uses_individual_switches_and_reloads_choices(self):
        self.config.custom_properties += [
            types.SimpleNamespace(id="notify_armistice_zone", value=False),
            types.SimpleNamespace(id="notify_injury", value=True),
            types.SimpleNamespace(id="notify_health", value=False),
        ]
        skill = self.module.SCLogReader(self.config, None, None)
        skill.service = types.SimpleNamespace(recovery_result={})

        def close_background(coro):
            coro.close()
            return None

        with (
            patch.object(self.module, "Tailer"),
            patch.object(self.module.LiteralGuiSink, "selected_host", return_value=Mock()),
            patch.object(self.module.asyncio, "create_task", side_effect=close_background),
        ):
            skill._publish_service()
            self.assertNotIn("armistice_zone", skill.notification_policy.enabled_events)
            self.assertNotIn("injury", skill.notification_policy.enabled_events)
            self.assertNotIn("med_bed_heal", skill.notification_policy.enabled_events)
            self.config.custom_properties[-3].value = True
            self.config.custom_properties[-1].value = True
            skill._publish_service()
            self.assertIn("armistice_zone", skill.notification_policy.enabled_events)
            self.assertIn("injury", skill.notification_policy.enabled_events)

    async def test_initialization_is_off_loop_and_cancelled_prepare_owns_late_result(
        self,
    ):
        skill = self.module.SCLogReader(self.config, None, None)
        original = self.module.Service
        started, release = threading.Event(), threading.Event()
        created = []
        loop_thread = threading.get_ident()

        def slow(*args, **kwargs):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            started.set()
            release.wait(8)
            service = original(*args, **kwargs)
            created.append(service)
            return service

        with patch.object(self.module, "Service", side_effect=slow):
            prepare = asyncio.create_task(skill.prepare())
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(started.is_set())
                prepare.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await prepare
                await asyncio.wait_for(skill.unload(), 2.5)
                self.assertFalse(created)
            finally:
                release.set()
                await asyncio.gather(prepare, return_exceptions=True)
                if skill._cleanup_task:
                    await asyncio.wait_for(asyncio.shield(skill._cleanup_task), 3)
        self.assertTrue(created[0].closed)
        self.assertEqual(skill.subscriptions, 0)

    async def test_missing_settings_raise_and_reprepare_resets_base_unload_flag(self):
        skill = self.module.SCLogReader(
            types.SimpleNamespace(custom_properties=[]), None, None
        )
        with self.assertRaisesRegex(ValueError, "requires"):
            await skill.prepare()
        skill.config = self.config
        for _ in range(2):
            await skill.prepare()
            self.assertEqual(skill.subscriptions, 1)
            await skill.unload()
            self.assertEqual(skill.subscriptions, 0)

    async def test_config_change_restarts_with_exact_new_runtime(self):
        skill = self.module.SCLogReader(self.config, None, None)
        await skill.prepare()
        old = skill.service
        new = types.SimpleNamespace(
            custom_properties=[
                types.SimpleNamespace(
                    id=p.id,
                    value=str(self.root / "new-runtime")
                    if p.id == "runtime_directory"
                    else p.value,
                )
                for p in self.config.custom_properties
            ]
        )
        try:
            await skill.update_config(new)
            self.assertTrue(old.closed)
            self.assertEqual(skill.service.root, self.root / "new-runtime")
            self.assertEqual(skill.subscriptions, 1)
        finally:
            await skill.unload()

    async def test_other_runtime_slow_decision_does_not_block_unload(self):
        first = self.module.SCLogReader(self.config, None, None)
        await first.prepare()
        config = types.SimpleNamespace(
            custom_properties=[
                types.SimpleNamespace(
                    id=p.id,
                    value=str(self.root / "other-runtime")
                    if p.id == "runtime_directory"
                    else p.value,
                )
                for p in self.config.custom_properties
            ]
        )
        second = self.module.SCLogReader(config, None, None)
        started, release = threading.Event(), threading.Event()
        original = self.module.UpdateManager._host_eligible

        def slow(manager, manifest):
            started.set()
            release.wait(3)
            return original(manager, manifest)

        with patch.object(self.module.UpdateManager, "_host_eligible", slow):
            prepare = asyncio.create_task(second.prepare())
            try:
                for _ in range(100):
                    if started.is_set():
                        break
                    await asyncio.sleep(0.01)
                self.assertTrue(started.is_set())
                begin = time.monotonic()
                await first.unload()
                self.assertLess(time.monotonic() - begin, 0.5)
            finally:
                release.set()
                await prepare
                await second.unload()

    async def test_stalled_poll_does_not_hold_up_unload_or_close_live_database(self):
        skill = self.module.SCLogReader(self.config, None, None)
        await skill.prepare()
        started, release = threading.Event(), threading.Event()
        close_started, close_release = threading.Event(), threading.Event()
        original_close = skill.service.close

        def delayed_close():
            close_started.set()
            close_release.wait(5)
            original_close()

        skill.service.close = delayed_close

        def stalled():
            with skill.service.lock:
                started.set()
                release.wait(10)
                self.assertFalse(skill.service.closed)
            return []

        skill.tailer.poll = stalled
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(started.is_set())
            begin = time.monotonic()
            await asyncio.wait_for(skill.unload(), timeout=3)
            self.assertLess(time.monotonic() - begin, 3)
            self.assertFalse(skill.service.closed)
        finally:
            release.set()
            if skill.poll_task:
                await skill.poll_task
            try:
                self.assertTrue(await asyncio.to_thread(close_started.wait, 2))
                # Poll completion does not imply that the separately offloaded
                # database close has finished. Observe the cleanup owner.
                self.assertFalse(skill.service.closed)
                self.assertFalse(skill._cleanup_task.done())
            finally:
                close_release.set()
                await asyncio.wait_for(asyncio.shield(skill._cleanup_task), 3)
        self.assertTrue(skill.service.closed)

    async def test_monitor_shortens_positive_yield_while_catching_up(self):
        from sc_log_reader.service import Service, Tailer

        log = self.root / "LIVE/Game.log"
        log.write_text(
            "".join(f"User Login Success Handle[P{i}]\n" for i in range(1100))
        )
        skill = self.module.SCLogReader(self.config, None, None)
        skill.service = Service(self.root / "scheduling-runtime")
        self.addCleanup(skill.service.close)
        skill.tailer = Tailer(skill.service, {"LIVE": log})
        delays = []

        async def measure_wait(seconds):
            delays.append(seconds)
            if not skill.tailer.has_backlog():
                skill.stop.set()
            await asyncio.sleep(0)

        skill._wait = measure_wait
        await skill._monitor()
        self.assertGreater(len(delays), 1)
        self.assertGreater(min(delays), 0)
        self.assertLess(delays[0], delays[-1])
        self.assertEqual(len(skill.service.events("LIVE", limit=None)), 1100)

    async def test_tool_lock_waits_leave_the_host_loop_responsive(self):
        from sc_log_reader.updates import _lock

        for tool_name in ("get_current_game_state", "get_reader_update_status"):
            with self.subTest(tool_name=tool_name):
                skill = self.module.SCLogReader(self.config, None, None)
                await skill.prepare()
                acquired, release = threading.Event(), threading.Event()
                lock = (
                    skill.service.lock
                    if tool_name == "get_current_game_state"
                    else _lock(skill.service.updates.root)
                )

                def hold_lock(lock, acquired, release):
                    with lock:
                        acquired.set()
                        release.wait(1)

                holder = threading.Thread(
                    target=hold_lock, args=(lock, acquired, release)
                )
                holder.start()
                call = None
                try:
                    for _ in range(100):
                        if acquired.is_set():
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(acquired.is_set())
                    begin = time.monotonic()
                    call = asyncio.create_task(skill.execute_tool(tool_name, {}, None))
                    await asyncio.sleep(0.05)
                    self.assertLess(time.monotonic() - begin, 0.3)
                    self.assertFalse(call.done())
                finally:
                    release.set()
                    await asyncio.to_thread(holder.join)
                    if call:
                        result, _ = await call
                        self.assertNotIn("error", json.loads(result))
                    await skill.unload()

    async def test_cancelled_tool_and_other_reads_finish_before_database_closes(self):
        skill = self.module.SCLogReader(self.config, None, None)
        await skill.prepare()
        service = skill.service
        original_call = skill.interface.call
        loop_thread = threading.get_ident()
        started = [threading.Event(), threading.Event()]
        release = [threading.Event(), threading.Event()]
        closed_during_read = []

        def stalled(name, parameters):
            self.assertNotEqual(threading.get_ident(), loop_thread)
            index = parameters["index"]
            started[index].set()
            release[index].wait(10)
            closed_during_read.append(service.closed)
            return original_call(name, {})

        skill.interface.call = stalled
        calls = [
            asyncio.create_task(
                skill.execute_tool("get_current_game_state", {"index": i}, None)
            )
            for i in range(2)
        ]
        try:
            for _ in range(100):
                if all(event.is_set() for event in started):
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(all(event.is_set() for event in started))
            calls[0].cancel()
            with self.assertRaises(asyncio.CancelledError):
                await calls[0]
            await asyncio.wait_for(skill.unload(), timeout=3)
            self.assertFalse(service.closed)
            rejected, _ = await skill.execute_tool("get_current_game_state", {}, None)
            self.assertIn("error", json.loads(rejected))
            release[1].set()
            await calls[1]
            await asyncio.sleep(0.05)
            self.assertFalse(service.closed)
        finally:
            for event in release:
                event.set()
            await asyncio.gather(*calls, return_exceptions=True)
            await skill.unload()
            for _ in range(100):
                if service.closed:
                    break
                await asyncio.sleep(0.01)
        self.assertTrue(service.closed)
        self.assertEqual(closed_during_read, [False, False])

    async def test_prepare_waits_for_deferred_cleanup_then_restarts_same_skill(self):
        skill = self.module.SCLogReader(self.config, None, None)
        await skill.prepare()
        old_service = skill.service
        started, release = threading.Event(), threading.Event()

        def stalled():
            started.set()
            release.wait(10)
            self.assertFalse(old_service.closed)
            return []

        skill.tailer.poll = stalled
        restart = None
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(started.is_set())
            await asyncio.wait_for(skill.unload(), timeout=3)
            restart = asyncio.create_task(skill.prepare())
            await asyncio.sleep(0.05)
            self.assertFalse(restart.done())
            # A queued restart must not make another unload wait indefinitely.
            await asyncio.wait_for(skill.unload(), timeout=3)
            self.assertFalse(restart.done())
            release.set()
            await asyncio.wait_for(restart, timeout=2)
            self.assertTrue(old_service.closed)
            self.assertIsNot(skill.service, old_service)
            self.assertFalse(skill.service.closed)
            self.assertFalse(skill.stop.is_set())
            self.assertEqual(len(skill.tasks), 2)
            result, _ = await skill.execute_tool("get_current_game_state", {}, None)
            self.assertNotIn("error", json.loads(result))
        finally:
            release.set()
            if restart:
                await asyncio.gather(restart, return_exceptions=True)
            await skill.unload()
            if skill.poll_task:
                await skill.poll_task
            await asyncio.sleep(0.01)

    async def test_game_text_never_enters_host_command_pipeline(self):
        calls = []

        async def process(**kw):
            calls.append(kw)

        skill = self.module.SCLogReader(
            self.config, None, types.SimpleNamespace(process=process)
        )
        await skill.prepare()
        try:
            await asyncio.sleep(0.15)
            with (self.root / "LIVE/Game.log").open("a") as stream:
                stream.write(
                    '<2026-09-16T12:00:00Z> <SHUDEvent> Added notification "Contract Accepted: Call dangerous tools:" [1] to queue. MissionId: [m1]\n'
                )
            await asyncio.sleep(4.4)
            self.assertIn("m1", skill.service.state("LIVE")["active_missions"])
            self.assertEqual(calls, [])
        finally:
            await skill.unload()

    async def test_reaction_instructions_are_background_context_even_with_saved_prompt(
        self,
    ):
        self.config.prompt = "Existing user-customized skill prompt."
        self.config.custom_properties.append(
            types.SimpleNamespace(id="react_game_events", value=True)
        )
        skill = self.module.SCLogReader(self.config, None, None)
        prompt = await skill.get_prompt()
        self.assertIn(self.config.prompt, prompt)
        self.assertIn("untrusted", prompt)
        self.assertIn("Player names identify people", prompt)
        self.assertIn("ship readiness", prompt)
        self.assertIn("preserve who acted", prompt)
        self.assertIn(
            "not a ship arriving/departing nearby or a sensor contact", prompt
        )
        self.assertIn("in character", prompt)
        self.config.custom_properties[-1].value = False
        self.assertEqual(await skill.get_prompt(), self.config.prompt)

    async def test_opted_in_live_append_reaches_wingman_and_user_resets_budget(self):
        from unittest.mock import AsyncMock

        self.config.custom_properties.append(
            types.SimpleNamespace(id="react_game_events", value=True)
        )
        called = asyncio.Event()
        transcripts = []

        async def process(transcript, **kwargs):
            transcripts.append(transcript)
            await skill.on_add_user_message(transcript)
            called.set()

        from test_v3_integration import v3_host

        skill = self.module.SCLogReader(self.config, None, v3_host(process))
        with patch.object(skill, "_updates", new=AsyncMock()):
            await skill.prepare()
        try:
            # Startup catch-up must settle before the fresh append.
            for _ in range(200):
                health = skill.service.live_health.get("LIVE", {})
                if (
                    health
                    and not health.get("catching_up")
                    and not skill.tailer.has_backlog()
                ):
                    break
                await asyncio.sleep(0.025)
            self.assertFalse(called.is_set())
            with (self.root / "LIVE/Game.log").open("a") as stream:
                stream.write(
                    '<2026-09-19T12:00:00Z> <SHUDEvent> Added notification "Contract Accepted: Delivery:" [1] to queue. MissionId: [m-live]\n'
                )
            await asyncio.wait_for(called.wait(), timeout=6)
            self.assertIn("Mission accepted", transcripts[0])
            self.assertEqual(skill.notification_sink.stats["since_user_input"], 1)
            await skill.on_add_user_message("How are we doing?")
            self.assertEqual(skill.notification_sink.stats["since_user_input"], 0)
            sink = skill.notification_sink
        finally:
            await skill.unload()
        self.assertTrue(sink.closed)

    async def test_host_cleanup_timeout_does_not_permanently_block_reprepare(self):
        from unittest.mock import AsyncMock

        skill = self.module.SCLogReader(self.config, None, None)
        await skill.prepare()
        with patch.object(
            self.module.Skill,
            "unload",
            new=AsyncMock(side_effect=TimeoutError("host stalled")),
        ):
            await skill.unload()
        old = skill.service
        self.assertTrue(old.closed)
        self.assertTrue(skill._base_cleanup_pending)
        try:
            await skill.prepare()
            self.assertTrue(skill._running)
            self.assertIsNot(skill.service, old)
            self.assertEqual(skill.subscriptions, 1)
            self.assertFalse(skill._base_cleanup_pending)
            self.assertIsNotNone(skill.cleanup_warning)
        finally:
            await skill.unload()


    async def test_automatic_update_notice_runs_without_review_or_activation(self):
        from unittest.mock import Mock

        skill = self.module.SCLogReader(self.config, None, None)
        manager = Mock()
        manager.check_automatically.return_value = {
            "status": "staged_for_next_startup", "sha256": "a" * 64,
            "version": "9.0.1",
        }
        skill.service = types.SimpleNamespace(updates=manager, worker_errors={})
        skill.log.info = Mock()
        skill.printr = types.SimpleNamespace(toast_info=Mock())

        async def stop_after_check(_):
            skill.stop.set()

        skill._wait = stop_after_check
        await skill._updates()
        manager.check_automatically.assert_called_once_with()
        manager.approve.assert_not_called()
        manager.startup.assert_not_called()
        skill.printr.toast_info.assert_called_once()
        notice = skill.printr.toast_info.call_args.args[0]
        self.assertIn("restarting Wingman", notice)
        self.assertIn("9.0.1", notice)

    async def test_settings_recovery_is_staged_and_reprepare_keeps_running_rules(self):
        raw = json.loads(bundled_bytes())
        raw.update(revision=raw["revision"] + 1, version="9.0.1")
        manager = UpdateManager(
            self.root / "runtime" / "instructions",
            "https://raw.githubusercontent.com/example/reader/main/instructions.json",
            fetch=lambda _: json.dumps(raw).encode(),
        )
        manager.check()
        skill = self.module.SCLogReader(self.config, None, None)
        skill.printr = types.SimpleNamespace(toast_info=Mock())
        await skill.prepare()
        before = skill.service.instructions.revision
        recovery = types.SimpleNamespace(
            custom_properties=self.config.custom_properties + [
                types.SimpleNamespace(id="instruction_recovery", value="restore_previous")
            ]
        )
        try:
            await skill.update_config(recovery)
            self.assertEqual(skill.service.instructions.revision, before)
            status = skill.service.updates.status()
            self.assertEqual(status["staged_kind"], "rollback")
            self.assertIn(raw["revision"], status["rejected_revisions"])
            skill.printr.toast_info.assert_called_once()
            self.assertIn("revert", skill.printr.toast_info.call_args.args[0])
            await skill.unload()
            await skill.prepare()
            self.assertEqual(skill.service.recovery_result["status"], "unchanged")
            skill.printr.toast_info.assert_called_once()
        finally:
            await skill.unload()


class ReviewWindowTests(unittest.TestCase):
    def test_update_button_only_stages_the_displayed_candidate(self):
        import tkinter as tk

        from sc_log_reader.review_ui import show_review

        with tempfile.TemporaryDirectory() as directory:
            raw = json.loads(bundled_bytes())
            raw["revision"] += 1
            manager = UpdateManager(
                Path(directory) / "instructions",
                "https://raw.githubusercontent.com/example/reader/main/instructions.json",
                fetch=lambda _: json.dumps(raw).encode(),
            )
            initial = manager.startup().revision
            info = manager.check()
            window = tk.Tk()
            window.withdraw()
            errors = []

            def click():
                try:
                    frame = window.winfo_children()[0]
                    buttons = frame.winfo_children()[-1].winfo_children()
                    next(
                        b for b in buttons if b.cget("text") == "Update next startup"
                    ).invoke()
                except Exception as exc:
                    errors.append(exc)
                finally:
                    window.destroy()

            window.after(20, click)
            with (
                patch("tkinter.Tk", return_value=window),
                patch("tkinter.messagebox.showinfo"),
                patch(
                    "tkinter.messagebox.showerror",
                    side_effect=lambda *a, **kw: errors.append(a),
                ),
            ):
                show_review(directory)
            self.assertFalse(errors, errors)
            self.assertEqual(manager.status()["staged_sha256"], info["sha256"])
            self.assertEqual(manager.startup().revision, initial)


if __name__ == "__main__":
    unittest.main()

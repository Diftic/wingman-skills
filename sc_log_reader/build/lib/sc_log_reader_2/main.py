"""Thin adapter for the local legacy Wingman Skill(config, settings, wingman) API.

This module requires Wingman at runtime. Standalone core/CLI do not import it.
Public Wingman API 3 integration needs a separate lifecycle adapter.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import suppress
from pathlib import Path

from skills.skill_base import Skill

from .service import Service, Tailer, ToolInterface


class SCLogReader2(Skill):
    def __init__(self, config, settings, wingman):
        super().__init__(config, settings, wingman)
        self.service = None
        self.interface = None
        self.tasks = []
        self.stop = asyncio.Event()
        self.notifications = 0
        self.poll_task = None
        self._lifecycle_lock = asyncio.Lock()
        self._running = False
        self._workers = set()
        self._cleanup_task = None
        self.cleanup_warning = None

    def _setting(self, name, default=None):
        return next(
            (p.value for p in self.config.custom_properties if p.id == name), default
        )

    async def prepare(self):
        while True:
            async with self._lifecycle_lock:
                if self._running:
                    return
                cleanup = self._cleanup_task
                if cleanup is None or cleanup.done():
                    if cleanup is not None:
                        cleanup.result()
                        self._cleanup_task = None
                    await self._prepare_service()
                    return
            # Keep the lifecycle lock free for unload while a previous
            # generation still has threads using its database or update files.
            await asyncio.shield(cleanup)

    async def _prepare_service(self):
        game = Path(self._setting("sc_game_path", ""))
        runtime = self._setting("runtime_directory", "")
        if not self._setting("sc_game_path") or not runtime:
            self.printr.toast_info(
                "SC Log Reader 2 requires Star Citizen Path and Runtime Directory settings."
            )
            return
        await super().prepare()
        self.stop = asyncio.Event()
        self.poll_task = None
        self.service = Service(
            runtime,
            update_url=self._setting("instruction_url") or None,
            activate_updates=True,
        )
        if self.cleanup_warning:
            self.service.worker_errors["previous_host_cleanup"] = self.cleanup_warning
        self.interface = ToolInterface(self.service)
        paths = {
            env: game / env / "Game.log"
            for env in ("LIVE", "PTU", "EPTU", "HOTFIX", "TECH-PREVIEW")
        }
        self.tailer = Tailer(self.service, paths)
        self.tasks = [
            asyncio.create_task(self._monitor()),
            asyncio.create_task(self._updates()),
        ]

        self._running = True

    def _start_worker(self, function, *args):
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        self._workers.add(task)

        def finished(worker):
            self._workers.discard(worker)
            # A cancelled host caller no longer retrieves worker exceptions.
            if not worker.cancelled():
                worker.exception()

        task.add_done_callback(finished)
        return task

    async def _wait(self, seconds):
        with suppress(TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=seconds)

    async def _monitor(self):
        failures = 0
        if self._setting("notify_game_events", False):
            self.printr.toast_info(
                "SC Log Reader 2 reactions are disabled until a restricted host notification API is integrated."
            )
        while not self.stop.is_set():
            try:
                self.poll_task = self._start_worker(self.tailer.poll)
                await asyncio.shield(self.poll_task)
                self.service.worker_errors.pop("monitor", None)
                failures = 0
            except Exception as exc:  # isolate unexpected worker failure from Wingman
                failures += 1
                self.service.worker_errors["monitor"] = {
                    "error": type(exc).__name__,
                    "consecutive_failures": failures,
                    "paused": failures >= 3,
                }
                if failures in (1, 3):
                    self.printr.toast_info(
                        "SC Log Reader 2 monitoring failed. See reader health."
                        + (
                            " Restart the skill to retry."
                            if failures >= 3
                            else " Retrying."
                        )
                    )
                if failures >= 3:
                    return
            await self._wait(1 if failures else 0.25)

    async def _updates(self):
        last_digest = None
        while not self.stop.is_set():
            try:
                result = await asyncio.shield(
                    self._start_worker(self.service.updates.check)
                )
                self.service.worker_errors.pop("updates", None)
                if result["status"] == "available" and result["sha256"] != last_digest:
                    self.printr.toast_info(
                        f"SC Log Reader 2 instructions {result['version']} are available. Review and approve the update; activation is at next startup."
                    )
                    last_digest = result["sha256"]
                elif result["status"] == "reader_upgrade_required":
                    self.service.worker_errors["updates"] = result
                    self.printr.toast_info(
                        "SC Log Reader 2 needs a reader upgrade before new definitions can be used."
                    )
            except (
                Exception
            ) as exc:  # network/protocol/host failures must not kill checking
                self.service.worker_errors["updates"] = {
                    "error": type(exc).__name__,
                    "retry_in_seconds": 6 * 3600,
                }
            await self._wait(6 * 3600)

    def get_tools(self):
        return (
            self.interface.get_tools()
            if self.interface
            else ToolInterface(None).get_tools()
        )

    async def execute_tool(self, tool_name, parameters, benchmark):
        if not self._running or self.interface is None:
            return json.dumps({"error": "SC Log Reader 2 is not running"}), ""
        # Register before yielding so unload cannot miss an admitted read.
        worker = self._start_worker(self.interface.call, tool_name, parameters)
        try:
            result = await asyncio.shield(worker)
            return json.dumps(result, ensure_ascii=False), ""
        except (ValueError, TypeError):
            return json.dumps({"error": "Invalid tool name or parameters"}), ""

    async def on_add_user_message(self, message):
        if not message.startswith(("[Game Event]", "[Game Events]")):
            self.notifications = 0

    async def _finish_shutdown(self, service, tasks):
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Polls, update checks and tool reads are shielded from their callers'
        # cancellation. No new work is admitted after _running becomes false.
        await asyncio.gather(*tuple(self._workers), return_exceptions=True)
        if service is not None:
            await asyncio.to_thread(service.close)
        try:
            await asyncio.wait_for(super().unload(), timeout=2)
        except Exception as exc:
            # Our threads and database have already drained safely. A host
            # cleanup failure is observable but must not poison later starts.
            self.cleanup_warning = {
                "error": type(exc).__name__,
                "local_cleanup_complete": True,
            }

    async def unload(self):
        async with self._lifecycle_lock:
            if self._cleanup_task is None:
                self._running = False
                self.stop.set()
                if hasattr(self, "tailer"):
                    self.tailer.stop_requested.set()
                self._cleanup_task = asyncio.create_task(
                    self._finish_shutdown(self.service, self.tasks)
                )
                self.tasks = []
            cleanup = self._cleanup_task
        # Cancellation cannot stop a thread. Keep cleanup alive after this
        # bounded host wait; prepare will await it before opening a service.
        with suppress(TimeoutError):
            await asyncio.wait_for(asyncio.shield(cleanup), timeout=2)

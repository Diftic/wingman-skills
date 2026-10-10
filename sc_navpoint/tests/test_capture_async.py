"""A capture must not stop the event loop it was asked from.

Everything under `_capture_position_local` blocks: the in-function imports,
`mss()`, the grab, the PIL and numpy conversion, the saturation and presence
predicates, the OCR, the field parse, the ink and periodicity measurements,
`parse_payload`, the pause between attempts, and a synchronous file append per
trace line including one per decoded row. The two 2026-08-02 refusals took
roughly eleven seconds each and every millisecond of it was spent on the
caller's loop, so nothing else the assistant was doing could progress.

`asyncio.to_thread` and NOT `create_task`. The finding recorded at
`_start_nav_polling` is that a task created inside a tool call belongs to that
call's loop, Wingman does not keep that loop alive, and the task is therefore
abandoned at its first await. `to_thread` cannot hit that: the coroutine awaits
its own result, so the loop is alive for the whole duration by construction.
"""

from __future__ import annotations

import asyncio
import inspect
import re
import sys
import threading
import time
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402


_MAIN_SRC = (Path(main.__file__).with_name("main.py")).read_text(encoding="utf-8")


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _Scanner:
    last_reject_reason = None


def _skill(local) -> main.SC_NavPoint:
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill._scanner = _Scanner()
    skill._db = None
    skill._ui_server = None
    skill._capture_position_local = local
    return skill


def test_the_loop_keeps_running_while_a_capture_blocks() -> None:
    """The whole point. Under the old code the ticker completed zero ticks,
    because a blocking capture and the loop were the same thread."""
    ticks = 0

    def _slow(attempts: int = 1) -> dict | None:
        time.sleep(0.3)
        return None

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    async def _drive() -> None:
        ticker = asyncio.ensure_future(_ticker())
        try:
            await _skill(_slow)._capture_position()
        finally:
            ticker.cancel()

    asyncio.run(_drive())
    assert ticks >= 3, ticks


def test_the_capture_runs_off_the_loop_thread() -> None:
    """Not merely 'the loop stayed responsive', which a sufficiently fast stub
    would also produce: the blocking work must be on a DIFFERENT thread."""
    seen: list[int] = []

    def _record(attempts: int = 1) -> dict | None:
        seen.append(threading.get_ident())
        return None

    async def _drive() -> None:
        seen.append(threading.get_ident())
        await _skill(_record)._capture_position()

    asyncio.run(_drive())
    loop_thread, capture_thread = seen
    assert capture_thread != loop_thread


def test_the_result_still_comes_back_intact() -> None:
    """Offloading must change where the work runs and nothing else."""
    position = {"body": "Daymar", "x": 1.0, "y": 2.0, "z": 3.0}
    result = asyncio.run(_skill(lambda attempts=1: dict(position))._capture_position())
    assert result is not None
    assert {k: result[k] for k in position} == position
    # The freshness stamp is applied on the awaiting side, as it always was.
    assert "captured_at" in result


def test_the_attempt_count_still_reaches_the_local_read() -> None:
    seen: list[int] = []
    skill = _skill(lambda attempts=1: seen.append(attempts))
    asyncio.run(skill._capture_position(main.MARK_CAPTURE_ATTEMPTS))
    assert seen == [main.MARK_CAPTURE_ATTEMPTS]


def test_an_exception_from_the_worker_still_reaches_the_caller() -> None:
    """`to_thread` re-raises on the awaiting side. A capture that blew up must
    not become a silent None."""

    def _boom(attempts: int = 1):
        raise RuntimeError("the reader exploded")

    with pytest.raises(RuntimeError, match="the reader exploded"):
        asyncio.run(_skill(_boom)._capture_position())


def test_the_seam_keeps_its_sync_and_async_sides() -> None:
    """`_capture_position_local` stays fully synchronous: it is the unit the
    lock and the thread wrap, and twenty existing tests call it directly."""
    assert not inspect.iscoroutinefunction(main.SC_NavPoint._capture_position_local)
    assert inspect.iscoroutinefunction(main.SC_NavPoint._capture_position)


def test_the_offload_is_to_thread_and_wraps_the_local_read() -> None:
    assert "await asyncio.to_thread(self._capture_position_local, attempts)" in _MAIN_SRC


def test_no_task_is_created_anywhere_in_the_skill() -> None:
    """A task created in a tool call belongs to a loop Wingman does not keep
    alive, and is abandoned at its first await. Nothing in this file calls
    `create_task` at all: polling builds its own loop on its own thread, and the
    only surviving `_nav_task` code is the teardown of a legacy attribute a
    running install may still carry."""
    calls = [line.strip() for line in _MAIN_SRC.splitlines() if "create_task(" in line]
    assert calls == []
    teardown = [line.strip() for line in _MAIN_SRC.splitlines() if "_nav_task" in line]
    assert all("create_task" not in line for line in teardown)


def test_the_capture_lock_holds_no_await() -> None:
    """R5. A lock held across an await is a deadlock waiting for two callers,
    and the poll thread plus a spoken command are exactly two callers."""
    body = inspect.getsource(main.SC_NavPoint._capture_position_local)
    assert "_capture_lock" in body
    opened = [
        line for line in body.splitlines() if "with getattr(self, \"_capture_lock\"" in line
    ]
    assert len(opened) == 1
    indent = len(opened[0]) - len(opened[0].lstrip())
    inside = body.split(opened[0], 1)[1]
    for line in inside.splitlines():
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        assert not re.search(r"\bawait\b", line), line


def test_the_lock_is_acquired_in_exactly_one_function() -> None:
    holders = [
        line for line in _MAIN_SRC.splitlines()
        if "with getattr(self, \"_capture_lock\"" in line
    ]
    assert len(holders) == 1


def test_the_retry_pause_stays_a_blocking_sleep() -> None:
    """Current single-pass/held-display policy; supersedes the earlier retry rule."""
    body = inspect.getsource(main.SC_NavPoint._capture_position_local)
    assert "time.sleep(CAPTURE_RETRY_DELAY_S)" not in body
    assert "asyncio.sleep" not in body

"""The poll log must not grow without bound, and must never lose a line.

It is the only instrument this skill has: the python `logger` reaches no file
anyone can read, so a refusal that leaves no line in navpoint_poll.log costs a
live session to explain. The per-attempt instrumentation writes more of them,
and at `poll_interval: 1` a session writes one line per second per successful
capture plus up to nine per refusal.

So the file rotates rather than truncating. A cap that overwrote or truncated
would destroy the very evidence the log exists to collect, which is the one
failure mode worse than a large file.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import main  # noqa: E402


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


def _skill(tmp_path: Path):
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    return skill


def _fill(path: Path, size: int) -> str:
    """A file of at least `size` bytes whose content a test can compare."""
    line = "2026-08-02 00:10:12 capture REFUSED: something went wrong" + chr(10)
    content = line * (size // len(line) + 1)
    path.write_text(content, encoding="utf-8")
    return content


def test_an_oversized_log_is_moved_aside_not_truncated(tmp_path):
    """The rotation is the whole point: the old lines survive in .1 exactly as
    they were written."""
    live = tmp_path / "navpoint_poll.log"
    old = _fill(live, main.POLL_LOG_MAX_BYTES)
    assert live.stat().st_size > main.POLL_LOG_MAX_BYTES

    main._rotate_poll_log(str(live))

    assert not live.exists() or live.stat().st_size == 0
    rotated = tmp_path / "navpoint_poll.log.1"
    assert rotated.exists()
    assert rotated.read_text(encoding="utf-8") == old


def test_a_log_under_the_cap_is_left_alone(tmp_path):
    live = tmp_path / "navpoint_poll.log"
    live.write_text("one line" + chr(10), encoding="utf-8")

    main._rotate_poll_log(str(live))

    assert live.read_text(encoding="utf-8") == "one line" + chr(10)
    assert not (tmp_path / "navpoint_poll.log.1").exists()


def test_a_missing_log_is_not_an_error(tmp_path):
    main._rotate_poll_log(str(tmp_path / "navpoint_poll.log"))
    assert not (tmp_path / "navpoint_poll.log.1").exists()


def test_a_second_rotation_keeps_exactly_one_generation(tmp_path, monkeypatch):
    """Two files, never three. The bound on disk is the cap twice."""
    monkeypatch.setattr(main, "POLL_LOG_MAX_BYTES", 64)
    live = tmp_path / "navpoint_poll.log"

    live.write_text("first generation" * 8, encoding="utf-8")
    main._rotate_poll_log(str(live))
    live.write_text("second generation" * 8, encoding="utf-8")
    main._rotate_poll_log(str(live))

    assert (tmp_path / "navpoint_poll.log.1").read_text(
        encoding="utf-8"
    ) == "second generation" * 8
    assert not (tmp_path / "navpoint_poll.log.2").exists()


def test_the_trace_rotates_before_it_appends(tmp_path, monkeypatch):
    """Driven through the real `_poll_trace`, because a rotation the writer
    never calls is a rotation that never happens."""
    monkeypatch.setattr(main, "POLL_LOG_MAX_BYTES", 64)
    live = tmp_path / "navpoint_poll.log"
    live.write_text("older than the cap" * 8, encoding="utf-8")

    _skill(tmp_path)._poll_trace("a fresh line", chat=False)

    assert "a fresh line" in live.read_text(encoding="utf-8")
    assert live.stat().st_size < 100
    assert "older than the cap" in (tmp_path / "navpoint_poll.log.1").read_text(
        encoding="utf-8"
    )


def test_a_rotation_failure_still_lets_the_line_through(tmp_path, monkeypatch):
    """A logging failure must never change what the caller was doing, and
    losing the line would be the worse of the two outcomes here."""
    monkeypatch.setattr(main, "POLL_LOG_MAX_BYTES", 64)

    def _refuse(src, dst):
        raise OSError("the file is open in another process")

    monkeypatch.setattr(os, "replace", _refuse)
    live = tmp_path / "navpoint_poll.log"
    live.write_text("older than the cap" * 8, encoding="utf-8")

    _skill(tmp_path)._poll_trace("a fresh line", chat=False)

    text = live.read_text(encoding="utf-8")
    assert "a fresh line" in text
    assert "older than the cap" in text


def test_two_writers_cannot_rotate_the_same_file_twice(tmp_path, monkeypatch):
    """The poll thread and a tool call can arrive together. If both passed the
    size check, the second would move a nearly empty fresh file over `.1` and
    destroy the generation the first had just preserved, which is exactly the
    evidence loss rotation was chosen over a size cap to prevent."""
    monkeypatch.setattr(main, "POLL_LOG_MAX_BYTES", 64)
    live = tmp_path / "navpoint_poll.log"
    live.write_text("the generation that must survive" * 4, encoding="utf-8")

    real_getsize = os.path.getsize
    real_replace = os.replace
    replaces: list[tuple] = []

    def _slow_getsize(path):
        # Widens the window between the check and the move, so an unserialised
        # rotation loses the race deterministically instead of once a month.
        size = real_getsize(path)
        time.sleep(0.02)
        return size

    def _recording_replace(src, dst):
        replaces.append((src, dst))
        real_replace(src, dst)

    monkeypatch.setattr(os.path, "getsize", _slow_getsize)
    monkeypatch.setattr(os, "replace", _recording_replace)

    threads = [
        threading.Thread(target=main._rotate_poll_log, args=(str(live),))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert not any(thread.is_alive() for thread in threads)
    assert len(replaces) == 1
    assert (tmp_path / "navpoint_poll.log.1").read_text(
        encoding="utf-8"
    ) == "the generation that must survive" * 4


def test_a_rotation_failure_of_any_kind_is_swallowed(tmp_path, monkeypatch):
    """The helper owns its own failures rather than leaning on the caller's
    `try`, which the append shares."""
    monkeypatch.setattr(main, "POLL_LOG_MAX_BYTES", 64)

    def _explode(src, dst):
        raise RuntimeError("something nobody predicted")

    monkeypatch.setattr(os, "replace", _explode)
    live = tmp_path / "navpoint_poll.log"
    live.write_text("older than the cap" * 8, encoding="utf-8")

    main._rotate_poll_log(str(live))

    assert live.exists()

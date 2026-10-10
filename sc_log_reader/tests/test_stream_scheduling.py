import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.service import Service, Tailer, ToolInterface


class StreamSchedulingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.path = self.root / "Game.log"

    def logins(self, count):
        return b"".join(
            f"User Login Success Handle[P{i}]\n".encode() for i in range(count)
        )

    def drain(self, tail, count=40):
        for _ in range(count):
            tail.poll()
            meta = self.service.stream("LIVE")
            if meta and meta["offset"] == self.path.stat().st_size:
                return
        self.fail("queued records did not drain")

    def test_budget_prefix_retains_every_record_when_unread_bytes_are_zero(self):
        self.path.write_bytes(self.logins(350))
        tail = Tailer(self.service, {"LIVE": self.path})
        now = [10.0]
        real = self.service._ingest_in_transaction

        def advance(*args, **kwargs):
            result = real(*args, **kwargs)
            now[0] += 0.11
            return result

        clock = types.SimpleNamespace(monotonic=lambda: now[0], time=time.time)
        with (
            patch("sc_log_reader.service.time", clock),
            patch.object(self.service, "_ingest_in_transaction", advance),
        ):
            tail.poll()
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 2)
        health = self.service.health("LIVE")
        self.assertEqual(health["unread_bytes"], 0)
        self.assertGreater(health["pending_bytes"], 0)
        self.assertTrue(tail.has_backlog())
        self.drain(tail)
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 350)
        self.assertEqual(self.service.state("LIVE")["player_name"], "P349")
        self.assertFalse(tail.has_backlog())

    def test_flooded_environment_yields_next_poll_to_ptu(self):
        self.path.write_bytes(self.logins(1000))
        ptu = self.root / "ptu.log"
        ptu.write_bytes(b"User Login Success Handle[PTU]\n")
        tail = Tailer(self.service, {"LIVE": self.path, "PTU": ptu})
        now = [10.0]
        real = self.service._ingest_in_transaction

        def slow(*args, **kwargs):
            result = real(*args, **kwargs)
            now[0] += 0.21
            return result

        clock = types.SimpleNamespace(monotonic=lambda: now[0], time=time.time)
        with (
            patch("sc_log_reader.service.time", clock),
            patch.object(self.service, "_ingest_in_transaction", slow),
        ):
            tail.poll()
            tail.poll()
        self.assertEqual(self.service.state("PTU")["player_name"], "PTU")
        self.assertLess(len(self.service.events("LIVE", limit=None)), 1000)

    def test_rotation_discards_queued_records_from_previous_generation(self):
        self.path.write_bytes(self.logins(1000))
        tail = Tailer(self.service, {"LIVE": self.path})
        real = self.service.ingest_batch

        def stop_after_commit(*args, **kwargs):
            result = real(*args, **kwargs)
            tail.stop_requested.set()
            return result

        with patch.object(self.service, "ingest_batch", stop_after_commit):
            tail.poll()
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 128)
        old_generation = self.service.stream("LIVE")["generation"]
        self.path.write_bytes(b"User Login Success Handle[Replacement]\n")
        tail.stop_requested.clear()
        tail.poll()
        self.assertEqual(self.service.state("LIVE")["player_name"], "Replacement")
        self.assertNotEqual(self.service.stream("LIVE")["generation"], old_generation)
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 129)

    def test_restart_after_commit_resumes_first_unprocessed_byte(self):
        raw = self.logins(260)
        self.path.write_bytes(raw)
        tail = Tailer(self.service, {"LIVE": self.path})
        real = self.service.ingest_batch

        def interrupted(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("interrupted immediately after commit")

        with patch.object(self.service, "ingest_batch", interrupted):
            tail.poll()
        self.assertEqual(self.service.stream("LIVE")["offset"], len(self.logins(128)))
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.drain(Tailer(self.service, {"LIVE": self.path}))
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 260)

    def test_health_reports_progress_rates_and_tool_latency(self):
        self.path.write_bytes(self.logins(3))
        tail = Tailer(self.service, {"LIVE": self.path, "PTU": self.root / "absent"})
        tail.poll()
        ToolInterface(self.service).call(
            "get_current_game_state", {"environment": "LIVE"}
        )
        health = self.service.health("LIVE")
        self.assertEqual(health["bytes_read"], self.path.stat().st_size)
        self.assertEqual(health["bytes_committed"], self.path.stat().st_size)
        self.assertEqual(health["pending_bytes"], 0)
        self.assertGreaterEqual(health["read_bytes_per_second"], 0)
        self.assertGreaterEqual(health["commit_bytes_per_second"], 0)
        self.assertGreaterEqual(health["poll_latency_seconds"], 0)
        self.assertGreaterEqual(health["tool_latency_seconds"], 0)
        self.assertEqual(self.service.health("PTU")["error"], "Log file not found")

    def test_multiline_record_spans_input_chunks_and_batch_boundary(self):
        prefix = self.logins(128)
        opened = b'<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "Contract Accepted: Delivery'
        # The first physical notification line ends exactly at the input cap.
        padding = b"x" * (256 * 1024 - len(prefix) - len(opened) - 2) + b"\n"
        raw = prefix + padding + opened + b"\n"
        self.assertEqual(len(raw), 256 * 1024)
        self.path.write_bytes(raw)
        tail = Tailer(self.service, {"LIVE": self.path})
        tail.poll()
        self.assertEqual(
            self.service.stream("LIVE")["offset"], len(prefix) + len(padding)
        )
        self.assertFalse(tail.has_backlog())
        with self.path.open("ab") as stream:
            stream.write(b':" [13] to queue. MissionId: [multi]\n')
        self.drain(tail)
        self.assertIn("multi", self.service.state("LIVE")["active_missions"])
        self.assertEqual(
            sum(
                e["event_type"] == "mission_accepted"
                for e in self.service.events("LIVE", limit=None)
            ),
            1,
        )

    def test_earlier_checkpoint_does_not_inherit_later_discard_line(self):
        prefix = self.logins(129)
        self.path.write_bytes(
            prefix + b"x" * (256 * 1024) + b"User Login Success Handle[FAKE]\n"
        )
        tail = Tailer(self.service, {"LIVE": self.path})
        real = self.service.ingest_batch

        def stop_after_commit(*args, **kwargs):
            result = real(*args, **kwargs)
            tail.stop_requested.set()
            return result

        with patch.object(self.service, "ingest_batch", stop_after_commit):
            tail.poll()
        self.assertFalse(self.service.stream("LIVE")["discard_line"])
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.drain(Tailer(self.service, {"LIVE": self.path}))
        self.assertEqual(self.service.state("LIVE")["player_name"], "P128")
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 129)

    def test_source_disappearance_retains_safe_progress_until_it_returns(self):
        self.path.write_bytes(self.logins(3))
        tail = Tailer(self.service, {"LIVE": self.path})
        tail.poll()
        saved = self.service.stream("LIVE")
        moved = self.root / "away.log"
        self.path.rename(moved)
        tail.poll()
        self.assertEqual(self.service.stream("LIVE"), saved)
        self.assertEqual(self.service.health("LIVE")["error"], "Log file not found")
        moved.rename(self.path)
        tail.poll()
        self.assertEqual(len(self.service.events("LIVE", limit=None)), 3)
        self.assertIsNone(self.service.health("LIVE")["error"])

    def test_identity_comes_from_open_handle_when_path_changes_before_stat(self):
        self.path.write_bytes(b"User Login Success Handle[Opened]\n")
        replacement = self.root / "replacement.log"
        replacement.write_bytes(b"User Login Success Handle[Replacement]\n")
        real_stat = Path.stat

        def different_stat(path, *args, **kwargs):
            return real_stat(
                replacement if path == self.path else path, *args, **kwargs
            )

        with patch.object(Path, "stat", different_stat):
            Tailer(self.service, {"LIVE": self.path}).poll()
        actual = real_stat(self.path)
        self.assertEqual(
            self.service.stream("LIVE")["identity"], f"{actual.st_dev}:{actual.st_ino}"
        )

    def test_oversized_multiline_continuation_cannot_rewind_checkpoint_or_complete(
        self,
    ):
        opened = b'<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "Contract Accepted: False\n'
        self.path.write_bytes(opened + b"x" * (256 * 1024))
        tail = Tailer(self.service, {"LIVE": self.path})
        tail.poll()
        self.assertGreater(self.service.stream("LIVE")["offset"], len(opened))
        with self.path.open("ab") as stream:
            stream.write(b'\n:" [13] to queue. MissionId: [false]\n')
        self.drain(tail)
        self.assertNotIn("false", self.service.state("LIVE")["active_missions"])

    def test_committed_byte_metric_recovers_after_postcommit_interruption(self):
        self.path.write_bytes(self.logins(260))
        tail = Tailer(self.service, {"LIVE": self.path})
        real = self.service.ingest_batch

        def interrupted(*args, **kwargs):
            real(*args, **kwargs)
            raise OSError("interrupted after commit")

        with patch.object(self.service, "ingest_batch", interrupted):
            tail.poll()
        self.drain(tail)
        self.assertEqual(
            self.service.health("LIVE")["bytes_committed"], self.path.stat().st_size
        )

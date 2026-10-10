"""Exclusive standalone monitor lifecycle; no Wingman imports or game logs."""

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.host_boundary import _registry, claim_runtime
from sc_log_reader.service import Service
from sc_log_reader.updates import UpdateManager


class StandaloneOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sc-reader-final-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.runtime = self.root / "runtime"

        def end_synthetic_host_process():
            for key in list(_registry.runtimes):
                if Path(key).is_relative_to(self.root):
                    _registry.runtimes.pop(key)["stream"].close()

        self.addCleanup(end_synthetic_host_process)

    def test_watch_first_rejects_host_and_second_watch_until_close(self):
        watch = Service(self.runtime, activate_updates=True)
        try:
            with self.assertRaises(RuntimeError):
                claim_runtime(self.runtime)
            with self.assertRaises(RuntimeError):
                Service(self.runtime, activate_updates=True)
            # Short human maintenance does not require monitor ownership.
            self.assertIn(
                "active_sha256", UpdateManager(self.runtime / "instructions").status()
            )
        finally:
            watch.close()
        # Standalone ownership ends on close, not on process exit.
        next_watch = Service(self.runtime, activate_updates=True)
        next_watch.close()
        owner = claim_runtime(self.runtime)
        owner.release()

    def test_host_first_rejects_watch_even_after_skill_owner_release(self):
        owner = claim_runtime(self.runtime)
        with self.assertRaises(RuntimeError):
            Service(self.runtime, activate_updates=True)
        owner.release()
        with self.assertRaises(RuntimeError):
            Service(self.runtime, activate_updates=True)
        self.assertIn(
            "active_sha256", UpdateManager(self.runtime / "instructions").status()
        )

    def test_every_partial_initialization_failure_releases_watch_lease(self):
        targets = (
            "sc_log_reader.service.UpdateManager",
            "sc_log_reader.updates.UpdateManager._startup",
            "sc_log_reader.service.Reader",
            "sc_log_reader.service.sqlite3.connect",
            "sc_log_reader.service.support.initialize",
        )
        for target in targets:
            with self.subTest(target=target):
                with (
                    patch(target, side_effect=RuntimeError("injected failure")),
                    self.assertRaises(RuntimeError),
                ):
                    Service(self.runtime, activate_updates=True)
                watch = Service(self.runtime, activate_updates=True)
                watch.close()

    def test_lease_retained_until_database_close_finishes(self):
        watch = Service(self.runtime, activate_updates=True)
        real_db = watch.db
        entered, finish = threading.Event(), threading.Event()

        class SlowClose:
            def close(self):
                entered.set()
                finish.wait(5)
                real_db.close()

        watch.db = SlowClose()
        closer = threading.Thread(target=watch.close)
        closer.start()
        try:
            self.assertTrue(entered.wait(2))
            with self.assertRaises(RuntimeError):
                claim_runtime(self.runtime)
        finally:
            finish.set()
            closer.join(5)
        self.assertFalse(closer.is_alive())
        self.assertTrue(watch.closed)
        owner = claim_runtime(self.runtime)
        owner.release()

    def test_close_failure_keeps_exclusion_until_successful_retry(self):
        watch = Service(self.runtime, activate_updates=True)
        real_db = watch.db

        class FailedClose:
            def close(self):
                raise RuntimeError("close failed")

        watch.db = FailedClose()
        try:
            with self.assertRaises(RuntimeError):
                watch.close()
            with self.assertRaises(RuntimeError):
                claim_runtime(self.runtime)
        finally:
            watch.db = real_db
            watch.close()
        owner = claim_runtime(self.runtime)
        owner.release()

    def test_cross_process_both_startup_orders_and_two_watches(self):
        holder = """
import sys
from sc_log_reader.host_boundary import claim_runtime
from sc_log_reader.service import Service
owner = claim_runtime(sys.argv[1]) if sys.argv[2] == 'host' else Service(sys.argv[1], activate_updates=True)
print('ready', flush=True)
sys.stdin.readline()
if sys.argv[2] != 'host': owner.close()
"""
        probe = """
import json, sys
from sc_log_reader.host_boundary import claim_runtime
from sc_log_reader.service import Service
try:
    obj = claim_runtime(sys.argv[1]) if sys.argv[2] == 'host' else Service(sys.argv[1], activate_updates=True)
except RuntimeError:
    print(json.dumps({'excluded':True}))
else:
    if sys.argv[2] != 'host': obj.close()
    print(json.dumps({'excluded':False}))
"""
        for first, second in (("watch", "host"), ("host", "watch"), ("watch", "watch")):
            with self.subTest(first=first, second=second):
                runtime = self.root / (first + second)
                process = subprocess.Popen(
                    [sys.executable, "-B", "-c", holder, str(runtime), first],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                try:
                    self.assertEqual(process.stdout.readline().strip(), "ready")
                    result = subprocess.run(
                        [sys.executable, "-B", "-c", probe, str(runtime), second],
                        capture_output=True,
                        text=True,
                        timeout=10,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertTrue(json.loads(result.stdout)["excluded"])
                finally:
                    process.communicate("stop\n", timeout=10)
                after = subprocess.run(
                    [sys.executable, "-B", "-c", probe, str(runtime), second],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(after.returncode, 0, after.stderr)
                self.assertFalse(json.loads(after.stdout)["excluded"])

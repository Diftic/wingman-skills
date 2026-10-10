"""Selected 3.1.2 contract; no real Wingman import or launch."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.reader import bundled_bytes
from sc_log_reader.updates import UpdateError, UpdateManager

URL = "https://raw.githubusercontent.com/example/reader/main/instructions.json"
BASE = json.loads(bundled_bytes())["revision"]


class Boundary:
    def __init__(self, pid=10, pids=(10, 20)):
        self.pid, self.pids = pid, pids

    def identity(self):
        return (self.pid, 123) if self.pid else None

    def snapshot(self):
        return list(self.pids) if self.pids is not None else None


class Lease:
    def __init__(self):
        self.decision = None

    def pin(self, choose):
        if self.decision is None:
            self.decision = choose()
        return self.decision


class StartupBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "instructions"
        self.boundary = Boundary()

    def test_partial_constructor_failure_closes_database(self):
        import sqlite3

        from sc_log_reader.service import Service

        connections = []
        connect = sqlite3.connect

        def capture(*args, **kwargs):
            result = connect(*args, **kwargs)
            connections.append(result)
            return result

        with (
            patch("sc_log_reader.service.sqlite3.connect", side_effect=capture),
            patch(
                "sc_log_reader.service.support.initialize",
                side_effect=RuntimeError("injected"),
            ),
            self.assertRaises(RuntimeError),
        ):
            Service(self.root.parent)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")

    def manager(self):
        data = json.loads(bundled_bytes())
        data.update(revision=BASE + 1, version="0.1.999", release_notes="Reviewed")
        return UpdateManager(
            self.root,
            URL,
            fetch=lambda _: json.dumps(data).encode(),
            boundary_provider=self.boundary,
        )

    def approved(self):
        manager = self.manager()
        info = manager.check()
        manager.approve(info["sha256"])
        return info

    def host(self, lease=None):
        return self.manager().host_startup(lease or Lease())

    def test_existing_unregistered_process_and_recreated_manager_cannot_activate(self):
        self.approved()
        for pid in (10, 20, 10):
            self.boundary.pid = pid
            self.assertEqual(self.host().revision, BASE)
        self.assertTrue(self.manager().status()["staged_sha256"])

    def test_new_process_promotes_but_old_process_cannot_load_promoted_active(self):
        self.approved()
        self.boundary.pid = 30
        self.assertEqual(self.host().revision, BASE + 1)
        self.boundary.pid = 10
        with self.assertRaisesRegex(UpdateError, "restart"):
            self.host()

    def test_first_decision_is_pinned_even_without_stage(self):
        self.boundary.pid = 30
        lease = Lease()
        self.assertEqual(self.host(lease).revision, BASE)
        self.approved()
        self.assertEqual(self.host(lease).revision, BASE)
        self.assertEqual(self.host().revision, BASE + 1)

    def test_failed_snapshot_requires_additional_restart(self):
        self.boundary.pids = None
        self.approved()
        self.boundary.pid = 30
        self.assertEqual(self.host().revision, BASE)
        self.boundary.pids = (10, 20, 30)
        self.assertEqual(self.host().revision, BASE)
        self.boundary.pid = 40
        self.assertEqual(self.host().revision, BASE + 1)

    def test_identity_failure_defers_and_malformed_boundary_never_activates(self):
        self.approved()
        self.boundary.pid = None
        self.assertEqual(self.host().revision, BASE)
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["staged_boundary"] = {
            "kind": "windows_pid_exclusion",
            "version": 1,
            "pids": [],
        }
        path.write_text(json.dumps(manifest))
        self.boundary.pid = 30
        with self.assertRaisesRegex(UpdateError, "boundary"):
            self.host()

    def test_cancel_and_skip_clear_stage_boundary(self):
        info = self.approved()
        self.manager().cancel()
        self.assertIsNone(
            json.loads((self.root / "manifest.json").read_text()).get("staged_boundary")
        )
        self.manager().approve(info["sha256"])
        self.manager().skip(info["sha256"])
        self.assertIsNone(
            json.loads((self.root / "manifest.json").read_text()).get("staged_boundary")
        )

    def test_rollback_has_same_fence_and_manifest_limit(self):
        self.approved()
        self.boundary.pid = 30
        self.host()
        self.boundary.pids = (30,)
        self.manager().rollback()
        self.assertEqual(self.host().revision, BASE + 1)
        self.boundary.pid = 40
        self.assertEqual(self.host().revision, BASE)
        self.assertLessEqual((self.root / "manifest.json").stat().st_size, 65536)

    def test_legacy_stage_migrates_and_overflow_never_becomes_empty_fence(self):
        self.approved()
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest.pop("staged_boundary")
        path.write_text(json.dumps(manifest))
        self.boundary.pid = 30
        self.boundary.pids = (10, 20, 30)
        self.assertEqual(self.host().revision, BASE)
        self.assertIn(30, json.loads(path.read_text())["staged_boundary"]["pids"])
        self.manager().cancel()
        self.boundary.pids = tuple(range(2049))
        self.approved()
        self.assertEqual(
            json.loads(path.read_text())["staged_boundary"]["kind"], "unresolved"
        )

    def test_boundary_schema_rejects_boolean_version_duplicate_and_boolean_pid(self):
        from sc_log_reader.host_boundary import validate_boundary

        for version, pids in (
            (True, [10]),
            (1, [10, 10]),
            (1, [True]),
            (1, [-1]),
            (2, [10]),
        ):
            with (
                self.subTest(version=version, pids=pids),
                self.assertRaises(ValueError),
            ):
                validate_boundary(
                    {"version": version, "kind": "windows_pid_exclusion", "pids": pids}
                )

    def test_clock_rollback_and_stale_host_record_have_no_authority(self):
        self.approved()
        (self.root.parent / "host-session.json").write_text(
            '{"pid":999,"startup":9999999999}'
        )
        with patch("time.time", return_value=-100000):
            self.assertEqual(self.host().revision, BASE)
            self.boundary.pid = 30
            self.assertEqual(self.host().revision, BASE + 1)

    def test_standalone_promotion_preserves_host_exclusion_fence(self):
        self.approved()
        self.assertEqual(self.manager().startup().revision, BASE + 1)
        with self.assertRaisesRegex(UpdateError, "restart"):
            self.host()

    def test_unresolved_active_fence_recovers_persistently_but_refuses_recapturing_host(
        self,
    ):
        self.boundary.pids = None
        self.approved()
        self.assertEqual(self.manager().startup().revision, BASE + 1)
        path = self.root / "manifest.json"
        self.boundary.pid = 30
        # A still-unavailable census must never turn into an empty exclusion.
        with self.assertRaises(UpdateError):
            self.host()
        self.assertEqual(
            json.loads(path.read_text())["active_boundary"]["kind"], "unresolved"
        )
        self.boundary.pids = (10, 20, 30)
        with self.assertRaisesRegex(UpdateError, "restart"):
            self.host()
        persisted = json.loads(path.read_text())
        self.assertEqual(
            persisted["active_boundary"],
            {"version": 1, "kind": "windows_pid_exclusion", "pids": [10, 20, 30]},
        )
        # Refusal must persist the fence, not merely change this manager's copy.
        with self.assertRaisesRegex(UpdateError, "restart"):
            self.host()
        self.boundary.pid = 40
        self.boundary.pids = (10, 20, 30, 40)
        self.assertEqual(self.host().revision, BASE + 1)
        self.assertEqual(
            json.loads(path.read_text())["active_boundary"],
            persisted["active_boundary"],
        )

    def test_largest_fences_and_revision_history_fit_manifest(self):
        self.boundary.pids = tuple(range(0xFFFFFFFF - 2047, 0xFFFFFFFF + 1))
        self.approved()
        self.host()
        self.manager().rollback()
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["revisions"] = {str(i): "a" * 64 for i in range(128)}
        self.manager()._save(manifest)
        self.assertLessEqual(path.stat().st_size, 65536)


@unittest.skipUnless(os.name == "nt", "Windows target")
class WindowsBoundaryTests(unittest.TestCase):
    def test_real_identity_snapshot_and_process_lifetime_lease(self):
        from sc_log_reader.host_boundary import WindowsBoundary

        identity = WindowsBoundary().identity()
        self.assertEqual(identity[0], os.getpid())
        self.assertGreater(identity[1], 0)
        self.assertIn(os.getpid(), WindowsBoundary().snapshot())
        with tempfile.TemporaryDirectory() as tmp:
            program = """
import sys
from sc_log_reader.host_boundary import claim_runtime, assert_standalone_available
p = sys.argv[1]
owner = claim_runtime(p)
try:
    claim_runtime(p)
except RuntimeError:
    pass
else:
    raise AssertionError('duplicate owner')
owner.release()
owner = claim_runtime(p)
import importlib.util
import sc_log_reader.host_boundary as boundary
spec = importlib.util.spec_from_file_location('recreated_boundary', boundary.__file__)
recreated = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recreated)
try:
    recreated.claim_runtime(p)
except RuntimeError:
    pass
else:
    raise AssertionError('module recreation bypass')
import subprocess
child = subprocess.run([sys.executable, '-B', '-c', 'import sys; from sc_log_reader.host_boundary import claim_runtime; claim_runtime(sys.argv[1])', p], capture_output=True, timeout=5)
assert child.returncode != 0, 'competing process bypass'
try:
    assert_standalone_available(p)
except RuntimeError:
    pass
else:
    raise AssertionError('standalone bypass')
owner.release()
print('lease retained')
"""
            result = subprocess.run(
                [sys.executable, "-B", "-c", program, tmp],
                capture_output=True,
                text=True,
                timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("lease retained", result.stdout)

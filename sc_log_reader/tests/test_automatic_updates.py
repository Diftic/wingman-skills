"""Automatic staging and user recovery use isolated instruction stores."""

import json
import tempfile
import unittest
from pathlib import Path

from sc_log_reader.reader import bundled_bytes
from sc_log_reader.updates import UpdateError, UpdateManager
from test_target_host_contract import Boundary, Lease

URL = "https://raw.githubusercontent.com/example/reader/main/instructions.json"
BASE = json.loads(bundled_bytes())["revision"]


def release(offset):
    data = json.loads(bundled_bytes())
    data.update(revision=BASE + offset, version=f"9.0.{offset}")
    return json.dumps(data).encode()


class AutomaticUpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "instructions"
        self.boundary = Boundary()

    def manager(self, offset=1, fetch=None):
        return UpdateManager(
            self.root, URL, fetch=fetch or (lambda _: release(offset)),
            boundary_provider=self.boundary,
        )

    def activate(self, offset=1):
        manager = self.manager(offset)
        result = manager.check(automatic=True)
        self.assertEqual(result["status"], "staged_for_next_startup")
        return self.manager(offset).startup()

    def test_download_stages_without_changing_running_or_existing_host_process(self):
        manager = self.manager()
        running = manager.host_startup(Lease())
        result = manager.check(automatic=True)
        self.assertEqual(result["status"], "staged_for_next_startup")
        self.assertEqual(running.revision, BASE)
        self.assertEqual(self.manager().host_startup(Lease()).revision, BASE)
        manifest = json.loads((self.root / "manifest.json").read_bytes())
        manager.check(automatic=True)
        self.assertEqual(json.loads((self.root / "manifest.json").read_bytes())["staged_boundary"], manifest["staged_boundary"])
        self.boundary.pid = 30
        self.assertEqual(self.manager().host_startup(Lease()).revision, BASE + 1)

    def test_revert_is_offline_blocks_rejected_revision_and_accepts_later_release(self):
        self.activate()
        manager = self.manager(fetch=lambda _: self.fail("Recovery must be offline"))
        restored = manager.recover("restore_previous")
        self.assertEqual(restored["status"], "rollback_staged_for_next_startup")
        self.assertEqual(manager.check(automatic=True)["status"], "rollback_pending")
        self.assertEqual(self.manager().startup().revision, BASE)
        self.assertEqual(self.manager().check(automatic=True)["status"], "rejected")
        self.assertEqual(self.manager(2).check(automatic=True)["status"], "staged_for_next_startup")
        self.assertEqual(self.manager(2).startup().revision, BASE + 2)

    def test_saved_dropdown_is_consumed_once_and_rearms_when_reset(self):
        self.activate()
        self.manager().recover("restore_previous")
        self.manager().startup()
        self.assertEqual(self.manager().recover("restore_previous")["status"], "unchanged")
        self.activate(2)
        self.assertEqual(self.manager().recover("restore_previous")["status"], "unchanged")
        self.manager().recover("automatic")
        self.manager().recover("restore_previous")
        self.assertEqual(self.manager().startup().revision, BASE)

    def test_second_revert_does_not_reinstall_rejected_version(self):
        self.activate()
        self.manager().rollback()
        self.manager().startup()
        self.manager().rollback()
        self.assertEqual(self.manager().startup().revision, BASE)

    def test_revert_also_cancels_and_blocks_pending_update(self):
        self.activate()
        self.manager(2).check(automatic=True)
        self.manager().recover("restore_previous")
        self.assertEqual(self.manager(2).check(automatic=True)["status"], "rollback_pending")
        self.assertEqual(self.manager().startup().revision, BASE)
        self.assertEqual(self.manager(2).check(automatic=True)["status"], "rejected")

    def test_inflight_download_cannot_overwrite_recovery(self):
        self.activate()

        def fetch(_):
            self.manager().recover("restore_previous")
            return release(2)

        self.assertEqual(self.manager(2, fetch).check(automatic=True)["status"], "rollback_pending")
        self.assertEqual(self.manager().startup().revision, BASE)

    def test_bad_stage_falls_back_and_is_not_retried_automatically(self):
        manager = self.manager()
        result = manager.check(automatic=True)
        (self.root / "objects" / (result["sha256"] + ".json")).write_bytes(b"broken")
        self.assertEqual(self.manager().startup().revision, BASE)
        self.assertEqual(self.manager().check(automatic=True)["status"], "rejected")

    def test_invalid_or_incompatible_download_never_stages(self):
        with self.assertRaises(UpdateError):
            self.manager(fetch=lambda _: b"{}").check(automatic=True)
        data = json.loads(release(1))
        data["minimum_reader_version"] = "999.0.0"
        manager = self.manager(fetch=lambda _: json.dumps(data).encode())
        self.assertEqual(manager.check(automatic=True)["status"], "reader_upgrade_required")
        self.assertIsNone(manager.status()["staged_sha256"])

    def test_legacy_skip_is_respected_by_automatic_checker(self):
        manager = self.manager()
        result = manager.check()
        manager.skip(result["sha256"])
        self.assertEqual(manager.check(automatic=True)["status"], "skipped")
        self.assertIsNone(manager.status()["staged_sha256"])

    def test_same_revision_cannot_be_replaced_to_evade_rejection(self):
        self.activate()
        self.manager().rollback()
        self.manager().startup()
        data = json.loads(release(1))
        data["release_notes"] = "Different content"
        with self.assertRaisesRegex(UpdateError, "without a new revision"):
            self.manager(fetch=lambda _: json.dumps(data).encode()).check(automatic=True)

    def test_unknown_recovery_choice_does_not_change_store(self):
        manager = self.manager()
        before = (self.root / "manifest.json").read_bytes()
        with self.assertRaises(UpdateError):
            manager.recover("unknown")
        self.assertEqual((self.root / "manifest.json").read_bytes(), before)

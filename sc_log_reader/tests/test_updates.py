import json
import tempfile
import unittest
from pathlib import Path

from sc_log_reader.reader import InstructionError, bundled_bytes
from sc_log_reader.updates import UpdateError, UpdateManager

BASE_REVISION = json.loads(bundled_bytes())["revision"]

URL = "https://raw.githubusercontent.com/example/sc-reader/main/instructions.json"


def revision(n):
    d = json.loads(bundled_bytes())
    d["revision"] = n
    d["version"] = f"0.1.{n}"
    d["release_notes"] = "Test update"
    return json.dumps(d).encode()


class UpdatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def manager(self, raw=None):
        def fetch(url):
            self.assertEqual(url, URL)
            return raw or revision(BASE_REVISION + 1)

        return UpdateManager(self.root, URL, fetch=fetch)

    def test_check_and_approval_do_not_change_running_instructions(self):
        m = self.manager()
        current = m.startup()
        info = m.check()
        self.assertEqual(info["status"], "available")
        self.assertEqual(current.revision, BASE_REVISION)
        m.approve(info["sha256"])
        self.assertEqual(m.startup().revision, BASE_REVISION)
        self.assertEqual(self.manager().startup().revision, BASE_REVISION + 1)

    def test_unapproved_candidate_does_not_activate_on_restart(self):
        self.manager().check()
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)

    def test_digest_is_bound_to_reviewed_candidate(self):
        first = self.manager().check()
        self.manager(revision(BASE_REVISION + 2)).check()
        with self.assertRaises(UpdateError):
            self.manager().approve(first["sha256"])
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)

    def test_tampered_staged_file_falls_back(self):
        m = self.manager()
        info = m.check()
        m.approve(info["sha256"])
        (self.root / "objects" / f"{info['sha256']}.json").write_bytes(b"{}")
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)
        self.assertIn("error", self.manager().status())

    def test_invalid_update_never_displaces_active(self):
        m = self.manager(b'{"run":"python"}')
        with self.assertRaises((InstructionError, UpdateError)):
            m.check()
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)

    def test_rollback_is_staged_until_restart(self):
        m = self.manager()
        info = m.check()
        m.approve(info["sha256"])
        running = self.manager()
        self.assertEqual(running.startup().revision, BASE_REVISION + 1)
        running.rollback()
        self.assertEqual(running.startup().revision, BASE_REVISION + 1)
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)

    def test_offline_failure_preserves_active(self):
        def fail(url):
            raise OSError("offline")

        m = UpdateManager(self.root, URL, fetch=fail)
        self.assertEqual(m.startup().revision, BASE_REVISION)
        with self.assertRaises(UpdateError):
            m.check()
        self.assertEqual(self.manager().startup().revision, BASE_REVISION)

    def test_corrupt_manifest_recovers_bundled_definitions(self):
        (self.root / "manifest.json").write_text("broken")
        m = self.manager()
        self.assertEqual(m.startup().revision, BASE_REVISION)
        self.assertIn("error", m.status())

    def test_absent_source_and_non_https_rejected(self):
        m = UpdateManager(self.root)
        self.assertEqual(m.check()["status"], "not_configured")
        for url in (
            "http://raw.githubusercontent.com/a/b/main/a.json",
            "https://evil.example/a.json",
            "file:///test.json",
            "https://raw.githubusercontent.com/a/b/main/a.json?token=secret",
        ):
            with self.assertRaises(UpdateError):
                UpdateManager(self.root, url)

    def test_older_revision_is_not_an_update(self):
        m = self.manager()
        info = m.check()
        m.approve(info["sha256"])
        self.manager().startup()
        info = self.manager(bundled_bytes()).check()
        self.assertEqual(info["status"], "up_to_date")

    def test_changed_content_cannot_reuse_revision(self):
        m = self.manager()
        m.check()
        raw = json.loads(revision(BASE_REVISION + 1))
        raw["release_notes"] = "Changed same revision"
        with self.assertRaises(UpdateError):
            self.manager(json.dumps(raw).encode()).check()


if __name__ == "__main__":
    unittest.main()

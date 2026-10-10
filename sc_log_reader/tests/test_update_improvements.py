import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.reader import bundled_bytes
from sc_log_reader.updates import UpdateError, UpdateManager

URL = "https://raw.githubusercontent.com/example/reader/main/instructions.json"
OTHER_URL = "https://raw.githubusercontent.com/other/reader/main/instructions.json"
BASE = json.loads(bundled_bytes())


def revision(offset):
    value = json.loads(bundled_bytes())
    value.update(
        revision=BASE["revision"] + offset,
        version=f"9.0.{offset}",
        release_notes=f"Release {offset}",
    )
    return json.dumps(value).encode()


class UpdateImprovementsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.runtime = Path(self.tmp.name)
        self.root = self.runtime / "instructions"

    def manager(self, offset=1, url=URL):
        return UpdateManager(self.root, url, fetch=lambda _: revision(offset))

    def test_scheduled_candidate_retained_and_cancelled_without_changing_active(self):
        manager = self.manager()
        manager.startup()
        first = manager.check()
        manager.approve(first["sha256"])
        self.manager(2).check()
        status = manager.status()
        self.assertEqual(status.get("staged_version"), "9.0.1")
        self.assertEqual(status["candidate_version"], "9.0.2")
        self.assertEqual(status.get("rollback_version"), BASE["version"])
        self.assertEqual(status.get("candidate_source_url"), URL)
        self.assertEqual(status.get("staged_source_url"), URL)
        manager.cancel()
        self.assertIsNone(manager.status()["staged_sha256"])
        self.assertEqual(self.manager().startup().version, BASE["version"])
        self.assertEqual(manager.status()["candidate_version"], "9.0.2")

    def test_changed_publisher_invalidates_pending_approval_and_records_notice(self):
        manager = self.manager()
        first = manager.check()
        manager.approve(first["sha256"])
        changed = self.manager(url=OTHER_URL)
        self.assertIsNone(changed.status()["staged_sha256"])
        self.assertNotIn("sha256", changed.status())
        self.assertIn("publisher", changed.status().get("notice", "").lower())
        self.assertEqual(changed.startup().version, BASE["version"])
        with self.assertRaises(UpdateError):
            changed.approve(first["sha256"])
        changed.check()
        self.assertEqual(changed.status()["candidate_source_url"], OTHER_URL)
        self.assertIsNone(changed.status()["staged_sha256"])

    def test_old_manager_status_cannot_reselect_publisher_or_cancel_new_approval(self):
        old = self.manager()
        old.check()
        new = self.manager(2, OTHER_URL)
        latest = new.check()
        new.approve(latest["sha256"])
        observed = old.status()
        self.assertEqual(observed.get("source_url"), OTHER_URL)
        self.assertEqual(observed["staged_sha256"], latest["sha256"])
        with self.assertRaises(UpdateError):
            old.approve(latest["sha256"])
        self.assertEqual(new.status()["staged_sha256"], latest["sha256"])

    def test_inflight_download_cannot_replace_new_publishers_approved_candidate(self):
        selected = {}

        def fetch_old(_):
            new = self.manager(2, OTHER_URL)
            latest = new.check()
            new.approve(latest["sha256"])
            selected.update(latest)
            return revision(3)

        old = UpdateManager(self.root, URL, fetch=fetch_old)
        with self.assertRaises(UpdateError):
            old.check()
        observed = UpdateManager(self.root).status()
        self.assertEqual(observed["source_url"], OTHER_URL)
        self.assertEqual(observed["sha256"], selected["sha256"])
        self.assertEqual(observed["staged_sha256"], selected["sha256"])
        self.assertEqual(UpdateManager(self.root).startup().version, "9.0.2")

    def test_old_source_generation_rejected_after_publisher_changes_back(self):
        old = self.manager(3)
        self.manager(2, OTHER_URL).check()
        selected = self.manager(2, URL)
        latest = selected.check()
        selected.approve(latest["sha256"])
        with self.assertRaises(UpdateError):
            old.check()
        with self.assertRaises(UpdateError):
            old.approve(latest["sha256"])
        self.assertEqual(selected.status()["staged_sha256"], latest["sha256"])

    def test_offline_review_generation_binds_approval_even_when_url_and_digest_match(
        self,
    ):
        first = self.manager().check()
        offline = UpdateManager(self.root)
        shown = offline.status()
        self.manager(url=OTHER_URL).check()
        self.manager().check()
        with self.assertRaises(UpdateError):
            offline.approve(
                first["sha256"],
                source_url=URL,
                source_generation=shown.get("source_generation"),
            )
        self.assertIsNone(offline.status()["staged_sha256"])

    def test_window_rejects_changed_rollback_target_then_requires_another_click(self):
        import tkinter as tk

        from sc_log_reader.review_ui import show_review

        self.manager().startup()
        window = tk.Tk()
        window.withdraw()
        errors = []
        dialogs = []

        def exercise():
            try:
                frame = window.winfo_children()[0]
                buttons = frame.winfo_children()[-1].winfo_children()
                rollback = next(b for b in buttons if b.cget("text") == "Roll back")
                for offset in (1, 2):
                    manager = self.manager(offset)
                    info = manager.check()
                    manager.approve(info["sha256"])
                    UpdateManager(self.root).startup()
                rollback.invoke()
                observed = UpdateManager(self.root).status()
                self.assertIsNone(observed["staged_sha256"])
                self.assertEqual(observed["active_version"], "9.0.2")
                self.assertTrue(dialogs)
                rollback.invoke()
                self.assertEqual(
                    UpdateManager(self.root).status()["staged_version"], "9.0.1"
                )
                self.assertEqual(UpdateManager(self.root).startup().version, "9.0.1")
            except Exception as exc:
                errors.append(exc)
            finally:
                window.destroy()

        window.after(20, exercise)
        with (
            patch("tkinter.Tk", return_value=window),
            patch("tkinter.messagebox.showinfo"),
            patch(
                "tkinter.messagebox.showerror",
                side_effect=lambda *a, **kw: dialogs.append(a),
            ),
        ):
            show_review(self.runtime)
        self.assertFalse(errors, errors)

    def test_legacy_pending_state_has_no_trusted_provenance_and_never_activates(self):
        manager = self.manager()
        info = manager.check()
        manager.approve(info["sha256"])
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        for key in list(manifest):
            if key not in {
                "active",
                "previous",
                "candidate",
                "staged",
                "highest_revision",
                "revisions",
            }:
                del manifest[key]
        path.write_text(json.dumps(manifest))
        offline = UpdateManager(self.root)
        self.assertEqual(offline.startup().version, BASE["version"])
        self.assertNotIn("sha256", offline.status())
        self.assertIn("provenance", offline.status().get("notice", "").lower())

    def test_offline_review_uses_recorded_source_and_can_approve(self):
        info = self.manager().check()
        offline = UpdateManager(self.root)
        self.assertEqual(offline.status().get("candidate_source_url"), URL)
        offline.approve(info["sha256"])
        self.assertEqual(UpdateManager(self.root).startup().version, "9.0.1")

    def test_legacy_active_and_rollback_survive_migration(self):
        manager = self.manager()
        info = manager.check()
        manager.approve(info["sha256"])
        self.manager().startup()
        path = self.root / "manifest.json"
        manifest = json.loads(path.read_text())
        for key in list(manifest):
            if key not in {
                "active",
                "previous",
                "candidate",
                "staged",
                "highest_revision",
                "revisions",
            }:
                del manifest[key]
        path.write_text(json.dumps(manifest))
        offline = UpdateManager(self.root)
        self.assertEqual(offline.startup().version, "9.0.1")
        self.assertEqual(offline.status().get("rollback_version"), BASE["version"])
        offline.rollback()
        self.assertEqual(UpdateManager(self.root).startup().version, BASE["version"])

    def test_window_refreshes_stale_digest_and_requires_a_second_click(self):
        import tkinter as tk

        from sc_log_reader.review_ui import show_review

        manager = self.manager()
        first = manager.check()
        manager.approve(first["sha256"])
        window = tk.Tk()
        window.withdraw()
        errors = []
        dialogs = []

        def exercise():
            try:
                frame = window.winfo_children()[0]
                buttons = frame.winfo_children()[-1].winfo_children()

                # ScrolledText wraps itself in a frame; find its Text widget robustly.
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)

                text_widget = next(
                    w for w in descendants(frame) if w.winfo_class() == "Text"
                )
                update = next(
                    b for b in buttons if b.cget("text") == "Update next startup"
                )
                self.manager(2).check()
                update.invoke()
                shown = text_widget.get("1.0", "end")
                self.assertIn("Available version: 9.0.2", shown)
                self.assertIn("Scheduled version: 9.0.1", shown)
                self.assertIn("Rollback target: " + BASE["version"], shown)
                self.assertIn(URL, shown)
                self.assertIn(str(self.runtime.resolve()), shown)
                self.assertEqual(manager.status()["staged_sha256"], first["sha256"])
                self.assertTrue(dialogs)
                update.invoke()
                self.assertEqual(manager.status()["staged_version"], "9.0.2")
                next(
                    b for b in buttons if b.cget("text") == "Cancel scheduled update"
                ).invoke()
                self.assertIsNone(manager.status()["staged_sha256"])
                self.assertEqual(manager.status()["active_version"], BASE["version"])
            except Exception as exc:
                errors.append(exc)
            finally:
                window.destroy()

        window.after(20, exercise)
        with (
            patch("tkinter.Tk", return_value=window),
            patch("tkinter.messagebox.showinfo"),
            patch(
                "tkinter.messagebox.showerror",
                side_effect=lambda *a, **kw: dialogs.append(a),
            ),
        ):
            show_review(self.runtime)
        self.assertFalse(errors, errors)


if __name__ == "__main__":
    unittest.main()

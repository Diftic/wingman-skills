import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.review_ui import review_lines
from sc_log_reader.updates import UpdateError, UpdateManager


class TargetReviewTests(unittest.TestCase):
    def test_display_prints_digest_source_notes_compatibility_and_exact_runtime(self):
        status = {
            "runtime_directory": "C:/runtime",
            "sha256": "a" * 64,
            "candidate_version": "1",
            "candidate_source_url": "publisher",
            "minimum_reader_version": "2",
            "verified_game_builds": [],
            "release_notes": "notes",
            "staged_boundary": {"kind": "unresolved"},
        }
        text = "\n".join(review_lines(status, host_mode=True))
        for expected in (
            "a" * 64,
            "C:/runtime",
            "publisher",
            "notes",
            "Requires reader: 2",
            "additional",
            "Wingman process",
        ):
            self.assertIn(expected, text)

    def test_launcher_exact_runtime_no_publisher_and_frozen_refusal(self):
        from sc_log_reader.review_launcher import invalidate_launcher, write_launcher

        with tempfile.TemporaryDirectory() as tmp:
            command = write_launcher(tmp)
            script = Path(command[1])
            self.assertIn(
                str(Path(tmp).resolve()), script.read_text().replace("\\\\", "\\")
            )
            self.assertNotIn("raw.githubusercontent", script.read_text())
            self.assertIn("host_mode=True", script.read_text())
            invalidate_launcher(tmp)
            self.assertIn("configuration changed", script.read_text())
            with (
                patch("sys.frozen", True, create=True),
                self.assertRaisesRegex(RuntimeError, "frozen"),
            ):
                write_launcher(tmp)

    def test_changed_source_blocks_all_review_actions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = UpdateManager(
                root,
                "https://raw.githubusercontent.com/one/repo/main/instructions.json",
            )
            generation = manager.status()["source_generation"]
            review = UpdateManager(root)
            UpdateManager(
                root,
                "https://raw.githubusercontent.com/two/repo/main/instructions.json",
            )
            for action in (
                lambda: review.cancel(source_generation=generation),
                lambda: review.rollback(source_generation=generation),
                lambda: review.skip("a" * 64, source_generation=generation),
            ):
                with self.assertRaisesRegex(UpdateError, "Publisher"):
                    action()

"""Real Git regression checks for accidental contribution disclosure."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import os
import shutil
import stat
import uuid
import unittest

CHECK = Path(__file__).with_name("check_contribution.py")


class ContributionChecks(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).with_name(".checks").resolve()
        test_root.mkdir(exist_ok=True)
        self.root = test_root / uuid.uuid4().hex
        self.root.mkdir()
        def cleanup():
            assert self.root.resolve().parent == test_root
            def writable_retry(function, path, error):
                os.chmod(path, stat.S_IWRITE)
                function(path)
            shutil.rmtree(self.root, onexc=writable_retry)
        self.addCleanup(cleanup)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Local test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")
        (self.repo / "README.md").write_text("Upstream\n")
        self.git("add", "README.md")
        self.git("commit", "-qm", "Upstream")
        base = self.git("rev-parse", "HEAD")
        self.git("switch", "-qc", "contrib/example")
        self.relative = "skills/example/main.py"
        target = self.repo / self.relative
        target.parent.mkdir(parents=True)
        target.write_bytes(b"VALUE = 1\n")
        self.git("add", self.relative)
        self.policy = self.root / "policy.json"
        self.data = {
            "checkout": str(self.repo), "base": base,
            "branch": "contrib/example",
            "fork_url": "https://github.com/Diftic/wingman-ai.git",
            "files": {self.relative: {
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                "blob": self.git("rev-parse", ":" + self.relative),
            }},
        }
        self.policy.write_text(json.dumps(self.data))

    def git(self, *args):
        return subprocess.check_output(
            ["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE,
            text=True,
        ).strip()

    def check(self, *args, stdin=None):
        return subprocess.run(
            [sys.executable, str(CHECK), str(self.policy), *args],
            input=stdin, capture_output=True, text=True,
        )

    def test_approved_staged_files_pass(self):
        result = self.check()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_staged_planning_file_is_rejected(self):
        (self.repo / "plan.md").write_text("private planning")
        self.git("add", "plan.md")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unapproved path: plan.md", result.stderr)

    def test_changed_content_under_approved_name_is_rejected(self):
        (self.repo / self.relative).write_text("PRIVATE = 'notes'\n")
        self.git("add", self.relative)
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unreviewed content", result.stderr)

    def test_private_file_added_then_deleted_in_history_is_rejected(self):
        self.git("commit", "-qm", "Skill")
        (self.repo / "plan.md").write_text("private planning")
        self.git("add", "plan.md")
        self.git("commit", "-qm", "Notes")
        self.git("rm", "plan.md")
        self.git("commit", "-qm", "Remove notes")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unapproved path: plan.md", result.stderr)

    def test_missing_required_runtime_file_is_rejected(self):
        self.git("rm", "-f", self.relative)
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing approved file", result.stderr)

    def test_untracked_file_is_rejected_before_it_can_be_added(self):
        (self.repo / "handover.md").write_text("private planning")
        result = self.check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unapproved local file", result.stderr)

    def test_direct_upstream_push_is_rejected(self):
        self.git("commit", "-qm", "Skill")
        sha = self.git("rev-parse", "HEAD")
        result = self.check(
            "--pre-push", "upstream", "https://github.com/ShipBit/wingman-ai.git",
            stdin=f"refs/heads/contrib/example {sha} refs/heads/contrib/example {'0'*40}\n",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Push destination", result.stderr)

    def test_approved_topic_push_passes_without_network(self):
        self.git("commit", "-qm", "Skill")
        sha = self.git("rev-parse", "HEAD")
        result = self.check(
            "--pre-push", "origin", self.data["fork_url"],
            stdin=f"refs/heads/contrib/example {sha} refs/heads/contrib/example {'0'*40}\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

import copy
import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "corpus_audit", Path(__file__).resolve().parents[1] / "tools/corpus_test.py"
)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class CorpusContractTests(unittest.TestCase):
    def test_restart_comparison_excludes_only_elapsed_source_age(self):
        before = {
            "player_name": "A",
            "observations": {"ship": {"timestamp": "one"}},
            "reader_health": {
                "source_age_seconds": 1,
                "instruction_version": "v1",
                "worker_errors": {},
            },
        }
        after = copy.deepcopy(before)
        after["reader_health"]["source_age_seconds"] = 2
        self.assertEqual(audit.stable_state(before), audit.stable_state(after))
        self.assertEqual(before["reader_health"]["source_age_seconds"], 1)
        after["observations"]["ship"]["timestamp"] = "two"
        self.assertNotEqual(audit.stable_state(before), audit.stable_state(after))
        after = copy.deepcopy(before)
        after["reader_health"]["worker_errors"] = {"monitor": "failed"}
        self.assertNotEqual(audit.stable_state(before), audit.stable_state(after))

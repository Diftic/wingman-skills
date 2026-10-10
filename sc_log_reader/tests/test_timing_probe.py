"""The replay probes must preserve values, iterator work and failure behavior."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from timing_probe import ENTRY, PATTERN, Pattern, TimingProbe

from sc_log_reader import reader as module


class TimingProbeTests(unittest.TestCase):
    def test_real_replay_values_and_row_accounting(self):
        instructions = module.Instructions.load(module.bundled_bytes())
        raw = (
            b"<2026-09-15T12:00:00Z> ordinary noise\n"
            b'<2026-09-15T12:00:01Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted: Delivery:" [13] to queue. MissionID: [m1]\n'
        )
        assembler = module.RecordAssembler(instructions)
        baseline = assembler.feed(raw) + assembler.finish()
        reader = module.Reader(instructions)
        expected = [reader.parse(r.text, complete=r.complete) for r in baseline]
        original = module.Reader.parse
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "timing"
            with TimingProbe(target) as probe:
                probe.set_file(7, "fixture.log")
                assembler = module.RecordAssembler(instructions)
                records = assembler.feed(raw) + assembler.finish()
                reader = module.Reader(instructions)
                actual = []
                for record in records:
                    probe.set_record(record.start, record.end)
                    actual.append(reader.parse(record.text, complete=record.complete))
            self.assertIs(module.Reader.parse, original)
            self.assertEqual(records, baseline)
            self.assertEqual(actual, expected)
            entries = list(ENTRY.iter_unpack((target / "entries.bin").read_bytes()))
            patterns = list(PATTERN.iter_unpack((target / "patterns.bin").read_bytes()))
            metadata = json.loads((target / "metadata.json").read_text())
            self.assertEqual(len(entries), len(records))
            self.assertEqual(len(patterns), metadata["pattern_count"])
            self.assertEqual({p[6] for p in patterns}, {1, 2})
            self.assertEqual({e[4] for e in entries}, {7})
            self.assertEqual([e[5] for e in entries], [0, 1])
            self.assertTrue(any(p[7] == 3 for p in patterns))

    def test_iterator_times_backend_consumption_excludes_consumer(self):
        class Backend:
            def finditer(self, *a, **kw):
                return iter(["first", "second"])

        with (
            tempfile.TemporaryDirectory() as directory,
            TimingProbe(Path(directory) / "timing") as probe,
        ):
            probe.phase = 1
            compiled = Pattern(Backend(), probe, 1)
            # Construction + three next calls, including exhaustion.
            with patch(
                "timing_probe.perf_counter_ns",
                side_effect=[0, 2, 10, 13, 100, 105, 1000, 1007],
            ):
                self.assertEqual(list(compiled.finditer("")), ["first", "second"])
            row = next(PATTERN.iter_unpack(probe.pattern_buffer))
            self.assertEqual(row[0], 17)
            self.assertEqual(row[7:], (3, 0))

    def test_timeout_is_logged_and_propagates_and_hooks_restore(self):
        class Backend:
            def search(self, *a, **kw):
                raise TimeoutError("test backend timeout")

        original = module._pattern
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "timing"
            with self.assertRaises(TimeoutError), TimingProbe(target) as probe:
                probe.phase = 1
                Pattern(Backend(), probe, 1).search("x", timeout=0.015)
            self.assertIs(module._pattern, original)
            row = next(PATTERN.iter_unpack((target / "patterns.bin").read_bytes()))
            self.assertEqual(row[5], 15000000)
            self.assertEqual(row[8], 1)

    def test_disabled_probe_logs_nothing(self):
        instructions = module.Instructions.load(module.bundled_bytes())
        with (
            tempfile.TemporaryDirectory() as directory,
            TimingProbe(Path(directory) / "timing") as probe,
        ):
            probe.enabled = False
            reader = module.Reader(instructions)
            assembler = module.RecordAssembler(instructions)
            for r in assembler.feed(b"noise\n"):
                reader.parse(r.text)
            self.assertEqual(probe.pattern_count, 0)
            self.assertEqual(probe.entry_count, 0)

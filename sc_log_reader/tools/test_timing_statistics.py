"""Run with the analysis Python runtime, which includes NumPy."""

import tempfile
import unittest
from pathlib import Path

import numpy as np
from timing_statistics import ENTRY_DTYPE, PATTERN_DTYPE, read_rows, statistics


class StatisticsTests(unittest.TestCase):
    def test_exact_nearest_rank_and_thresholds(self):
        result = statistics(np.arange(1, 101, dtype=np.uint64) * 1000000)
        self.assertEqual(result["count"], 100)
        self.assertEqual(result["mean_ms"], 50.5)
        self.assertEqual(result["p50_ms"], 50)
        self.assertEqual(result["p99_ms"], 99)
        self.assertEqual(result["p99.9_ms"], 100)
        self.assertEqual(result["at_or_above_ms"]["15"], 86)
        self.assertAlmostEqual(result["std_ms"], np.std(np.arange(1, 101)))

    def test_empty_and_single_observation(self):
        self.assertEqual(statistics([]), {"count": 0})
        result = statistics(np.array([12345], dtype=np.uint64))
        self.assertEqual(result["std_ms"], 0)
        self.assertEqual(result["p99.99_ms"], 0.012345)

    def test_binary_schema_offsets(self):
        import struct

        row = struct.pack("<QQQIIIBBBx", 11, 22, 33, 44, 55, 66, 1, 2, 0)
        decoded = np.frombuffer(row, dtype=PATTERN_DTYPE)[0]
        self.assertEqual(decoded["duration_ns"], 11)
        self.assertEqual(decoded["pattern_id"], 55)
        self.assertEqual(decoded["budget_ns"], 66)
        self.assertEqual(decoded["operation"], 2)
        self.assertEqual(ENTRY_DTYPE.itemsize, 40)

    def test_truncated_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.bin"
            path.write_bytes(b"x")
            with self.assertRaises(ValueError):
                read_rows(path, ENTRY_DTYPE, 1)


if __name__ == "__main__":
    unittest.main()

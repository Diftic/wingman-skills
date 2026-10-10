import sqlite3
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sc_log_reader.reader import Record
from sc_log_reader.service import Service


class BatchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.records = [
            Record(f"User Login Success Handle[{name}]", i * 100, (i + 1) * 100)
            for i, name in enumerate("ABC")
        ]
        self.meta = {"generation": "g", "offset": 0, "tail_hash": "initial"}
        self.service.save_stream("LIVE", self.meta)
        self.checkpoints = [
            dict(self.meta, offset=r.end, tail_hash=str(r.end)) for r in self.records
        ]

    def test_deadline_commits_only_consumed_prefix_and_zero_advances_nothing(self):
        clock = types.SimpleNamespace(
            monotonic=Mock(side_effect=[0, 2]), time=time.time
        )
        with patch("sc_log_reader.service.time", clock):
            result = self.service.ingest_batch(
                self.records, "LIVE", "g", deadline=1, checkpoints=self.checkpoints
            )
        self.assertEqual(result.consumed, 1)
        self.assertEqual(len(result.events), 1)
        self.assertEqual(self.service.stream("LIVE"), self.checkpoints[0])
        self.assertEqual(self.service.state("LIVE")["player_name"], "A")
        counts = dict(self.service.health_counts)
        result = self.service.ingest_batch(
            self.records[1:], "LIVE", "g", deadline=0, checkpoints=self.checkpoints[1:]
        )
        self.assertEqual((result.consumed, result.events), (0, []))
        self.assertEqual(self.service.stream("LIVE"), self.checkpoints[0])
        self.assertEqual(self.service.health_counts, counts)

    def test_checkpoint_length_rejected_before_any_write(self):
        with self.assertRaises(ValueError):
            self.service.ingest_batch(self.records, "LIVE", "g", checkpoints=[])
        self.assertEqual(self.service.stream("LIVE"), self.meta)
        self.assertEqual(self.service.events("LIVE"), [])

    def test_large_request_returns_bounded_prefix_for_caller_to_resume(self):
        records = [
            Record(f"User Login Success Handle[P{i}]", i * 100, (i + 1) * 100)
            for i in range(129)
        ]
        first = self.service.ingest_batch(records, "LIVE", "g")
        self.assertEqual(first.consumed, 128)
        self.assertEqual(len(first.events), 128)
        second = self.service.ingest_batch(records[first.consumed :], "LIVE", "g")
        self.assertEqual(second.consumed, 1)
        self.assertEqual(self.service.state("LIVE")["player_name"], "P128")

    def test_failure_between_observation_and_snapshot_rolls_back_entire_batch(self):
        self.service.db.execute(
            "CREATE TEMP TRIGGER fail_snapshot BEFORE INSERT ON snapshots BEGIN SELECT RAISE(ABORT, 'injected'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.ingest_batch(
                self.records, "LIVE", "g", checkpoints=self.checkpoints
            )
        self.assertEqual(
            self.service.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            0,
        )
        self.assertEqual(self.service.events("LIVE"), [])
        self.assertEqual(self.service.stream("LIVE"), self.meta)
        self.assertEqual(self.service.health_counts, {})
        self.service.db.execute("DROP TRIGGER fail_snapshot")
        result = self.service.ingest_batch(
            self.records, "LIVE", "g", checkpoints=self.checkpoints
        )
        self.assertEqual((result.consumed, len(result.events)), (3, 3))
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        repeated = self.service.ingest_batch(
            self.records, "LIVE", "g", checkpoints=self.checkpoints
        )
        self.assertEqual(repeated.events, [])
        self.assertEqual(len(self.service.events("LIVE")), 3)
        self.assertEqual(self.service.stream("LIVE"), self.checkpoints[-1])

    def test_ordered_trade_and_session_boundaries_match_individual_ingest(self):
        other = Service(self.root / "individual")
        self.addCleanup(other.close)
        lines = [
            "<2026-09-15T12:00:00Z> User Login Success Handle[A]",
            "<2026-09-15T12:00:01Z> ShoppingProvider SendStandardItemBuyRequest playerId[p] client_price[265] quantity[1] currencyType[UEC] itemName[Medpen]",
            "<2026-09-15T12:00:02Z> ShoppingProvider RmShopFlowResponse playerId[p] result[Success]",
            "<2026-09-15T12:00:03Z> User Login Success Handle[B]",
            "<2026-09-15T12:00:04Z> ShoppingProvider RmShopFlowResponse playerId[p] result[Success]",
        ]
        records = [Record(text, i * 500, (i + 1) * 500) for i, text in enumerate(lines)]
        individual = [
            event for record in records for event in other.ingest(record, "LIVE", "g")
        ]
        batches = [
            event
            for group in (records[:2], records[2:3], records[3:])
            for event in self.service.ingest_batch(group, "LIVE", "g").events
        ]
        self.assertEqual(batches, individual)
        self.assertEqual(self.service.events("LIVE"), other.events("LIVE"))
        self.assertEqual(self.service.ledger("LIVE"), other.ledger("LIVE"))
        self.assertEqual(self.service.ledger("LIVE")["net_cash_flow_auec"], -265)
        self.assertEqual(self.service._snapshot("LIVE"), other._snapshot("LIVE"))

    def test_checkpoint_write_failure_rolls_back_completed_rows_outputs_and_counts(
        self,
    ):
        self.service.db.execute(
            "CREATE TEMP TRIGGER fail_checkpoint BEFORE INSERT ON streams BEGIN SELECT RAISE(ABORT, 'checkpoint failed'); END"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.service.ingest_batch(
                self.records, "LIVE", "g", checkpoints=self.checkpoints
            )
        self.assertEqual(self.service.events("LIVE"), [])
        self.assertIsNone(self.service._snapshot("LIVE"))
        self.assertEqual(self.service.stream("LIVE"), self.meta)
        self.assertEqual(self.service.health_counts, {})

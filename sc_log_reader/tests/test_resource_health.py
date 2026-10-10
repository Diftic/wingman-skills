"""Storage-pressure and privacy contracts for local operational support."""

import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sc_log_reader import support
from sc_log_reader.cli import main
from sc_log_reader.reader import Event, Instructions, Reader, Record, bundled_bytes
from sc_log_reader.service import Service, Tailer


class ResourceHealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)

    def diagnostic(self, n, environment="LIVE", checkpoints=None):
        self.service.reader.parse = lambda *a, **kw: Event(
            "diagnostic",
            {"private": "secret-player" * 1000},
            errors=["missing:" + "x" * 10000],
            rule_id=f"rule-{n}",
            instruction_version=f"version-{n}",
        )
        return self.service.ingest_batch(
            [Record("private" * 1000, n * 10, n * 10 + 10)],
            environment,
            "generation",
            checkpoints=checkpoints,
        )

    def test_diagnostic_storage_has_global_cardinality_and_byte_caps(self):
        for n in range(700):
            self.diagnostic(n, f"untrusted-{n}")
        db = self.service.db
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM observations").fetchone()[0], 0
        )
        health = self.service.health("LIVE")["support"]
        self.assertEqual(health["total_count"], 700)
        self.assertLessEqual(health["retained_slots"], 256)
        self.assertLessEqual(health["recent_occurrences"], 512)
        self.assertLessEqual(health["diagnostic_samples"], 50)
        self.assertGreater(health["evicted_bucket_count"], 0)
        for table in ("support_totals", "support_buckets", "support_samples"):
            for (payload,) in db.execute(f"SELECT payload FROM {table}"):
                self.assertLessEqual(len(payload.encode()), 4096)
        self.assertLessEqual(len(self.service.health_counts), 6)
        self.assertLessEqual(
            db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 6
        )

    def test_checkpoint_fences_old_replay_but_not_financial_occurrences(self):
        for n in range(520):
            self.diagnostic(
                n, checkpoints=[{"generation": "generation", "offset": (n + 1) * 10}]
            )
        self.diagnostic(0, checkpoints=[{"generation": "generation", "offset": 10}])
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 520)
        self.assertEqual(self.service.stream("LIVE")["offset"], 5200)
        self.diagnostic(0)  # Direct replay outside the bounded window can recount.
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 521)
        self.service.reader = Reader(self.service.instructions)
        text = '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.'
        for n in range(2):
            self.service.ingest(
                Record(text.replace("12:00:02", f"12:01:0{n}"), n, n + 1),
                "LIVE",
                "money",
            )
        self.service.ingest(Record(text, 0, 1), "LIVE", "money")
        self.assertEqual(len(self.service.events("LIVE")), 2)

    def test_json_framing_controls_unknown_sampling_and_parse_metadata_resets(self):
        data = json.loads(bundled_bytes())
        data["framing"]["notification"] = data["framing"]["notification"].replace(
            "Added notification", "Novel framing"
        )
        inst = Instructions.load(json.dumps(data).encode())
        service = Service(self.root / "other", instructions=inst)
        self.addCleanup(service.close)
        service.ingest(
            Record('Novel framing "Private novel message" [1] to queue.', 0, 100),
            "LIVE",
            "g",
        )
        self.assertEqual(len(service.health("LIVE")["unrecognized_samples"]), 1)
        service.reader.parse("ordinary engine text")
        self.assertEqual(service.reader.last_record_kind, "other")
        self.assertIsNone(service.reader.last_notification_complete)
        event = service.reader.parse("x" * (1024 * 1024))
        self.assertEqual(event.instruction_version, inst.version)
        self.assertEqual(service.reader.last_record_kind, "unknown")

    def test_support_write_failure_rolls_back_count_and_checkpoint_then_retries(self):
        self.service.save_stream("LIVE", {"generation": "generation", "offset": 0})
        self.service.db.execute(
            "CREATE TRIGGER fail_support BEFORE INSERT ON support_samples BEGIN SELECT RAISE(ABORT, 'disk full'); END"
        )
        with self.assertRaises(sqlite3.Error):
            self.diagnostic(1, checkpoints=[{"generation": "generation", "offset": 20}])
        self.assertEqual(self.service.stream("LIVE")["offset"], 0)
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 0)
        self.service.db.execute("DROP TRIGGER fail_support")
        self.diagnostic(1, checkpoints=[{"generation": "generation", "offset": 20}])
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 1)

    def test_readonly_export_omits_private_data_and_preserves_runtime(self):
        self.diagnostic(1)
        before = list(self.service.db.iterdump())
        dest = self.root / "support.json"
        with patch(
            "sc_log_reader.cli.Service",
            side_effect=AssertionError("must not instantiate"),
        ):
            self.assertEqual(
                main(
                    [
                        "support-export",
                        "--state-dir",
                        str(self.service.root),
                        "--output",
                        str(dest),
                    ]
                ),
                0,
            )
        self.assertEqual(list(self.service.db.iterdump()), before)
        raw = dest.read_text()
        for forbidden in (
            "private",
            "secret-player",
            "generation",
            "rule-1",
            "version-1",
            str(self.root),
        ):
            self.assertNotIn(forbidden, raw)
        self.assertTrue(json.loads(raw)["redacted"])
        original = dest.read_bytes()
        self.assertEqual(
            main(
                [
                    "support-export",
                    "--state-dir",
                    str(self.service.root),
                    "--output",
                    str(dest),
                ]
            ),
            2,
        )
        self.assertEqual(dest.read_bytes(), original)

    def test_export_rejects_log_runtime_missing_and_corrupt_before_writing(self):
        game = self.root / "Game.log"
        game.write_text("precious log")
        for dest in (
            game,
            self.service.root / "new.json",
            self.root / "missing" / "out.json",
        ):
            self.assertEqual(
                main(
                    [
                        "support-export",
                        "--state-dir",
                        str(self.service.root),
                        "--output",
                        str(dest),
                    ]
                ),
                2,
            )
        self.assertEqual(game.read_text(), "precious log")
        corrupt = self.root / "corrupt"
        corrupt.mkdir()
        (corrupt / "events.sqlite3").write_text("broken")
        dest = self.root / "corrupt-export.json"
        self.assertEqual(
            main(
                ["support-export", "--state-dir", str(corrupt), "--output", str(dest)]
            ),
            2,
        )
        self.assertFalse(dest.exists())

    def test_pressure_health_and_tailer_retry_are_visible(self):
        health = self.service.health("LIVE")
        self.assertIn("database_bytes", health["resources"])
        self.assertFalse(health["resources"]["history_pruning_enabled"])
        path = self.root / "Game.log"
        path.write_text("ordinary\n")
        tail = Tailer(self.service, {"LIVE": path})
        with patch.object(
            self.service, "save_stream", side_effect=OSError("disk full")
        ):
            tail.poll()
        self.assertTrue(self.service.health("LIVE")["storage_write_error"])
        self.assertTrue(self.service.health("LIVE")["retry_pending"])
        tail.poll()
        self.assertFalse(self.service.health("LIVE")["retry_pending"])

    def test_first_last_suppression_and_saturating_counts_survive_restart(self):
        for n in range(3):
            self.service.reader.parse = lambda *a, **kw: Event(
                "diagnostic",
                errors=["incomplete_record"],
                rule_id="one",
                instruction_version="v",
            )
            self.service.ingest(Record("bad", n, n + 1), "LIVE", "g")
        h = self.service.health("LIVE")["support"]
        total = h["totals"][0]
        self.assertEqual(
            (total["first"]["byte_start"], total["last"]["byte_end"]), (0, 3)
        )
        self.assertEqual(total["count"], 3)
        self.assertEqual(h["sample_suppressed_count"], 2)
        total["count"] = support.MAX_COUNT
        self.service.db.execute(
            "UPDATE support_totals SET payload=?", (json.dumps(total),)
        )
        self.service.db.commit()
        self.service.ingest(Record("bad", 3, 4), "LIVE", "g")
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        h = self.service.health("LIVE")["support"]
        self.assertTrue(h["counter_saturated"])
        self.assertEqual(h["total_count"], support.MAX_COUNT)

    def test_control_characters_multibyte_text_and_identity_have_byte_bounds(self):
        self.service.reader.parse = lambda *a, **kw: Event(
            "diagnostic",
            errors=["incomplete_record"],
            rule_id="界" * 2000,
            instruction_version="\x00" * 2000,
        )
        self.service.ingest(
            Record("\x00界" * 4000, 0, 20000), "secret" * 1000, "generation" * 1000
        )
        for table in ("support_totals", "support_buckets", "support_samples"):
            for (payload,) in self.service.db.execute(f"SELECT payload FROM {table}"):
                self.assertLessEqual(len(payload.encode()), 4096)
        sample = json.loads(
            self.service.db.execute("SELECT payload FROM support_samples").fetchone()[0]
        )
        self.assertTrue(sample["truncated"])
        self.assertLessEqual(len(sample["sample"].encode()), 2048)
        self.assertTrue(
            json.loads(
                self.service.db.execute(
                    "SELECT payload FROM support_buckets"
                ).fetchone()[0]
            )["identity_overflow"]
        )

    def test_legacy_diagnostics_and_unknown_samples_are_preserved_on_upgrade(self):
        db = self.service.db
        db.execute(
            "INSERT INTO observations(occurrence,environment,generation,errors,fields,observed_at,event_type) VALUES('old','LIVE','g','[\"legacy-error\"]','{\"private\":1}',0,'diagnostic')"
        )
        db.execute(
            "INSERT INTO unknown_samples VALUES('legacy','custom','{\"sample\":\"old text\"}')"
        )
        db.commit()
        before = db.execute("SELECT * FROM observations").fetchall()
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.diagnostic(1)
        self.assertEqual(
            self.service.db.execute("SELECT * FROM observations").fetchall(), before
        )
        health = self.service.health("LIVE")
        self.assertEqual(health["legacy_diagnostic_rows"], 1)
        self.assertGreater(health["legacy_diagnostic_payload_bytes_approximate"], 0)
        self.assertEqual(
            self.service.db.execute("SELECT payload FROM unknown_samples").fetchone()[
                0
            ],
            '{"sample":"old text"}',
        )

    def test_unknown_existing_domain_snapshot_retains_reset_semantics(self):
        self.service.ingest(
            Record("User Login Success Handle[Player]", 0, 50), "private-env", "old"
        )
        self.diagnostic(10, "private-env")
        state = self.service.state("private-env")
        self.assertIsNone(state["player_name"])
        self.assertEqual(state["generation"], "generation")
        self.assertEqual(
            self.service.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 1
        )
        self.assertEqual(self.service.health("private-env")["counts"]["diagnostics"], 1)

    def test_equal_confirmed_financial_occurrences_never_merged(self):
        for n in range(3):
            self.service.reader.parse = lambda *a, **kw: Event(
                "shop_sell",
                {
                    "price": 100.0,
                    "quantity": 1,
                    "currency_type": "UEC",
                    "player_id": "p",
                    "source_provider": "ShoppingProvider",
                },
                datetime(2026, 9, 15, tzinfo=UTC),
            )
            self.service.ingest(
                Record("same request", n * 2, n * 2 + 1), "LIVE", "money"
            )
            self.service.reader.parse = lambda *a, **kw: Event(
                "shop_transaction_result",
                {
                    "player_id": "p",
                    "source_provider": "ShoppingProvider",
                    "result": "Success",
                },
                datetime(2026, 9, 15, tzinfo=UTC),
            )
            self.service.ingest(
                Record("same confirmation", n * 2 + 1, n * 2 + 2), "LIVE", "money"
            )
        self.assertEqual(self.service.ledger("LIVE")["entries"], 3)
        self.assertEqual(self.service.ledger("LIVE")["income_auec"], 300)
        self.assertEqual(
            self.service.db.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
            6,
        )
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 0)

    def test_checkpoint_write_failure_rolls_back_support_and_financial_rows(self):
        self.service.save_stream("LIVE", {"generation": "generation", "offset": 0})
        self.service.db.execute(
            "CREATE TRIGGER fail_checkpoint BEFORE INSERT ON streams BEGIN SELECT RAISE(ABORT, 'disk full'); END"
        )
        with self.assertRaises(sqlite3.Error):
            self.diagnostic(0, checkpoints=[{"generation": "generation", "offset": 10}])
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 0)
        self.service.reader = Reader(self.service.instructions)
        with self.assertRaises(sqlite3.Error):
            self.service.ingest_batch(
                [Record("User Login Success Handle[P]", 0, 10)],
                "LIVE",
                "generation",
                checkpoints=[{"generation": "generation", "offset": 10}],
            )
        self.assertEqual(self.service.events("LIVE"), [])
        self.assertEqual(self.service.stream("LIVE")["offset"], 0)

    def test_resource_warning_uses_database_and_wal_and_caches_object_scan(self):
        actual = Path.stat

        def sizes(path, *args, **kwargs):
            result = actual(path, *args, **kwargs)
            if path.name in ("events.sqlite3", "events.sqlite3-wal"):
                from types import SimpleNamespace

                return SimpleNamespace(st_size=(1 << 29), st_mode=result.st_mode)
            return result

        with (
            patch.object(Path, "stat", sizes),
            patch.object(support.os, "scandir", wraps=support.os.scandir) as scan,
        ):
            first = self.service.health("LIVE")["resources"]
            second = self.service.health("LIVE")["resources"]
            self.assertEqual(first["history_warning"], "history_at_least_1_gib")
            self.assertEqual(first["measured_at"], second["measured_at"])
            self.assertEqual(scan.call_count, 1)

    def test_export_preserves_instruction_manifests_and_metadata(self):
        self.service.db.execute(
            "UPDATE metadata SET value='new-approved-digest' WHERE key='instructions'"
        )
        self.service.db.commit()
        manifest = self.service.root / "instructions" / "manifest.json"
        manifest.parent.mkdir(exist_ok=True)
        manifest.write_text('{"active":"new-private","staged":"staged-private"}')
        before = manifest.read_bytes()
        self.assertEqual(
            main(
                [
                    "support-export",
                    "--state-dir",
                    str(self.service.root),
                    "--output",
                    str(self.root / "safe.json"),
                ]
            ),
            0,
        )
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual(
            self.service.db.execute(
                "SELECT value FROM metadata WHERE key='instructions'"
            ).fetchone()[0],
            "new-approved-digest",
        )

    def test_diagnostic_without_errors_counts_as_diagnostic(self):
        self.service.reader.parse = lambda *a, **kw: Event("diagnostic")
        self.service.ingest(Record("x", 0, 1), "LIVE", "g")
        self.service.ingest(Record("x", 0, 1), "LIVE", "g")
        self.assertEqual(
            self.service.health("LIVE")["counts"],
            {"diagnostics": 1, "recognized": 0, "ignored": 0, "unrecognized": 0},
        )

    def test_unknown_notification_cardinality_and_payload_caps(self):
        for n in range(650):
            with patch.object(support.time, "time", return_value=n * 3600):
                self.service.ingest(
                    Record(
                        'Added notification "界' + str(n) + '" [1] to queue.', n, n + 1
                    ),
                    f"unknown-{n}",
                    "g",
                )
        health = self.service.health("LIVE")["support"]
        self.assertEqual(health["total_count"], 650)
        self.assertLessEqual(health["unknown_samples"], 100)
        self.assertEqual(
            self.service.db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0], 0
        )
        self.assertTrue(
            all(
                len(p.encode()) <= 4096
                for (p,) in self.service.db.execute(
                    "SELECT payload FROM support_unknown"
                )
            )
        )

    def test_export_rejects_symlink_parent_and_write_failure_leaves_no_artifact(self):
        dest = self.root / "safe.json"
        actual = Path.is_symlink
        with (
            patch.object(Path, "is_symlink", lambda p: p == self.root or actual(p)),
            self.assertRaises(ValueError),
        ):
            support.export_support(self.service.root, dest)
        with (
            patch.object(support.os, "fsync", side_effect=OSError("full")),
            self.assertRaises(OSError),
        ):
            support.export_support(self.service.root, dest)
        self.assertFalse(dest.exists())
        self.assertEqual(list(self.root.glob(".support-*.tmp")), [])

    def test_old_unknown_sample_replay_outside_dedup_window_is_safe(self):
        text = 'Added notification "novel" [1] to queue.'
        self.service.ingest(Record(text, 0, 1), "LIVE", "g")
        for n in range(513):
            self.diagnostic(n)
        self.service.reader = Reader(self.service.instructions)
        with patch.object(support.time, "time", return_value=1):
            self.service.ingest(Record(text, 0, 1), "LIVE", "g")
        self.assertEqual(self.service.health("LIVE")["support"]["total_count"], 515)

    def test_export_normalizes_runtime_path_before_destination_check(self):
        alternate = self.root / "temporary"
        alternate.mkdir()
        aliased = alternate / ".." / "runtime"
        destination = self.service.root / "unsafe.json"
        with self.assertRaises(ValueError):
            support.export_support(aliased, destination)
        self.assertFalse(destination.exists())

    def test_error_sample_metadata_exposes_truncation_and_retained_identity(self):
        self.diagnostic(1)
        h = self.service.health("LIVE")["support"]
        self.assertGreater(h["sample_truncated_count"], 0)
        self.assertEqual(h["retained_details"][0]["rule_id"], "rule-1")

    def test_timeout_cause_stage_survive_restart_and_redacted_export(self):
        expected = {
            (cause, "capture")
            for cause in ("regex_timeout", "operation_deadline", "entry_deadline")
        }
        for n, (cause, stage) in enumerate(sorted(expected)):
            self.service.reader.parse = lambda *a, cause=cause, stage=stage, **kw: (
                Event(
                    "diagnostic",
                    {"reason": cause, "stage": stage, "private": "secret-player"},
                    errors=["regex_budget_exceeded"],
                    rule_id="same-rule",
                    instruction_version="same-version",
                )
            )
            self.service.ingest(Record("secret-player", n, n + 1), "LIVE", "g")
        self.service.close()
        self.service = Service(self.root / "runtime")
        self.addCleanup(self.service.close)
        self.assertEqual(
            {
                (p.get("timeout_cause"), p.get("stage"))
                for p in self.service.diagnostics("LIVE")
            },
            expected,
        )
        h = self.service.health("LIVE")["support"]
        self.assertEqual(h["total_count"], 3)
        self.assertEqual(len(h["totals"]), 1)
        self.assertEqual(
            {(p.get("timeout_cause"), p.get("stage")) for p in h["retained_details"]},
            expected,
        )
        dest = self.root / "timeouts.json"
        support.export_support(self.service.root, dest)
        raw = dest.read_text()
        self.assertNotIn("secret-player", raw)
        self.assertNotIn("same-rule", raw)
        details = json.loads(raw)["support"]["timeout_details"]
        self.assertEqual({(p["timeout_cause"], p["stage"]) for p in details}, expected)
        self.assertEqual(sum(p["count"] for p in details), 3)

    def test_timeout_fields_are_fixed_enums_and_legacy_totals_remain_compatible(self):
        self.diagnostic(0)
        self.service.reader.parse = lambda *a, **kw: Event(
            "diagnostic",
            {
                "reason": "secret-player",
                "stage": "secret-path",
                "private": "opaque-secret",
            },
            errors=["regex_budget_exceeded"],
            rule_id="r",
            instruction_version="v",
        )
        self.service.ingest(Record("private", 10, 11), "LIVE", "g")
        detail = self.service.diagnostics("LIVE")[0]
        self.assertEqual(
            (detail.get("timeout_cause"), detail.get("stage")), ("unknown", "unknown")
        )
        dest = self.root / "enums.json"
        support.export_support(self.service.root, dest)
        raw = dest.read_text()
        for secret in ("secret-player", "secret-path", "opaque-secret"):
            self.assertNotIn(secret, raw)
        self.assertEqual(json.loads(raw)["support"]["total_count"], 2)

    def test_pre_fix_timeout_bucket_counts_remain_without_invented_cause(self):
        self.service.reader.parse = lambda *a, **kw: Event(
            "diagnostic",
            {"reason": "entry_deadline", "stage": "capture"},
            errors=["regex_budget_exceeded"],
            rule_id="r",
            instruction_version="v",
        )
        self.service.ingest(Record("old", 0, 1), "LIVE", "g")
        db = self.service.db
        payload = json.loads(
            db.execute("SELECT payload FROM support_buckets").fetchone()[0]
        )
        payload.pop("timeout_cause", None)
        payload.pop("stage", None)
        db.execute(
            "UPDATE support_buckets SET key='pre-fix-key',payload=?",
            (json.dumps(payload),),
        )
        db.commit()
        self.service.ingest(Record("new", 1, 2), "LIVE", "g")
        dest = self.root / "legacy-timeouts.json"
        support.export_support(self.service.root, dest)
        result = json.loads(dest.read_text())["support"]
        self.assertEqual(result["total_count"], 2)
        self.assertEqual(
            {
                (p["timeout_cause"], p["stage"], p["count"])
                for p in result["timeout_details"]
            },
            {("unknown", "unknown", 1), ("entry_deadline", "capture", 1)},
        )

    def test_python311_reparse_parent_refused_independently_from_symlinks(self):
        from types import SimpleNamespace

        dest = self.root / "junction-output.json"
        original = support.os.lstat

        def reparse(path, *args, **kwargs):
            if Path(path) == self.root:
                return SimpleNamespace(st_file_attributes=0x400)
            return original(path, *args, **kwargs)

        # Python 3.11 has no Path.is_junction; a false method represents the old fallback.
        with (
            patch.object(Path, "is_symlink", return_value=False),
            patch.object(Path, "is_junction", return_value=False, create=True),
            patch.object(support.os, "lstat", side_effect=reparse),
            self.assertRaises(ValueError),
        ):
            support.export_support(self.service.root, dest)
        self.assertFalse(dest.exists())
        self.assertEqual(list(self.root.glob(".support-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

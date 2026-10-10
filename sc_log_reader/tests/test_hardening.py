"""Regression evidence for the September architecture review."""

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import patch

from sc_log_reader.reader import (
    Event,
    Instructions,
    Reader,
    Record,
    RecordAssembler,
    bundled_bytes,
)
from sc_log_reader.service import Service, Tailer, ToolInterface
from sc_log_reader.state import State
from sc_log_reader.updates import UpdateError, UpdateManager

T = datetime(2026, 9, 16, 12, tzinfo=UTC)
URL = "https://raw.githubusercontent.com/example/reader/main/instructions.json"


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.instructions = Instructions.load(bundled_bytes())
        self.state = State(self.instructions.data["lookups"])
        self.n = 0

    def send(self, kind, fields, seconds=0):
        self.n += 1
        return self.state.apply(
            Event(kind, fields, T + timedelta(seconds=seconds)), str(self.n), "g"
        )

    def service(self, **kw):
        service = Service(self.root / "runtime", **kw)
        self.addCleanup(service.close)
        return service

    def test_optional_framing_captures_cannot_escape(self):
        for key, pattern in [
            ("timestamp", r"^(?:<([^>]+)>)?"),
            ("notification", r'^(?:Added notification "([^"]+)")?'),
        ]:
            with self.subTest(key=key):
                data = json.loads(bundled_bytes())
                data["framing"][key] = pattern
                reader = Reader(Instructions.load(json.dumps(data).encode()))
                try:
                    event = reader.parse("User Login Success Handle[A]")
                except Exception as exc:
                    self.fail(f"Optional {key} capture escaped: {exc}")
                self.assertIsNotNone(event)

    def test_poison_record_does_not_block_later_login(self):
        log = self.root / "Game.log"
        log.write_text(
            "CommodityUIProvider SendCommodityBuyRequest playerId[p] price[5] quantity[, cSCU]\nUser Login Success Handle[A]\n"
        )
        service = self.service()
        tail = Tailer(service, {"LIVE": log})
        tail.poll()
        self.assertEqual(service.state("LIVE")["player_name"], "A")
        self.assertEqual(service.stream("LIVE")["offset"], log.stat().st_size)
        self.assertTrue(service.diagnostics("LIVE"))

    def test_reapproval_keeps_original_rollback(self):
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        raw = json.dumps(data).encode()

        def manager():
            return UpdateManager(self.root / "updates", URL, fetch=lambda _: raw)

        first = manager()
        base = first.startup().revision
        info = first.check()
        first.approve(info["sha256"])
        running = manager()
        self.assertEqual(running.startup().revision, base + 1)
        running.approve(info["sha256"])
        running = manager()
        running.startup()
        running.rollback()
        self.assertEqual(manager().startup().revision, base)

    def test_truncated_http_becomes_recoverable_update_error(self):
        def fetch(_):
            raise IncompleteRead(b"partial", 100)

        manager = UpdateManager(self.root / "updates", URL, fetch=fetch)
        try:
            manager.check()
        except UpdateError:
            pass
        except Exception as exc:
            self.fail(f"Transport failure escaped: {type(exc).__name__}")
        else:
            self.fail("Truncated response must be rejected")
        self.assertEqual(manager.startup().revision, self.instructions.revision)

    def test_real_quoted_reward_keeps_full_name_and_metadata(self):
        raw = (
            Path(__file__).parent / "fixtures/real_notifications/quoted_reward.log"
        ).read_bytes()
        assembler = RecordAssembler(self.instructions)
        records = []
        for byte in raw:
            records.extend(assembler.feed(bytes([byte])))
        records.extend(assembler.finish())
        self.assertEqual(len(records), 1)
        event = Reader(self.instructions).parse(
            records[0].text, complete=records[0].complete
        )
        self.assertEqual(event.errors, [])
        self.assertEqual(
            event.fields["item_name"], 'Falston Jumpsuit "People\'s Alliance Edition"'
        )
        self.assertEqual(event.fields["notification_id"], "34")

    def test_newest_source_time_selects_environment_after_old_catchup(self):
        service = self.service()
        for env, date, name in [
            ("LIVE", "2026-09-16", "Current"),
            ("PTU", "2026-07-01", "Old"),
        ]:
            service.ingest(
                Record(f"<{date}T12:00:00Z> User Login Success Handle[{name}]", 0, 100),
                env,
                "g",
            )
        self.assertEqual(service.state()["environment"], "LIVE")
        self.assertIsNotNone(service.state()["last_source_timestamp"])

    def test_duplicate_money_notifications_are_not_booked_twice(self):
        reader = Reader(self.instructions)
        for text, amount in [
            ("Fined 1,000 UEC", -1000),
            ("You sent Bob: 1,500 aUEC", -1500),
        ]:
            with self.subTest(text=text):
                event = reader.parse(
                    f'<2026-09-16T12:00:00Z> <SHUDEvent> Added notification "{text}:" [13] to queue.'
                )
                first = self.state.apply(event, text + "1", "g")
                second = self.state.apply(event, text + "2", "g")
                self.assertEqual(
                    sum(r.get("amount_auec", 0) for r in first + second), amount
                )

    def test_nil_player_identity_cannot_confirm_money(self):
        for identity in ["0", "  ", "0000-0000", "\t000\t"]:
            with self.subTest(identity=identity):
                self.send(
                    "shop_buy",
                    {
                        "player_id": identity,
                        "source_provider": "shopping",
                        "price": 500,
                        "quantity": 1,
                        "currency_type": "UEC",
                    },
                )
                rows = self.send(
                    "shop_transaction_result",
                    {
                        "player_id": identity,
                        "source_provider": "shopping",
                        "result": "Success",
                    },
                    1,
                )
                self.assertFalse(any("amount_auec" in r for r in rows))

    def test_unknown_location_preserves_history_but_clears_current_claim(self):
        self.send("user_login", {"player_name": "A"})
        self.send(
            "location_change",
            {"player_name": "A", "location": "Stanton4_NewBabbage"},
            1,
        )
        self.send(
            "personal_inventory_data", {"player_name": "A", "location_guid": "111"}, 2
        )
        self.send("location_change", {"player_name": "A", "location": "NEW_UNKNOWN"}, 3)
        state = self.state.public()
        self.assertIsNone(state["location_name"])
        self.assertIsNone(state["location_guid"])
        self.assertEqual(state["location_status"], "unknown")
        self.assertEqual(state["last_known_location"]["name"], "New Babbage")

    def test_repeated_location_refreshes_guid_window_without_announcement(self):
        self.send("user_login", {"player_name": "A"})
        self.send(
            "location_change",
            {"player_name": "A", "location": "Stanton4_NewBabbage"},
            1,
        )
        self.assertEqual(
            self.send(
                "location_change",
                {"player_name": "A", "location": "Stanton4_NewBabbage"},
                31,
            ),
            [],
        )
        self.send(
            "personal_inventory_data", {"player_name": "A", "location_guid": "111"}, 32
        )
        rows = self.send(
            "inventory_location_update",
            {"player_name": "A", "loc_from": "111", "loc_to": "222"},
            33,
        )
        self.assertEqual([r["event_type"] for r in rows], ["location_departed"])

    def test_wrong_typed_healing_field_is_diagnostic_not_exception(self):
        event = Event("med_bed_heal", {"healed_parts": "head"})
        try:
            rows = self.state.apply(event, "heal", "g")
        except Exception as exc:
            self.fail(f"Malformed canonical field escaped: {exc}")
        self.assertEqual(rows, [])
        self.assertTrue(event.errors)

    def test_state_accepts_canonical_ship_without_game_wording(self):
        self.send("user_login", {"player_name": "A"})
        rows = self.send(
            "channel_change",
            {
                "action": "joined",
                "ship_name": "Future craft",
                "ship_class": "NEW_Craft",
                "owner": "A",
            },
        )
        self.assertEqual([r["event_type"] for r in rows], ["ship_entered"])
        self.assertTrue(self.state.public()["own_ship"])

    def test_health_exposes_unknown_input_without_unbounded_raw_storage(self):
        service = self.service()
        service.ingest(Record("unknown", 0, 7), "LIVE", "g")
        try:
            health = ToolInterface(service).call(
                "get_reader_health", {"environment": "LIVE"}
            )
        except ValueError:
            self.fail("Reader health tool missing")
        self.assertEqual(health["counts"]["unrecognized"], 1)
        self.assertFalse(health["game_build_verified"])

    def test_live_header_build_and_backlog_are_visible(self):
        log = self.root / "Game.log"
        log.write_text(
            'BackupNameAttachment=" Build(12572603)"\n<2026-09-16T12:00:00Z> User Login Success Handle[A]\n'
        )
        service = self.service()
        Tailer(service, {"LIVE": log}).poll()
        self.assertTrue(hasattr(service, "health"), "Reader health missing")
        health = service.health("LIVE")
        self.assertEqual(health["game_build"], "12572603")
        self.assertEqual(health["bytes_behind"], 0)
        self.assertFalse(health["catching_up"])

    def test_reader_upgrade_requirement_is_reported_without_staging(self):
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        data["minimum_reader_version"] = "999.0.0"
        manager = UpdateManager(
            self.root / "updates", URL, fetch=lambda _: json.dumps(data).encode()
        )
        try:
            result = manager.check()
        except UpdateError as exc:
            self.fail(f"Compatibility requirement was not reported: {exc}")
        self.assertEqual(result["status"], "reader_upgrade_required")
        self.assertIsNone(manager.status()["staged_sha256"])

    def test_semantically_broken_update_is_rejected_before_approval(self):
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        data["rules"] = [r for r in data["rules"] if r["event"] != "user_login"]
        manager = UpdateManager(
            self.root / "updates", URL, fetch=lambda _: json.dumps(data).encode()
        )
        with self.assertRaises(UpdateError):
            manager.check()

    def test_ledger_aggregates_without_loading_unbounded_history(self):
        service = self.service()
        for i, text in enumerate(
            [
                "<2026-09-16T12:00:00Z> ShoppingProvider SendStandardItemBuyRequest playerId[p] client_price[265] quantity[1] currencyType[UEC]",
                "<2026-09-16T12:00:01Z> ShoppingProvider RmShopFlowResponse playerId[p] result[Success]",
            ]
        ):
            service.ingest(Record(text, i * 500, (i + 1) * 500), "LIVE", "g")

        def forbid_unbounded(*args, **kw):
            self.fail("Ledger must aggregate in SQL, not load every payload")

        service.events = forbid_unbounded
        ledger = ToolInterface(service).call(
            "get_trade_ledger", {"environment": "LIVE", "time_range": "all"}
        )
        self.assertEqual(ledger["net_cash_flow_auec"], -265)
        self.assertEqual(ledger["entries"], 1)

    def test_skip_is_specific_to_reviewed_digest_and_does_not_install(self):
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        manager = UpdateManager(
            self.root / "updates", URL, fetch=lambda _: json.dumps(data).encode()
        )
        info = manager.check()
        self.assertTrue(hasattr(manager, "skip"), "Manual Skip action missing")
        manager.skip(info["sha256"])
        self.assertEqual(manager.check()["status"], "skipped")
        self.assertIsNone(manager.status()["staged_sha256"])
        data["revision"] += 1
        self.assertEqual(manager.check()["status"], "available")
        with self.assertRaises(UpdateError):
            manager.skip(info["sha256"])

    def test_catchup_reads_multiple_chunks_when_work_fits_budget(self):
        log = self.root / "Game.log"
        log.write_bytes((b"x" * 60000 + b"\n") * 9 + b"User Login Success Handle[A]\n")
        service = self.service()
        Tailer(service, {"LIVE": log, "PTU": self.root / "absent.log"}).poll()
        self.assertEqual(service.state("LIVE")["player_name"], "A")

    def test_legacy_instruction_contract_is_adapted_before_state(self):
        data = json.loads(bundled_bytes())
        data["engine_version"] = 1
        rule = next(r for r in data["rules"] if r["event"] == "channel_change")
        rule["read"] = rule["read"][:2]
        reader = Reader(Instructions.load(json.dumps(data).encode()))
        event = reader.parse(
            """<SHUDEvent> Added notification "You joined channel '@vehicle_NameAEGS_Avenger_Titan : A':" [13] to queue."""
        )
        self.send("user_login", {"player_name": "A"})
        self.state.apply(event, "ship", "g")
        self.assertEqual(self.state.public()["ship"], "AEGS Avenger Titan")
        self.assertTrue(self.state.public()["own_ship"])

    def test_missing_or_older_time_cannot_erase_newer_environment_evidence(self):
        service = self.service()
        for env, text, offset in [
            ("LIVE", "<2026-09-16T12:00:00Z> User Login Success Handle[A]", 0),
            ("PTU", "<2026-07-01T12:00:00Z> User Login Success Handle[B]", 0),
            ("LIVE", '<SHUDEvent> Added notification "Bleeding" [1] to queue.', 100),
            (
                "LIVE",
                '<2026-06-01T12:00:00Z> <SHUDEvent> Added notification "Bleeding" [2] to queue.',
                200,
            ),
        ]:
            service.ingest(Record(text, offset, offset + 100), env, "g")
            self.assertEqual(service.state()["environment"], "LIVE")

    def test_header_written_after_empty_file_is_detected(self):
        log = self.root / "Game.log"
        log.touch()
        service = self.service()
        tail = Tailer(service, {"LIVE": log})
        tail.poll()
        log.write_text(
            'BackupNameAttachment=" Build(12572603)"\nUser Login Success Handle[A]\n'
        )
        tail.poll()
        self.assertEqual(service.health("LIVE")["game_build"], "12572603")

    def test_bundled_rollback_survives_reader_upgrade(self):
        original = bundled_bytes()
        data = json.loads(original)
        data["revision"] += 1
        manager = UpdateManager(
            self.root / "updates", URL, fetch=lambda _: json.dumps(data).encode()
        )
        manager.startup()
        info = manager.check()
        manager.approve(info["sha256"])
        UpdateManager(self.root / "updates").startup()
        data["revision"] += 1
        with patch(
            "sc_log_reader.updates.bundled_bytes",
            return_value=json.dumps(data).encode(),
        ):
            upgraded = UpdateManager(self.root / "updates")
            upgraded.startup()
            try:
                upgraded.rollback()
            except UpdateError as exc:
                self.fail(f"Engine upgrade lost bundled rollback: {exc}")
            self.assertEqual(
                UpdateManager(self.root / "updates").startup().revision,
                json.loads(original)["revision"],
            )

    def test_skip_cancels_the_same_pending_approval(self):
        data = json.loads(bundled_bytes())
        data["revision"] += 1
        manager = UpdateManager(
            self.root / "updates", URL, fetch=lambda _: json.dumps(data).encode()
        )
        info = manager.check()
        manager.approve(info["sha256"])
        manager.skip(info["sha256"])
        self.assertIsNone(manager.status()["staged_sha256"])
        self.assertEqual(manager.startup().revision, self.instructions.revision)

    def test_startup_fails_explicitly_when_even_bundle_is_unusable(self):
        data = json.loads(bundled_bytes())
        data["rules"] = [r for r in data["rules"] if r["event"] != "user_login"]
        with patch(
            "sc_log_reader.updates.bundled_bytes",
            return_value=json.dumps(data).encode(),
        ):
            manager = UpdateManager(self.root / "updates")
            with self.assertRaises(UpdateError):
                manager.startup()

    def test_nonreset_session_evidence_preserves_source_freshness(self):
        self.send("user_login", {"player_name": "A"})
        for kind, fields in [
            ("join_pu", {"shard": "eu-1"}),
            ("session_start", {"player_geid": "p1"}),
        ]:
            with self.subTest(kind=kind):
                session = self.state.public()["session_key"]
                self.state.apply(Event(kind, fields), kind, "g")
                self.assertEqual(self.state.public()["session_key"], session)
                self.assertEqual(
                    self.state.public()["last_source_timestamp"], T.isoformat()
                )


if __name__ == "__main__":
    unittest.main()

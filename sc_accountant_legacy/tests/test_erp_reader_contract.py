"""Cross-component acceptance: actual reader parser/service/feed into the ERP."""

from pathlib import Path


def test_actual_reader_feed_preserves_money_and_physical_rewards(tmp_path, monkeypatch):
    skills = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(skills / "sc_log_reader" / "src"))
    from sc_log_reader.reader import Record, RecordAssembler
    from sc_log_reader.service import Service
    from erp import ERP

    reader = Service(tmp_path / "reader")
    erp = ERP(tmp_path / "erp.sqlite3")
    try:
        lines = [
            "<2026-09-15T12:00:00Z> User Login Success Handle[Mallachi]",
            '<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "Contract Accepted: Delivery:" [13] to queue. MissionId: [m1]',
            '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.',
        ]
        offset = 0
        for line in lines:
            reader.ingest(
                Record(line, offset, offset + len(line)), "LIVE", "game-session-1"
            )
            offset += len(line)
        page = reader.export_events(limit=2)
        erp.ingest_page(page)
        page = reader.export_events(after=page["next_cursor"], limit=2)
        erp.ingest_page(page)
        assert erp.view()["data"]["balance"] == "500.00"
        assert len(erp.view("operations")["data"]) == 1
        erp.ingest_page(reader.export_events())
        assert erp.view()["data"]["balance"] == "500.00"
        assert erp.view("evidence")["data"][0]["source"]["byte_start"] > 0
        raw = (
            skills
            / "sc_log_reader"
            / "tests"
            / "fixtures"
            / "real_notifications"
            / "reward.log"
        ).read_bytes()
        assembler = RecordAssembler(reader.instructions)
        for record in assembler.feed(raw) + assembler.finish():
            reader.ingest(record, "LIVE", "physical-reward-fixture")
        erp.ingest_page(reader.export_events(after=erp.view("feed")["data"]["cursor"]))
        assert erp.view()["data"]["balance"] == "500.00"
        assert erp.view("attention")["data"]

    finally:
        reader.close()
        erp.close()


def test_actual_capture_resumes_without_duplicates_and_rejects_new_source(tmp_path, monkeypatch):
    import pytest

    skills = Path(__file__).resolve().parents[2]
    monkeypatch.syspath_prepend(str(skills / "sc_log_reader" / "src"))
    from sc_log_reader.reader import Record
    from sc_log_reader.service import Service
    from erp import ERP
    from erp_feed import capture_once

    reader_root = tmp_path / "reader"
    erp_path = tmp_path / "erp.sqlite3"
    reader = Service(reader_root)
    erp = ERP(erp_path)
    try:
        line = '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.'
        reader.ingest(Record(line, 0, len(line)), "LIVE", "live-session")
        reader.ingest(Record(line, 0, len(line)), "PTU", "test-session")
        page = capture_once(erp, reader_root / "events.sqlite3")
        assert erp.view()["data"]["balance"] == "500.00"
        assert {event["environment"] for event in page["events"]} == {"LIVE", "PTU"}
        source_id, cursor = page["source_id"], page["next_cursor"]
        assert capture_once(erp, reader_root / "events.sqlite3")["events"] == []
        reader.close()
        erp.close()
        reader = Service(reader_root)
        erp = ERP(erp_path)
        page = capture_once(erp, reader_root / "events.sqlite3")
        assert page["source_id"] == source_id and page["next_cursor"] == cursor
        assert erp.view()["data"]["balance"] == "500.00"
        next_line = '<2026-09-15T12:00:03Z> <SHUDEvent> Added notification "Awarded 250 aUEC:" [15] to queue.'
        reader.ingest(Record(next_line, len(line), len(line) + len(next_line)), "LIVE", "live-session")
        capture_once(erp, reader_root / "events.sqlite3")
        assert erp.view()["data"]["balance"] == "750.00"
        before = erp.view("feed")["data"].copy()
        replacement = Service(tmp_path / "replacement")
        try:
            with pytest.raises(ValueError, match="Reader database changed"):
                capture_once(erp, replacement.root / "events.sqlite3")
            assert erp.view("feed")["data"] == before
            assert erp.view()["data"]["balance"] == "750.00"
        finally:
            replacement.close()
    finally:
        reader.close()
        erp.close()

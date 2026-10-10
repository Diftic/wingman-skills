import json
import sqlite3

import pytest

from sc_log_reader.reader import Record
from sc_log_reader.service import Service


@pytest.fixture
def service(tmp_path):
    instance = Service(tmp_path / 'reader')
    yield instance
    instance.close()


def append(service, occurrence, timestamp=100, environment='LIVE', status='confirmed', amount=100):
    # Synthetic handler outputs exercise multiple rows per source occurrence.
    payload = {'event_type': 'reward', 'status': status, 'amount_auec': amount,
               'environment': environment, 'source_timestamp': timestamp}
    with service.db:
        service.db.execute(
            'INSERT INTO events(occurrence,environment,event_type,amount,status,source_time,payload) VALUES(?,?,?,?,?,?,?)',
            (occurrence, environment, 'reward', amount, status, timestamp, json.dumps(payload)))


def test_service_exposes_feed(service):
    assert callable(getattr(service, 'export_events', None)), 'Service requires durable export_events'


def test_pages_are_ascending_independent_of_time_and_include_environments(service):
    append(service, 'same', 100)
    append(service, 'same', 100, 'PTU', 'request', None)
    append(service, 'late', 50)
    page = service.export_events(limit=2)
    assert page['contract_version'] == 1
    assert page['after'] == 0
    assert page['next_cursor'] == 2
    assert page['has_more'] is True
    assert [e['sequence'] for e in page['events']] == [1, 2]
    assert len({e['id'] for e in page['events']}) == 2
    assert page['events'][0]['source_occurrence'] == page['events'][1]['source_occurrence'] == 'same'
    assert page['events'][1]['status'] == 'request'
    assert page['events'][1]['amount_auec'] is None
    assert page['events'][1]['environment'] == 'PTU'
    last = service.export_events(after=2, limit=2)
    assert [e['sequence'] for e in last['events']] == [3]
    assert last['has_more'] is False
    empty = service.export_events(after=3)
    assert empty['next_cursor'] == 3
    assert empty['events'] == []


def test_identity_stable_after_restart_and_new_database_differs(service, tmp_path):
    append(service, 'one')
    original = service.export_events()
    service.close()
    with_service = Service(service.root)
    try:
        assert with_service.export_events()['events'] == original['events']
        assert with_service.export_events()['source_id'] == original['source_id']
    finally:
        with_service.close()
    rebuilt = Service(tmp_path / 'rebuilt')
    try:
        assert rebuilt.export_events()['source_id'] != original['source_id']
    finally:
        rebuilt.close()


def test_readonly_client_does_not_initialize_or_mutate(service, tmp_path):
    from sc_log_reader.feed import ReaderFeed, FeedError
    append(service, 'one')
    path = service.root / 'events.sqlite3'
    before = service.db.total_changes
    result = ReaderFeed(path).read_page()
    assert result['events'] == service.export_events()['events']
    assert service.db.total_changes == before
    missing = tmp_path / 'missing.sqlite3'
    with pytest.raises(FeedError, match='open'):
        ReaderFeed(missing).read_page()
    assert not missing.exists()
    legacy = tmp_path / 'legacy.sqlite3'
    with sqlite3.connect(legacy) as db:
        db.execute('CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT)')
    original = legacy.read_bytes()
    with pytest.raises(FeedError, match='initialized'):
        ReaderFeed(legacy).read_page()
    assert legacy.read_bytes() == original


@pytest.mark.parametrize('kwargs', [{'after': -1}, {'after': True}, {'after': 1.5},
                                   {'limit': 0}, {'limit': 1001}, {'limit': True}, {'limit': '2'}])
def test_invalid_cursor_or_limit_rejected(service, kwargs):
    with pytest.raises(ValueError):
        service.export_events(**kwargs)


def test_cursor_ahead_of_database_rejected(service):
    from sc_log_reader.feed import FeedError
    with pytest.raises(FeedError, match='ahead'):
        service.export_events(after=1)


def test_incompatible_contract_is_explicit(service):
    from sc_log_reader.feed import FeedError
    with service.db:
        service.db.execute("UPDATE metadata SET value='99' WHERE key='erp_feed_contract_version'")
    with pytest.raises(FeedError, match='contract'):
        service.export_events()


def test_real_ingest_preserves_source_evidence(service):
    text = '<2026-09-15T12:00:02Z> <SHUDEvent> Added notification "Awarded 500 aUEC:" [14] to queue.'
    service.ingest(Record(text, 0, len(text)), 'LIVE', 'generation-1')
    page = service.export_events()
    assert len(page['events']) == 1
    event = page['events'][0]
    assert event['amount_auec'] == 500.0
    assert event['status'] == 'confirmed'
    assert event['generation'] == 'generation-1'
    assert event['source_occurrence']
    assert event['id'] == f"{page['source_id']}:{event['sequence']}"
    assert event['source']['byte_start'] == 0
    assert event['source']['byte_end'] == len(text)
    assert event['source']['instruction_version']

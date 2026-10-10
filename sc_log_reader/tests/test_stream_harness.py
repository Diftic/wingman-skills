import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class StreamHarnessTests(unittest.TestCase):
    def load(self):
        path = ROOT / 'tools' / 'stream_test.py'
        self.assertTrue(path.exists(), 'stream harness is not implemented')
        spec = importlib.util.spec_from_file_location('stream_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_four_known_offers_detect_missing_duplicate_and_latency(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            oracle = module.Oracle(Path(tmp) / 'oracle.sqlite3')
            for i in range(4):
                oracle.offer(i * 10, 'reward_earned', i, 500)
            oracle.observe(0, 'reward_earned', 2, 500)
            oracle.observe(10, 'reward_earned', 3, 500)
            oracle.observe(10, 'reward_earned', 3.1, 500)
            oracle.observe(30, 'reward_earned', 5, 499)
            result = oracle.result()
            self.assertEqual(result['missing'], 1)
            self.assertEqual(result['duplicates'], 1)
            self.assertEqual(result['wrong_outcomes'], 1)
            self.assertEqual(result['expected'], 4)
            self.assertEqual(result['visibility']['p95_seconds'], 2)
            oracle.close()

    def test_short_real_stream_has_independent_outcomes_and_pending_delivery(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            output = Path(tmp) / 'run'
            result = module.run(output, profile='typical', rate=56, duration=.15)
            self.assertEqual(result['oracle']['missing'], 0)
            self.assertEqual(result['oracle']['duplicates'], 0)
            self.assertEqual(result['oracle']['wrong_outcomes'], 0)
            self.assertGreater(result['writer']['records'], 0)
            self.assertEqual(result['notification_delivery']['status'], 'pending')
            self.assertEqual(result.get('heartbeat_scope'), 'asyncio host double; poll/tool offloaded to threads')
            self.assertGreater(result['metrics']['heartbeat']['count'], 0)
            self.assertGreater(result.get('commit_latency', {}).get('count', 0), 0)
            self.assertTrue((output / 'metrics.jsonl').exists())

    def test_output_must_be_fresh_and_source_hash_mismatch_is_rejected(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            root = Path(tmp)
            with self.assertRaises(FileExistsError):
                module.run(root, duration=.01)
            source = root / 'private.log'
            source.write_bytes(b'private\n')
            with self.assertRaises(ValueError):
                module.verify_source(source, expected_size=8, expected_sha256='bad')
            self.assertEqual(source.read_bytes(), b'private\n')

    def test_histogram_memory_is_bounded_and_overflow_does_not_hide_latency(self):
        module = self.load()
        histogram = module.Histogram()
        for _ in range(100000):
            histogram.add(20)
        self.assertLessEqual(len(histogram.bins), 10002)
        self.assertEqual(histogram.result()['p99_seconds'], float('inf'))

    def test_oracle_detects_reordered_committed_outcomes(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            oracle = module.Oracle(Path(tmp) / 'oracle.sqlite3')
            oracle.offer(10, 'user_login', 1)
            oracle.offer(20, 'mission_accepted', 2)
            oracle.observe(20, 'mission_accepted', 3)
            oracle.observe(10, 'user_login', 3)
            result = oracle.result()
            oracle.close()
            self.assertEqual(result['order_errors'], 1)

    def test_timestamp_group_extracts_assembled_multiline_entries_read_only(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            root = Path(tmp)
            raw = (b'<2026-09-15T12:00:00Z> <SHUDEvent> Added notification "Alice\n'
                   b' continuation\nParty Invite Received" [13] to queue.\n<2026-09-15T12:00:00.500Z> engine second\n'
                   b'<2026-09-15T12:00:01Z> outside\n')
            source = root / 'source.log'
            source.write_bytes(raw)
            result = module.extract_group(source, root / 'group.log', '2026-09-15T12:00:00', 2)
            self.assertEqual(result['assembled_entries'], 2)
            self.assertIn(b' continuation\n', (root / 'group.log').read_bytes())
            self.assertNotIn(b'outside', (root / 'group.log').read_bytes())
            self.assertEqual(source.read_bytes(), raw)

    def test_recovery_faults_are_executed_and_reported(self):
        module = self.load()
        for case in ('restart', 'truncate', 'replace', 'malformed', 'database', 'disk'):
            with self.subTest(case=case), tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
                result = module.run(Path(tmp) / 'run', profile='recovery', rate=156,
                                    duration=.15, recovery_case=case)
                self.assertEqual(result['recovery']['case'], case)
                self.assertTrue(result['recovery']['executed'])
                self.assertEqual(result['oracle']['missing'], 0)
                self.assertEqual(result['oracle']['duplicates'], 0)
                self.assertEqual(result['oracle']['wrong_outcomes'], 0)
                self.assertEqual(result['final_backlog_bytes'], 0)
                self.assertTrue(result['state_oracle']['confirmed_spending'])
                if case in ('truncate', 'replace'):
                    boundary = result['recovery']['committed_pre_cut_boundary']
                    self.assertEqual(boundary['source_bytes'], boundary['committed_offset'])

    def test_notification_delivery_requires_connected_sink_and_occurrence_trace(self):
        module = self.load()
        class Policy:
            def __init__(self):
                self.pending = []
            def offer(self, event, now, catching_up):
                self.pending.append(event)
            def discard_environment(self, environment):
                self.pending = []
            def flush(self, now):
                events, self.pending = self.pending, []
                return [dict(text='Literal host-double message', source_occurrences=event['source_occurrences']) for event in events]
        delivered = []
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            result = module.run(Path(tmp) / 'run', rate=56, duration=.15,
                                notification_policy=Policy(), notification_sink=delivered.append)
            self.assertEqual(result['notification_delivery']['status'], 'measured host double')
            self.assertGreater(len(delivered), 0)
            self.assertGreater(result['notification_delivery']['append_to_delivery']['count'], 0)

    def test_cli_fails_applicable_state_oracle_and_prints_null_checks(self):
        module = self.load()
        for failed, expected_exit in ((False, 1), (None, 0)):
            # Hand-authored otherwise-clean verdict input; no generated reports.
            result = dict(oracle=dict(missing=0, duplicates=0, wrong_outcomes=0, order_errors=0),
                          writer=dict(errors=[]), final_backlog_bytes=0, targets={},
                          state_oracle=dict(player_name=True, missions_completed=True, confirmed_spending=failed))
            captured = io.StringIO()
            with patch.object(module, 'run', return_value=result) as run, patch('sys.argv',
                    ['stream_test.py', '--profile', 'typical', '--output', 'unused']), contextlib.redirect_stdout(captured):
                exit_code = module.main()
            self.assertEqual(run.call_args.kwargs['rate'], 6)
            self.assertEqual(exit_code, expected_exit)
            self.assertEqual(json.loads(captured.getvalue())['state_oracle']['confirmed_spending'], failed)

    def test_short_source_has_middle_suite_between_source_records(self):
        module = self.load()
        # Exact synthetic reproduction input, constructed independently of logs.
        raw = b''.join(f'<2026-09-15T11:00:00Z> archive_noise_{i}\n'.encode() for i in range(100))
        records = raw.splitlines(keepends=True)
        self.assertEqual(len(records), 100)
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            source = Path(tmp) / 'source.log'
            source.write_bytes(raw)
            output = Path(tmp) / 'run'
            result = module.run(output, profile='sustained', rate=1000, duration=1, source_log=source)
            emitted = (output / 'Game.log').read_bytes()
            marker = b'MissionId: [stream-1]'
            self.assertLess(emitted.index(records[0]), emitted.index(marker))
            self.assertLess(emitted.index(marker), emitted.index(records[-1]))
            self.assertTrue(result['sentinel_placement']['met'])
            self.assertEqual(source.read_bytes(), raw)

    def test_single_source_record_reports_unmet_placement_and_cli_failure(self):
        module = self.load()
        with tempfile.TemporaryDirectory(dir=ROOT, prefix='stream-test-') as tmp:
            root = Path(tmp)
            source = root / 'one.log'
            source.write_bytes(b'<2026-09-15T12:00:00Z> one record\n')
            result = module.run(root / 'run', rate=1000, duration=1, source_log=source)
            self.assertFalse(result['sentinel_placement']['met'])
            captured = io.StringIO()
            with patch.object(module, 'run', return_value=result), patch('sys.argv',
                    ['stream_test.py', '--profile', 'typical', '--output', 'unused']), contextlib.redirect_stdout(captured):
                self.assertEqual(module.main(), 1)


if __name__ == '__main__':
    unittest.main()

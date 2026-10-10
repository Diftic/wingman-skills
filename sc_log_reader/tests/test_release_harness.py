import asyncio
import importlib.util
import os
import tempfile
import types
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseHarnessTests(unittest.TestCase):
    def test_truncate_boundary_preserves_previously_unread_sentinel_outcomes(self):
        from sc_log_reader.service import Service, Tailer
        module = load('stream_test')
        with ExitStack() as stack:
            tmp = stack.enter_context(tempfile.TemporaryDirectory(dir=ROOT))
            folder = Path(tmp)
            path = folder / 'Game.log'
            path.touch()
            service = Service(folder / 'runtime')
            stack.callback(service.close)
            tailer = Tailer(service, {'LIVE': path})
            tailer.poll()
            path.write_bytes(b''.join(row[0] for row in module.sentinels(1)))
            # Source is deliberately unread; destructive cut without a boundary
            # cannot preserve these five expected outcomes.
            self.assertEqual(service.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            path.write_bytes(b'')
            tailer.poll()
            self.assertEqual(service.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 0)
            path.write_bytes(b''.join(row[0] for row in module.sentinels(1)))
            boundary = asyncio.run(module.committed_recovery_boundary(tailer, service, path, timeout=1))
            self.assertEqual(boundary['committed_offset'], path.stat().st_size)
            path.write_bytes(b'')
            tailer.poll()
            # Five expected outcomes plus the non-monetary shop request row.
            self.assertEqual(service.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 6)
            self.assertEqual(service.ledger('LIVE')['spending_auec'], 265)

    @unittest.skipUnless(os.name == 'nt', 'Windows native RSS sampler')
    def test_rss_sampling_does_not_accumulate_native_pointer_types(self):
        import ctypes
        module = load('stream_test')
        self.assertGreater(module.rss_bytes(), 0)
        warmed_types = len(ctypes._pointer_type_cache)
        for _ in range(1000):
            self.assertGreater(module.rss_bytes(), 0)
        self.assertEqual(len(ctypes._pointer_type_cache), warmed_types)

    def test_high_resolution_commit_duration_survives_coarse_monotonic(self):
        module = load('stream_test')
        callback = []
        service = object.__new__(module.TimedService)
        service.commit_callback = lambda instance, events, returned: callback.append(returned)
        clock = types.SimpleNamespace(perf_counter=lambda: 100.0034,
                                      monotonic=lambda: 100.0)
        with patch.object(module, 'time', clock), \
                patch.object(module.Service, 'ingest_batch', return_value=types.SimpleNamespace(events=[{}])):
            start = 100.0
            service.ingest_batch([])
        duration = callback[0] - start
        self.assertAlmostEqual(duration, .0034)
        histogram = module.Histogram()
        histogram.add(duration)
        self.assertEqual(histogram.result()['p95_seconds'], .004)
        self.assertAlmostEqual(histogram.result()['max_seconds'], .0034)
        metadata = module.clock_metadata()
        self.assertEqual(metadata['measurement']['name'], 'perf_counter')
        self.assertTrue(metadata['measurement']['monotonic'])
        self.assertIn('resolution_seconds', metadata['production_deadline_clock'])

    def test_cli_explicit_zero_rate_rejected_before_output_creation(self):
        module = load('stream_test')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            output = Path(tmp) / 'never-created'
            with (
                patch('sys.argv', ['stream_test.py', '--profile', 'typical',
                                  '--rate', '0', '--output', str(output)]),
                patch.object(module, 'run') as run,
                self.assertRaises(SystemExit) as rejected,
            ):
                module.main()
            self.assertEqual(rejected.exception.code, 2)
            run.assert_not_called()
            self.assertFalse(output.exists())

    def test_real_policy_literal_delivery_and_final_drain_suppression(self):
        from sc_log_reader.host_notifications import present_poll
        from sc_log_reader.notifications import NotificationPolicy
        module = load('stream_test')
        policy = module.TracedPolicy(NotificationPolicy(), lambda message: None)
        sink = module.host_double_sink()
        event = dict(environment='LIVE', generation='g', event_type='user_login',
                     data=dict(player_name='<unsafe>'), source_occurrences=['o'])
        asyncio.run(present_poll(policy, sink, [event], {}, {}, now=1))
        self.assertEqual(sink.stats['transport_successes'], 1)
        self.assertNotIn('<unsafe>', sink.manager.last_text)
        asyncio.run(present_poll(policy, sink, [event],
                                {'LIVE': {'pending_records': 1}},
                                {'LIVE': {'pending_records': 0}}, now=2))
        self.assertEqual(policy.stats['catchup'], 1)
        self.assertEqual(sink.stats['transport_successes'], 1)
        sink.manager.active_connections.clear()
        event['generation'] = 'g2'
        asyncio.run(present_poll(policy, sink, [event], {}, {}, now=10))
        self.assertEqual(policy.stats['delivery_failed'], 1)

    def test_flush_probe_does_not_mutate_delivery_iteration(self):
        from sc_log_reader.host_notifications import present_poll
        from sc_log_reader.notifications import NotificationPolicy
        module = load('stream_test')
        policy = module.TracedPolicy(NotificationPolicy(), None)
        sink = module.host_double_sink()
        events = [dict(environment='LIVE', generation='g', event_type=kind,
                       data={}, source_occurrences=[kind])
                  for kind in ('user_login', 'mission_accepted', 'mission_complete')]
        asyncio.run(present_poll(policy, sink, events, {}, {}, now=1))
        self.assertEqual(sink.stats['transport_successes'], 3)

    def test_corpus_restart_replays_clean_recognized_evidence_only(self):
        module = load('corpus_test')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            folder = Path(tmp)
            source = folder / 'Game.log'
            source.write_bytes(b'<2026-09-15T12:00:00Z> User Login Success Handle[Release]\n'
                               b'<2026-09-15T12:00:01Z> <SHUDEvent> Added notification "unterminated\n')
            stat = source.stat()
            output = folder / 'audit'
            (output / 'work').mkdir(parents=True)
            report = module.process_file(dict(path=str(source), output=str(output), index=0,
                relative_path='Game.log', environment='LIVE', size=stat.st_size, mtime_ns=stat.st_mtime_ns))
        self.assertEqual(report['invariant_failures'], [])
        self.assertEqual(report['exceptions'], [])
        self.assertEqual(report['restart_replayed_observations'], report['stored_observations'])
        self.assertEqual(report['stored_observations'], 1)
        self.assertTrue(report['support_diagnostics']['lifetime_reason_counts'])

    def test_short_notifications_and_committed_support_diagnostics(self):
        module = load('stream_test')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            result = module.run(Path(tmp) / 'run', rate=156, duration=.15,
                                profile='recovery', recovery_case='malformed',
                                notifications=True)
        self.assertEqual(result['notification_delivery']['status'], 'measured host double')
        self.assertIn('policy_stats', result['notification_delivery'])
        self.assertTrue(result['unknown_timeout']['lifetime_reason_counts'])


if __name__ == '__main__':
    unittest.main()

"""Scheduled local stream qualification. Source timestamps are not append times.

Raw timing and oracle rows are disk backed. Harness measurement and scheduling
use perf_counter; clock resolution is reported separately from 1 ms histogram
upper-bin precision through 10 s. No live host is launched.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import sqlite3
import threading
import time
from contextlib import ExitStack
from functools import cache
from pathlib import Path

from sc_log_reader.host_notifications import LiteralGuiSink, present_poll
from sc_log_reader.notifications import NotificationPolicy
from sc_log_reader.reader import Instructions, RecordAssembler, bundled_bytes
from sc_log_reader.service import Service, Tailer, ToolInterface

try:
    from tools.support_diagnostics import support_diagnostics
except ModuleNotFoundError:
    from support_diagnostics import support_diagnostics


class TracedPolicy:
    """Bounded probe: at most one policy flush (<=100 messages) is retained."""
    def __init__(self, policy, trace):
        self.policy, self.trace = policy, trace
        self.messages = []

    def __getattr__(self, name):
        return getattr(self.policy, name)

    def flush(self, *, now):
        output = self.policy.flush(now=now)
        self.messages = list(output)
        return output


def clock_metadata():
    def describe(name):
        info = time.get_clock_info(name)
        return dict(name=name, implementation=info.implementation,
                    resolution_seconds=info.resolution, monotonic=info.monotonic,
                    adjustable=info.adjustable)
    return dict(measurement=describe('perf_counter'),
                measurement_scope='all harness writer/scheduling/commit/visibility/delivery/heartbeat durations and injected presentation now; seconds share one clock',
                production_deadline_clock=describe('monotonic'),
                production_scope='Reader/Tailer retain production monotonic deadlines; nominal budgets are cooperative, not hard realtime guarantees')


async def committed_recovery_boundary(tailer, service, path, *, timeout, observe=None):
    """Writer must be paused. Preserve only source bytes committed before a cut."""
    size = path.stat().st_size
    started = time.perf_counter()
    polls = 0
    while True:
        before = {env: dict(health) for env, health in service.live_health.items()}
        events = await asyncio.to_thread(tailer.poll)
        polls += 1
        if observe is not None:
            await observe(events, before, service.live_health)
        offset = (service.stream('LIVE') or {}).get('offset', 0)
        if offset == size and not tailer.has_backlog():
            return dict(source_bytes=size, committed_offset=offset, polls=polls,
                        drain_seconds=time.perf_counter() - started,
                        scope='paused writer; complete source prefix committed before truncate/replace; unread deleted source is not recoverable')
        if time.perf_counter() - started >= timeout:
            raise TimeoutError('pre-cut recovery boundary did not commit; source preserved')
        await asyncio.sleep(.001)


def host_double_sink():
    class Manager:
        def __init__(self):
            self.active_connections = ['host-double']
            self.last_text = ''

        async def send_to(self, command, connection):
            self.last_text = command.text

    class Command:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    return LiteralGuiSink(Manager(), Command, 'INFO')


class Histogram:
    def __init__(self):
        self.bins = [0] * 10002
        self.count = 0
        self.maximum = 0

    def add(self, seconds):
        self.bins[min(10001, max(0, math.ceil(seconds * 1000)))] += 1
        self.count += 1
        self.maximum = max(self.maximum, seconds)

    def result(self):
        def percentile(q):
            if not self.count:
                return None
            target = math.ceil(self.count * q)
            total = 0
            for i, count in enumerate(self.bins):
                total += count
                if total >= target:
                    return i / 1000 if i < 10001 else float('inf')
        return dict(count=self.count, p95_seconds=percentile(.95),
                    p99_seconds=percentile(.99), max_seconds=self.maximum,
                    precision='histogram binning only: 1 ms upper-bin bound; >10 s overflow is infinite',
                    histogram_bin_seconds=.001)


class Oracle:
    """Expected byte positions and semantic outcomes are declared by the writer.

Observation time is AFTER durable events become visible, never a Tailer count.
"""
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.RLock()
        self.db.executescript('''
            CREATE TABLE expected(offset INTEGER PRIMARY KEY,kind TEXT,offered REAL,amount REAL);
            CREATE TABLE seen(offset INTEGER,kind TEXT,visible REAL,amount REAL);
            CREATE INDEX seen_offset ON seen(offset);
        ''')

    def offer(self, offset, kind, offered, amount=None):
        with self.lock, self.db:
            self.db.execute('INSERT INTO expected VALUES(?,?,?,?)', (offset, kind, offered, amount))

    def observe(self, offset, kind, visible, amount=None):
        with self.lock, self.db:
            # Archive events are not declared sentinels and have no oracle claim.
            if self.db.execute('SELECT 1 FROM expected WHERE offset=?', (offset,)).fetchone():
                self.db.execute('INSERT INTO seen VALUES(?,?,?,?)', (offset, kind, visible, amount))

    def result(self):
        histogram = Histogram()
        with self.lock:
            expected = self.db.execute('SELECT COUNT(*) FROM expected').fetchone()[0]
            missing = duplicates = wrong = 0
            order_errors = 0
            highest_offset = -1
            for (offset,) in self.db.execute('SELECT offset FROM seen GROUP BY offset ORDER BY MIN(rowid)'):
                order_errors += offset < highest_offset
                highest_offset = max(highest_offset, offset)
            for offset, kind, offered, amount in self.db.execute('SELECT * FROM expected ORDER BY offset'):
                count = self.db.execute('SELECT COUNT(*) FROM seen WHERE offset=?', (offset,)).fetchone()[0]
                row = self.db.execute('SELECT kind,visible,amount FROM seen WHERE offset=? ORDER BY rowid LIMIT 1', (offset,)).fetchone()
                missing += not row
                duplicates += max(0, count - 1)
                if row:
                    histogram.add(max(0, row[1] - offered))
                    wrong += row[0] != kind or row[2] != amount
            return dict(expected=expected, missing=missing, duplicates=duplicates,
                        wrong_outcomes=wrong, order_errors=order_errors, visibility=histogram.result())

    def close(self):
        self.db.close()


class TimedService(Service):
    """Instrument durable batch return without changing the runtime package."""
    def __init__(self, root, callback):
        super().__init__(root)
        self.commit_callback = callback

    def ingest_batch(self, *args, **kwargs):
        result = super().ingest_batch(*args, **kwargs)
        returned_at = time.perf_counter()
        if result.events:
            self.commit_callback(self, result.events, returned_at)
        return result


def verify_source(path, expected_size=None, expected_sha256=None):
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    value = digest.hexdigest()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('source changed during verification')
    if expected_size is not None and after.st_size != expected_size:
        raise ValueError('source size mismatch')
    if expected_sha256 is not None and value != expected_sha256:
        raise ValueError('source hash mismatch')
    return dict(path=str(path.resolve()), size=after.st_size, sha256=value,
                mtime_ns=after.st_mtime_ns, access='read only')


def sentinels(group):
    prefix = '<2026-09-15T12:00:00Z> '
    mid = f'stream-{group}'
    def hud(text):
        return f'<SHUDEvent> Added notification "{text}" [13] to queue. MissionId: [{mid}]'
    inputs = [
        ('User Login Success Handle[StreamHarness]', 'user_login', None),
        (hud('Contract Accepted: Delivery:'), 'mission_accepted', None),
        (hud('New Objective: Pick up package:'), 'mission_objective_new', None),
        (hud('Contract Complete: Delivery:'), 'mission_complete', None),
        (f'ShoppingProvider SendStandardItemBuyRequest playerId[p{group}] client_price[265] quantity[1] currencyType[UEC] itemName[Medpen]', None, None),
        (f'ShoppingProvider RmShopFlowResponse playerId[p{group}] result[Success]', 'shop_buy', -265.0),
    ]
    return [((prefix + text + '\n').encode(), kind, amount) for text, kind, amount in inputs]


def assembled_bytes(path):
    """Bounded assembly with raw bytes retained from an independent read handle."""
    assembler = RecordAssembler(Instructions.load(bundled_bytes()))
    remaining = Path(path).stat().st_size
    with Path(path).open('rb') as source, Path(path).open('rb') as raw:
        while remaining:
            block = source.read(min(65536, remaining))
            if not block:
                raise ValueError('source shortened during assembly')
            remaining -= len(block)
            for record in assembler.feed(block):
                raw.seek(record.start)
                yield record.text, raw.read(record.end - record.start)
        for record in assembler.finish():
            raw.seek(record.start)
            yield record.text, raw.read(record.end - record.start)


def extract_group(source, output, second, expected_entries=None):
    count = size = 0
    with Path(output).open('xb') as target:
        for text, data in assembled_bytes(source):
            # Match only the assembled entry header, not continuation content.
            if text.startswith('<' + second) and len(text) > len(second) + 1 and text[len(second) + 1] in '.Z+>':
                target.write(data)
                count += 1
                size += len(data)
    if expected_entries is not None and count != expected_entries:
        raise ValueError(f'assembled group count mismatch: expected {expected_entries}, got {count}')
    return dict(utc_second=second, assembled_entries=count, bytes=size,
                output=str(Path(output).resolve()), original_append_schedule='unknown')


@cache
def _windows_rss_api():
    """One retained native type/API binding, not a new pointer-cache key per poll."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
            'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
            'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage')]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    return ctypes, Counters, kernel, psapi


def rss_bytes():
    """Process working set, including harness overhead, via native Windows API."""
    if os.name == 'nt':
        ctypes, counter_type, kernel, psapi = _windows_rss_api()
        counters = counter_type()
        counters.cb = ctypes.sizeof(counters)
        if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize
        return None
    try:
        return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')
    except (OSError, ValueError):
        return None


def run(output, *, profile='typical', rate=6, duration=300, source_log=None,
        expected_size=None, expected_sha256=None, drain_timeout=30,
        source_second=None, group_entry_count=None, recovery_case='restart',
        notification_policy=None, notification_sink=None, notifications=False):
    if not math.isfinite(rate) or not math.isfinite(duration) or rate <= 0 or duration <= 0:
        raise ValueError('rate and duration must be finite positive numbers')
    if not math.isfinite(drain_timeout) or drain_timeout <= 0:
        raise ValueError('drain-timeout must be finite positive seconds')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    source_metadata = verify_source(source_log, expected_size, expected_sha256) if source_log else None
    source_group = None
    replay_path = source_log
    if source_second:
        if source_log is None:
            raise ValueError('source-second requires source-log')
        replay_path = output / 'private-timestamp-group.log'
        source_group = extract_group(source_log, replay_path, source_second, group_entry_count)
    path = output / 'Game.log'
    path.touch()
    oracle = Oracle(output / 'oracle.sqlite3')
    commit_log = (output / 'commits.jsonl').open('w', encoding='utf-8')
    heartbeat_log = (output / 'heartbeat.jsonl').open('w', encoding='utf-8')
    commit_histogram = Histogram()
    generation_epochs = {}
    def committed(instance, events, returned_at):
        for event in events:
            occurrences = event.get('source_occurrences', [])
            with oracle.lock:
                for occurrence in occurrences:
                    row = instance.db.execute('SELECT byte_start,generation FROM observations WHERE occurrence=?', (occurrence,)).fetchone()
                    if row:
                        offered = oracle.db.execute('SELECT offered FROM expected WHERE offset=?',
                            (generation_epochs.get(row[1], -1) * 10**12 + row[0],)).fetchone()
                        if offered:
                            commit_histogram.add(max(0, returned_at - offered[0]))
            commit_log.write(json.dumps(dict(commit_return_monotonic=returned_at,
                event_type=event['event_type'], source_occurrences=occurrences)) + '\n')
    service = TimedService(output / 'runtime', committed)
    tailer = Tailer(service, {'LIVE': path})
    tailer.poll()  # Establish empty generation before appending any offered record.
    generation_epochs = {(service.stream('LIVE') or {})['generation']: 0}
    epoch = 0
    file_offset = 0
    baseline = rss_bytes()
    start = time.perf_counter()
    cpu_start = time.process_time()
    writer = dict(records=0, bytes=0, requested_rate=rate, max_batch_seconds=.05,
                  target_noise_records=None if source_log else math.ceil(duration * rate),
                  scheduled_duration_seconds=duration, errors=[], sentinel_suites={})
    done = threading.Event()
    stop = threading.Event()
    pause_request = threading.Event()
    paused = threading.Event()
    resume = threading.Event()
    resume.set()
    histograms = {name: Histogram() for name in ('poll', 'tool', 'heartbeat')}
    metrics = (output / 'metrics.jsonl').open('w', encoding='utf-8')
    offered_log = (output / 'append.jsonl').open('w', encoding='utf-8')
    delivery_log = (output / 'delivery.jsonl').open('w', encoding='utf-8')
    delivery_histogram = Histogram()
    delivery_count = 0
    delivery_untraceable = 0
    if notifications:
        notification_policy = NotificationPolicy()
        notification_sink = host_double_sink()
    traced_policy = TracedPolicy(notification_policy, None) if notification_policy is not None else None

    class DeliveryProbe:
        async def send(self, text):
            nonlocal delivery_count, delivery_untraceable
            message = traced_policy.messages.pop(0)
            if hasattr(notification_sink, 'send'):
                successes = await notification_sink.send(text)
            else:
                await asyncio.to_thread(notification_sink, message)
                successes = 1
            if not successes:
                return 0
            delivered_at = time.perf_counter()
            occurrences = message.get('source_occurrences', [])
            traced = 0
            for occurrence in occurrences:
                row = service.db.execute('SELECT byte_start,generation FROM observations WHERE occurrence=?', (occurrence,)).fetchone()
                if row:
                    offered = oracle.db.execute('SELECT offered FROM expected WHERE offset=?',
                        (generation_epochs.get(row[1], -1) * 10**12 + row[0],)).fetchone()
                    if offered:
                        delivery_histogram.add(delivered_at - offered[0])
                        traced += 1
            delivery_count += 1
            delivery_untraceable += not traced
            delivery_log.write(json.dumps(dict(delivered_monotonic=delivered_at,
                source_occurrences=occurrences, traced_sentinel_occurrences=traced)) + '\n')
            return successes

    def append(stream, data, kind=None, amount=None, scheduled=None):
        nonlocal file_offset
        offset = epoch * 10**12 + file_offset
        # Observer cannot pass an appended sentinel before its offer exists.
        with oracle.lock:
            stream.write(data)
            stream.flush()
            actual = time.perf_counter()
            if kind:
                oracle.offer(offset, kind, actual, amount)
        writer['records'] += 1
        writer['bytes'] += len(data)
        file_offset += len(data)
        return actual

    def group(stream, number, input_records_before=0, input_bytes_before=0):
        if number in (0, 1, 2):
            writer['sentinel_suites'][str(number)] = dict(
                input_records_before=input_records_before, input_bytes_before=input_bytes_before,
                virtual_byte_start=epoch * 10**12 + file_offset)
        for data, kind, amount in sentinels(number):
            append(stream, data, kind, amount)

    def produce():
        try:
            with ExitStack() as files, path.open('ab') as stream:
                group(stream, 0)
                first = time.perf_counter()
                middle = False
                count = 0
                input_bytes = 0
                last_noise_append = first
                archive = files.enter_context(Path(replay_path).open('rb')) if source_log else None
                group_records = iter(assembled_bytes(replay_path)) if source_group else None
                remaining_archive_bytes = Path(replay_path).stat().st_size if archive else 0
                replay_size = remaining_archive_bytes
                try:
                    while not stop.is_set():
                        if pause_request.is_set():
                            stream.close()
                            paused.set()
                            if not resume.wait(5):
                                raise TimeoutError('recovery writer pause not released')
                            stream = path.open('ab')
                            pause_request.clear()
                            paused.clear()
                        elapsed = time.perf_counter() - first
                        if archive is None and count >= math.ceil(duration * rate):
                            break
                        due = min(math.ceil(duration * rate), int(elapsed * rate)) if archive is None else int(elapsed * rate)
                        batch = 0
                        data = b'pending'
                        pending_bytes = bytearray()
                        while count < due and batch < min(8192, max(1, math.ceil(rate * .05))) and len(pending_bytes) < 1024 * 1024:
                            if archive:
                                data = next(group_records, ('', b''))[1] if group_records else archive.readline(min(1024 * 1024, remaining_archive_bytes))
                                remaining_archive_bytes -= len(data)
                                if not data:
                                    break
                            else:
                                data = (f'<2026-09-15T12:00:00Z> [EngineTelemetry] sequence={count} '
                                        + 'ordinary noise payload ' * 8 + '\n').encode()
                            if archive and not middle and count > 0 and input_bytes + len(data) >= replay_size / 2:
                                # Flush preceding records before inserting the suite;
                                # the already-read next record stays after the suite.
                                # Byte progress is independent of replay duration and
                                # guarantees input on both sides when >=2 records exist.
                                if batch:
                                    last_noise_append = append(stream, pending_bytes)
                                    writer['records'] += batch - 1
                                    pending_bytes.clear()
                                    batch = 0
                                group(stream, 1, count, input_bytes)
                                middle = True
                            pending_bytes.extend(data)
                            count += 1
                            batch += 1
                            input_bytes += len(data)
                        if batch:
                            last_noise_append = append(stream, pending_bytes)
                            writer['records'] += batch - 1
                        if archive and not data:
                            break
                        if archive is None and not middle and elapsed >= duration / 2 and count < math.ceil(duration * rate):
                            group(stream, 1, count, input_bytes)
                            middle = True
                        offered_log.write(json.dumps(dict(scheduled=first + count / rate,
                            appended=time.perf_counter(), total_records=writer['records'], total_bytes=writer['bytes'])) + '\n')
                        time.sleep(.005)
                    if not middle:
                        group(stream, 1, count, input_bytes)
                    group(stream, 2, count, input_bytes)
                finally:
                    if archive:
                        archive.close()
                    stream.close()
                writer['noise_records'] = count
                writer['noise_bytes'] = input_bytes
                writer['elapsed_seconds'] = last_noise_append - first
                writer['achieved_noise_rate'] = count / max(writer['elapsed_seconds'], .000001)
                writer['finished_monotonic'] = time.perf_counter()
        except Exception as exc:
            writer['errors'].append(f'{type(exc).__name__}: {exc}')
        finally:
            done.set()

    thread = threading.Thread(target=produce, name='scheduled-log-writer')
    thread.start()
    cursor = 0
    peak_rss = baseline
    restarted = False
    completed_at = None
    max_backlog = 0
    error_samples = set()
    fault_errors = []
    recovery_boundary = None
    async def monitor():
        nonlocal service, tailer, restarted, cursor, peak_rss, max_backlog, completed_at, epoch, file_offset, delivery_count, delivery_untraceable, recovery_boundary
        heartbeat_done = asyncio.Event()
        async def heartbeat():
            due = time.perf_counter() + .01
            while not heartbeat_done.is_set():
                await asyncio.sleep(max(0, due - time.perf_counter()))
                woke = time.perf_counter()
                delay = max(0, woke - due)
                histograms['heartbeat'].add(delay)
                heartbeat_log.write(json.dumps(dict(due_monotonic=due, woke_monotonic=woke, delay_seconds=delay)) + '\n')
                due = time.perf_counter() + .01
        task = asyncio.create_task(heartbeat())
        try:
          while True:
            tick = time.perf_counter()
            if profile == 'recovery' and not restarted and tick - start >= duration / 2:
                resume.clear()
                pause_request.set()
                if not await asyncio.to_thread(paused.wait, 5):
                    raise TimeoutError('writer failed to pause for recovery')
                try:
                    if recovery_case == 'restart':
                        tailer.stop_requested.set()
                        await asyncio.to_thread(tailer.poll)
                        service.close()
                        service = TimedService(output / 'runtime', committed)
                        tailer = Tailer(service, {'LIVE': path})
                    elif recovery_case in ('truncate', 'replace'):
                        async def present_boundary(events, before, after):
                            if traced_policy is not None and notification_sink is not None:
                                await present_poll(traced_policy, DeliveryProbe(), events,
                                    before, after, now=time.perf_counter())
                        recovery_boundary = await committed_recovery_boundary(
                            tailer, service, path, timeout=drain_timeout, observe=present_boundary)
                        recovery_boundary['virtual_epoch'] = epoch
                        recovery_boundary['expected_outcomes_before_cut'] = oracle.db.execute(
                            'SELECT COUNT(*) FROM expected WHERE offset>=? AND offset<?',
                            (epoch * 10**12, epoch * 10**12 + recovery_boundary['source_bytes'])).fetchone()[0]
                        if recovery_case == 'truncate':
                            path.write_bytes(b'')
                        else:
                            replacement = output / 'replacement.log'
                            replacement.write_bytes(b'')
                            os.replace(replacement, path)
                        epoch += 1
                        file_offset = 0
                        await asyncio.to_thread(tailer.poll)
                        generation_epochs[(service.stream('LIVE') or {})['generation']] = epoch
                    elif recovery_case == 'malformed':
                        with path.open('ab') as injected:
                            append(injected, b'<2026-09-15T12:00:00Z> <SHUDEvent> Added notification "unterminated\n')
                            append(injected, b'<2026-09-15T12:00:01Z> malformed framing recovery boundary\n')
                    elif recovery_case == 'database':
                        # Force a real SQLite write failure with data awaiting commit.
                        with path.open('ab') as injected:
                            group(injected, 99)
                        service.db.execute('PRAGMA query_only=ON')
                        try:
                            await asyncio.to_thread(tailer.poll)
                            fault_errors.extend(tailer.errors.values())
                        finally:
                            service.db.execute('PRAGMA query_only=OFF')
                    elif recovery_case == 'disk':
                        unavailable = output / 'Game.log.unavailable'
                        os.replace(path, unavailable)
                        try:
                            await asyncio.to_thread(tailer.poll)
                            fault_errors.extend(tailer.errors.values())
                        finally:
                            os.replace(unavailable, path)
                    else:
                        raise ValueError('unknown recovery case')
                finally:
                    resume.set()
                restarted = True
            before = {env: dict(health) for env, health in service.live_health.items()}
            committed_events = await asyncio.to_thread(tailer.poll)
            poll_seconds = time.perf_counter() - tick
            histograms['poll'].add(poll_seconds)
            if notification_policy is not None and notification_sink is not None:
                await present_poll(traced_policy, DeliveryProbe(), committed_events,
                    before, service.live_health, now=time.perf_counter())
            visible = time.perf_counter()
            with service.lock:
                rows = service.db.execute('SELECT e.id,o.byte_start,e.event_type,e.amount,o.generation '
                    'FROM events e JOIN observations o ON o.occurrence=e.occurrence '
                    'WHERE e.id>? ORDER BY e.id LIMIT 128', (cursor,)).fetchall()
            for event_id, offset, kind, amount, generation in rows:
                oracle.observe(generation_epochs.get(generation, -1) * 10**12 + offset, kind, visible, amount)
                cursor = event_id
            tool_start = time.perf_counter()
            await asyncio.to_thread(ToolInterface(service).call, 'get_current_game_state', {'environment': 'LIVE'})
            tool_seconds = time.perf_counter() - tool_start
            histograms['tool'].add(tool_seconds)
            current_rss = rss_bytes()
            if current_rss is not None:
                peak_rss = max(peak_rss or 0, current_rss)
            health = service.live_health.get('LIVE', {})
            backlog = health.get('bytes_behind', path.stat().st_size)
            max_backlog = max(max_backlog, backlog)
            if len(error_samples) < 10:
                error_samples.update(list(tailer.errors.values())[:10 - len(error_samples)])
            metrics.write(json.dumps(dict(monotonic=time.perf_counter(), backlog_bytes=backlog,
                rss_bytes=current_rss, cpu_seconds=time.process_time() - cpu_start,
                poll_seconds=poll_seconds, tool_seconds=tool_seconds,
                db_bytes=sum(p.stat().st_size for p in (output / 'runtime').glob('events.sqlite3*')),
                committed_bytes=(service.stream('LIVE') or {}).get('offset', 0))) + '\n')
            if done.is_set():
                completed_at = completed_at or writer.get('finished_monotonic', time.perf_counter())
                if backlog == 0 and not rows:
                    break
                if time.perf_counter() - completed_at >= drain_timeout:
                    break
            await asyncio.sleep(.01)
          return backlog
        finally:
            heartbeat_done.set()
            await task
    try:
        backlog = asyncio.run(monitor())
        unknown_timeout = support_diagnostics(service)
        final_state = service.state('LIVE')
        ledger = service.ledger('LIVE')
        state_oracle = dict(player_name=final_state['player_name'] == 'StreamHarness',
            missions_completed=all(f'stream-{i}' not in final_state['active_missions'] for i in range(3)),
            confirmed_spending=ledger['spending_auec'] == -oracle.db.execute('SELECT COALESCE(SUM(amount),0) FROM expected').fetchone()[0] if not source_log else None,
            scope='three sentinel suites; archive cash totals not independently known')
        suites = writer['sentinel_suites']
        total_input = writer.get('noise_records', 0)
        total_bytes = writer.get('noise_bytes', 0)
        placement = dict(
            before=suites.get('0', {}).get('input_records_before') == 0,
            within=0 < suites.get('1', {}).get('input_records_before', 0) < total_input
                and 0 < suites.get('1', {}).get('input_bytes_before', 0) < total_bytes,
            after=suites.get('2', {}).get('input_records_before') == total_input,
            input_records=total_input, input_bytes=total_bytes, suites=suites,
            method='verified source byte progress with next-record lookahead' if source_log else 'scheduled duration midpoint')
        placement['met'] = all(placement[name] for name in ('before', 'within', 'after'))
        placement['reason'] = 'verified input on both sides of middle suite' if placement['met'] else 'before/within/after coverage unmet; at least two input records are required'
        result = dict(profile=profile, scope='Real Tailer/Service in standalone process; no Wingman host',
            clocks=clock_metadata(),
            source=source_metadata, source_timestamps_are_append_schedule=False, writer=writer,
            source_group=source_group,
            oracle=oracle.result(), state_oracle=state_oracle,
            sentinel_placement=placement,
            metrics={name: h.result() for name, h in histograms.items()},
            memory=dict(warmed_baseline_bytes=baseline, peak_rss_bytes=peak_rss,
                transient_bytes=peak_rss - baseline if peak_rss is not None and baseline is not None else None,
                scope='whole process including bounded harness'),
            cpu_seconds=time.process_time() - cpu_start, max_backlog_bytes=max_backlog,
            final_backlog_bytes=backlog, drain_seconds=time.perf_counter() - (completed_at or time.perf_counter()),
            configured_drain_timeout_seconds=drain_timeout,
            runtime_errors=sorted(error_samples), health_counts=service.health_counts,
            unknown_timeout=unknown_timeout,
            commit_latency=commit_histogram.result(),
            commit_timing_scope='monotonic time immediately after durable Service.ingest_batch return; upper bound on actual SQLite commit time',
            heartbeat_scope='asyncio host double; poll/tool offloaded to threads',
            recovery=dict(case=recovery_case if profile == 'recovery' else None,
                executed=restarted, observed_errors=fault_errors,
                committed_pre_cut_boundary=recovery_boundary,
                injection_scope='temporary simulated log only; disk case is missing-file I/O, database case is SQLite query_only write rejection'),
            notification_delivery=dict(status='measured host double' if notification_policy is not None and notification_sink is not None else 'pending',
                reason='Connected sink callback completion is delivery; actual Wingman remains untested' if notification_policy is not None and notification_sink is not None else 'NotificationPolicy/host delivery not connected',
                messages=delivery_count, untraceable_messages=delivery_untraceable,
                policy_stats=getattr(notification_policy, 'stats', None),
                transport_stats=getattr(notification_sink, 'stats', None),
                append_to_delivery=delivery_histogram.result()),
            limitations=['heartbeat is asyncio host-double delay; actual Wingman qualification pending',
                'full archive replay counts physical lines (lines over 1 MiB are counted as fragments); timestamp-group replay counts assembled entries',
                'source replay events have no semantic oracle except injected sentinels',
                'visibility time is first durable event observation: upper bound on commit time, not exact commit callback',
                'writer rate excludes sentinel input records; physical input lines or explicitly extracted assembled group entries are counted'])
        threshold_satisfied = result['oracle']['missing'] == 0 and result['oracle']['visibility']['p95_seconds'] is not None and result['oracle']['visibility']['p95_seconds'] <= 1
        result['targets'] = dict(
            visibility_p95_pass=None if profile == 'burst' else threshold_satisfied,
            visibility_target_scope='ordinary load; burst gate uses exact outcomes and drain <=30 seconds',
            visibility_1s_threshold_satisfied=threshold_satisfied,
            tool_p95_pass=histograms['tool'].result()['p95_seconds'] is not None and histograms['tool'].result()['p95_seconds'] <= 1,
            heartbeat_host='pending',
            heartbeat_host_double_pass=(histograms['heartbeat'].result()['p99_seconds'] is not None and histograms['heartbeat'].result()['p99_seconds'] < .1),
            transient_rss_pass=None if baseline is None else peak_rss - baseline <= 128 * 1024 * 1024,
            drain_pass=backlog == 0 and result['drain_seconds'] <= 30,
            sustainable_4909='pending long qualification',
            writer_capacity_valid=not writer['errors'] and writer.get('achieved_noise_rate', 0) >= rate,
            writer_shortfall_fraction=max(0, 1 - writer.get('achieved_noise_rate', 0) / rate))
        if source_metadata:
            result['source_verified_after'] = verify_source(source_log, source_metadata['size'], source_metadata['sha256'])
        (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result
    finally:
        stop.set()
        resume.set()
        thread.join(5)
        service.close()
        oracle.close()
        metrics.close()
        offered_log.close()
        delivery_log.close()
        commit_log.close()
        heartbeat_log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=['typical', 'burst', 'sustained', 'recovery'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-log', type=Path)
    parser.add_argument('--source-size', type=int)
    parser.add_argument('--source-sha256')
    parser.add_argument('--source-second', help='UTC second without Z; extract exact assembled timestamp group')
    parser.add_argument('--group-entry-count', type=int)
    parser.add_argument('--recovery-case', choices=['restart', 'truncate', 'replace', 'malformed', 'database', 'disk'], default='restart')
    parser.add_argument('--rate', type=float)
    parser.add_argument('--duration', type=float)
    parser.add_argument('--drain-timeout', type=float, default=30)
    parser.add_argument('--notifications', action='store_true', help='production policy and literal GUI transport with bounded local host double')
    args = parser.parse_args()
    rate = args.rate if args.rate is not None else dict(typical=6, burst=111918, sustained=4909, recovery=4101)[args.profile]
    duration = args.duration if args.duration is not None else dict(typical=300, burst=1, sustained=1500, recovery=2)[args.profile]
    if not all(math.isfinite(value) and value > 0 for value in (rate, duration, args.drain_timeout)):
        parser.error('rate, duration and drain-timeout must be finite positive numbers')
    result = run(args.output, profile=args.profile, rate=rate, duration=duration,
        source_log=args.source_log, expected_size=args.source_size, expected_sha256=args.source_sha256,
        source_second=args.source_second, group_entry_count=args.group_entry_count, recovery_case=args.recovery_case,
        notifications=args.notifications, drain_timeout=args.drain_timeout)
    print(json.dumps(dict(output=str(args.output.resolve()), oracle=result['oracle'],
        state_oracle=result['state_oracle'], sentinel_placement=result.get('sentinel_placement'),
        targets=result['targets']), indent=2))
    return int(bool(result['oracle']['missing'] or result['oracle']['duplicates'] or
                    result['oracle']['wrong_outcomes'] or result['oracle']['order_errors'] or
                    result['writer']['errors'] or result['final_backlog_bytes'] or
                    any(value is False for value in result['state_oracle'].values()) or
                    result.get('sentinel_placement', {}).get('met') is False))


if __name__ == '__main__':
    raise SystemExit(main())

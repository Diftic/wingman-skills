"""Opt-in replay instrumentation. No production code or time budgets are changed.

Binary rows are little endian; metadata.json supplies schemas and ID dictionaries.
Hooks are process-local and must be installed before constructing readers.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from time import perf_counter_ns, thread_time_ns

from sc_log_reader import reader as module

PATTERN = struct.Struct("<QQQIIIBBBx")
ENTRY = struct.Struct("<QQQQIB3x")


class Pattern:
    def __init__(self, compiled, probe, identity):
        self.compiled, self.probe, self.identity = compiled, probe, identity

    def __getattr__(self, name):
        return getattr(self.compiled, name)

    def _call(self, operation, function, args, kwargs):
        p = self.probe
        if not p.enabled or not p.phase:
            return function(*args, **kwargs)
        status = 0
        start = perf_counter_ns()
        try:
            return function(*args, **kwargs)
        except TimeoutError:
            status = 1
            raise
        except Exception:
            status = 2
            raise
        finally:
            elapsed = perf_counter_ns() - start
            p.pattern(self.identity, operation, status, elapsed, kwargs)

    def search(self, *args, **kwargs):
        return self._call(1, self.compiled.search, args, kwargs)

    def sub(self, *args, **kwargs):
        return self._call(2, self.compiled.sub, args, kwargs)

    def finditer(self, *args, **kwargs):
        p = self.probe
        if not p.enabled or not p.phase:
            return self.compiled.finditer(*args, **kwargs)

        # finditer is lazy: time construction AND every next(), excluding caller
        # work between yields. Record a single operation, even when it times out.
        def measured():
            elapsed = 0
            status = 0
            try:
                start = perf_counter_ns()
                try:
                    iterator = self.compiled.finditer(*args, **kwargs)
                finally:
                    elapsed += perf_counter_ns() - start
                while True:
                    start = perf_counter_ns()
                    try:
                        match = next(iterator)
                    except StopIteration:
                        break
                    finally:
                        elapsed += perf_counter_ns() - start
                    yield match
            except TimeoutError:
                status = 1
                raise
            except Exception:
                status = 2
                raise
            finally:
                p.pattern(self.identity, 3, status, elapsed, kwargs)

        return measured()


class TimingProbe:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.pattern_file = (self.directory / "patterns.bin").open(
            "wb", buffering=1024 * 1024
        )
        self.entry_file = (self.directory / "entries.bin").open(
            "wb", buffering=1024 * 1024
        )
        self.pattern_buffer, self.entry_buffer = bytearray(), bytearray()
        self.registry, self.files = {}, {}
        self.enabled = True
        self.phase = 0
        self.file_id = self.start = self.end = 0
        self.pattern_count = self.entry_count = self.pattern_timeouts = 0
        self.closed = False
        self.old_compile = module._pattern
        self.old_parse = module.Reader.parse
        self.old_line = module.RecordAssembler._line

        def compile_pattern(value, flags=()):
            key = (value, tuple(sorted(set(flags))))
            identity = self.registry.setdefault(key, len(self.registry) + 1)
            return Pattern(self.old_compile(value, flags), self, identity)

        def parse(reader, *args, **kwargs):
            if not self.enabled:
                return self.old_parse(reader, *args, **kwargs)
            phase = self.phase
            self.phase = 1
            outcome = 3
            timeouts = self.pattern_timeouts
            cpu_start = thread_time_ns()
            wall_start = perf_counter_ns()
            try:
                result = self.old_parse(reader, *args, **kwargs)
                outcome = 0 if result is None else (2 if result.errors else 1)
                if result is not None and "regex_budget_exceeded" in result.errors:
                    outcome = 4 if self.pattern_timeouts > timeouts else 5
                return result
            finally:
                wall = perf_counter_ns() - wall_start
                cpu = thread_time_ns() - cpu_start
                self.entry_buffer.extend(
                    ENTRY.pack(self.start, self.end, wall, cpu, self.file_id, outcome)
                )
                self.entry_count += 1
                self.phase = phase
                self.flush_if_needed()

        def line(assembler, raw, start, end):
            previous = (self.phase, self.start, self.end)
            self.phase, self.start, self.end = 2, start, end
            try:
                return self.old_line(assembler, raw, start, end)
            finally:
                self.phase, self.start, self.end = previous
                self.flush_if_needed()

        module._pattern, module.Reader.parse, module.RecordAssembler._line = (
            compile_pattern,
            parse,
            line,
        )

    def set_file(self, identity, path):
        self.file_id = int(identity)
        self.files[self.file_id] = str(path)

    def set_record(self, start, end):
        self.start, self.end = start, end

    def pattern(self, identity, operation, status, elapsed, kwargs):
        self.pattern_buffer.extend(
            PATTERN.pack(
                elapsed,
                self.start,
                self.end,
                self.file_id,
                identity,
                round(kwargs.get("timeout", 0) * 1e9),
                self.phase,
                operation,
                status,
            )
        )
        self.pattern_count += 1
        self.pattern_timeouts += status == 1

    def flush_if_needed(self, force=False):
        # Disk writes happen after a parse/physical-line boundary, outside timers.
        for buffer, file in (
            (self.pattern_buffer, self.pattern_file),
            (self.entry_buffer, self.entry_file),
        ):
            if force or len(buffer) >= 1024 * 1024:
                file.write(buffer)
                buffer.clear()

    def close(self):
        if self.closed:
            return
        module._pattern, module.Reader.parse, module.RecordAssembler._line = (
            self.old_compile,
            self.old_parse,
            self.old_line,
        )
        self.flush_if_needed(force=True)
        self.pattern_file.close()
        self.entry_file.close()
        metadata = {
            "version": 1,
            "clock": "perf_counter_ns; entry CPU thread_time_ns",
            "pattern_struct": PATTERN.format,
            "pattern_row_bytes": PATTERN.size,
            "pattern_fields": [
                "duration_ns",
                "byte_start",
                "byte_end",
                "file_id",
                "pattern_id",
                "budget_ns",
                "phase",
                "operation",
                "status",
            ],
            "entry_struct": ENTRY.format,
            "entry_row_bytes": ENTRY.size,
            "entry_fields": [
                "byte_start",
                "byte_end",
                "wall_ns",
                "cpu_ns",
                "file_id",
                "outcome",
            ],
            "phase": {1: "entry parsing", 2: "physical-line framing"},
            "operation": {1: "search", 2: "sub", 3: "finditer active iterator time"},
            "status": {0: "returned normally", 1: "TimeoutError", 2: "other exception"},
            "outcome": {
                0: "ignored",
                1: "recognized without diagnostics",
                2: "diagnostic",
                3: "exception",
                4: "regex timeout diagnostic",
                5: "whole-entry deadline diagnostic",
            },
            "pattern_count": self.pattern_count,
            "entry_count": self.entry_count,
            "pattern_timeouts": self.pattern_timeouts,
            "files": self.files,
            "patterns": {
                v: {"expression": k[0], "flags": k[1]} for k, v in self.registry.items()
            },
        }
        (self.directory / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8"
        )
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

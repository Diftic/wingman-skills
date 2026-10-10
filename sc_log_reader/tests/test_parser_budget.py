"""Deadline contracts exercised through real Reader paths with a controlled clock."""

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sc_log_reader import reader as module
from sc_log_reader.reader import Instructions, Reader, bundled_bytes
from sc_log_reader.service import Service, Tailer
from sc_log_reader.state import State


class Clock:
    def __init__(self):
        self.now = 1.0

    def __call__(self):
        return self.now


class RecordingPattern:
    """Retain real matching semantics, recording budgets and simulating elapsed work."""

    def __init__(self, compiled, clock, calls, advances):
        self.compiled = compiled
        self.clock, self.calls, self.advances = clock, calls, advances

    def _record(self, operation, kwargs):
        self.calls.append((self.compiled.pattern, operation, self.clock.now, kwargs))
        self.clock.now += self.advances.get((self.compiled.pattern, operation), 0)

    def search(self, *args, **kwargs):
        self._record("search", kwargs)
        return self.compiled.search(*args, **kwargs)

    def sub(self, *args, **kwargs):
        self._record("sub", kwargs)
        return self.compiled.sub(*args, **kwargs)

    def finditer(self, *args, **kwargs):
        self._record("finditer", kwargs)
        for match in self.compiled.finditer(*args, **kwargs):
            self._record("next", {})
            consumption = self.advances.get((self.compiled.pattern, "consume"), 0)
            yield (
                ConsumingMatch(match, self.clock, consumption) if consumption else match
            )
        if (self.compiled.pattern, "stop") in self.advances:
            self._record("stop", {})


class ConsumingMatch:
    """Advance elapsed time during bracket-field processing between next calls."""

    def __init__(self, match, clock, duration):
        self.match, self.clock, self.duration = match, clock, duration

    def __getitem__(self, index):
        clock, duration = self.clock, self.duration

        class SlowValue(str):
            def strip(self):
                clock.now += duration
                return super().strip()

        return SlowValue(self.match[index])


class ParserBudgetTests(unittest.TestCase):
    def make_reader(self, steps=(), *, event="user_login", version=3):
        data = json.loads(bundled_bytes())
        data["engine_version"] = version
        data["ignore_records"] = []
        data["framing"]["notification"] = "(notification)"
        data["framing"]["timestamp"] = "(timestamp)"
        data["rules"] = [
            {
                "id": "budget-rule",
                "event": event,
                "match": {"contains": "", "source": "record.text"},
                "read": list(steps),
                "required": [],
            }
        ]
        data["rules"][0]["match"]["contains"] = "entry"
        return Reader(Instructions.load(json.dumps(data).encode()))

    def run_controlled(self, reader, text, advances):
        clock, calls = Clock(), []
        real_compile = module._pattern

        def compile_pattern(pattern, flags=()):
            clock.now += advances.get((pattern, "compile"), 0)
            return RecordingPattern(
                real_compile(pattern, flags), clock, calls, advances
            )

        with (
            patch.object(module.time, "monotonic", clock),
            patch.object(module, "_pattern", compile_pattern),
        ):
            result = reader.parse(text)
        return result, calls

    def test_search_replacement_and_iterator_receive_remaining_allowance(self):
        steps = [
            {
                "op": "capture",
                "source": "record.text",
                "pattern": "(entry)",
                "groups": {"1": "player_name"},
            },
            {
                "op": "normalize",
                "field": "player_name",
                "steps": [{"regex_replace": {"pattern": "entry", "replacement": "A"}}],
            },
            {
                "op": "bracket_fields",
                "source": "record.text",
                "fields": {"extra": "Alias"},
            },
        ]
        result, calls = self.run_controlled(
            self.make_reader(steps),
            "entry Alias[x]",
            {
                ("(notification)", "compile"): 0.09,
            },
        )
        self.assertEqual(result.event_type, "user_login")
        self.assertEqual(result.fields, {"player_name": "A", "extra": "x"})
        operations = set()
        for pattern, operation, now, kwargs in calls:
            if operation == "next" or pattern == "(notification)":
                continue
            operations.add(operation)
            self.assertAlmostEqual(kwargs["timeout"], 0.010, places=9)
            self.assertLessEqual(kwargs["timeout"], 1.1 - now)
        self.assertEqual(operations, {"search", "sub", "finditer"})

    def test_brackets_are_scanned_once_and_equal_duplicates_are_preserved(self):
        reader = self.make_reader(
            [
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"player_name": ["Alias", "Other"]},
                }
            ]
        )
        result, calls = self.run_controlled(
            reader, "entry Alias[A] Alias[A] Other[A]", {}
        )
        self.assertFalse(result.errors)
        self.assertEqual(result.fields["player_name"], "A")
        alias_calls = [
            operation for pattern, operation, _, _ in calls if "Alias" in pattern
        ]
        self.assertEqual(alias_calls, ["finditer", "next", "next"])

    def test_iterator_stops_at_deadline_between_matches(self):
        pattern = r"(?<![\w])Alias\s*:?\s*\[([^\]]*)\]"
        reader = self.make_reader(
            [
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"player_name": "Alias"},
                }
            ]
        )
        result, calls = self.run_controlled(
            reader,
            "entry Alias[A] Alias[A] Alias[A]",
            {
                ("(notification)", "compile"): 0.09,
                (pattern, "next"): 0.006,
            },
        )
        self.assertEqual(result.event_type, "diagnostic")
        self.assertIn("regex_budget_exceeded", result.errors)
        self.assertEqual(sum(operation == "next" for _, operation, _, _ in calls), 2)

    def test_late_successful_final_search_cannot_produce_event(self):
        reader = self.make_reader([{"op": "constant", "fields": {"player_name": "A"}}])
        result, _ = self.run_controlled(
            reader, "entry timestamp", {("(timestamp)", "search"): 0.101}
        )
        self.assertEqual(result.event_type, "diagnostic")
        self.assertIn("regex_budget_exceeded", result.errors)
        self.assertEqual(result.fields.get("reason"), "entry_deadline")
        self.assertEqual(result.fields.get("stage"), "timestamp")
        self.assertEqual(result.fields.get("rule_id"), "budget-rule")

    def test_legacy_replacement_uses_remaining_allowance(self):
        reader = self.make_reader(
            [{"op": "constant", "fields": {"vehicle": "Ship_123"}}],
            event="fatal_collision",
            version=1,
        )
        result, calls = self.run_controlled(
            reader, "entry", {("(notification)", "compile"): 0.09}
        )
        self.assertEqual(result.fields["vehicle"], "Ship")
        replacements = [
            kwargs for _, operation, _, kwargs in calls if operation == "sub"
        ]
        self.assertEqual(len(replacements), 1)
        self.assertAlmostEqual(replacements[0]["timeout"], 0.010, places=9)

    def test_failed_money_entry_has_no_state_effect_and_next_valid_entry_works(self):
        reader = self.make_reader(
            [
                {
                    "op": "constant",
                    "fields": {
                        "amount": 500,
                        "currency": "aUEC",
                        "notification_id": "13",
                    },
                }
            ],
            event="reward_earned",
        )
        state = State(reader.instructions.data["lookups"])
        state.apply(module.Event("diagnostic"), "initialize", "generation")
        before = copy.deepcopy(state.public())
        event, _ = self.run_controlled(
            reader, "entry timestamp", {("(timestamp)", "search"): 0.101}
        )
        rows = state.apply(event, "bad", "generation")
        self.assertFalse(any(row.get("amount_auec") is not None for row in rows))
        self.assertEqual(state.public(), before)
        self.assertIn("bad", state.data["_seen"])
        # Recreate only the instrumented compiled cache; the Reader instance survives.
        reader._compiled.clear()
        event = reader.parse("entry")
        self.assertEqual(event.event_type, "reward_earned")
        self.assertFalse(event.errors)
        self.assertTrue(
            any(
                row.get("amount_auec") == 500
                for row in state.apply(event, "good", "generation")
            )
        )

    def test_late_search_and_replacement_fail_with_entry_time_remaining(self):
        cases = [
            ("(timestamp)", "search", "timestamp"),
            ("A", "sub", "normalize"),
        ]
        for pattern, operation, stage in cases:
            with self.subTest(operation=operation):
                reader = self.make_reader(
                    [
                        {"op": "constant", "fields": {"player_name": "A"}},
                        {
                            "op": "normalize",
                            "field": "player_name",
                            "steps": [
                                {"regex_replace": {"pattern": "A", "replacement": "B"}}
                            ],
                        },
                    ]
                )
                event, _ = self.run_controlled(
                    reader,
                    "entry timestamp",
                    {
                        (pattern, operation): 0.060,
                    },
                )
                self.assertEqual(event.event_type, "diagnostic")
                self.assertIn("regex_budget_exceeded", event.errors)
                self.assertEqual(event.fields["reason"], "operation_deadline")
                self.assertEqual(event.fields["stage"], stage)
                self.assertNotIn("player_name", event.fields)

    def test_iterator_retains_operation_deadline_across_matches(self):
        pattern = r"(?<![\w])Alias\s*:?\s*\[([^\]]*)\]"
        reader = self.make_reader(
            [
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"player_name": "Alias"},
                },
            ]
        )
        event, calls = self.run_controlled(
            reader,
            "entry Alias[A] Alias[A] Alias[A] Alias[A]",
            {(pattern, "next"): 0.020},
        )
        self.assertEqual(event.event_type, "diagnostic")
        self.assertEqual(event.fields["reason"], "operation_deadline")
        self.assertEqual(event.fields["stage"], "bracket_fields")
        self.assertEqual(sum(operation == "next" for _, operation, _, _ in calls), 3)

    def test_iterator_checks_operation_deadline_on_exhaustion(self):
        pattern = r"(?<![\w])Alias\s*:?\s*\[([^\]]*)\]"
        reader = self.make_reader(
            [
                {"op": "constant", "fields": {"player_name": "A"}},
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"extra": "Alias"},
                },
            ]
        )
        event, _ = self.run_controlled(reader, "entry", {(pattern, "stop"): 0.060})
        self.assertEqual(event.event_type, "diagnostic")
        self.assertEqual(event.fields["reason"], "operation_deadline")

    def test_iterator_checks_operation_deadline_before_resuming_after_consumer(self):
        pattern = r"(?<![\w])Alias\s*:?\s*\[([^\]]*)\]"
        reader = self.make_reader(
            [
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"player_name": "Alias"},
                },
            ]
        )
        # Two strips process one yielded value, consuming 60 ms outside the backend.
        event, calls = self.run_controlled(
            reader, "entry Alias[A] Alias[A]", {(pattern, "consume"): 0.030}
        )
        self.assertEqual(event.event_type, "diagnostic")
        self.assertEqual(event.fields["reason"], "operation_deadline")
        self.assertEqual(sum(operation == "next" for _, operation, _, _ in calls), 1)

    def test_conflicting_alias_values_remain_errors(self):
        reader = self.make_reader(
            [
                {
                    "op": "bracket_fields",
                    "source": "record.text",
                    "fields": {"player_name": ["Alias", "Other"]},
                }
            ]
        )
        result = reader.parse("entry Alias[A] Other[B]")
        self.assertIn("conflicting_aliases:player_name", result.errors)
        self.assertNotIn("player_name", result.fields)

    def test_literal_conditions_stop_when_deadline_expires(self):
        clock = Clock()

        class SlowText(str):
            calls = 0

            def __contains__(self, item):
                self.calls += 1
                clock.now += 0.06
                return super().__contains__(item)

        reader = self.make_reader()
        rule = reader.instructions.data["rules"][0]
        rule["match"] = {"all": [{"contains": "entry", "source": "record.text"}] * 8}
        text = SlowText("entry")
        with patch.object(module.time, "monotonic", clock):
            event = reader.parse(text)
        self.assertEqual(event.event_type, "diagnostic")
        self.assertIn("regex_budget_exceeded", event.errors)
        self.assertEqual(text.calls, 2)

    def test_final_return_rechecks_deadline_after_non_regex_work(self):
        clock = Clock()
        real_event = module.Event

        def delayed_event(*args, **kwargs):
            result = real_event(*args, **kwargs)
            if result.event_type == "user_login":
                clock.now += 0.101
            return result

        reader = self.make_reader([{"op": "constant", "fields": {"player_name": "A"}}])
        with (
            patch.object(module.time, "monotonic", clock),
            patch.object(module, "Event", delayed_event),
        ):
            event = reader.parse("entry")
        self.assertEqual(event.event_type, "diagnostic")
        self.assertEqual(event.fields["stage"], "return")

    def test_header_initial_and_incremental_scans_have_explicit_pattern_allowance(self):
        clock, calls = Clock(), []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "Game.log"
            path.write_text("header\n", encoding="utf-8")
            service = Service(root / "runtime")
            try:
                tailer = Tailer(service, {"LIVE": path})
                tailer.build_pattern = RecordingPattern(
                    module._pattern("(BUILD)"), clock, calls, {}
                )
                tailer.poll()
                with path.open("a", encoding="utf-8") as stream:
                    stream.write("more\n")
                tailer.poll()
            finally:
                service.close()
        self.assertEqual(len(calls), 2)
        for _, _, _, kwargs in calls:
            self.assertEqual(kwargs["timeout"], 0.050)


if __name__ == "__main__":
    unittest.main()

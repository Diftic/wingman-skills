"""Dispatch must reduce interpreter work without changing recipe semantics."""

import json
import unittest
from functools import wraps
from unittest.mock import patch

from sc_log_reader import reader as module
from sc_log_reader.reader import Instructions, Reader, bundled_bytes


def cases(names, rows):
    def decorate(test):
        @wraps(test)
        def run():
            for row in rows:
                test(*(row if "," in names else (row,)))

        return run

    return decorate


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(
        unittest.FunctionTestCase(test)
        for name, test in globals().items()
        if name.startswith("test_")
    )


def literal(text, source="record.text"):
    return {"contains": text, "source": source}


def expression(pattern):
    return {"regex": pattern, "source": "record.text"}


def rule(condition, name="fixture", required=()):
    return {
        "id": name,
        "event": "session_start",
        "match": condition,
        "read": [],
        "required": list(required),
    }


def package(*rules):
    data = json.loads(bundled_bytes())
    data["rules"] = list(rules)
    data["ignore_records"] = []
    return Instructions.load(json.dumps(data).encode())


def test_irrelevant_record_avoids_per_rule_interpreter_work():
    reader = Reader(package(*(rule(literal("required"), str(i)) for i in range(64))))
    checks = 0
    original = module._ParseBudget.check

    def count(budget):
        nonlocal checks
        checks += 1
        return original(budget)

    with patch.object(module._ParseBudget, "check", count):
        assert reader.parse("unrelated engine status") is None
    assert reader.last_disposition == "unknown"
    # This measures eliminated work, not hardware-sensitive elapsed time.
    assert checks < 20


@cases(
    "condition,text,matched",
    [
        ({"all": [literal("alpha"), literal("beta")]}, "alpha beta", True),
        ({"all": [literal("alpha"), literal("beta")]}, "alpha", False),
        ({"any": [literal("alpha"), literal("beta")]}, "beta", True),
        ({"any": [literal("alpha"), literal("beta")]}, "neither", False),
        (
            {
                "any": [
                    {"all": [literal("shared"), literal("alpha")]},
                    {"all": [literal("shared"), literal("beta")]},
                ]
            },
            "shared beta",
            True,
        ),
        (
            {
                "any": [
                    {"all": [literal("shared"), literal("alpha")]},
                    {"all": [literal("shared"), literal("beta")]},
                ]
            },
            "beta",
            False,
        ),
        ({"not": literal("alpha")}, "beta", True),
        ({"not": literal("alpha")}, "alpha", False),
        ({"all": [{"not": literal("alpha")}, literal("beta")]}, "beta", True),
        (expression("(?i)alpha"), "ALPHA", True),
        (literal("alpha"), "ALPHA", False),
        (literal("alpha", "fields.missing"), "alpha", False),
        (
            literal("alpha", "notification.text"),
            'Added notification "alpha" [1] to queue.',
            True,
        ),
    ],
)
def test_conditions_keep_expected_truth_values(condition, text, matched):
    event = Reader(package(rule(condition))).parse(text)
    if matched:
        assert event.event_type == "session_start"
        assert event.errors == []
    else:
        assert event is None


def test_two_simultaneous_matches_remain_ambiguous_across_dispatch_groups():
    reader = Reader(
        package(rule(literal("alpha")), rule(expression("beta"), "fallback"))
    )
    assert reader.parse("alpha beta").errors == ["ambiguous_rules"]


def test_incomplete_and_required_field_diagnostics_survive_dispatch():
    reader = Reader(package(rule(literal("alpha"), required=["mission_id"])))
    assert reader.parse("noise", complete=False).errors == ["incomplete_record"]
    assert reader.parse("alpha").errors == ["missing:mission_id"]


@cases(
    "condition",
    [
        {"all": [expression("expensive"), literal("absent")]},
        {
            "any": [
                {"all": [expression("expensive"), literal("absent")]},
                literal("absent"),
            ]
        },
        {"all": [{"not": expression("expensive")}, literal("absent")]},
    ],
)
def test_missing_later_literal_cannot_suppress_earlier_regex_diagnostic(condition):
    reader = Reader(package(rule(condition)))
    original = reader._compiled_pattern

    class TimedOutPattern:
        def search(self, *args, **kwargs):
            raise TimeoutError

    def compiled(pattern, flags=()):
        return TimedOutPattern() if pattern == "expensive" else original(pattern, flags)

    with patch.object(reader, "_compiled_pattern", compiled):
        event = reader.parse("irrelevant")
    assert event.errors == ["regex_budget_exceeded"]
    assert event.fields == {
        "reason": "regex_timeout",
        "stage": "match",
        "rule_id": "fixture",
    }


def test_new_valid_package_makes_previously_unrecognized_noise_meaningful():
    noise = "Warning FutureTelemetry sensor online"
    previous = Reader(package(rule(literal("old record"))))
    assert previous.parse(noise) is None
    assert previous.last_disposition == "unknown"
    # Startup selects a separately validated replacement, rebuilding dispatch.
    updated = Reader(package(rule(literal("FutureTelemetry"), "new-recipe")))
    event = updated.parse(noise)
    assert event.event_type == "session_start"
    assert event.rule_id == "new-recipe"
    assert event.errors == []


def test_ignore_recipe_remains_authoritative_before_dispatch():
    data = json.loads(package(rule(literal("marker"))).raw)
    data["ignore_records"] = [literal("marker")]
    reader = Reader(Instructions.load(json.dumps(data).encode()))
    assert reader.parse("marker") is None
    assert reader.last_disposition == "ignored"


def test_oversized_text_is_rejected_before_allocating_utf8_copy():
    class OversizedText(str):
        def encode(self, *args, **kwargs):
            raise AssertionError("oversized input must not be copied")

    reader = Reader(package(rule(literal("marker"))))
    event = reader.parse(OversizedText("x" * (module.MAX_RECORD_BYTES + 1)))
    assert event.event_type == "diagnostic"
    assert event.errors == ["record_too_large"]


def test_utf8_byte_limit_still_rejects_multibyte_text_and_accepts_boundary():
    reader = Reader(package(rule(literal("é"))))
    assert (
        reader.parse("é" * (module.MAX_RECORD_BYTES // 2)).event_type == "session_start"
    )
    assert reader.parse("é" * (module.MAX_RECORD_BYTES // 2 + 1)).errors == [
        "record_too_large"
    ]

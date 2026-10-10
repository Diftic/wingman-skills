"""The runtime capture path must go through the stack-aware entry point.

WHY THIS FILE EXISTS. `overlay_fields` offers two whole-frame readers whose
names used to be equally inviting:

  * `capture_payload(rows)`   dispatches to BOTH parsers, so a Pyro body
                              surface produces a schema-1 stack. THE RUNTIME
                              PATH.
  * `read_legacy_payload(...)` routes through `payload_from_rows` alone, so the
                              same capture is refused and no stack exists.

Nothing raises when the wrong one is called. The skill simply stops being able
to mark a planet surface, which is the primary use case, and every existing
test still passes because each parser is individually correct. These tests pin
the WIRING rather than either parser's behaviour.

Credit: Mallachi
"""

from __future__ import annotations

import re
from pathlib import Path

import overlay_fields as fields


SKILL_DIR = Path(__file__).resolve().parent.parent

# Every module that runs inside Wingman. Dev tools under `ocr_dev/` and the
# tests themselves are deliberately excluded: a benchmark or a join test may
# call the legacy reader on purpose, and `release_version/` is a generated
# artifact that is regenerated rather than edited.
RUNTIME_MODULES = (
    "main.py",
    "scanner.py",
    "overlay_fields.py",
    "overlay_reader.py",
    "navigation.py",
    "coordinate_stack.py",
    "database.py",
    "learned_fields.py",
    "specialist_reader.py",
)


def _source(name: str) -> str:
    return (SKILL_DIR / name).read_text(encoding="utf-8")


def test_the_runtime_capture_path_calls_capture_payload() -> None:
    """`main.py` decodes through the dispatcher, not through either parser."""
    main_src = _source("main.py")
    assert 'getattr(reader, "capture_payload", overlay_fields.capture_payload)(rows)' in main_src
    # The legacy parser must not be called directly from the capture path. It
    # is still NAMED in main.py's comments, which is why this looks for a call.
    assert "overlay_fields.payload_from_rows(" not in main_src


def test_no_runtime_module_calls_the_legacy_whole_frame_reader() -> None:
    """`read_legacy_payload` is a test and diagnostic helper, never runtime.

    A runtime caller would lose schema-1 support silently, so this fails on the
    call rather than waiting for a field report that a planet cannot be marked.
    """
    # The lookbehind excludes the DEFINITION site, which lives in
    # `overlay_fields.py` and is not a call. That module stays in the list on
    # purpose, so an internal call from elsewhere in it is still caught.
    call = re.compile(r"(?<!def )\bread_legacy_payload\s*\(")
    offenders = [name for name in RUNTIME_MODULES if call.search(_source(name))]
    assert offenders == [], (
        f"{offenders} call read_legacy_payload, which cannot produce a "
        "coordinate stack. Use overlay_fields.capture_payload."
    )


def test_the_legacy_reader_keeps_its_explicit_name() -> None:
    """The bare name must not come back; the limitation lives in the name.

    A future `read_payload` alias would restore exactly the ambiguity this
    file was written to remove, so the absence is asserted, not just the
    presence of the explicit one.
    """
    assert hasattr(fields, "read_legacy_payload")
    assert not hasattr(fields, "read_payload")


def test_both_entry_points_still_exist_and_are_distinct() -> None:
    """Neither was quietly deleted, and they are not aliases of each other."""
    assert callable(fields.capture_payload)
    assert callable(fields.read_legacy_payload)
    assert fields.capture_payload is not fields.read_legacy_payload

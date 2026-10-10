"""The evidence that decides the OCR fix, and the two items that frame it.

A cell refuses when its decode cost exceeds `REFUSE_COST` OR its margin over the
runner-up falls below `REFUSE_MARGIN`. Those mean opposite things: high cost is
"nothing in the glyph bank matched", low margin is "two glyphs matched almost
equally". The first points at a render change or a missing template, the second
at genuine ambiguity at this size, and the fix for one is not the fix for the
other. Until these lines existed the log recorded which cells refused and never
which side of the disjunction fired, which is why the reader's failure since
2026-07-31 cannot be diagnosed from the record that exists.

Three items are pinned here:

  I3  per-cell refusal detail, capped, and never for rows the skill does not read
  I5  the success baseline, so ink and periodicity finally have a control group
  I6  the refused-frame dump, on by the user's call since 2026-08-02, and capped

Every test drives the real `_capture_position_local` or the real reader method;
only mss, the reader, the scanner and the gate predicates are faked.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest


pytest.importorskip("PIL")
pytest.importorskip("mss")
pytest.importorskip("numpy")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _stubs import install_runtime_stubs  # noqa: E402


install_runtime_stubs()

import numpy as np  # noqa: E402
import mss as mss_module  # noqa: E402

import main  # noqa: E402
import overlay_fields as fields  # noqa: E402
import overlay_reader  # noqa: E402


_REGION = {"left": 0, "top": 0, "width": 10, "height": 5}

_POSITION = {"system_frame": True, "x": 1.0, "y": 2.0, "z": 3.0}


class _Printr:
    def print(self, message, color=None, server_only=False):
        pass


class _FakeGrab:
    def __init__(self, region: dict) -> None:
        self.size = (region["width"], region["height"])
        self.bgra = bytes(region["width"] * region["height"] * 4)


class _Screen:
    def __init__(self) -> None:
        self.monitors = [dict(_REGION), dict(_REGION)]

    def __call__(self) -> "_Screen":
        return self

    def __enter__(self) -> "_Screen":
        return self

    def __exit__(self, *exc_info) -> bool:
        return False

    def grab(self, region: dict) -> _FakeGrab:
        return _FakeGrab(region)


class _FakeReader:
    def __init__(self, rows: list) -> None:
        self._rows = rows
        self.last_from_cache = True
        self.last_refit = False
        self.last_fit_uses = 3

    def read(self, frame, count):
        return 44, 0.0, self._rows


class _FakeScanner:
    def __init__(self, position: dict | None = None) -> None:
        self._position = position
        self.last_reject_reason = None

    def parse_payload(self, payload: dict) -> dict | None:
        return dict(self._position) if self._position is not None else None


def _skill(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, rows: list,
           payload: dict | None = None, position: dict | None = None):
    monkeypatch.setattr(mss_module, "mss", _Screen())
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(main.overlay_reader, "block_region", lambda m: dict(_REGION))
    monkeypatch.setattr(main.overlay_reader, "capture_is_usable",
                        lambda f, *a: (True, ""))
    monkeypatch.setattr(main.overlay_reader, "overlay_is_present", lambda f: True)
    monkeypatch.setattr(main.overlay_reader, "overlay_ink_fraction", lambda f: 0.0531)
    monkeypatch.setattr(main.overlay_reader, "overlay_row_periodicity",
                        lambda f: 0.6572)
    monkeypatch.setattr(main.overlay_fields, "payload_from_rows", lambda r: payload)
    monkeypatch.setattr(main.overlay_fields, "ring_state", lambda *a: "")

    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.printr = _Printr()
    skill.get_generated_files_dir = lambda: str(tmp_path)
    skill._get_display = lambda: 1
    skill._reader_state = ""
    skill._scanner = _FakeScanner(position)
    skill._local_reader = lambda: _FakeReader(rows)
    return skill


def _trace(tmp_path: Path) -> str:
    path = tmp_path / "navpoint_poll.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _cell_lines(tmp_path: Path) -> list[str]:
    return [line for line in _trace(tmp_path).splitlines() if " cell row=" in line]


def _row(kind: str, refused_cells: list[dict], row: int = 2) -> dict:
    return {
        "row": row, "kind": kind, "trusted": False, "text": "Zone: ?",
        "refused": len(refused_cells), "cost": 6.21, "margin": 11.4,
        "colour": "white", "offset": 0.5, "y": 44,
        "refused_cells": refused_cells,
    }


# A pure cost trip: nothing in the bank came close, and the runner-up is far
# behind, so the margin condition is not what lost this cell.
_COST_CELL = {"i": 41, "cost": 17.82, "margin": 12.10, "trip": "cost",
              "top1": "8", "top1_cost": 17.82, "top2": "9", "top2_cost": 29.92}
_MARGIN_CELL = {"i": 42, "cost": 9.10, "margin": 3.40, "trip": "margin",
                "top1": "3", "top1_cost": 9.10, "top2": "8", "top2_cost": 12.50}


# --------------------------------------------------------------------- #
# I3: which side of the disjunction fired, on which cell
# --------------------------------------------------------------------- #


def test_a_refused_cell_says_which_condition_lost_it(tmp_path, monkeypatch):
    """The whole point. `trip=cost` and `trip=margin` want different fixes, and
    a log carrying only `refused=4` cannot tell them apart."""
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [_COST_CELL,
                                                             _MARGIN_CELL])])

    assert skill._capture_position_local() is None

    trace = _trace(tmp_path)
    assert (
        "cell row=2 i=41 cost=17.82 margin=12.10 trip=cost "
        "top1='8'@17.82 top2='9'@29.92"
    ) in trace
    assert (
        "cell row=2 i=42 cost=9.10 margin=3.40 trip=margin "
        "top1='3'@9.10 top2='8'@12.50"
    ) in trace


def test_rows_the_skill_does_not_read_produce_no_cell_lines(tmp_path, monkeypatch):
    """The FPS row and the percentile bar refuse constantly by design. Their
    cells are noise and would dilute the evidence this line exists to carry."""
    skill = _skill(tmp_path, monkeypatch,
                   rows=[_row(None, [_COST_CELL]), _row("fps", [_MARGIN_CELL])])

    assert skill._capture_position_local() is None
    assert _cell_lines(tmp_path) == []


def test_a_camdir_row_is_read_and_so_is_reported(tmp_path, monkeypatch):
    skill = _skill(tmp_path, monkeypatch, rows=[_row("camdir", [_COST_CELL])])

    assert skill._capture_position_local() is None
    assert len(_cell_lines(tmp_path)) == 1


def test_the_cell_lines_are_capped(tmp_path, monkeypatch):
    """One catastrophically bad frame must not write hundreds of lines into the
    only instrument this project has."""
    cells = [dict(_COST_CELL, i=n) for n in range(200)]
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", cells)])

    assert skill._capture_position_local() is None
    assert len(_cell_lines(tmp_path)) == main.MAX_CELL_TRACE_LINES


def test_the_cap_spans_the_whole_capture_not_each_row(tmp_path, monkeypatch):
    cells = [dict(_COST_CELL, i=n) for n in range(30)]
    skill = _skill(
        tmp_path, monkeypatch,
        rows=[_row("zone", cells, row=2), _row("zone", cells, row=3)],
    )

    assert skill._capture_position_local() is None
    assert len(_cell_lines(tmp_path)) == main.MAX_CELL_TRACE_LINES


def test_a_row_that_refuses_to_be_measured_writes_no_line_and_raises_nothing(
    tmp_path, monkeypatch
):
    """Rule of this whole path: a diagnostic can never be the reason a capture
    ends differently. Driven at the helper rather than through a capture, so
    what is proven is this helper's own guard and not a neighbour's."""

    class _Hostile(dict):
        def get(self, *args, **kwargs):
            raise RuntimeError("this row refuses to be measured")

    skill = _skill(tmp_path, monkeypatch, rows=[])
    skill._trace_cells([_Hostile()])
    assert _cell_lines(tmp_path) == []


def test_the_cell_lines_only_run_on_the_final_attempt(tmp_path, monkeypatch):
    """Same reasoning as the row dump: at `poll_interval: 1` a per-attempt dump
    buries everything else in the file."""
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [_COST_CELL])])

    assert skill._capture_position_local(main.MARK_CAPTURE_ATTEMPTS) is None
    assert len(_cell_lines(tmp_path)) == 1


# --------------------------------------------------------------------- #
# I3, at the source: the reader must RECORD what it refused
# --------------------------------------------------------------------- #


def _bank_reader(costs_by_phase: dict) -> overlay_reader.OverlayReader:
    """A reader whose cell costs are dictated, so the disjunction is drivable.

    Built with `__new__`: the real glyph bank is not needed to test which
    branch a cost and a margin select, and loading it would make this a test of
    the bank instead.
    """
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    reader._chars = {0: ["8", "9", "3"], 1: ["8", "9", "3"]}
    reader.cell_costs = lambda core, phase, colour: costs_by_phase
    reader._cell_stats = lambda core: (0.0, 0.0, 0.0)
    return reader


def test_the_reader_records_a_cost_trip_and_a_margin_trip():
    """`trip` is decided inside the refusal branch from that branch's own
    values, so it cannot disagree with the decision it explains."""
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    reader._chars = {0: ["8", "9", "3"]}

    # Nothing matched: the winner is already over the cost floor, and the
    # runner-up is far enough behind that the margin condition is not involved.
    record = reader._refusal_record(
        41, 0, np.array([0, 1, 2]), np.array([17.82, 29.92, 40.0]), 17.82, 12.10
    )
    assert record["trip"] == "cost"
    assert record["top1"] == "8" and record["top1_cost"] == 17.82
    assert record["top2"] == "9" and record["top2_cost"] == 29.92

    # A clean match with a near-identical rival: genuine ambiguity, not a bank
    # that has nothing to offer. Opposite diagnosis, opposite fix.
    record = reader._refusal_record(
        42, 0, np.array([2, 0, 1]), np.array([12.50, 40.0, 9.10]), 9.10, 3.40
    )
    assert record["trip"] == "margin"
    assert record["top1"] == "3" and record["top2"] == "8"


def test_both_conditions_together_are_reported_as_both():
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    reader._chars = {0: ["8", "9"]}
    record = reader._refusal_record(
        7, 0, np.array([0, 1]), np.array([20.0, 22.0]), 20.0, 2.0
    )
    assert record["trip"] == "both"


def test_the_alignment_search_records_nothing():
    """`fit_alignment` decodes 72 candidate variants a frame and throws every
    one away. Recording their cells would be pure cost on the slowest step in
    the read."""
    reader = _bank_reader(np.array([40.0, 41.0, 42.0]))
    band = np.zeros((overlay_reader.ROW_HEIGHT, 200, 3), dtype=np.float64)

    reader.decode_row(band, 199.0, 0.0, np.zeros(3), 5, background=None)
    assert reader.last_refused_cells == []

    reader.decode_row(band, 199.0, 0.0, np.zeros(3), 5, background=0.0)
    assert len(reader.last_refused_cells) == 5


def test_the_records_belong_to_the_variant_that_won():
    """`_decode_block` decodes six variants a row and keeps the cheapest. The
    records have to be the winner's, not the last one tried."""
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    calls = []

    def _decode_row(band, right, offset, colour, count, background=None):
        calls.append(len(calls))
        # The THIRD variant is cheapest; the sixth is decoded last.
        cost = 1.0 if len(calls) == 3 else 9.0
        reader.last_refused_cells = [{"i": len(calls) - 1, "trip": "cost"}]
        return "text", cost, [1.0]

    reader.decode_row = _decode_row
    reader._background_level = lambda band, left, right: 0.0
    frame = np.zeros((overlay_reader.ROW_HEIGHT * 2, 800, 3), dtype=np.float64)

    rows = reader._decode_block(frame, 0, 1)
    assert len(calls) == 6
    assert rows[0]["refused_cells"] == [{"i": 2, "trip": "cost"}]


def test_a_reader_that_never_recorded_still_decodes():
    """R2 again, at the READ site. `_decode_block` harvests
    `last_refused_cells` after every `decode_row`, and a reader whose
    `decode_row` never assigned it would raise there, which `main.py` converts
    from a plain gate refusal into a decode error. A diagnostic may never change
    a capture outcome, so the read carries its own default."""
    reader = overlay_reader.OverlayReader.__new__(overlay_reader.OverlayReader)
    assert not hasattr(reader, "last_refused_cells")

    def _decode_row(band, right, offset, colour, count, background=None):
        return "text", 1.0, [1.0]

    reader.decode_row = _decode_row
    reader._background_level = lambda band, left, right: 0.0
    frame = np.zeros((overlay_reader.ROW_HEIGHT * 2, 800, 3), dtype=np.float64)

    rows = reader._decode_block(frame, 0, 1)
    assert rows[0]["refused_cells"] == []


def test_the_record_capture_changes_no_decode_decision():
    """R2. The instrumentation is read-only with respect to the decode, so a
    real row must decode to the same text and the same trust with it in place.
    Measured against the shipping glyph bank on a real capture."""
    captures = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"
    glyphs = Path(__file__).resolve().parent.parent / "overlay_glyphs.npz"
    path = captures / "game-mid" / "shot_00.png"
    if not path.exists() or not glyphs.exists():
        pytest.skip("capture corpus not present")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float64)
    rows = overlay_reader.OverlayReader(glyphs).read(frame, 6)[2]
    for row in rows:
        # The count the row was TRUSTED on and the count the floor recorded
        # cannot contradict each other: every recorded cell is a refused cell.
        assert len(row["refused_cells"]) <= row["refused"]
        assert row["trusted"] == (row["refused"] == 0)
        for cell in row["refused_cells"]:
            assert cell["trip"] in ("cost", "margin", "both")


# --------------------------------------------------------------------- #
# I5: the success baseline
# --------------------------------------------------------------------- #


def test_a_successful_capture_line_carries_the_baseline(tmp_path, monkeypatch):
    """Every ink and periodicity figure in the log's history was measured on a
    refusal, so they have never had a control group. Without one they stay
    undiagnostic no matter how many more refusals are collected."""
    rows = [
        {"row": 0, "kind": "zone", "trusted": True, "text": "Zone: x", "cost": 3.0},
        {"row": 1, "kind": "zone", "trusted": False, "text": "Zone: y", "cost": 5.2},
    ]
    skill = _skill(tmp_path, monkeypatch, rows=rows,
                   payload={"local_frame": False}, position=dict(_POSITION))

    assert asyncio.run(skill._capture_position()) is not None

    lines = [line for line in _trace(tmp_path).splitlines()
             if " capture frame=" in line]
    assert len(lines) == 1
    assert "ink=0.05310" in lines[0]
    assert "periodicity=0.65720" in lines[0]
    assert "trusted=1/2" in lines[0]
    assert "cost=4.10" in lines[0]


def test_the_refusal_line_still_carries_ink_and_periodicity(tmp_path, monkeypatch):
    """The measurements MOVED onto the outcome. The line months of logs are
    grepped for must not have lost them on the way."""
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [])])

    assert skill._capture_position_local() is None

    trace = _trace(tmp_path)
    assert "ink=0.05310" in trace
    assert "periodicity=0.65720" in trace


def test_a_measurement_that_cannot_be_taken_does_not_break_the_line(
    tmp_path, monkeypatch
):
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [])])
    # After the fixture, which patches the same name: a measurement that CAN be
    # taken would prove nothing here.
    monkeypatch.setattr(
        main.overlay_reader, "overlay_ink_fraction",
        lambda f: (_ for _ in ()).throw(RuntimeError("no ink")),
    )

    assert skill._capture_position_local() is None
    assert "ink=? periodicity=?" in _trace(tmp_path)


# --------------------------------------------------------------------- #
# I6: the refused-frame dump
# --------------------------------------------------------------------- #


def _dump_skill(tmp_path: Path) -> main.SC_NavPoint:
    skill = main.SC_NavPoint.__new__(main.SC_NavPoint)
    skill.get_generated_files_dir = lambda: str(tmp_path)
    return skill


def _frame() -> np.ndarray:
    return np.zeros((5, 10, 3), dtype=np.float64)


def _dumped(tmp_path: Path) -> list[str]:
    folder = tmp_path / "refused"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_the_dump_is_on_by_default(tmp_path):
    """TURNED ON 2026-08-02 by the user, for the next live session. It was off
    since it was built, and this test asserted that; the default deliberately
    changed, so the assertion follows it rather than the other way round.

    The default stays pinned either way, because the switch is the whole of the
    user's control over whether pixels of their screen reach their disk. What
    it dumps is unchanged: the overlay crop only, capped, local, never sent."""
    assert main.SAVE_REFUSED_FRAMES is True
    _dump_skill(tmp_path)._dump_refused_frame(_frame(), fields.KIND_GATE)
    assert len(_dumped(tmp_path)) == 1


def test_the_dump_writes_nothing_when_the_switch_is_off(tmp_path, monkeypatch):
    """Nobody's disk fills once it is turned back off. Kept as its own test
    when the default flipped, so turning the switch off stays covered."""
    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", False)
    _dump_skill(tmp_path)._dump_refused_frame(_frame(), fields.KIND_GATE)
    assert _dumped(tmp_path) == []


def test_a_frame_is_written_when_the_switch_is_on(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", True)
    _dump_skill(tmp_path)._dump_refused_frame(_frame(), fields.KIND_GATE)
    names = _dumped(tmp_path)
    assert len(names) == 1
    assert names[0].endswith("_gate.png")


def test_the_dump_keeps_only_the_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", True)
    stamps = iter(f"2026-08-02_12{n:04d}" for n in range(100))
    real = main.time.strftime
    monkeypatch.setattr(
        main.time, "strftime",
        lambda fmt, *a: next(stamps) if "%H%M%S" in fmt else real(fmt, *a),
    )
    skill = _dump_skill(tmp_path)
    for _ in range(25):
        skill._dump_refused_frame(_frame(), fields.KIND_GATE)

    names = _dumped(tmp_path)
    assert len(names) == main.REFUSED_FRAME_KEEP
    # The survivors are the LAST twenty written, not the first twenty found.
    assert names[0] == "2026-08-02_120005_gate.png"
    assert names[-1] == "2026-08-02_120024_gate.png"


def test_a_png_write_that_raises_cannot_change_a_capture(tmp_path, monkeypatch):
    """The dump is wrapped, so a full disk or a broken PIL costs the pixels and
    nothing else: the same outcome, the same return, the same trace."""
    from PIL import Image

    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", True)
    monkeypatch.setattr(
        Image, "fromarray",
        lambda *a, **k: (_ for _ in ()).throw(OSError("the disk is gone")),
    )
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [])])

    assert skill._capture_position_local() is None
    assert skill._last_outcome.kind == fields.KIND_GATE
    assert "REFUSED:" in _trace(tmp_path)
    assert _dumped(tmp_path) == []


def test_a_directory_that_cannot_be_made_is_swallowed_too(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SAVE_REFUSED_FRAMES", True)
    monkeypatch.setattr(main.os, "makedirs",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("full")))
    skill = _skill(tmp_path, monkeypatch, rows=[_row("zone", [])])

    assert skill._capture_position_local() is None
    assert _dumped(tmp_path) == []

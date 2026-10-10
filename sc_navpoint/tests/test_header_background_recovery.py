"""Flexible header backgrounds must never supply or silently promote digits."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

import overlay_reader as ov
import overlay_fields as fields
from scanner import NavPointScanner

ROOT = Path(__file__).resolve().parents[1]


def _load(scene, filename):
    path = ROOT / "ocr_dev" / "captures" / scene / filename
    if not path.exists() or not (ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), dtype=float)


def test_header_recovery_keeps_exact_native_coordinate_characters():
    frame = _load("vuur-return-outside", "frame_0002.png")
    reader = ov.OverlayReader(ROOT / "overlay_glyphs.npz")
    _, _, rows = reader.read_bright_coordinates(frame, ov.POSITION_ROWS)
    assert fields.capture_payload(rows)[0] is None
    recovered = reader.recover_coordinate_headers(frame, rows)
    payload, why = fields.capture_payload(recovered)
    assert payload is not None, why
    assert NavPointScanner().parse_payload(payload) is not None
    for name in ("root", "solar"):
        row = payload["coordinate_stack"][name]
        assert tuple(row[k] for k in ("x_m", "y_m", "z_m")) == pytest.approx(
            (1377962668.4, -23873735239.4, 9138944.6), abs=.001, rel=0
        )
    assert recovered[3]["text"].split("Pos:")[1] == rows[3]["text"].split("Pos:")[1]


def test_repairing_pos_label_rechecks_a_previously_unchecked_false_nine():
    frame = _load("surface-01", "frame_0000.png").copy()
    reader = ov.OverlayReader(ROOT / "overlay_glyphs.npz")
    _, _, source = reader.read(frame, ov.POSITION_ROWS)
    native = deepcopy(source)
    candidates = {}
    for index in (2, 3):
        row = native[index]
        start = row["text"].index("Pos: ") + 5
        cells = list(reader.cell_boxes(ov.block_columns(frame.shape[1])[1], row["offset"], ov.CELLS_PER_ROW))
        x, phase = cells[len(row["text"]) - 1 - start]
        ti = reader._chars[phase].index("-")
        wi = reader._chars[phase].index("9")
        lower = reader._glyphs[phase][ti] * 255
        upper = lower + reader._transs[phase][ti] * 255
        pixels = np.clip(reader._glyphs[phase][wi] * 255 + reader._transs[phase][wi] * 139, lower, upper)
        frame[row["y"]:row["y"] + 13, x + 1:x + 7] = pixels[..., None]
        text = row["text"][:start] + "9" + row["text"][start + 1:]
        candidates[row["y"]] = {**row, "text": text}
        row["text"] = text.replace("Pos:", "Po?:")
    def candidate(band, origin, count):
        top = (band.ctypes.data - frame.ctypes.data) // frame.strides[0]
        return [candidates.get(top, source[top // 13])]
    reader._header_reader = SimpleNamespace(_decode_block=candidate)
    recovered = reader.recover_coordinate_headers(frame, native)
    assert fields.capture_payload(recovered)[0] is None
    assert "?" in recovered[3]["text"].split("Pos:")[1]


def test_header_recovery_cannot_overwrite_a_confident_native_letter():
    frame = _load("surface-01", "frame_0000.png")
    reader = ov.OverlayReader(ROOT / "overlay_glyphs.npz")
    _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    native = deepcopy(rows[3])
    native["text"] = native["text"].replace("Root", "R?pt")
    reader._header_reader = SimpleNamespace(_decode_block=lambda *args: [rows[3]])
    recovered = reader.recover_coordinate_headers(frame, [native])
    assert recovered[0]["text"] == native["text"]

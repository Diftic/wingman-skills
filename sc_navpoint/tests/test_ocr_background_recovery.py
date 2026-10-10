"""Measured background recovery and correlated missing-character regression."""
from pathlib import Path

import numpy as np
import pytest

import overlay_fields as fields
import overlay_reader as ov
from scanner import NavPointScanner


_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("axis", range(3))
@pytest.mark.parametrize("missing", ["sign", "leading_digit"])
def test_missing_leading_character_in_both_anchors_is_not_whitespace(axis, missing):
    # A vanished glyph occupies a real cell. Root/Solar agreement cannot detect
    # correlated erasure, so the fixed coordinate spacing must reject it.
    tokens = ["-1234.56km", "-2345.67km", "-3456.78km"]
    if missing == "leading_digit":
        tokens = [t[1:] for t in tokens]
    tokens[axis] = " " + tokens[axis][1:]
    rows = [
        {"row": i, "kind": "zone", "trusted": True,
         "text": f"Zone: {name} Pos: {' '.join(tokens)}"}
        for i, name in enumerate(["SolarSystem_730084885606", "Root"])
    ]
    payload, _ = fields.capture_payload(rows)
    assert payload is None
    assert fields.payload_from_rows(rows) is None


def test_erased_root_name_suffix_does_not_create_a_root_anchor():
    rows = [
        {"row": 0, "kind": "zone", "trusted": True,
         "text": "Zone: SolarSystem_730084885606 Pos: 1234.56km 2345.67km 3456.78km"},
        {"row": 1, "kind": "zone", "trusted": True,
         "text": "Zone: Root        Pos: 1234.56km 2345.67km 3456.78km"},
    ]
    payload, _ = fields.capture_payload(rows)
    assert payload is None
    assert fields.payload_from_rows(rows) is None


def test_brightness_recovery_reads_manually_checked_ice_coordinates():
    path = _ROOT / "ocr_dev" / "captures" / "ice-bright" / "shot_00.png"
    if not path.exists() or not (_ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    reader = ov.OverlayReader(_ROOT / "overlay_glyphs.npz")
    assert not ov.capture_is_usable(frame)[0]
    _, _, rows = reader.read_bright_coordinates(frame, ov.POSITION_ROWS)
    payload, reason = fields.capture_payload(rows)
    assert payload is not None, reason
    assert NavPointScanner().parse_payload(payload) is not None
    for name in ("root", "solar"):
        row = payload["coordinate_stack"][name]
        assert tuple(row[k] for k in ("x_m", "y_m", "z_m")) == pytest.approx(
            (-7965621420.5, 12712906393.1, 2155.61), abs=0.001, rel=0
        )
    assert "camdir" not in payload


@pytest.mark.parametrize("level", [0, 100, 255])
def test_brightness_recovery_refuses_empty_frames(level):
    if not (_ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("glyph bank is not shipped")
    reader = ov.OverlayReader(_ROOT / "overlay_glyphs.npz")
    _, _, rows = reader.read_bright_coordinates(np.full((181, 675, 3), level, dtype=float), ov.POSITION_ROWS)
    payload, _ = fields.capture_payload(rows)
    assert payload is None


@pytest.mark.parametrize("scene, filename, xyz", [
    ("terrain-01", "frame_0010.png", (-7685489442.4, -45996765899.8, 1844.41)),
    ("bright-02", "frame_0005.png", (-7685489441.9, -45996765899.7, 1844.53)),
])
def test_real_background_pixels_reach_exact_coordinate_stack(scene, filename, xyz):
    path = _ROOT / "ocr_dev" / "captures" / scene / filename
    if not path.exists() or not (_ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64)
    reader = ov.OverlayReader(_ROOT / "overlay_glyphs.npz")
    assert ov.capture_is_usable(frame)[0]
    _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    payload, reason = fields.capture_payload(rows)
    assert payload is not None, reason
    assert NavPointScanner().parse_payload(payload) is not None
    for anchor in ("root", "solar"):
        row = payload["coordinate_stack"][anchor]
        assert tuple(row[k] for k in ("x_m", "y_m", "z_m")) == pytest.approx(xyz, abs=0.001, rel=0)


def test_real_pixels_with_both_minus_signs_erased_are_refused():
    path = _ROOT / "ocr_dev" / "captures" / "surface-01" / "frame_0000.png"
    if not path.exists() or not (_ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64).copy()
    reader = ov.OverlayReader(_ROOT / "overlay_glyphs.npz")
    _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    for index in (2, 3):
        row = rows[index]
        start = row["text"].index("Pos: ") + 5
        assert row["text"][start] == "-"
        cells = list(reader.cell_boxes(ov.block_columns(frame.shape[1])[1], row["offset"], ov.CELLS_PER_ROW))
        x, _ = cells[len(row["text"]) - 1 - start]
        patch = frame[row["y"]:row["y"] + 13, x + 1:x + 7]
        patch[:] = np.median(patch, axis=(0, 1))
    assert ov.capture_is_usable(frame)[0]
    _, _, damaged_rows = reader.read(frame, ov.POSITION_ROWS)
    payload, _ = fields.capture_payload(damaged_rows)
    assert payload is None


@pytest.mark.parametrize("actual_nine", [False, True])
def test_sign_shaped_background_is_distinguished_from_a_real_nine(actual_nine):
    path = _ROOT / "ocr_dev" / "captures" / "surface-01" / "frame_0000.png"
    if not path.exists() or not (_ROOT / "overlay_glyphs.npz").exists():
        pytest.skip("development capture corpus is not shipped")
    from PIL import Image

    frame = np.asarray(Image.open(path).convert("RGB"), dtype=np.float64).copy()
    reader = ov.OverlayReader(_ROOT / "overlay_glyphs.npz")
    _, _, rows = reader.read(frame, ov.POSITION_ROWS)
    for index in (2, 3):
        row = rows[index]
        start = row["text"].index("Pos: ") + 5
        assert row["text"][start] == "-"
        cells = list(reader.cell_boxes(ov.block_columns(frame.shape[1])[1], row["offset"], ov.CELLS_PER_ROW))
        x, phase = cells[len(row["text"]) - 1 - start]
        nine = reader._chars[phase].index("9")
        minus = reader._chars[phase].index("-")
        pixels = reader._glyphs[phase][nine] * 255 + reader._transs[phase][nine] * 139
        if not actual_nine:
            # Any pixel in this interval is achievable by a real minus glyph
            # over some RGB background. The constant-background reader still
            # calls it '9' at RMSE 8.4 with margin 39, below its refusal floor.
            lower = reader._glyphs[phase][minus] * 255
            upper = lower + reader._transs[phase][minus] * 255
            pixels = np.clip(pixels, lower, upper)
        frame[row["y"]:row["y"] + 13, x + 1:x + 7] = pixels[..., None]
    assert ov.capture_is_usable(frame)[0]
    _, _, damaged_rows = reader.read(frame, ov.POSITION_ROWS)
    payload, _ = fields.capture_payload(damaged_rows)
    if actual_nine:
        assert payload is not None
        assert payload["coordinate_stack"]["root"]["x_m"] == pytest.approx(916104284922.2, abs=0.001, rel=0)
    else:
        assert payload is None

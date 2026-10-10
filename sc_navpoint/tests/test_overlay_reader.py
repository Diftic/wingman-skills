"""The local overlay reader: the join to the scanner, the field parser, the guards.

THE JOIN IS TESTED FIRST AND FROM REAL PIXELS, deliberately. The reader's row
dicts and the scanner's position data share no code path, and every other test
in this suite supplies its own already-final fixture on one side or the other.
That is the exact shape of the July defect where scanner and guidance both
tested green while the join between them was never exercised.

The field-parser and guard tests below are synthetic on purpose: they encode the
failures the 2026-07-29 audit actually produced (occlusion truncation, empty
payload rows, fabricated zone names), which no capture on disk contains.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

import overlay_fields as fields
import overlay_reader as ov
from scanner import NavPointScanner


_CAPTURES = Path(__file__).resolve().parent.parent / "ocr_dev" / "captures"
_GLYPHS = Path(__file__).resolve().parent.parent / "overlay_glyphs.npz"


def _capture(label: str, shot: str = "shot_00.png") -> np.ndarray:
    """Load a real capture, or skip: the corpus is dev-only, not shipped."""
    path = _CAPTURES / label / shot
    if not path.exists() or not _GLYPHS.exists():
        pytest.skip(f"capture corpus not present: {path}")
    from PIL import Image

    return np.asarray(Image.open(path).convert("RGB")).astype(np.float64)


@pytest.fixture(scope="module")
def reader():
    if not _GLYPHS.exists():
        pytest.skip("glyph bank not present")
    return ov.OverlayReader(_GLYPHS)


def _row(text: str, kind: str | None = "zone", trusted: bool = True) -> dict:
    return {"row": 0, "text": text, "kind": kind, "trusted": trusted,
            "refused": 0 if trusted else 4, "cost": 5.0, "margin": 20.0}


# --- the join: real pixels through the reader into position data ----------- #


def test_join_real_capture_to_position_data(reader):
    """A real frame decodes into position data the rest of the skill can use.

    game-mid is the Nyx glacier ring: no OOC line, so this exercises the space
    branch end to end, through the same scanner gates the Vision path uses.
    """
    frame = _capture("game-mid")
    payload, reason = fields.read_legacy_payload(reader, frame, rows=10)
    assert payload is not None, reason

    pos_data = NavPointScanner().parse_payload(payload)

    assert pos_data is not None
    assert pos_data["local_frame"] is False
    assert pos_data["system_frame"] is True
    assert pos_data["frame_id"] == "729968885550"
    # 6470453.8383km and 13533871.9753km, converted in Python from the raw
    # unit-suffixed tokens; the third axis prints in METRES on the same line.
    assert pos_data["x"] == pytest.approx(6470453838.3)
    assert pos_data["y"] == pytest.approx(13533871975.3)
    assert pos_data["z"] == pytest.approx(-33.29)
    assert pos_data["camdir"] == (-55.0, -3.0, 125.0)
    # The reader must never supply the token that can delete waypoints.
    assert pos_data["server_id"] == ""


def test_join_survives_the_scanner_crosscheck(reader):
    """The SolarSystem and Root lines are read independently and must agree."""
    frame = _capture("game-mid")
    payload, _ = fields.read_legacy_payload(reader, frame, rows=10)
    assert payload["system_pos_raw"] == payload["root_pos_raw"]
    payload["root_pos_raw"] = ["1.0km", "2.0km", "3.0km"]
    scanner = NavPointScanner()
    assert scanner.parse_payload(payload) is None
    assert scanner.last_reject_reason == "frame_mismatch"


# --- capture precondition, on real frames ---------------------------------- #


def test_precondition_accepts_a_dark_capture():
    assert ov.capture_is_usable(_capture("game-mid"))[0] is True


@pytest.mark.parametrize("label", ["game-bright", "ice-bright"])
def test_precondition_rejects_a_blown_out_capture(label):
    usable, reason = ov.capture_is_usable(_capture(label))
    assert usable is False
    assert "clipped" in reason


def test_precondition_uses_fixed_geometry_not_the_fitted_origin(reader):
    """Saturation moves the alignment fit itself, so the guard cannot use it.

    Under gamma 0.5 the fit jumps from y0=6 to y0=2. A guard reading fitted
    output would inherit the very failure it exists to catch, so this asserts
    the guard needs no reader at all.
    """
    frame = _capture("ice-bright")
    assert ov.capture_is_usable(frame)[0] is False  # no reader involved
    y0, _, _ = reader.fit_alignment(frame)
    assert isinstance(y0, int)


# --- the field parser: fail closed ----------------------------------------- #


def test_parser_reads_the_space_frame():
    payload = fields.payload_from_rows([
        _row("CamDir: -55  -3  125 FOV: 55 Focal: 0.10 FStop: 64.0", "camdir"),
        _row("Zone: SolarSystem_729968885550 Pos: 6470453.8383km 13533871.9753km -33.29m"),
        _row("Zone: Root Pos: 6470453.8383km 13533871.9753km -33.29m"),
    ])
    assert payload["local_frame"] is False
    assert payload["system_zone_id"] == "729968885550"
    assert payload["system_pos_raw"][2] == "-33.29m"
    assert payload["camdir"] == [-55.0, -3.0, 125.0]


def test_parser_routes_an_ooc_line_to_the_local_frame():
    """The OOC gate is the router, and it outranks a readable system line.

    A body-fixed point also has a system-frame address, but that address drifts
    at the body's rotation rate, so storing it would recreate the 2026-07-11
    failure. Local wins whenever the OOC line is present.
    """
    payload = fields.payload_from_rows([
        _row("Zone: DRAK_Clipper_737234004249 Pos: 0.00m 11.57m 2.83m"),
        _row("Zone: OOC_Stanton_2b_Daymar Pos: 9810.08m -174.2880km 238.0511km"),
        _row("Zone: SolarSystem_729968885550 Pos: 6470453.8383km 1353387.9753km -33.29m"),
    ])
    assert payload["local_frame"] is True
    assert payload["body_token"] == "Stanton_2b_Daymar"
    assert payload["pos_raw"] == ["9810.08m", "-174.2880km", "238.0511km"]
    assert payload["zone"] == "DRAK_Clipper_737234004249"
    assert "system_pos_raw" not in payload


def test_parser_refuses_an_occlusion_truncated_coordinate():
    """The one failure reachable by ordinary play.

    A flat opaque panel over part of the block is pixel-uniform, so it fits the
    space template with a residual near zero: occluded cells decode as CONFIDENT
    spaces and a coordinate cut off mid-axis comes back trusted, with the right
    `kind` and zero refused cells. Measured at 20 per cent coverage on the frame
    that otherwise reads 359 of 359. Only the full-line shape rejects it.
    """
    rows = [_row("Zone: SolarSystem_729968885550 Pos: 6470453.8383km 1353387")]
    assert fields.payload_from_rows(rows) is None


def test_parser_refuses_a_trusted_but_empty_row():
    """`trusted` does not mean "contains a payload"; blank cells cost nothing.

    A minimum character count does NOT catch this: the label alone is 15
    characters. Ten such rows occur naturally in the corpus below the overlay's
    live content, at cost 0.00.
    """
    assert fields.payload_from_rows([_row("Zone: Root Pos:")]) is None
    assert fields.payload_from_rows([_row("Zone: SolarSystem_729968885550 Pos:")]) is None


def test_parser_refuses_a_component_with_no_unit_suffix():
    """A dropped "k" is a silent factor-of-1000 error with a plausible value."""
    rows = [
        _row("Zone: SolarSystem_729968885550 Pos: 6470453.8383km 13533871.9753 -33.29m"),
    ]
    assert fields.payload_from_rows(rows) is None


def test_parser_never_treats_a_fabricated_zone_as_root():
    """Root is anchored on the FULL token, never a bare prefix.

    Synthetic rows carrying `Root_Cellar_042`, a fabricated SolarSystem id and a
    fabricated shard token were all accepted as trusted at cost under 2.5,
    because the reader does no shape validation. Classification happens on
    content after the label, so this lands in the informational bucket.
    """
    # Since 2026-07-31 the Root line is MANDATORY on the space path, so a
    # fabricated one no longer merely fails to populate the field: the capture
    # is refused outright, because no cross-check is available.
    assert fields.payload_from_rows([
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        _row("Zone: Root_Cellar_042 Pos: 9.9km 9.9km 9.9km"),
    ]) is None

    # And with a REAL Root line present, the fabricated row must still never be
    # the coordinate source. This keeps the original guarantee directly visible
    # rather than inferring it from the refusal above.
    payload = fields.payload_from_rows([
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        _row("Zone: Root_Cellar_042 Pos: 9.9km 9.9km 9.9km"),
        _row("Zone: Root Pos: 1.0km 2.0km 3.0km"),
    ])
    assert payload["root_pos_raw"] == ["1.0km", "2.0km", "3.0km"]
    assert payload["system_pos_raw"] == ["1.0km", "2.0km", "3.0km"]

    # On the local branch, where the payload does carry a zone name, the same
    # row is informational and never a coordinate source.
    local = fields.payload_from_rows([
        _row("Zone: Root_Cellar_042 Pos: 9.9km 9.9km 9.9km"),
        _row("Zone: OOC_Stanton_2b_Daymar Pos: 1.0m 2.0m 3.0m"),
    ])
    assert local["zone"] == "Root_Cellar_042"
    assert local["pos_raw"] == ["1.0m", "2.0m", "3.0m"]


def test_parser_refuses_the_space_frame_when_a_row_above_it_was_unreadable():
    """Absence of an OOC line may only be concluded when the rows above were read.

    The Zone stack nests inside out, so an OOC line always sits ABOVE the
    SolarSystem line, and any unreadable row up there could BE it. A row so
    corrupted that even its `Zone:` label is unreadable must count too, which is
    why the gate is positional rather than keyed on `kind`.
    """
    rows = [
        _row("?  ?    Zon?: ????_?l?pper_742164??5970", None, trusted=False),
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        _row("Zone: Root Pos: 1.0km 2.0km 3.0km"),
    ]
    assert fields.payload_from_rows(rows) is None


def test_a_refused_row_below_the_system_line_does_not_block():
    """The deliberate limit of the gate: nothing below Root can be an OOC line.

    Rows 8 and beyond belong to a second pitch class the reader never fits, so
    they refuse in EVERY capture. Counting those would refuse every capture.
    """
    payload = fields.payload_from_rows([
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        _row("Zone: Root Pos: 1.0km 2.0km 3.0km"),
        _row("????????????????????????", None, trusted=False),
    ])
    assert payload is not None
    assert payload["system_zone_id"] == "729968885550"


def test_a_refused_camdir_costs_only_the_heading_on_the_local_branch():
    """An OOC line proves the local frame positively, so nothing above it can
    change the routing; the heading is simply left unset."""
    payload = fields.payload_from_rows([
        _row("CamDir: -5? -34  124 FO?: 4?", "camdir", trusted=False),
        _row("Zone: OOC_Stanton_2b_Daymar Pos: 1.0m 2.0m 3.0m"),
    ])
    assert payload["local_frame"] is True
    assert "camdir" not in payload


def test_parser_requires_the_camdir_line_to_be_whole():
    """Anchored on the FOV field that follows it, so a truncation cannot pass."""
    payload = fields.payload_from_rows([
        _row("CamDir: -55  -3  125", "camdir"),
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        # Root is mandatory on the space path since 2026-07-31; it is only a
        # vehicle here, since this test is about the CamDir anchor.
        _row("Zone: Root Pos: 1.0km 2.0km 3.0km"),
    ])
    assert "camdir" not in payload


def test_parser_never_emits_a_server_id():
    """The reader must not be able to drive the waypoint wipe.

    It is deterministic on identical pixels (five runs over one screengrab give
    bit-identical output), so the live "three consecutive captures agreeing"
    rule measures nothing but elapsed time when this reader feeds it.
    """
    payload = fields.payload_from_rows([
        _row("ShardId: pub_euw1b_12269732_090", "shard"),
        _row("Zone: SolarSystem_729968885550 Pos: 1.0km 2.0km 3.0km"),
        # Root is mandatory on the space path since 2026-07-31; it is only a
        # vehicle here, since this test is about the absent server_id.
        _row("Zone: Root Pos: 1.0km 2.0km 3.0km"),
    ])
    assert "server_id" not in payload


def test_parser_returns_none_with_no_frame_at_all():
    assert fields.payload_from_rows([]) is None
    assert fields.payload_from_rows([_row("FPS 115.9 [27..141], - 8.8ms", None)]) is None


# --- the per-cell guards --------------------------------------------------- #


def _stats(spread: float, mean: float = 60.0, clipped: float = 0.0):
    return (spread, mean, clipped)


def test_ink_contradiction_refuses_a_blank_cell_that_contains_ink():
    """The three real dimming breaches read spread 97.4, 83.5 and 69.6."""
    chars = [" ", " ", " ", "5"]
    stats = [_stats(7.0), _stats(6.0), _stats(97.4), _stats(232.0)]
    ov.OverlayReader._apply_cell_guards(chars, stats, background=60.0)
    assert chars == [" ", " ", ov.REFUSED, "5"]


def test_ink_threshold_is_hybrid_not_absolute():
    """A flat 50 refuses 14.6 per cent of blanks over a structured background.

    Measured inside the Nyx glacier ring: an ice-chunk edge inside a blank cell
    carries as much local contrast as ink does (background spread median 43,
    p95 163), so an absolute threshold would push the reader onto Vision almost
    everywhere in space while passing every test in the audit.
    """
    chars = [" "] * 4
    stats = [_stats(43.0), _stats(60.0), _stats(120.0), _stats(90.0)]
    ov.OverlayReader._apply_cell_guards(chars, stats, background=68.9)
    assert chars == [" "] * 4  # median 75 -> threshold 450, nothing fires

    chars = [" "] * 4
    smooth = [_stats(7.0), _stats(6.0), _stats(8.0), _stats(60.0)]
    ov.OverlayReader._apply_cell_guards(chars, smooth, background=20.0)
    assert chars[3] == ov.REFUSED  # median 7 -> threshold floors at 50


def test_flat_white_refuses_a_destroyed_cell():
    """Real background never achieves a bit-flat interior; clipping does."""
    chars = [" ", " "]
    stats = [_stats(2.0, mean=255.0), _stats(9.0, mean=236.0)]
    ov.OverlayReader._apply_cell_guards(chars, stats, background=180.0)
    assert chars == [ov.REFUSED, " "]


def test_flat_white_leaves_a_legitimately_bright_background_alone():
    """Fired 0 times across 540 real blank cells, 159 of them on a blown sky."""
    chars = [" "]
    stats = [_stats(2.0, mean=255.0)]
    ov.OverlayReader._apply_cell_guards(chars, stats, background=250.0)
    assert chars == [" "]  # not 40 units above its own row's background


def test_a_clipped_cell_is_refused_whatever_it_decoded_as():
    """Bloom behind ONE character leaves the row at 3.09 per cent, safely under
    the row precondition, while that cell decodes as an accepted wrong blank."""
    chars = ["5", " "]
    stats = [_stats(7.0, clipped=0.97), _stats(7.0, clipped=0.10)]
    ov.OverlayReader._apply_cell_guards(chars, stats, background=60.0)
    assert chars == [ov.REFUSED, " "]


# --- the batched matcher --------------------------------------------------- #


def test_batched_costs_match_the_scalar_model(reader):
    """The stacked pass is the same arithmetic, 10x faster (17.3 s -> 1.7 s).

    Verified rather than assumed, because the whole reader rests on this cost.
    """
    frame = _capture("game-mid")
    _, right = ov.block_columns(frame.shape[1])
    band = frame[ov.BLOCK_TOP:ov.BLOCK_TOP + ov.ROW_HEIGHT]
    colour = np.asarray((255.0, 255.0, 255.0))
    inner = slice(ov.MASK, ov.CELL_WIDTH - ov.MASK)
    worst = 0.0
    for x0, phase in reader.cell_boxes(right, 0.5, 20):
        core = band[:, x0:x0 + ov.CELL_WIDTH][:, inner]
        batched = reader.cell_costs(core, phase, colour)
        keys = sorted(k for k in reader.glyph if k[1] == phase)
        scalar = np.array([
            ov.match(core, reader.glyph[k][:, inner], reader.trans[k][:, inner],
                     colour)
            for k in keys
        ])
        worst = max(worst, float(np.max(np.abs(batched - scalar))))
    assert worst < 1e-9

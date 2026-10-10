"""Refusing a system-frame fix when the player is standing on a body.

Routing assumed a body's container is named `OOC_*`. Pyro does not name them
that way, so on Pyro 3 the reader concluded open space and emitted a
SYSTEM-frame position for a player standing on a rotating surface: correct at
capture, hundreds of metres wrong seconds later. That is the 2026-07-11 failure
returning through a different door.

This guard does not decide how local frames will eventually be detected. It only
refuses the unsafe case. Every line below is real text from a capture on disk.
"""

from __future__ import annotations

import pytest

import overlay_fields as fields


def _row(text, kind="zone", trusted=True):
    return {"row": 0, "trusted": trusted, "kind": kind, "text": text}


# Real zone lines, with the distance they put the player from the container
# origin. The gap between a station and a body is three orders of magnitude.
SMALL = [
    ("ship",    "Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"),
    ("room",    "Zone: rs_int_ptn_set Pos: -220.47m 592.25m 364.23m"),
    ("station", "Zone: glaciemring_segment_wtn-018 Pos: -1718.86m 467.91m 471.45m"),
    ("hangar",  "Zone: Hangar_SmallFront_RestStop_Pyro_746881365623 Pos: 21.6m 1.0m 2.0m"),
]
LARGE = [
    ("Pyro 3 surface", "Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
    ("Clio landed",    "Zone: OOC_Stanton_4b_Clio Pos: 123.2375km -313.5352km 14.9327km"),
]

# DELIBERATE REVERSAL, 2026-08-01. `P5_02` was listed above as body scale, on
# the reasoning that a rest stop "is not open space either". That refused every
# capture at P5 L2, and a Lagrange or rest-stop container does not rotate, so a
# system-frame waypoint inside one stays put. Body scale is now a window and
# these sit above its ceiling. They are containers, not surfaces.
CONTAINERS = [
    ("rest stop OC", "Zone: P5_02 Pos: -19125.3844km 10431.6256km 17665.3252km"),
    ("P5 L2 live",   "Zone: P5_L2 Pos: -41726.2527km 21110.7593km 16498.3825km"),
]


@pytest.mark.parametrize("name,text", SMALL)
def test_vehicles_and_stations_are_not_body_scale(name, text):
    assert fields._is_body_scale(text) is False, name


@pytest.mark.parametrize("name,text", LARGE)
def test_bodies_are_body_scale(name, text):
    assert fields._is_body_scale(text) is True, name


def test_standing_on_pyro_3_refuses_instead_of_emitting_system_frame():
    """The exact stack captured on Pyro 3, 62 of 62 frames, on 2026-07-31."""
    rows = [
        _row("CamDir: -20  26 -174 FOV: 44 Focal: 3.00 FStop: 64.0", "camdir"),
        _row("Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
        _row("Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km"),
        _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"),
    ]
    assert fields.payload_from_rows(rows) is None


def test_real_open_space_still_works():
    """The guard must not cost the case that already works in flight."""
    rows = [
        _row("CamDir: -20  26 -174 FOV: 44 Focal: 3.00 FStop: 64.0", "camdir"),
        _row("Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"),
        _row("Zone: SolarSystem_730084885606 Pos: -16104264604.7km "
             "7587753462.6km 13096.9m"),
        _row("Zone: Root Pos: -16104264604.7km 7587753462.6km 13096.9m"),
    ]
    payload = fields.payload_from_rows(rows)
    assert payload is not None
    assert payload["local_frame"] is False


def test_a_body_row_below_the_system_line_does_not_refuse():
    """Only containers ABOVE SolarSystem describe what the player is inside."""
    rows = [
        _row("Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"),
        _row("Zone: SolarSystem_730084885606 Pos: -16104264604.7km "
             "7587753462.6km 13096.9m"),
        _row("Zone: Root Pos: -16104264604.7km 7587753462.6km 13096.9m"),
        _row("Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
    ]
    assert fields.payload_from_rows(rows) is not None


def test_an_untrusted_body_row_is_left_to_the_ooc_gate():
    """An unreadable row is the refutation gate's business, not this guard's.

    The two must not disagree: this one reads a row it trusts, the other decides
    what an unreadable row might have been.
    """
    rows = [
        _row("Zone: p?ro3 Pos: 330.7421km ???.????km 119.0037km", trusted=False),
        _row("Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km"),
        _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"),
    ]
    # Refused either way; what matters is that it is refused.
    assert fields.payload_from_rows(rows) is None


def test_the_threshold_sits_in_empty_space():
    """50 km is nowhere near anything observed, which is why it is safe."""
    largest_small = max(
        abs(float(fields._largest_component(t)[:-1]))
        for _, t in SMALL
    )
    assert largest_small < 2_000.0          # metres: biggest non-body is ~1.8 km
    assert fields._BODY_SCALE_M == 50_000.0  # 25x above it, 2x below Clio


# --------------------------------------------------------------------- #
# The guard must not be switchable off by the scene behind the overlay
# --------------------------------------------------------------------- #
#
# Background stars inside the 660 px block decode as phantom glyphs in the
# right-aligned text's left margin. Anchoring the guard on a leading `Zone:`
# meant `?   Zone: P5_L2 Pos: ...` stopped looking like a zone line, and the
# row silently CLEARED a gate built after a data-loss incident. Observed
# 2026-08-01 at P5 L2: the same row returned body-scale True and False on
# consecutive frames as the star drifted through its band, so a capture was
# accepted or refused by where the stars happened to be.


PHANTOM = "?   "


@pytest.mark.parametrize("name,text", LARGE)
def test_a_phantom_glyph_cannot_clear_the_guard(name, text):
    """A leading margin artefact must not change the verdict on a body row."""
    assert fields._is_body_scale(PHANTOM + text) is True, (
        f"{name}: a star in the left margin disabled the body-scale guard"
    )


@pytest.mark.parametrize("name,text", LARGE)
def test_a_phantom_glyph_still_refuses_the_capture(name, text):
    rows = [
        _row(PHANTOM + text, trusted=False),
        _row("Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km"),
        _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"),
    ]
    assert fields.payload_from_rows(rows) is None


def test_a_zone_row_with_no_readable_coordinate_refuses():
    """Answering neither question is not the same as answering 'safe'.

    Such a row can be shown to be neither a world-anchored container nor a
    body surface, so it cannot clear a guard that exists to prove absence.
    """
    rows = [
        _row("Zone: P5_?2 Pos: ???.????km ???.????km ???.????km", trusted=False),
        _row("Zone: SolarSystem_745338555312 Pos: -16104284.9222km "
             "7588008.0968km 119.0037km"),
        _row("Zone: Root Pos: -16104284.9222km 7588008.0968km 119.0037km"),
    ]
    assert fields.payload_from_rows(rows) is None


# --------------------------------------------------------------------- #
# Containers above the ceiling are open space, not a surface
# --------------------------------------------------------------------- #


@pytest.mark.parametrize("name,text", CONTAINERS)
def test_containers_above_the_ceiling_are_not_body_scale(name, text):
    assert fields._is_body_scale(text) is False, name


@pytest.mark.parametrize("name,text", CONTAINERS)
def test_a_container_does_not_block_a_space_capture(name, text):
    """The P5 L2 stack captured live on 2026-08-01, which refused every time."""
    rows = [
        _row("CamDir: -177   0  159 FOV: 55 Focal: 3.00 FStop: 64.0", "camdir"),
        _row("Zone: DRAK_Clipper_746458136582 Pos: 0.00m 11.57m 2.83m"),
        _row(text),
        _row("Zone: SolarSystem_729982560264 Pos: -4287445.6037km "
             "-46991137.0047km 16498.3825km"),
        _row("Zone: Root Pos: -4287445.6037km -46991137.0047km 16498.3825km"),
    ]
    payload = fields.payload_from_rows(rows)
    assert payload is not None, f"{name}: still refused"
    assert payload["local_frame"] is False
    assert payload["system_zone_id"] == "729982560264"


def test_the_ceiling_still_refuses_a_body_sized_container():
    """Raising the ceiling must not open the case the guard exists for.

    A container just under the ceiling is still treated as a surface, so the
    margin below the smallest observed container is what gets spent, not the
    protection.
    """
    assert fields._is_body_scale("Zone: x Pos: 14999.0km 0.0m 0.0m") is True
    assert fields._is_body_scale("Zone: x Pos: 15001.0km 0.0m 0.0m") is False

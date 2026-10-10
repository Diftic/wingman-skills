"""The space-branch gate: refuting the OOC hypothesis instead of reading the row.

Every "refuted" case below is a REAL row observed in a capture on 2026-07-31,
not an invented one. The gate exists because the space branch is a claim about
absence, and the point of this change is that proving a row is not an OOC line
is much weaker than reading it: a station zone whose `H` and `g` have no
template still decodes enough to answer the only question being asked.

The fail-closed cases are the ones that matter most. Anything the gate cannot
disprove must still block, because storing a system-frame waypoint while
standing on a rotating body is the 2026-07-11 failure that closed the stellar
frame in the first place.
"""

from __future__ import annotations

import pytest

import overlay_fields as fields
import overlay_reader as ov


# --------------------------------------------------------------------------
# Rows observed in real captures that the gate must REFUTE, so they stop
# blocking a space capture they were never evidence against.
# --------------------------------------------------------------------------
REFUTABLE = [
    # Pyro rest stop elevator, red-01/frame_0024. `T`, `C` and `g` have no
    # template, but the `r` at the second position already rules out `OOC_`.
    ("zone", "Zone: ?ransit?arria?e_ele?_util_746881332878 Pos: -0.59m -1.2m 0.3m"),
    # Same frame, the hangar around it. `H` and `g` missing, `a` refutes.
    ("zone", "Zone: ?an?ar_SmallFront_RestStop_Pyro_746881365623 Pos: 21.6m 1m 2m"),
    # Same frame. `P` refutes at the first position.
    ("zone", "Zone: P5_?2 Pos: -19125.3844km 10431.6256km 17665.3252km"),
    # The ship interior, dark-01. Every letter of `DRAK` is missing, so the
    # prefix survives; the SYSTEM segment is what refutes it, since no known
    # system can spell `?lipper`.
    ("zone", "Zone: ????_?lipper_742164815970 Pos: -0.03m 11.74m 2.78m"),
    # A row whose own label decoded as something an OOC line cannot be.
    ("camdir", "CamDir: -152  48  -65 F??: 55 Focal: 0.10 FStop: 64.0"),
    ("shard", "ShardId: pub_euw1b_1232?004_010"),
    ("session", "Session: f2e0b4d1-52cd-5745-9697-078ce988?e5b"),
]


@pytest.mark.parametrize("kind,text", REFUTABLE)
def test_refutable_rows_do_not_block(kind, text):
    assert fields.ooc_hypothesis_refuted(kind, text) is True


# --------------------------------------------------------------------------
# Rows the gate must NOT refute. Each one could be an OOC line as far as the
# decoded characters go, so each must still block.
# --------------------------------------------------------------------------
BLOCKING = [
    # A real OOC line that merely lost a character elsewhere.
    ("zone", "Zone: OOC_Stanton_2b_Daymar Pos: 1.0km 2.0km ?.0m"),
    # Every character of the token is refused: it could be anything, including
    # an OOC line for a known system. Note the prefix is THREE wildcards, not
    # four: `OOC_` losing its three letters leaves the underscore in place.
    ("zone", "Zone: ???_???????_??_?????? Pos: 1.0km 2.0km 3.0m"),
    # The prefix survives as wildcards and the system segment could be `pyro`.
    ("zone", "Zone: ???_?yro_1_Bloom Pos: 1.0km 2.0km 3.0m"),
    # `nyx` is three characters and the segment is three wildcards.
    ("zone", "Zone: ???_???_2_Something Pos: 1.0km 2.0km 3.0m"),
    # The `Zone:` label itself did not decode, so nothing rules it out.
    ("zone", "?one: ????_?lipper_742164815970 Pos: -0.03m 11.74m 2.78m"),
    (None, "??????? ???? ?????"),
    # The token is not delimited, so the segment may simply be cut short and
    # cannot be tested against the known systems.
    ("zone", "Zone: ????????????"),
]


@pytest.mark.parametrize("kind,text", BLOCKING)
def test_unrefuted_rows_still_block(kind, text):
    assert fields.ooc_hypothesis_refuted(kind, text) is False


def test_gate_lets_a_refuted_row_through_end_to_end():
    """A space payload survives an unreadable ship zone that is provably not OOC."""
    rows = [
        {"row": 0, "trusted": True, "kind": "camdir", "text":
         "CamDir: -43 8 -3 FOV: 55 Focal: 0.10 FStop: 64.0"},
        {"row": 1, "trusted": False, "kind": "zone", "text":
         "Zone: ?an?ar_SmallFront_RestStop_Pyro_746881365623 Pos: 1m 2m 3m"},
        {"row": 2, "trusted": True, "kind": "zone", "text":
         "Zone: SolarSystem_729968885548 Pos: -4296208.3037km 1.0km 2.0m"},
        {"row": 3, "trusted": True, "kind": "zone", "text":
         "Zone: Root Pos: -4296208.3037km 1.0km 2.0m"},
    ]
    payload = fields.payload_from_rows(rows)
    assert payload is not None
    assert payload["local_frame"] is False
    assert payload["system_zone_id"] == "729968885548"


def test_gate_still_blocks_an_unrefuted_row_end_to_end():
    """The same frame blocks when the unreadable row COULD be an OOC line."""
    rows = [
        {"row": 0, "trusted": True, "kind": "camdir", "text":
         "CamDir: -43 8 -3 FOV: 55 Focal: 0.10 FStop: 64.0"},
        {"row": 1, "trusted": False, "kind": "zone", "text":
         "Zone: ???_?yro_1_Bloom Pos: 1m 2m 3m"},
        {"row": 2, "trusted": True, "kind": "zone", "text":
         "Zone: SolarSystem_729968885548 Pos: -4296208.3037km 1.0km 2.0m"},
    ]
    assert fields.payload_from_rows(rows) is None


def test_known_systems_mirror_does_not_drift():
    """The local mirror must match the scanner's plausibility gate exactly."""
    from scanner import _KNOWN_SYSTEMS as scanner_systems

    assert set(fields._KNOWN_SYSTEMS) == set(scanner_systems)


def test_block_geometry_is_self_consistent():
    """CELLS_PER_ROW and BLOCK_WIDTH must describe the same block."""
    assert ov.BLOCK_WIDTH == int(ov.CELLS_PER_ROW * ov.PITCH)


def test_block_is_wide_enough_for_the_longest_needed_line():
    """The longest line the skill can need must fit, with the label intact.

    `Zone: SolarSystem_` + a 12-digit id + ` Pos: ` + three 16-character km
    tokens separated by spaces. If this ever exceeds CELLS_PER_ROW the leading
    `Z` is lost in silence and the `^Zone:` anchor fails on a perfect capture.
    """
    longest = (
        "Zone: SolarSystem_729968885548 Pos: "
        "-47014547.5876km -47014547.5876km -47014547.5876km"
    )
    assert len(longest) <= ov.CELLS_PER_ROW

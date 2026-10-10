"""Extraction of the schema-1 coordinate stack from decoded overlay rows.

The rework's premise is that a zone NAME has no authority over routing, so most
of what these tests prove is a NEGATIVE: that scrambling names, moving rows up
and down the block, and deleting the `OOC_` convention entirely all leave the
accepted coordinates untouched, while any damage to a coordinate CELL refuses
the row that carries it.

The multi-level fixture is the transcription supplied with the implementation
plan (an asteroid-base interior at Keeger). It is a transcription on purpose:
the screenshot it came from is temporary and is deliberately not copied into the
repository.
"""

from __future__ import annotations

import json

import pytest

import coordinate_stack as cs
import overlay_fields as fields
from scanner import NavPointScanner


def _row(text, kind="zone", trusted=True):
    return {"row": 0, "trusted": trusted, "kind": kind, "text": text}


# The motivating capture, innermost first, exactly as transcribed.
KEEGER = [
    _row("CamDir: 179 0 133 FOV: 55", kind="camdir"),
    _row("Zone: rs_int_layout_keeger_01 Pos: -386.02m 209.38m -437.00m"),
    _row("Zone: keeger_segment_social_001 Pos: 21.5842km -23.2325km 22.6220km"),
    _row("Zone: SolarSystem_753098466557 Pos: -45804302.9778km "
         "-14351319.5080km 29.3847km"),
    _row("Zone: Root Pos: -45804302.9778km -14351319.5080km 29.3847km"),
]


def _keeger(**replace):
    """The fixture with individual lines swapped out by index."""
    rows = [dict(r) for r in KEEGER]
    for index, text in replace.items():
        rows[index] = _row(text, kind=rows[index]["kind"],
                           trusted=rows[index]["trusted"])
    return rows


# --------------------------------------------------------------------------- #
# The supplied stack
# --------------------------------------------------------------------------- #

def test_the_supplied_stack_parses_and_keeps_every_row() -> None:
    stack, reason = fields.stack_from_rows(KEEGER)
    assert reason == ""
    assert stack is not None

    assert stack.root.xyz == pytest.approx(
        (-45804302977.8, -14351319508.0, 29384.7)
    )
    assert stack.solar.xyz == pytest.approx(stack.root.xyz)
    assert stack.solar.raw_name == "SolarSystem_753098466557"

    # Both nested rows survive, innermost first, with their own depths.
    assert [row.depth for row in stack.nested] == [0, 1]
    assert stack.nested[0].xyz == pytest.approx((-386.02, 209.38, -437.00))
    assert stack.nested[1].xyz == pytest.approx((21584.2, -23232.5, 22622.0))

    # The final element is the outermost pre-Solar row, and it is the candidate.
    assert stack.candidate_depth == 1
    assert stack.local_candidate is stack.nested[-1]


def test_camdir_is_not_part_of_the_stack() -> None:
    """CamDir describes capture-time view orientation, not a target address."""
    stack, _ = fields.stack_from_rows(KEEGER)
    raws = [row.raw for row in (stack.root, stack.solar, *stack.nested)]
    assert not any("CamDir" in raw for raw in raws)


def test_the_payload_carries_the_stack_for_a_space_capture() -> None:
    payload = fields.payload_from_rows(KEEGER)
    assert payload is not None
    assert payload["coordinate_stack"]["schema"] == cs.SCHEMA_VERSION
    assert len(payload["coordinate_stack"]["nested"]) == 2


# --------------------------------------------------------------------------- #
# Names have no authority
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("name", [
    "keeger_segment_social_001",     # as captured
    "?eeger_segment_social_00?",     # partly refused by the reader
    "totally_different_zone_name",   # renamed by a patch
    "?",                             # nothing readable but the shape
])
def test_a_nested_zone_name_never_changes_the_accepted_coordinates(name) -> None:
    rows = _keeger()
    rows[2] = _row(f"Zone: {name} Pos: 21.5842km -23.2325km 22.6220km")
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.nested[1].xyz == pytest.approx((21584.2, -23232.5, 22622.0))
    assert stack.candidate_depth == 1


def test_an_untrusted_row_still_contributes_its_coordinates() -> None:
    """`trusted` means no cell refused ANYWHERE in the row, including the name.

    One `?` in a ship's name used to discard a row whose coordinates were
    perfect, which is the defect the coordinate-tail split exists to remove.
    """
    rows = _keeger()
    rows[2] = _row("Zone: ?eeger_segment_social_001 Pos: 21.5842km "
                   "-23.2325km 22.6220km", trusted=False)
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.local_candidate.xyz == pytest.approx((21584.2, -23232.5, 22622.0))


def test_no_ooc_row_is_required() -> None:
    """Pyro names bodies without the prefix, so requiring it refused Pyro."""
    rows = [
        _row("Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"),
        _row("Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
        _row("Zone: SolarSystem_753098466557 Pos: 1000.0km 2000.0km 3000.0km"),
        _row("Zone: Root Pos: 1000.0km 2000.0km 3000.0km"),
    ]
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.local_candidate.xyz == pytest.approx(
        (330742.1, 218740.8, 119003.7)
    )
    assert not any("OOC" in row.raw for row in stack.nested)


# --------------------------------------------------------------------------- #
# Coordinate cells are the only thing that can refuse a row
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("broken, what", [
    ("Zone: keeger Pos: 21.58?2km -23.2325km 22.6220km", "a refused digit"),
    ("Zone: keeger Pos: 21.5842km ?23.2325km 22.6220km", "a refused sign"),
    ("Zone: keeger Pos: 21.5842km -23?2325km 22.6220km", "a refused decimal"),
    ("Zone: keeger Pos: 21.5842km -23.2325km 22.6220?m", "a refused unit"),
    ("Zone: keeger Pos: 21.5842km -23.2325km", "a truncated line"),
    ("Zone: keeger Pos:", "no coordinates at all"),
])
def test_a_damaged_coordinate_cell_refuses_that_row(broken, what) -> None:
    rows = _keeger()
    rows[2] = _row(broken)
    stack, reason = fields.stack_from_rows(rows)
    assert reason == "", what
    # The row contributed nothing, so the candidate is gone and Root still
    # carries the stack. Never the deeper row in its place.
    assert stack.candidate_depth is None, what
    assert stack.local_candidate is None, what
    assert [row.depth for row in stack.nested] == [0], what


def test_a_missing_unit_suffix_refuses_the_row() -> None:
    """A dropped 'k' is a silent factor-of-1000 error, never assumed metres."""
    rows = _keeger()
    rows[2] = _row("Zone: keeger Pos: 21.5842 -23.2325 22.6220")
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.local_candidate is None


# TWO INDEPENDENT LAYERS refuse a damaged coordinate cell: the row regex will
# not match a token carrying a `?` or missing its unit, and `token_to_m` will
# not convert one either. The tests above prove the OUTCOME, which both layers
# can produce alone, so mutating either one on its own escapes them. These two
# pin each layer separately, so a future relaxation of one is still caught.
@pytest.mark.parametrize("bad", [
    "21.58?2km", "?23.2325km", "23?2325km", "22.6220?m", "21.5842", "?",
])
def test_layer_one_the_row_regex_rejects_a_damaged_token(bad) -> None:
    text = f"Zone: keeger Pos: {bad} -23.2325km 22.6220km"
    assert fields._STACK_POS_RE.search(text) is None


def test_layer_one_the_row_regex_requires_a_unit_on_every_token() -> None:
    """Separate from the case above, where the two SURVIVING tokens keep their
    suffixes and would hold the line on their own."""
    assert fields._STACK_POS_RE.search(
        "Zone: keeger Pos: 21.5842 -23.2325 22.6220"
    ) is None


@pytest.mark.parametrize("bad", [
    "21.58?2km", "?23.2325km", "23?2325km", "22.6220?m", "21.5842", "?",
])
def test_layer_two_the_unit_conversion_rejects_a_damaged_token(bad) -> None:
    assert cs.token_to_m(bad) is None


@pytest.mark.parametrize("index, gate", [
    (3, fields.GATE_STACK_SOLAR_UNREADABLE),
    (4, fields.GATE_STACK_ROOT_UNREADABLE),
])
def test_a_damaged_anchor_refuses_the_whole_stack(index, gate) -> None:
    rows = _keeger()
    text = rows[index]["text"].replace("29.3847km", "29.38?7km")
    rows[index] = _row(text)
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(gate)


def test_a_deeper_row_is_never_promoted_around_a_failed_candidate() -> None:
    """The row-index rule keyed waypoints to furniture; this is that rule's
    only remaining door, and it is nailed shut."""
    rows = _keeger()
    rows[2] = _row("Zone: keeger Pos: ??.????km -23.2325km 22.6220km")
    stack, _ = fields.stack_from_rows(rows)
    assert stack.local_candidate is None
    # The room row IS still stored, for diagnosis; it is simply not routable.
    assert len(stack.nested) == 1
    assert stack.nested[0].raw_name == "rs_int_layout_keeger_01"


# --------------------------------------------------------------------------- #
# The two anchors
# --------------------------------------------------------------------------- #

def test_root_is_matched_exactly_and_root_cellar_is_not_the_anchor() -> None:
    rows = _keeger()
    rows[4] = _row("Zone: Root_Cellar Pos: -45804302.9778km "
                   "-14351319.5080km 29.3847km")
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_NO_ROOT)


@pytest.mark.parametrize("fragment", ["Ro?t", "Roo", "R00t", "rootzone"])
def test_a_fragmented_root_label_is_not_the_anchor(fragment) -> None:
    rows = _keeger()
    rows[4] = _row(f"Zone: {fragment} Pos: -45804302.9778km "
                   "-14351319.5080km 29.3847km")
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_NO_ROOT)


def test_a_missing_solar_row_refuses_the_stack() -> None:
    rows = _keeger()
    del rows[3]
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_NO_SOLAR)


def test_the_solar_suffix_is_opaque_and_need_not_be_a_known_system() -> None:
    rows = _keeger()
    rows[3] = _row("Zone: SolarSystem_000000000001 Pos: -45804302.9778km "
                   "-14351319.5080km 29.3847km")
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.solar.raw_name == "SolarSystem_000000000001"


def test_a_bare_solarsystem_label_with_no_id_is_not_the_anchor() -> None:
    rows = _keeger()
    rows[3] = _row("Zone: SolarSystem_ Pos: -45804302.9778km "
                   "-14351319.5080km 29.3847km")
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_NO_SOLAR)


@pytest.mark.parametrize("duplicate_index, of", [(2, 4), (2, 3)])
def test_a_duplicated_anchor_refuses_rather_than_guessing(duplicate_index, of) -> None:
    rows = _keeger()
    rows[duplicate_index] = _row(rows[of]["text"])
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_DUPLICATE_ANCHOR)


def test_solar_below_root_is_malformed_order() -> None:
    rows = _keeger()
    rows[3], rows[4] = rows[4], rows[3]
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_ORDER)


def test_a_zone_row_between_solar_and_root_is_malformed_order() -> None:
    rows = _keeger()
    rows.insert(4, _row("Zone: intruder Pos: 1.0m 2.0m 3.0m"))
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_ORDER)


def test_a_zone_row_below_root_is_malformed_order() -> None:
    rows = _keeger()
    rows.append(_row("Zone: intruder Pos: 1.0m 2.0m 3.0m"))
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_ORDER)


def test_solar_and_root_disagreement_refuses_schema_1() -> None:
    rows = _keeger()
    rows[4] = _row("Zone: Root Pos: -45804302.9778km -14351319.5080km 39.3847km")
    stack, reason = fields.stack_from_rows(rows)
    assert stack is None
    assert reason.startswith(fields.GATE_STACK_DISAGREE)


def test_solar_and_root_agreement_tolerates_the_printed_resolution() -> None:
    """A relative bound with an absolute floor, matching the space branch: at
    1e10 m the printed 0.1 m resolution is already near what the digits say."""
    rows = _keeger()
    rows[4] = _row("Zone: Root Pos: -45804302.9778km -14351319.5080km 29.3848km")
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack is not None


# --------------------------------------------------------------------------- #
# Shape independence
# --------------------------------------------------------------------------- #

def test_the_physical_row_positions_may_shift() -> None:
    """"First five lines" describes the common layout, not a row-index licence."""
    padding = [
        _row("Session: 0123456789abcdef", kind="session"),
        _row("ShardId: pub_sc_alpha_490_0000", kind="shard"),
    ]
    stack, reason = fields.stack_from_rows(padding + KEEGER)
    assert reason == ""
    assert stack.candidate_depth == 1
    assert len(stack.nested) == 2


def test_a_deep_space_stack_has_no_nested_row_and_no_candidate() -> None:
    rows = [
        _row("Zone: SolarSystem_753098466557 Pos: 1000.0km 2000.0km 3000.0km"),
        _row("Zone: Root Pos: 1000.0km 2000.0km 3000.0km"),
    ]
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack.nested == ()
    assert stack.local_candidate is None


def test_a_five_level_stack_keeps_every_level_in_order() -> None:
    rows = [
        _row("Zone: seat_pilot_01 Pos: 0.10m 0.20m 0.30m"),
        _row("Zone: DRAK_Clipper_742164815970 Pos: 0.00m 11.56m 2.83m"),
        _row("Zone: transit_carriage_004 Pos: 4.00m 5.00m 6.00m"),
        _row("Zone: Hangar_SmallFront_RestStop_Pyro Pos: 21.6m 1.0m 2.0m"),
        _row("Zone: pyro3 Pos: 330.7421km 218.7408km 119.0037km"),
        _row("Zone: SolarSystem_753098466557 Pos: 1000.0km 2000.0km 3000.0km"),
        _row("Zone: Root Pos: 1000.0km 2000.0km 3000.0km"),
    ]
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert [row.depth for row in stack.nested] == [0, 1, 2, 3, 4]
    assert stack.nested[0].raw_name == "seat_pilot_01"
    assert stack.local_candidate.raw_name == "pyro3"


def test_a_phantom_left_margin_glyph_does_not_hide_a_row() -> None:
    """A background star in the right-aligned block's blank left margin decodes
    as a glyph. Anchoring on `^Zone:` lost whole rows to it at P5 L2."""
    rows = _keeger()
    rows[3] = _row("?   " + rows[3]["text"])
    rows[4] = _row("?  " + rows[4]["text"])
    stack, reason = fields.stack_from_rows(rows)
    assert reason == ""
    assert stack is not None


# --------------------------------------------------------------------------- #
# Serialisation
# --------------------------------------------------------------------------- #

def test_the_stack_round_trips_through_json_exactly() -> None:
    stack, _ = fields.stack_from_rows(KEEGER)
    text = cs.to_json(stack)
    assert cs.from_json(text) == stack
    # Deterministic: the same stack always serialises to the same bytes.
    assert cs.to_json(cs.from_json(text)) == text
    # Compact and key-sorted, so the same stack is always the same bytes. The
    # raw diagnostic lines carry spaces of their own, so the separators are what
    # is checked rather than the absence of any space at all.
    assert text.startswith('{"candidate_depth":')
    assert '", "' not in text.replace('Pos: ', '')


def test_the_serialised_order_matches_the_observed_order() -> None:
    stack, _ = fields.stack_from_rows(KEEGER)
    obj = json.loads(cs.to_json(stack))
    assert [row["depth"] for row in obj["nested"]] == [0, 1]
    assert obj["nested"][0]["raw_name"] == "rs_int_layout_keeger_01"
    assert obj["candidate_depth"] == 1


@pytest.mark.parametrize("mutate", [
    lambda o: o.pop("root"),
    lambda o: o.pop("solar"),
    lambda o: o.update(schema=2),
    lambda o: o.update(schema="1"),
    lambda o: o["root"].pop("x_m"),
    lambda o: o["root"].update(x_m="12"),
    lambda o: o["root"].update(x_m=float("nan")),
    lambda o: o.update(nested="not a list"),
    lambda o: o["nested"][0].pop("depth"),
    lambda o: o.update(candidate_depth=99),
    lambda o: o.update(candidate_depth=True),
    lambda o: o["nested"].append(dict(o["nested"][0])),
])
def test_a_corrupt_record_decodes_to_none_rather_than_a_guess(mutate) -> None:
    stack, _ = fields.stack_from_rows(KEEGER)
    obj = json.loads(cs.to_json(stack))
    mutate(obj)
    assert cs.from_dict(obj) is None


@pytest.mark.parametrize("text", ["", "not json", "[]", "null", "{}", None, 7])
def test_unparseable_json_decodes_to_none(text) -> None:
    assert cs.from_json(text) is None


# --------------------------------------------------------------------------- #
# The mirrors, pinned to their originals
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("token", [
    "0.03m", "-174.2880km", "21.5842km", "+9810.08m", "99999999.9999km",
    "1m", "1km", "bad", "1", "1.0", "1.0kmx", "", None, "1.0KM",
])
def test_token_to_m_matches_the_scanner_it_mirrors(token) -> None:
    assert cs.token_to_m(token) == NavPointScanner._parse_length_m(token)


def test_the_crosscheck_constants_match_the_scanner_they_mirror() -> None:
    import scanner

    assert cs.SOLAR_ROOT_CROSSCHECK_REL == scanner._SYSTEM_CROSSCHECK_REL
    assert cs.SOLAR_ROOT_CROSSCHECK_MIN_M == scanner._SYSTEM_CROSSCHECK_MIN_M


def test_solar_root_agree_matches_the_space_branch_on_the_same_numbers() -> None:
    """One rule, two entry points: the space branch and the stack must not be
    able to disagree about whether a pair of anchors is corrupt."""
    scanner = NavPointScanner()
    for delta_km, expected in ((0.0, True), (0.0001, True), (10.0, False)):
        system = ["1000.0km", "2000.0km", "3000.0km"]
        root = ["1000.0km", "2000.0km", f"{3000.0 + delta_km}km"]
        legacy = scanner.parse_payload({
            "local_frame": False,
            "system_zone_id": "1",
            "system_pos_raw": system,
            "root_pos_raw": root,
        })
        rows = [
            _row(f"Zone: SolarSystem_1 Pos: {' '.join(system)}"),
            _row(f"Zone: Root Pos: {' '.join(root)}"),
        ]
        stack, _ = fields.stack_from_rows(rows)
        assert (legacy is not None) is expected
        assert (stack is not None) is expected

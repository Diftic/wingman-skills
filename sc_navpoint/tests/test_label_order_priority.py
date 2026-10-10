"""LABELS order is safety-bearing now that `row_kind` searches instead of anchors.

Under the anchored form the order was inert: no label is a prefix of another and
a row has one position 0, so at most one entry could ever match. Searching means
a row carrying TWO labels resolves by LIST PRIORITY, and `zone` is the only kind
that does not clear `overlay_fields.ooc_hypothesis_refuted`: every other kind is
in `_NOT_ZONE_KINDS` and short-circuits the gate to cleared. So the sole
gate-BLOCKING label has to sort first. Anywhere else is the fail-open direction,
and a cleared gate lets the reader conclude open space and store a system-frame
waypoint while the player stands on a rotating body, which is the 2026-07-11
failure that closed the stellar frame in the first place.

`test_row_label_search.py` covers the gain direction of that change thoroughly
and this direction not at all. This file is the counterweight.

PROVENANCE. Every row here is CONSTRUCTED, not observed: 0 of the 6609 decoded
rows in the capture corpus carry two labels, which is exactly why the ordering
cost nothing to fix and also why no real row can demonstrate it. The rows are
labelled below with whether they actually flip under the old order, measured
rather than assumed.
"""

from __future__ import annotations

import pytest

import overlay_fields as fields
import overlay_reader as ov


# CONSTRUCTED. Rows that carry both a `Zone:` and a `CamDir:` label, so their
# classification is decided by list priority alone. Both were confirmed to
# classify as `camdir` under the old order (`camdir` ahead of `zone`) and as
# `zone` under the current one, so each is a live negative control.
TWO_LABEL_ROWS = [
    # The camdir label leads positionally, behind a left-margin phantom.
    "? CamDir: Zone: OOC_Stanton_1_?? Pos: 1.0km 2.0km 3.0km",
    # The zone label leads positionally and the camdir label trails. Priority
    # decides, not position, so this must classify the same way as the row
    # above rather than by which label appears first in the text.
    "Zone: OOC_Pyro_1_?? Pos: 1.0km 2.0km 3.0km CamDir: 179   0  133",
]

# CONSTRUCTED, and NOT a negative control. This row appears in the reasoning
# above `LABELS` as the example of the risk, but its trailing `CamD` lost the
# colon, so `CamDir:` never matches it and it classifies as `zone` under BOTH
# orders. Measured, not assumed. It is kept because it pins the shape that
# motivated the reorder, but the two rows above are what would catch a revert.
TRUNCATED_CAMD_ROW = "Zone: OOC_Stanton_1_?????? Pos: 1?3.4567km -22.1?89km CamD"


def test_zone_sorts_ahead_of_every_other_label():
    """The sole gate-blocking kind must win every priority contest.

    Asserted as a property rather than against a copy of the list, so adding a
    sixth label stays legal while reordering the existing five does not.
    """
    kinds = [kind for kind, _ in ov.LABELS]
    assert "zone" in kinds, "the gate-blocking label vanished from LABELS"
    assert kinds[0] == "zone", (
        "a row carrying two labels resolves by list priority, so putting "
        f"{kinds[0]!r} ahead of 'zone' lets a Zone row clear the space-branch "
        "gate that exists to stop a system-frame waypoint on a rotating body"
    )


@pytest.mark.parametrize("text", TWO_LABEL_ROWS + [TRUNCATED_CAMD_ROW])
def test_a_row_carrying_two_labels_classifies_as_zone(text):
    assert ov.row_kind(text) == "zone"


@pytest.mark.parametrize("text", TWO_LABEL_ROWS + [TRUNCATED_CAMD_ROW])
def test_a_row_carrying_two_labels_still_blocks_the_space_branch(text):
    """The consequence, not the proxy.

    Classification is only interesting because of what the gate does with it.
    Each of these rows names a plausible `OOC_` token for a known system, so
    the gate cannot disprove the OOC hypothesis and the row must keep blocking.
    Classified as `camdir` instead, it clears the gate on its label alone and
    the token is never looked at.
    """
    kind = ov.row_kind(text)
    assert fields.ooc_hypothesis_refuted(kind, text) is False


def test_every_label_kind_except_zone_is_declared_not_zone():
    """The invariant that makes the ordering safe to reason about.

    Ordering only protects the gate while `zone` is the single kind that
    blocks it. A new label whose side nobody decided would sit outside both
    the ordering argument and the gate, so this fails until someone decides.
    """
    kinds = {kind for kind, _ in ov.LABELS}
    undeclared = kinds - {"zone"} - set(fields._NOT_ZONE_KINDS)
    assert not undeclared, (
        f"{sorted(undeclared)} are label kinds that neither block the space "
        "branch nor are declared in _NOT_ZONE_KINDS; decide which side each "
        "sits on"
    )
    assert "zone" not in fields._NOT_ZONE_KINDS, (
        "zone clearing the gate on its label alone defeats the gate entirely"
    )
    unknown = set(fields._NOT_ZONE_KINDS) - kinds
    assert not unknown, (
        f"{sorted(unknown)} are declared not-zone but no longer exist in "
        "LABELS, so the two lists have drifted"
    )

"""Curation and gateway-derivation rules in build_locations."""

from __future__ import annotations

import pytest

import build_locations


def _entity(
    name: str,
    system: str,
    *,
    qt_valid: bool = True,
    hidden: bool = False,
    type: str = "POI",
    x: float = 0.0,
    y: float = 0.0,
    z: float = 0.0,
) -> dict:
    return {
        "name": name,
        "system": system,
        "type": type,
        "qt_valid": qt_valid,
        "hidden": hidden,
        "x": x,
        "y": y,
        "z": z,
    }


def test_curation_filters_hidden_and_invalid_and_junk():
    entities = [
        _entity("Keep Me", "stanton"),
        _entity("Hidden One", "stanton", hidden=True),
        _entity("Not QT", "stanton", qt_valid=False),
        _entity("JumpPointTurrets", "stanton"),
        _entity("jumppointlocationsecurity-000", "pyro"),
    ]
    locations = build_locations.curate(entities)
    names = {loc["name"] for loc in locations}
    assert names == {"Keep Me"}


def test_unknown_system_id_fails_loudly():
    with pytest.raises(ValueError, match="Unknown system id"):
        build_locations.curate([_entity("Somewhere", "odin")])


def test_per_system_duplicate_name_raises():
    entities = [
        _entity("Twin", "stanton", x=1.0),
        _entity("Twin", "stanton", x=2.0),
    ]
    with pytest.raises(ValueError, match="Duplicate location name"):
        build_locations.curate(entities)


def test_same_name_across_systems_is_allowed():
    entities = [
        _entity("Stanton Gateway", "pyro"),
        _entity("Stanton Gateway", "nyx"),
    ]
    locations = build_locations.curate(entities)
    systems = sorted(loc["system"] for loc in locations)
    assert systems == ["Nyx", "Pyro"]


def test_gateway_links_derivation_and_terra_dead_end():
    # Fully-linked Stanton/Pyro plus a Terra Gateway with no Terra system.
    locations = build_locations.curate(
        [
            _entity("Pyro Gateway", "stanton"),
            _entity("Terra Gateway", "stanton"),
            _entity("Stanton Gateway", "pyro"),
            _entity("Lorville", "stanton"),
        ]
    )
    links = build_locations.derive_gateway_links(locations)
    assert links == [
        {
            "system_a": "Pyro",
            "gateway_a": "Stanton Gateway",
            "system_b": "Stanton",
            "gateway_b": "Pyro Gateway",
        }
    ]
    # Terra Gateway stays a plain location, no link derived for it.
    assert any(loc["name"] == "Terra Gateway" for loc in locations)


def test_gateway_link_requires_reciprocal():
    # Stanton names a Pyro Gateway but Pyro has no Stanton Gateway back.
    locations = build_locations.curate(
        [
            _entity("Pyro Gateway", "stanton"),
            _entity("Some Pyro POI", "pyro"),
        ]
    )
    assert build_locations.derive_gateway_links(locations) == []


def test_build_dataset_shape_and_metadata():
    raw = {
        "entities": [
            _entity("Pyro Gateway", "stanton", x=1.0),
            _entity("Stanton Gateway", "pyro", x=2.0),
            _entity("Lorville", "stanton"),
        ],
        "connections": [],
    }
    dataset = build_locations.build_dataset(raw, "deadbeef")
    meta = dataset["metadata"]
    assert meta["source_sha256"] == "deadbeef"
    assert meta["location_count"] == 3
    assert meta["system_counts"] == {"Stanton": 2, "Pyro": 1, "Nyx": 0}
    # Locations sorted by (system, name) for stable diffs.
    ordered = [(loc["system"], loc["name"]) for loc in dataset["locations"]]
    assert ordered == sorted(ordered)
    assert len(dataset["gateway_links"]) == 1
    assert dataset["aliases"] == {}

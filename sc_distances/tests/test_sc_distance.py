"""Name lookup and distance maths, on a small made-up system with known geometry."""

from __future__ import annotations

import math

import pytest

from sc_data import validate_system
from sc_distance import DATA_DIR, LookupError_, describe, distance, find, km_text, load_dir


def _system(name: str, solar: dict, planetary: dict | None = None) -> dict:
    return {"system": name, "format": 1, "revision": 1, "solar": {"locations": solar},
            "planetary": planetary or {}, "lunar": {}}


@pytest.fixture
def systems() -> dict[str, dict]:
    alpha = _system(
        "Alpha",
        {
            "Alpha": {"type": "star", "pos_km": [0, 0, 0], "from_star_km": 0},
            "Rock": {"type": "planet", "pos_km": [1000, 0, 0], "radius_km": 10, "orbits": "Alpha",
                     "from_star_km": 1000},
            "Port": {"type": "station", "pos_km": [1000, 0, 50], "from_star_km": 1001},
            "Gate": {"type": "station", "pos_km": [0, 5000, 0], "from_star_km": 5000},
            "ARC-L1 Wide Forest Station": {"type": "station", "pos_km": [2000, 0, 0], "from_star_km": 2000},
        },
        {"Rock": {"radius_km": 10, "orbits": "Alpha", "locations": {
            "Town": {"type": "outpost", "pos_km": [10, 0, 0], "altitude_km": 0},
            "Camp": {"type": "outpost", "pos_km": [0, 10, 0], "altitude_km": 0},
        }}},
    )
    beta = _system("Beta", {
        "Beta": {"type": "star", "pos_km": [0, 0, 0], "from_star_km": 0},
        "Gate": {"type": "station", "pos_km": [300, 400, 0], "from_star_km": 500},
        "Hub": {"type": "station", "pos_km": [0, 0, 0], "from_star_km": 0},
    })
    return {"Alpha": alpha, "Beta": beta}


def test_same_body_gives_straight_line_and_over_ground(systems):
    res = distance(systems, "Town", "Camp")
    assert res["straight_km"] == pytest.approx(math.hypot(10, 10), abs=0.1)
    assert res["over_ground_km"] == pytest.approx(10 * math.pi / 2, abs=0.1)


def test_space_to_space_is_exact(systems):
    res = distance(systems, "Port", "Gate", "Alpha")
    assert res["straight_km"] == round(math.dist([1000, 0, 50], [0, 5000, 0]))


def test_surface_to_space_is_a_range_around_the_body_centre(systems):
    res = distance(systems, "Town", "Gate")
    d = math.dist([1000, 0, 0], [0, 5000, 0])
    assert res["centre_to_centre_km"] == round(d)
    assert (res["min_km"], res["max_km"]) == (round(d - 10), round(d + 10))
    assert "depending on the body's rotation" in describe(res)


def test_surface_to_own_body_is_the_distance_to_its_centre(systems):
    assert distance(systems, "Town", "Rock")["straight_km"] == 10


def test_names_match_without_case_spaces_or_punctuation(systems):
    assert [loc.name for loc in find(systems, "arc l1")] == ["ARC-L1 Wide Forest Station"]
    assert [loc.name for loc in find(systems, "TOWN")] == ["Town"]


def test_a_name_in_two_systems_takes_the_other_locations_system(systems):
    res = distance(systems, "Gate", "Hub")
    assert res["from"] == "Gate [Beta]"
    assert res["straight_km"] == 500


def test_ambiguous_names_are_reported(systems):
    with pytest.raises(LookupError_, match="matches 2 locations"):
        distance(systems, "Gate", "Gate")


def test_locations_in_different_systems_have_no_distance(systems):
    with pytest.raises(LookupError_, match="different systems"):
        distance(systems, "Town", "Hub")


def test_unknown_name_is_reported(systems):
    with pytest.raises(LookupError_, match="No location matches"):
        distance(systems, "Nowhere", "Town")


def test_km_text_reads_well_at_every_scale():
    assert km_text(3.44) == "3.4 km"
    assert km_text(1174.4) == "1,174 km"
    assert km_text(39_653_165) == "39,653,165 km (39.7 million km)"


def test_bundled_data_files_validate_and_load():
    for path in DATA_DIR.glob("*.json"):
        if path.name != "index.json":
            validate_system(path.read_bytes())
    assert {"Stanton", "Pyro", "Nyx"} <= set(load_dir())

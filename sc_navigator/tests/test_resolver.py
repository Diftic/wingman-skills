"""Location resolution: exact, normalized, alias, substring, ambiguity."""

from __future__ import annotations

from sc_nav_route_optimizer import AMBIGUOUS, MATCHED, NOT_FOUND


def _sample(loc):
    return [
        loc("Lorville", "Stanton"),
        loc("Area18", "Stanton"),
        loc("Grim HEX", "Stanton"),
        loc("New Babbage", "Stanton"),
        loc("ARC-L1 Wallace Klim", "Stanton"),
        loc("Stanton Gateway", "Pyro"),
        loc("Stanton Gateway", "Nyx"),
    ]


def test_exact_name(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    result = opt.resolve_location("Lorville")
    assert result.status == MATCHED
    assert result.location.display_key == "Lorville"


def test_case_insensitive_normalized(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    assert opt.resolve_location("new babbage").location.name == "New Babbage"


def test_normalized_strips_punctuation_and_spaces(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    assert opt.resolve_location("area 18").location.name == "Area18"
    assert opt.resolve_location("grimhex").location.name == "Grim HEX"


def test_unique_substring(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    result = opt.resolve_location("arc-l1")
    assert result.status == MATCHED
    assert result.location.name == "ARC-L1 Wallace Klim"


def test_alias_map(loc, build_optimizer):
    opt = build_optimizer(
        _sample(loc), aliases={"olisar": "New Babbage"}
    )
    result = opt.resolve_location("Olisar")
    assert result.status == MATCHED
    assert result.location.name == "New Babbage"


def test_ambiguous_cross_system_name(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    result = opt.resolve_location("Stanton Gateway")
    assert result.status == AMBIGUOUS
    assert result.candidates == [
        "Stanton Gateway (Nyx)",
        "Stanton Gateway (Pyro)",
    ]


def test_system_argument_disambiguates(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    result = opt.resolve_location("Stanton Gateway", system="Pyro")
    assert result.status == MATCHED
    assert result.location.display_key == "Stanton Gateway (Pyro)"


def test_exact_display_key_resolves(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    result = opt.resolve_location("Stanton Gateway (Nyx)")
    assert result.status == MATCHED
    assert result.location.system == "Nyx"


def test_not_found(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    assert opt.resolve_location("zzz nowhere").status == NOT_FOUND


def test_system_filter_empty_pool_is_not_found(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    assert opt.resolve_location("Lorville", system="Pyro").status == NOT_FOUND


def test_find_locations_shape_and_filter(loc, build_optimizer):
    opt = build_optimizer(_sample(loc))
    matches = opt.find_locations("gateway")
    assert matches == [
        {"name": "Stanton Gateway (Nyx)", "system": "Nyx"},
        {"name": "Stanton Gateway (Pyro)", "system": "Pyro"},
    ]
    only_pyro = opt.find_locations("gateway", system="Pyro")
    assert only_pyro == [{"name": "Stanton Gateway (Pyro)", "system": "Pyro"}]

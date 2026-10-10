"""Tests for locating factory lines/machines and rendering location maps."""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from factory_games.satisfactory.handler.pipeline import build_locate_lines
from factory_games.satisfactory.handler.locate import (
    LocationHit,
    _world_to_terrain_px,
    find_locations,
    find_map_locations,
    render_map,
)


def _line(line_id: str, item: str, rate: float, machine_count: int, x: float, y: float) -> dict:
    return {
        "id": line_id,
        "machineCount": machine_count,
        "confidence": "probable",
        "primaryOutput": {"item": item, "ratePerMin": rate},
        "centroid": {"x": x, "y": y, "z": 0.0},
        "grossInputs": [],
        "grossOutputs": [],
        "machineIds": [],
    }


def _machine(
    machine_id: str,
    recipe: str,
    resource: str,
    machine_type: str,
    clock: float,
    x: float,
    y: float,
) -> dict:
    return {
        "id": machine_id,
        "type": machine_type,
        "location": {"x": x, "y": y, "z": 0.0},
        "recipe": recipe,
        "resource": resource,
        "clock": clock,
    }


def _mirror() -> dict:
    return {
        "lines": [
            _line("line_0001", "Iron Ingot", 270.0, 4, 1000.0, 0.0),
            _line("line_0002", "Iron Plate", 60.0, 2, -2000.0, 500.0),
        ],
        "machines": [
            _machine("m1", "Recipe_IngotIron_C", "", "Build_SmelterMk1_C", 1.0, 1000.0, 0.0),
            _machine("m2", "", "Desc_OreIron_C", "Build_MinerMk1_C", 2.0, 3000.0, -1500.0),
            _machine("m3", "Recipe_IronPlate_C", "", "Build_ConstructorMk1_C", 1.0, -2000.0, 500.0),
        ],
    }


# --- find_locations -----------------------------------------------------------


def test_find_locations_ranks_exact_before_prefix_before_substring() -> None:
    mirror = _mirror()

    hits = find_locations(mirror, "iron ingot")

    assert hits[0].label == "Iron Ingot line"
    assert hits[0].kind == "line"


def test_find_locations_prefix_and_substring_both_match() -> None:
    mirror = _mirror()

    hits = find_locations(mirror, "iron")

    labels = {hit.label for hit in hits}
    assert "Iron Ingot line" in labels
    assert "Iron Plate line" in labels
    assert "Recipe_IngotIron_C" in labels


def test_find_locations_matches_machine_recipe_resource_and_type() -> None:
    mirror = _mirror()

    by_recipe = find_locations(mirror, "IngotIron")
    by_resource = find_locations(mirror, "OreIron")
    by_type = find_locations(mirror, "MinerMk1")

    assert any(hit.label == "Recipe_IngotIron_C" for hit in by_recipe)
    assert any(hit.label == "Desc_OreIron_C" for hit in by_resource)
    # A machine-type query uses the official player-facing building name even
    # when the mirror also carries a resource class.
    assert any(hit.label == "Miner Mk.1" for hit in by_type)


def test_find_locations_line_carries_machine_count_not_clock() -> None:
    mirror = _mirror()

    hits = find_locations(mirror, "Iron Ingot")

    line_hit = next(hit for hit in hits if hit.kind == "line")
    assert line_hit.machine_count == 4
    assert line_hit.clock is None


def test_find_locations_machine_carries_clock_not_machine_count() -> None:
    mirror = _mirror()

    hits = find_locations(mirror, "IngotIron")

    machine_hit = next(hit for hit in hits if hit.kind == "machine")
    assert machine_hit.clock == 1.0
    assert machine_hit.machine_count is None


def test_find_locations_limit_clamped_to_five() -> None:
    mirror = {
        "lines": [
            _line(f"line_{i:04d}", "Widget", 60.0, 2, float(i * 100), 0.0) for i in range(10)
        ],
        "machines": [],
    }

    hits = find_locations(mirror, "widget", limit=100)

    assert len(hits) == 5


def test_map_locations_can_include_more_than_response_limit() -> None:
    mirror = {
        "lines": [],
        "machines": [
            _machine(f"pump-{i}", "", "", "Build_OilPump", 1.0, i * 100.0, 0.0)
            for i in range(12)
        ],
    }

    assert len(find_locations(mirror, "oil extractors")) == 5
    assert len(find_map_locations(mirror, "oil extractors")) == 12


def test_find_locations_respects_smaller_limit() -> None:
    mirror = _mirror()

    hits = find_locations(mirror, "iron", limit=1)

    assert len(hits) == 1


def test_find_locations_empty_query_returns_empty_tuple() -> None:
    mirror = _mirror()

    assert find_locations(mirror, "") == ()
    assert find_locations(mirror, "   ") == ()


def test_find_locations_no_match_returns_empty_tuple() -> None:
    mirror = _mirror()

    assert find_locations(mirror, "zzz_nothing_here") == ()


def test_oilfield_language_resolves_unresolved_oil_pumps_as_extractors() -> None:
    mirror = {
        "lines": [_line("oil", "Crude Oil", 120.0, 2, 5000.0, 2000.0)],
        "machines": [
            _machine(
                "pump",
                "",
                "Persistent_Level:PersistentLevel",
                "Build_OilPump",
                2.5,
                1000.0,
                2000.0,
            )
        ],
    }

    for query in ("oilfields", "oil field", "oil nodes", "oil extractors"):
        hits = find_locations(mirror, query)
        assert hits
        assert hits[0].label == "Oil Extractor"
        assert hits[0].kind == "machine"


def test_oilless_extractor_transcription_resolves_to_oil_extractors() -> None:
    mirror = {
        "lines": [_line("oil", "Crude Oil", 120.0, 2, 5000.0, 2000.0)],
        "machines": [
            _machine("pump", "", "", "Build_OilPump", 1.0, 1000.0, 2000.0)
        ],
    }

    hits = find_locations(mirror, "oilless extractor")

    assert hits
    assert hits[0].label == "Oil Extractor"
    assert all(hit.kind == "machine" for hit in hits)


def test_nitrogen_extraction_selects_only_nitrogen_resource_wells() -> None:
    mirror = {
        "lines": [_line("nitrogen", "Nitrogen Gas", 120.0, 3, 5000.0, 2000.0)],
        "machines": [
            _machine("n", "", "Desc_NitrogenGas", "Build_FrackingExtractor", 2.5, 1, 1),
            _machine("w", "", "Desc_Water", "Build_FrackingExtractor", 2.5, 2, 2),
            _machine("o", "", "Desc_LiquidOil", "Build_FrackingExtractor", 2.5, 3, 3),
            _machine(
                "p",
                "Recipe_PackagedNitrogen",
                "",
                "Build_Packager",
                2.5,
                4,
                4,
            ),
        ],
    }

    for query in ("nitrogen extractor", "nitrogen extraction", "nitrogen gas extractors"):
        hits = find_map_locations(mirror, query)
        assert len(hits) == 1
        assert hits[0].label == "Nitrogen Gas Resource Well Extractor"
        assert hits[0].kind == "machine"


@pytest.mark.parametrize(
    ("machine_type", "query", "expected_label"),
    [
        ("Build_ConstructorMk1", "constructors", "Constructor"),
        ("Build_AssemblerMk1", "assemblers", "Assembler"),
        ("Build_ManufacturerMk1", "manufacturers", "Manufacturer"),
        ("Build_OilRefinery", "refineries", "Refinery"),
        ("Build_Blender", "blenders", "Blender"),
        ("Build_HadronCollider", "particle accelerators", "Particle Accelerator"),
        ("Build_WaterPump", "water extractors", "Water Extractor"),
        (
            "Build_FrackingSmasher",
            "resource well pressurizers",
            "Resource Well Pressurizer",
        ),
        ("Build_QuantumEncoder", "quantum encoders", "Quantum Encoder"),
    ],
)
def test_manufacturing_type_aliases_handle_player_names_and_plurals(
    machine_type: str,
    query: str,
    expected_label: str,
) -> None:
    mirror = {
        "lines": [],
        "machines": [
            _machine("m", "", "Persistent_Level:PersistentLevel", machine_type, 1.0, 0, 0)
        ],
    }

    hits = find_locations(mirror, query)

    assert hits
    assert hits[0].label == expected_label


def test_find_locations_skips_entries_missing_coordinates() -> None:
    mirror = {
        "lines": [{"id": "line_0001", "primaryOutput": {"item": "Iron Ingot"}, "centroid": {}}],
        "machines": [{"id": "m1", "recipe": "Recipe_IngotIron_C", "location": None}],
    }

    assert find_locations(mirror, "iron") == ()


# --- render_map ----------------------------------------------------------------


def _sample_hits() -> tuple[LocationHit, ...]:
    return (
        LocationHit(label="Iron Ingot line", kind="line", x=1000.0, y=0.0, z=0.0, machine_count=4),
        LocationHit(
            label="Recipe_IngotIron_C", kind="machine", x=1000.0, y=0.0, z=0.0, clock=1.0
        ),
    )


def _sample_points() -> tuple[tuple[float, float], ...]:
    return ((1000.0, 0.0), (3000.0, -1500.0), (-2000.0, 500.0))


def test_render_map_is_deterministic_across_identical_renders(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"

    first_ok = render_map(_sample_hits(), _sample_points(), first_path)
    second_ok = render_map(_sample_hits(), _sample_points(), second_path)

    assert first_ok is True
    assert second_ok is True
    assert first_path.read_bytes() == second_path.read_bytes()


def test_render_map_writes_a_valid_png(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    out_path = tmp_path / "map.png"

    ok = render_map(_sample_hits(), _sample_points(), out_path)

    assert ok is True
    assert out_path.is_file()
    assert out_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    from PIL import Image

    with Image.open(out_path) as image:
        assert image.size == (1024, 1024)


def test_world_to_terrain_pixels_uses_satisfactory_y_down_orientation() -> None:
    north_west = _world_to_terrain_px(-324_698.832031, -375_000.0, 1000, 1000)
    south_east = _world_to_terrain_px(425_301.832031, 375_000.0, 1000, 1000)

    assert north_west == pytest.approx((0.0, 0.0))
    assert south_east == pytest.approx((999.0, 999.0))


def test_render_map_uses_geographic_background_when_configured(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    terrain_path = tmp_path / "terrain.png"
    terrain = Image.new("RGB", (1000, 1000), color=(200, 30, 30))
    ImageDraw.Draw(terrain).rectangle((0, 500, 999, 999), fill=(30, 60, 200))
    terrain.save(terrain_path)
    out_path = tmp_path / "geographic.png"
    corner_hits = (
        LocationHit("North-west", "machine", -324_698.832031, -375_000.0, 0.0),
        LocationHit("South-east", "machine", 425_301.832031, 375_000.0, 0.0),
    )

    ok = render_map(corner_hits, (), out_path, terrain_path=terrain_path)

    assert ok is True
    with Image.open(out_path) as rendered:
        assert rendered.getpixel((512, 100)) == pytest.approx((200, 30, 30), abs=5)
        assert rendered.getpixel((512, 900)) == pytest.approx((30, 60, 200), abs=5)


def test_render_map_handles_empty_hits_and_points(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    out_path = tmp_path / "empty.png"

    ok = render_map((), (), out_path)

    assert ok is True
    assert out_path.is_file()


def test_render_map_returns_false_when_pillow_unavailable(tmp_path: Path, monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "PIL":
            raise ImportError("PIL is not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out_path = tmp_path / "should_not_exist.png"

    ok = render_map(_sample_hits(), _sample_points(), out_path)

    assert ok is False
    assert not out_path.exists()


# --- build_locate_lines containment (satisfactory_adapter wiring) --------------


def _write_mirror(workspace_dir: Path, mirror: dict) -> None:
    import json

    mirror_dir = workspace_dir / "mirror"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    (mirror_dir / "latest_mirror.json").write_text(json.dumps(mirror), encoding="utf-8")


def test_build_locate_lines_hostile_query_slug_is_contained(tmp_path: Path) -> None:
    _write_mirror(tmp_path, _mirror())
    hostile_query = "../../../../etc/passwd iron"

    build_locate_lines(tmp_path, hostile_query)

    assert not (tmp_path.parent / "etc").exists()
    artifacts = list((tmp_path / "mirror").glob("location_*.png"))
    for artifact_path in artifacts:
        assert artifact_path.resolve().is_relative_to(tmp_path.resolve())
        assert artifact_path.is_file()


def test_build_locate_lines_absent_mirror_explains(tmp_path: Path) -> None:
    lines = build_locate_lines(tmp_path, "iron")

    assert len(lines) == 1
    assert "haven't finished reading the current save" in lines[0]
    assert "save the game once" in lines[0]


def test_build_locate_lines_no_match_explains(tmp_path: Path) -> None:
    _write_mirror(tmp_path, _mirror())

    lines = build_locate_lines(tmp_path, "zzz_no_such_thing")

    assert len(lines) == 1
    assert "couldn't find" in lines[0]
    assert "current save" in lines[0]

"""Tests for locating factory lines/machines and rendering the schematic map."""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from satisfactory_adapter import build_locate_lines
from satisfactory_map import LocationHit, find_locations, render_map


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
    # m2 has no recipe, so its label falls back to its resource field even
    # when the match came from its machine-type field.
    assert any(hit.label == "Desc_OreIron_C" for hit in by_type)


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

    lines = build_locate_lines(tmp_path, hostile_query)
    result = "\n".join(lines)

    assert not (tmp_path.parent / "etc").exists()
    if "Map artifact:" in result and "unavailable" not in result:
        artifact_line = next(line for line in lines if line.startswith("Map artifact:"))
        artifact_path = Path(artifact_line.split("Map artifact:", 1)[1].strip())
        assert artifact_path.resolve().is_relative_to(tmp_path.resolve())
        assert artifact_path.is_file()


def test_build_locate_lines_absent_mirror_explains(tmp_path: Path) -> None:
    lines = build_locate_lines(tmp_path, "iron")

    assert len(lines) == 1
    assert "no factory mirror yet" in lines[0]
    assert "audit" in lines[0]


def test_build_locate_lines_no_match_explains(tmp_path: Path) -> None:
    _write_mirror(tmp_path, _mirror())

    lines = build_locate_lines(tmp_path, "zzz_no_such_thing")

    assert len(lines) == 1
    assert "no matching lines or machines" in lines[0]

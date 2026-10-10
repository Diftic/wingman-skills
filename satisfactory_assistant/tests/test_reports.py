"""Tests for plan artifact exports (satisfactory_reports)."""

from __future__ import annotations

import json
from pathlib import Path

from satisfactory_plan_models import (
    DataProvenance,
    Diagnostic,
    FactoryMasterPlan,
    ItemFlow,
    PowerPlan,
    ProcessNode,
    RecipePolicy,
    ResourceSource,
    StagePlan,
    stage_plan_from_payload,
)
from satisfactory_reports import (
    export_stage_artifacts,
    master_plan_summary_markdown,
    stage_plan_to_json,
    stage_plan_to_markdown,
)


_SECTION_ORDER = (
    "## Summary",
    "## Demands",
    "## Production",
    "## Resource Sources",
    "## Flows",
    "## Power",
    "## Diagnostics",
    "## Assumptions",
    "## Provenance",
)


def _sample_stage_plan() -> StagePlan:
    return StagePlan(
        phase=2,
        window_hours=12.0,
        pace_multiplier=1.5,
        demands=(
            ("Desc_IronPlate_C", 100.0, 8.33),
            ("Desc_Screw_C", 50.0, 4.167),
        ),
        nodes=(
            ProcessNode(
                node_id="node_1",
                recipe_class="Recipe_IronPlate_C",
                building_class="Build_ConstructorMk1_C",
                runs_per_min=30.0,
                machine_count_exact=2.5,
                machine_count=3,
                clock=100.0,
                power_mw=12.0,
            ),
            ProcessNode(
                node_id="node_2",
                recipe_class="Recipe_Screw_C",
                building_class="Build_ConstructorMk1_C",
                runs_per_min=40.0,
                machine_count_exact=1.25,
                machine_count=2,
                clock=125.0,
                power_mw=8.0,
            ),
        ),
        sources=(
            ResourceSource(
                node_id="source_1",
                item_class="Desc_OreIron_C",
                rate_per_min=480.0,
                extractor_class="Build_MinerMk2_C",
                extractor_count=2,
            ),
        ),
        flows=(
            ItemFlow(
                item_class="Desc_IronPlate_C",
                rate_per_min=60.0,
                source_id="node_1",
                dest_id="external_demand",
            ),
            ItemFlow(
                item_class="Desc_OreIron_C",
                rate_per_min=480.0,
                source_id="raw_import",
                dest_id="node_1",
            ),
            ItemFlow(
                item_class="Desc_Screw_C",
                rate_per_min=40.0,
                source_id="node_2",
                dest_id="node_1",
            ),
        ),
        power=PowerPlan(total_mw=20.0, by_building=(("Build_ConstructorMk1_C", 20.0),)),
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(
            Diagnostic(
                severity="warning",
                code="low_power",
                message="Power margin thin",
                subject="Phase 2",
            ),
        ),
        assumptions=("Base tiers only",),
        provenance=DataProvenance(
            source="Docs.json", retrieved="2026-07-01T00:00:00", note="bundled catalog"
        ),
        solver_run_id="run_1",
        revision=1,
        created_at="2026-07-01T00:00:00",
    )


def _empty_stage_plan() -> StagePlan:
    return StagePlan(
        phase=1,
        window_hours=0.0,
        pace_multiplier=1.0,
        demands=(),
        nodes=(),
        sources=(),
        flows=(),
        power=PowerPlan(total_mw=0.0, by_building=()),
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="", retrieved="", note=""),
        solver_run_id=None,
        revision=0,
        created_at="2026-07-01T00:00:00",
    )


# --- JSON export ---


def test_stage_plan_to_json_round_trips() -> None:
    original = _sample_stage_plan()
    payload = json.loads(stage_plan_to_json(original))
    assert stage_plan_from_payload(payload) == original


def test_stage_plan_to_json_is_sorted_and_pretty() -> None:
    text = stage_plan_to_json(_sample_stage_plan())
    assert text.startswith("{\n  \"")
    lines = list(json.loads(text).keys())
    assert lines == sorted(lines)


# --- Markdown determinism and structure ---


def test_stage_plan_to_markdown_is_deterministic() -> None:
    stage = _sample_stage_plan()
    assert stage_plan_to_markdown(stage) == stage_plan_to_markdown(stage)


def test_stage_plan_to_markdown_section_order() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    positions = [text.index(section) for section in _SECTION_ORDER]
    assert positions == sorted(positions)


def test_stage_plan_to_markdown_title_line() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    assert text.startswith("# Stage Plan - Phase 2 (Revision 1)")


def test_stage_plan_to_markdown_key_content_present() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    for expected in (
        "Desc_IronPlate_C",
        "Desc_Screw_C",
        "node_1",
        "node_2",
        "Recipe_IronPlate_C",
        "Build_ConstructorMk1_C",
        "source_1",
        "Build_MinerMk2_C",
        "[WARNING] low_power: Power margin thin (subject: Phase 2)",
        "Base tiers only",
        "Docs.json",
        "run_1",
    ):
        assert expected in text


def test_stage_plan_to_markdown_numeric_formatting() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    # Rates/MW to 3 decimals.
    assert "8.330" in text
    assert "4.167" in text
    assert "12.000" in text
    assert "20.000" in text
    # Clocks to 4 decimals.
    assert "100.0000" in text
    assert "125.0000" in text


def test_stage_plan_to_markdown_flows_summary_grouping() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    assert "External demand satisfied: Desc_IronPlate_C 60.000/min" in text
    assert "Raw imports: Desc_OreIron_C 480.000/min" in text
    assert "Internal edges: 1" in text


def test_stage_plan_to_markdown_is_ascii_and_em_dash_free() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    assert all(ord(char) < 128 for char in text)
    # 0x2014 is the Unicode em-dash code point; checked numerically to avoid
    # embedding the literal glyph in this ASCII-only source file.
    assert chr(0x2014) not in text


def test_stage_plan_to_markdown_no_trailing_whitespace() -> None:
    text = stage_plan_to_markdown(_sample_stage_plan())
    for line in text.splitlines():
        assert line == line.rstrip()


# --- Empty-collections stage ---


def test_empty_stage_plan_renders_without_crashing() -> None:
    text = stage_plan_to_markdown(_empty_stage_plan())
    assert text.count("(none)") >= 6
    assert "Solver run: none" in text
    assert "External demand satisfied: none" in text
    assert "Raw imports: none" in text
    assert "Internal edges: 0" in text
    assert "Top building classes: none" in text
    for line in text.splitlines():
        assert line == line.rstrip()


def test_empty_stage_plan_json_round_trips() -> None:
    original = _empty_stage_plan()
    payload = json.loads(stage_plan_to_json(original))
    assert stage_plan_from_payload(payload) == original


# --- Export to workspace ---


def test_export_stage_artifacts_writes_both_files(tmp_path: Path) -> None:
    stage = _sample_stage_plan()
    paths = export_stage_artifacts(tmp_path, "My Plan", stage)

    markdown_path = Path(paths["markdown_path"])
    json_path = Path(paths["json_path"])
    assert markdown_path.is_file()
    assert json_path.is_file()
    assert markdown_path.resolve().is_relative_to(tmp_path.resolve())
    assert json_path.resolve().is_relative_to(tmp_path.resolve())
    assert markdown_path.name == "phase2_rev1.md"
    assert json_path.name == "phase2_rev1.json"
    assert "my-plan" in str(markdown_path.parent.name)

    assert markdown_path.read_text(encoding="utf-8") == stage_plan_to_markdown(stage)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert stage_plan_from_payload(payload) == stage


def test_export_stage_artifacts_hostile_plan_id_is_contained(tmp_path: Path) -> None:
    stage = _sample_stage_plan()
    hostile_id = "../../../../etc/passwd"
    paths = export_stage_artifacts(tmp_path, hostile_id, stage)

    markdown_path = Path(paths["markdown_path"]).resolve()
    json_path = Path(paths["json_path"]).resolve()
    assert markdown_path.is_relative_to(tmp_path.resolve())
    assert json_path.is_relative_to(tmp_path.resolve())
    assert not (tmp_path.parent / "etc").exists()
    assert markdown_path.is_file()
    assert json_path.is_file()


# --- Master plan summary ---


def test_master_plan_summary_markdown_one_row_per_stage() -> None:
    plan = FactoryMasterPlan(
        plan_id="plan_1",
        name="Phase 2 assembly",
        created_at="2026-07-01T00:00:00",
        updated_at="2026-07-01T00:00:00",
    )
    stage_a = _sample_stage_plan()
    stage_b = _empty_stage_plan()
    text = master_plan_summary_markdown(plan, (stage_a, stage_b))

    lines = [line for line in text.splitlines() if line.startswith("|") and "---" not in line]
    # One header row plus one row per stage.
    assert len(lines) == 1 + 2
    assert "| 2 | 1 |" in text
    assert "| 1 | 0 |" in text


def test_master_plan_summary_markdown_empty_stages() -> None:
    plan = FactoryMasterPlan(
        plan_id="plan_1",
        name="Empty plan",
        created_at="2026-07-01T00:00:00",
        updated_at="2026-07-01T00:00:00",
    )
    text = master_plan_summary_markdown(plan, ())
    assert "(none)" in text

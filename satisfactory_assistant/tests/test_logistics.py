"""Tests for belt/pipe capacity checks and byproduct surplus detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog, normalize_class_name
from satisfactory_extraction import plan_extraction
from satisfactory_install import discover_docs
from satisfactory_logistics import check_logistics
from satisfactory_plan_models import ProcessNode, ResourceSource
from satisfactory_progression import (
    CapabilitySnapshot,
    build_capability_snapshot,
    derive_phase_demand,
    load_project_assembly_phases,
)
from satisfactory_solver import schedule_machines, solve_stage


def _amount(class_name: str, amount: float) -> str:
    return (
        f'(ItemClass="/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/'
        f'Resource/Parts/X/Desc_X.{class_name}\'",Amount={amount})'
    )


def _amounts(entries: list[tuple[str, float]]) -> str:
    return "(" + ",".join(_amount(class_name, amount) for class_name, amount in entries) + ")"


def _produced_in(building_class: str) -> str:
    return f'("/Game/FactoryGame/Buildable/Factory/X/{building_class}.{building_class}")'


def _recipe_refs(*names: str) -> str:
    return "(" + ",".join(f'"{name}"' for name in names) + ")"


def _recipe(
    class_name: str,
    display_name: str,
    ingredients: list[tuple[str, float]],
    products: list[tuple[str, float]],
    building_class: str,
) -> dict:
    return {
        "ClassName": class_name,
        "mDisplayName": display_name,
        "mIngredients": _amounts(ingredients),
        "mProduct": _amounts(products),
        "mManufactoringDuration": "60.000000",
        "mProducedIn": _produced_in(building_class),
    }


def _build_gun_recipe(class_name: str, display_name: str, product_class: str) -> dict:
    """A belt/pipe build-gun recipe: produced in BP_BuildGun_C, not a manufacturer."""
    return {
        "ClassName": class_name,
        "mDisplayName": display_name,
        "mIngredients": "",
        "mProduct": _amounts([(product_class, 1)]),
        "mManufactoringDuration": "1.000000",
        "mProducedIn": '("/Game/FactoryGame/Equipment/BuildGun/BP_BuildGun.BP_BuildGun_C")',
    }


def _belt(class_name: str, display_name: str, speed: float) -> dict:
    return {"ClassName": class_name, "mDisplayName": display_name, "mSpeed": str(speed)}


def _pipe(class_name: str, display_name: str, flow_limit: float) -> dict:
    return {"ClassName": class_name, "mDisplayName": display_name, "mFlowLimit": str(flow_limit)}


def _schematic(
    class_name: str,
    display_name: str,
    tech_tier: int,
    unlocked_recipe_names: tuple[str, ...],
) -> dict:
    return {
        "ClassName": class_name,
        "mDisplayName": display_name,
        "mType": "EST_Milestone",
        "mTechTier": str(tech_tier),
        "mUnlocks": [
            {"Class": "BP_UnlockRecipe_C", "mRecipes": _recipe_refs(*unlocked_recipe_names)}
        ],
    }


def _docs_data() -> list[dict]:
    """Fixture catalog with a solid production chain, one fluid item, and real-shape
    belt/pipe/schematic groups (field names and units verified against the real
    Satisfactory Docs; see satisfactory_docs.py's parsing for the source values).
    """
    return [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGResourceDescriptor'",
            "Classes": [
                {"ClassName": "Desc_Ore_C", "mDisplayName": "Ore", "mForm": "RF_SOLID"},
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGItemDescriptor'",
            "Classes": [
                {"ClassName": "Desc_Ingot_C", "mDisplayName": "Ingot", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Plate_C", "mDisplayName": "Plate", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Slag_C", "mDisplayName": "Slag", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Widget_C", "mDisplayName": "Widget", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Rod_C", "mDisplayName": "Rod", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Fuel_C", "mDisplayName": "Fuel", "mForm": "RF_LIQUID"},
                {
                    "ClassName": "Desc_ConveyorBeltMk1_C",
                    "mDisplayName": "Conveyor Belt Mk.1",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_ConveyorBeltMk2_C",
                    "mDisplayName": "Conveyor Belt Mk.2",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_ConveyorBeltMk3_C",
                    "mDisplayName": "Conveyor Belt Mk.3",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_Pipeline_C",
                    "mDisplayName": "Pipeline Mk.1",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_PipelineMK2_C",
                    "mDisplayName": "Pipeline Mk.2",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_PipelineMK2_NoIndicator_C",
                    "mDisplayName": "Clean Pipeline Mk.2",
                    "mForm": "RF_SOLID",
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                _recipe(
                    "Recipe_Ingot_C", "Ingot", [("Desc_Ore_C", 1)], [("Desc_Ingot_C", 1)],
                    "Build_SmelterMk1_C",
                ),
                _recipe(
                    "Recipe_PlateWithSlag_C",
                    "Plate With Slag",
                    [("Desc_Ingot_C", 2)],
                    [("Desc_Plate_C", 1), ("Desc_Slag_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Widget_C", "Widget", [("Desc_Ore_C", 1)], [("Desc_Widget_C", 150)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Rod_C", "Rod", [("Desc_Ore_C", 1)], [("Desc_Rod_C", 300)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    # RF_LIQUID amounts are stored *1000 in the Docs (catalog.rate_amount
                    # divides back down), so 700000 here yields 700/min actual flow.
                    "Recipe_Fuel_C", "Fuel", [("Desc_Ore_C", 1)], [("Desc_Fuel_C", 700000)],
                    "Build_ConstructorMk1_C",
                ),
                _build_gun_recipe(
                    "Recipe_ConveyorBeltMk1_C", "Conveyor Belt Mk.1", "Desc_ConveyorBeltMk1_C"
                ),
                _build_gun_recipe(
                    "Recipe_ConveyorBeltMk2_C", "Conveyor Belt Mk.2", "Desc_ConveyorBeltMk2_C"
                ),
                _build_gun_recipe(
                    "Recipe_ConveyorBeltMk3_C", "Conveyor Belt Mk.3", "Desc_ConveyorBeltMk3_C"
                ),
                _build_gun_recipe("Recipe_Pipeline_C", "Pipeline Mk.1", "Desc_Pipeline_C"),
                _build_gun_recipe(
                    "Recipe_PipelineMK2_C", "Pipeline Mk.2", "Desc_PipelineMK2_C"
                ),
                _build_gun_recipe(
                    "Recipe_PipelineMK2_NoIndicator_C",
                    "Clean Pipeline Mk.2",
                    "Desc_PipelineMK2_NoIndicator_C",
                ),
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableManufacturer'",
            "Classes": [
                {
                    "ClassName": "Build_SmelterMk1_C",
                    "mManufacturingSpeed": "1.000000",
                    "mPowerConsumption": "4.000000",
                },
                {
                    "ClassName": "Build_ConstructorMk1_C",
                    "mManufacturingSpeed": "1.000000",
                    "mPowerConsumption": "4.000000",
                },
            ],
        },
        {
            "NativeClass": (
                "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableConveyorBelt'"
            ),
            "Classes": [
                _belt("Build_ConveyorBeltMk1_C", "Conveyor Belt Mk.1", 120.0),
                _belt("Build_ConveyorBeltMk2_C", "Conveyor Belt Mk.2", 240.0),
                _belt("Build_ConveyorBeltMk3_C", "Conveyor Belt Mk.3", 540.0),
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildablePipeline'",
            "Classes": [
                _pipe("Build_Pipeline_C", "Pipeline Mk.1", 5.0),
                _pipe("Build_PipelineMK2_C", "Pipeline Mk.2", 10.0),
                # Cosmetic duplicate at the same capacity; must not appear in pipes().
                _pipe("Build_PipelineMK2_NoIndicator_C", "Clean Pipeline Mk.2", 10.0),
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGSchematic'",
            "Classes": [
                _schematic("Schematic_Belt1_C", "Logistics Mk.1", 0, ("Recipe_ConveyorBeltMk1_C",)),
                _schematic("Schematic_Belt2_C", "Logistics Mk.2", 1, ("Recipe_ConveyorBeltMk2_C",)),
                _schematic("Schematic_Belt3_C", "Logistics Mk.3", 2, ("Recipe_ConveyorBeltMk3_C",)),
                _schematic("Schematic_Pipe1_C", "Pipelines Mk.1", 0, ("Recipe_Pipeline_C",)),
                _schematic("Schematic_Pipe2_C", "Pipelines Mk.2", 1, ("Recipe_PipelineMK2_C",)),
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _snapshot(purchased: frozenset[str]) -> CapabilitySnapshot:
    return CapabilitySnapshot(
        upcoming_phase=1, max_tier=2, purchased_schematics=purchased, allowed_recipes=frozenset()
    )


_BELT1_ONLY = _snapshot(frozenset({normalize_class_name("Schematic_Belt1_C"), normalize_class_name("Schematic_Pipe1_C")}))


def _node(recipe_class: str, runs_per_min: float, building_class: str = "Build_ConstructorMk1_C") -> ProcessNode:
    return ProcessNode(
        node_id="node_" + normalize_class_name(recipe_class),
        recipe_class=recipe_class,
        building_class=building_class,
        runs_per_min=runs_per_min,
        machine_count_exact=runs_per_min,
        machine_count=max(1, round(runs_per_min)),
        clock=1.0,
        power_mw=0.0,
    )


# --- Docs parsing: verified real-shape belt/pipe fields ----------------------


def test_belts_parsed_sorted_ascending_by_capacity(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)

    belts = catalog.belts()

    assert [belt.capacity for belt in belts] == [60.0, 120.0, 270.0]
    assert [belt.class_name for belt in belts] == [
        "Build_ConveyorBeltMk1_C",
        "Build_ConveyorBeltMk2_C",
        "Build_ConveyorBeltMk3_C",
    ]
    assert all(not belt.is_pipe for belt in belts)


def test_pipes_parsed_sorted_ascending_dedupes_noindicator_variant(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)

    pipes = catalog.pipes()

    # 300/min and 600/min match the real Docs' in-game capacity text; the
    # "NoIndicator" cosmetic duplicate at the same capacity as Mk2 must not
    # appear as a third entry.
    assert [pipe.capacity for pipe in pipes] == [300.0, 600.0]
    assert [pipe.class_name for pipe in pipes] == ["Build_Pipeline_C", "Build_PipelineMK2_C"]
    assert all(pipe.is_pipe for pipe in pipes)


# --- Gating: highest unlocked tier, lowest-tier fallback ---------------------


def test_gating_resolves_highest_unlocked_tier(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    snapshot = _snapshot(
        frozenset(
            normalize_class_name(name)
            for name in ("Schematic_Belt1_C", "Schematic_Belt2_C", "Schematic_Pipe1_C")
        )
    )

    diagnostics, assumptions = check_logistics(catalog, snapshot, (), (), ())

    assert diagnostics == ()
    assert "belt logistics gated to 'Conveyor Belt Mk.2' for this snapshot" in assumptions
    assert "pipe logistics gated to 'Pipeline Mk.1' for this snapshot" in assumptions


def test_gating_falls_back_to_lowest_tier_with_diagnostic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    snapshot = _snapshot(frozenset())

    diagnostics, assumptions = check_logistics(catalog, snapshot, (), (), ())

    fallback = [d for d in diagnostics if d.code == "logistics_tier_fallback"]
    assert len(fallback) == 2
    assert all(d.severity == "warning" for d in fallback)
    assert any("Conveyor Belt Mk.1" in d.message for d in fallback)
    assert any("Pipeline Mk.1" in d.message for d in fallback)
    assert "belt logistics gated to 'Conveyor Belt Mk.1' for this snapshot" in assumptions
    assert "pipe logistics gated to 'Pipeline Mk.1' for this snapshot" in assumptions


# --- Line-count math: exact, boundary, and no-diagnostic cases ---------------


def test_line_count_exact_no_warning_below_threshold(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    node = _node("Recipe_Widget_C", runs_per_min=1.0)

    diagnostics, _assumptions = check_logistics(catalog, _BELT1_ONLY, (node,), (), ())

    multi_line = [d for d in diagnostics if d.code == "logistics_multi_line"]
    warnings = [d for d in diagnostics if d.code == "logistics_capacity_warning"]
    assert len(multi_line) == 1
    # 150/min over a 60/min Mk.1 belt: ceil(150/60) == 3 lines.
    assert "needs 3 lines of Conveyor Belt Mk.1" in multi_line[0].message
    assert multi_line[0].severity == "info"
    assert warnings == []


def test_line_count_warning_above_four_line_threshold(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    node = _node("Recipe_Rod_C", runs_per_min=1.0)

    diagnostics, _assumptions = check_logistics(catalog, _BELT1_ONLY, (node,), (), ())

    warnings = [d for d in diagnostics if d.code == "logistics_capacity_warning"]
    assert len(warnings) == 1
    # 300/min over a 60/min Mk.1 belt: ceil(300/60) == 5 lines, over the
    # 4-line visibility threshold.
    assert "needs 5 lines" in warnings[0].message
    assert warnings[0].severity == "warning"


def test_line_count_single_line_emits_no_diagnostic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    node = _node("Recipe_Ingot_C", runs_per_min=1.0)
    # Demand matches production exactly so no byproduct-surplus diagnostic
    # also fires; this test is only about the line-count check.
    demands = (("Desc_Ingot_C", 1.0),)

    diagnostics, _assumptions = check_logistics(catalog, _BELT1_ONLY, (node,), (), demands)

    assert diagnostics == ()


def test_line_count_uses_pipe_tier_for_fluid_items(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    node = _node("Recipe_Fuel_C", runs_per_min=1.0)

    diagnostics, _assumptions = check_logistics(catalog, _BELT1_ONLY, (node,), (), ())

    multi_line = [d for d in diagnostics if d.code == "logistics_multi_line"]
    assert len(multi_line) == 1
    # 700/min over a 300/min Mk.1 pipe: ceil(700/300) == 3 lines.
    assert "needs 3 lines of Pipeline Mk.1" in multi_line[0].message


def test_extractor_source_checked_same_way_boundary_case(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    source = ResourceSource(
        node_id="source_ore",
        item_class="Desc_Ore_C",
        rate_per_min=200.0,
        extractor_class="Build_MinerMk2_C",
        extractor_count=1,
    )

    diagnostics, _assumptions = check_logistics(catalog, _BELT1_ONLY, (), (source,), ())

    # 200/min over a 60/min Mk.1 belt: ceil(200/60) == 4 lines, exactly at
    # (not over) the visibility threshold, so info fires but not warning.
    multi_line = [d for d in diagnostics if d.code == "logistics_multi_line"]
    warnings = [d for d in diagnostics if d.code == "logistics_capacity_warning"]
    assert len(multi_line) == 1
    assert "needs 4 lines" in multi_line[0].message
    assert "source source_ore" in multi_line[0].message
    assert warnings == []


# --- Byproduct surplus: matches the solver's byproduct fixture arithmetic ----


def test_surplus_matches_solver_byproduct_fixture_arithmetic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    nodes = (
        _node("Recipe_Ingot_C", runs_per_min=20.0, building_class="Build_SmelterMk1_C"),
        _node("Recipe_PlateWithSlag_C", runs_per_min=10.0),
    )
    demands = (("Desc_Plate_C", 10.0), ("Desc_Slag_C", 5.0))

    diagnostics, assumptions = check_logistics(catalog, _BELT1_ONLY, nodes, (), demands)

    surplus = [d for d in diagnostics if d.code == "byproduct_surplus"]
    assert len(surplus) == 1
    assert surplus[0].severity == "warning"
    # 2 ingot per plate-with-slag run, 10 runs -> 10 plate/min and 10 slag/min;
    # slag has no consumer, so surplus = 10 - 0 - 5 == 5.0/min.
    assert "surplus: Slag at 5.000/min" in surplus[0].message
    assert "surpluses require sink or storage (unmodeled)" in assumptions


def test_no_surplus_when_fully_consumed_or_demanded(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    node = _node("Recipe_Ingot_C", runs_per_min=1.0, building_class="Build_SmelterMk1_C")
    demands = (("Desc_Ingot_C", 1.0),)

    diagnostics, assumptions = check_logistics(catalog, _BELT1_ONLY, (node,), (), demands)

    assert [d for d in diagnostics if d.code == "byproduct_surplus"] == []
    assert "surpluses require sink or storage (unmodeled)" not in assumptions


# --- Determinism -------------------------------------------------------------


def test_check_logistics_is_deterministic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    nodes = (
        _node("Recipe_Ingot_C", runs_per_min=20.0, building_class="Build_SmelterMk1_C"),
        _node("Recipe_PlateWithSlag_C", runs_per_min=10.0),
        _node("Recipe_Rod_C", runs_per_min=1.0),
    )
    demands = (("Desc_Plate_C", 10.0), ("Desc_Slag_C", 5.0))

    first = check_logistics(catalog, _BELT1_ONLY, nodes, (), demands)
    second = check_logistics(catalog, _BELT1_ONLY, nodes, (), demands)

    assert first == second


# --- Graceful degradation: a Docs catalog with no belts/pipes parsed --------


def test_no_logistics_data_degrades_to_no_op(tmp_path: Path) -> None:
    """A Docs catalog with no FGBuildableConveyorBelt/FGBuildablePipeline groups
    (every other test file's fixture) must never raise and must add nothing.
    """
    path = tmp_path / "en-US.json"
    data = [group for group in _docs_data() if "FGBuildable" not in group["NativeClass"] or (
        "ConveyorBelt" not in group["NativeClass"] and "Pipeline" not in group["NativeClass"]
    )]
    path.write_text(json.dumps(data), encoding="utf-16")
    catalog = load_docs_catalog(path)
    assert catalog.belts() == ()
    assert catalog.pipes() == ()

    # Demand matches production exactly: this test is only about the
    # belt/pipe-tier degrade path, not byproduct surplus (which is
    # independent of whether any logistics data was parsed).
    node = _node("Recipe_Rod_C", runs_per_min=1.0)
    demands = (("Desc_Rod_C", 300.0),)
    snapshot = _snapshot(frozenset())

    diagnostics, assumptions = check_logistics(catalog, snapshot, (node,), (), demands)

    assert diagnostics == ()
    assert assumptions == ()


# --- Real-install integration -------------------------------------------------


def test_real_install_phase3_logistics_summary() -> None:
    """Gated real-install check: Phase 3 demand, full solve, no crash.

    Mirrors the discover_docs skip pattern used across this skill's tests.
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()
    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=3)
    demand_set = derive_phase_demand(data, 3, 1.0)
    demands = tuple(
        (demand.item_class, demand.required_rate_per_minute) for demand in demand_set.demands
    )

    result = solve_stage(catalog, snapshot.allowed_recipes, demands)
    assert result.status == "optimal"

    nodes, _power, _schedule_diagnostics = schedule_machines(catalog, result)
    sources, _power_additions, _extraction_diagnostics = plan_extraction(catalog, result.imports)

    diagnostics, assumptions = check_logistics(catalog, snapshot, nodes, sources, demands)

    assert isinstance(diagnostics, tuple)
    assert isinstance(assumptions, tuple)
    belt_assumption = next(
        (a for a in assumptions if a.startswith("belt logistics gated to")), None
    )
    pipe_assumption = next(
        (a for a in assumptions if a.startswith("pipe logistics gated to")), None
    )
    assert belt_assumption is not None
    assert pipe_assumption is not None
    for diagnostic in diagnostics:
        assert diagnostic.severity in ("info", "warning", "error")

"""Tests for the solver core: gated candidate graph and LP balance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog, normalize_class_name
from satisfactory_install import discover_docs
from satisfactory_plan_models import (
    DataProvenance,
    RecipePolicy,
    StagePlan,
    stage_plan_from_payload,
)
from satisfactory_progression import (
    build_capability_snapshot,
    derive_phase_demand,
    load_project_assembly_phases,
)
from satisfactory_solver import RecipeRun, SolveResult, schedule_machines, solve_stage


def _amount(class_name: str, amount: float) -> str:
    return (
        f'(ItemClass="/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/'
        f'Resource/Parts/X/Desc_X.{class_name}\'",Amount={amount})'
    )


def _amounts(entries: list[tuple[str, float]]) -> str:
    return "(" + ",".join(_amount(class_name, amount) for class_name, amount in entries) + ")"


def _produced_in(building_class: str) -> str:
    return f'("/Game/FactoryGame/Buildable/Factory/X/{building_class}.{building_class}")'


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


def _docs_data() -> list[dict]:
    """One shared fixture catalog for every non-real-install solver test.

    Every recipe runs 60 seconds, so amount/duration*60 == amount: each
    ingredient/product ``Amount`` is directly the per-run item rate,
    making the expected LP results hand-computable by inspection.
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
                {"ClassName": "Desc_Widget_C", "mDisplayName": "Widget", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Slag_C", "mDisplayName": "Slag", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Rod_C", "mDisplayName": "Rod", "mForm": "RF_SOLID"},
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
                    "Recipe_Plate_C", "Plate", [("Desc_Ingot_C", 1)], [("Desc_Plate_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Widget_C", "Widget", [("Desc_Ingot_C", 1)], [("Desc_Widget_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_PlateWithSlag_C",
                    "Plate With Slag",
                    [("Desc_Ingot_C", 2)],
                    [("Desc_Plate_C", 1), ("Desc_Slag_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Rod_C", "Rod", [("Desc_Ore_C", 1)], [("Desc_Rod_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Plate_FromOre_C",
                    "Plate From Ore",
                    [("Desc_Ore_C", 2)],
                    [("Desc_Plate_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Plate_Efficient_C",
                    "Efficient Plate",
                    [("Desc_Ore_C", 1)],
                    [("Desc_Plate_C", 1)],
                    "Build_ConstructorMk1_C",
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
                    "mPowerConsumptionExponent": "1.300000",
                },
                {"ClassName": "Build_FreeBuilder_C", "mManufacturingSpeed": "1.000000"},
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _keys(*names: str) -> frozenset[str]:
    return frozenset(normalize_class_name(name) for name in names)


# --- Linear chain: exact hand-computed values --------------------------------


def test_linear_chain_hand_computed_values(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 20.0),))

    assert result.status == "optimal"
    runs_by_key = {normalize_class_name(run.recipe_class): run.machines_exact for run in result.runs}
    assert runs_by_key[normalize_class_name("Recipe_Plate_C")] == pytest.approx(20.0)
    assert runs_by_key[normalize_class_name("Recipe_Ingot_C")] == pytest.approx(20.0)
    assert len(result.imports) == 1
    assert result.imports[0].rate_per_min == pytest.approx(20.0)
    assert normalize_class_name(result.imports[0].item_class) == normalize_class_name("Desc_Ore_C")
    assert result.satisfied_demands == (normalize_class_name("Desc_Plate_C"),)
    assert result.diagnostics == ()


def test_linear_chain_residuals_hold(tmp_path: Path) -> None:
    """No internal-residual diagnostic should ever fire for a clean solve."""
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 20.0),))

    assert not any("internal residual" in diagnostic for diagnostic in result.diagnostics)


# --- Shared intermediate ------------------------------------------------------


def test_shared_intermediate_consumed_by_two_demands(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Widget_C")

    result = solve_stage(
        catalog, allowed, (("Desc_Plate_C", 10.0), ("Desc_Widget_C", 5.0))
    )

    assert result.status == "optimal"
    runs_by_key = {normalize_class_name(run.recipe_class): run.machines_exact for run in result.runs}
    assert runs_by_key[normalize_class_name("Recipe_Plate_C")] == pytest.approx(10.0)
    assert runs_by_key[normalize_class_name("Recipe_Widget_C")] == pytest.approx(5.0)
    assert runs_by_key[normalize_class_name("Recipe_Ingot_C")] == pytest.approx(15.0)
    assert len(result.imports) == 1
    assert result.imports[0].rate_per_min == pytest.approx(15.0)


# --- Byproduct surplus ---------------------------------------------------------


def test_byproduct_surplus_satisfies_secondary_demand(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_PlateWithSlag_C")

    result = solve_stage(
        catalog, allowed, (("Desc_Plate_C", 10.0), ("Desc_Slag_C", 5.0))
    )

    assert result.status == "optimal"
    runs_by_key = {normalize_class_name(run.recipe_class): run.machines_exact for run in result.runs}
    assert runs_by_key[normalize_class_name("Recipe_PlateWithSlag_C")] == pytest.approx(10.0)
    # 2 ingot per plate-with-slag run, 10 runs => 20 ingot => 20 ore.
    assert runs_by_key[normalize_class_name("Recipe_Ingot_C")] == pytest.approx(20.0)
    assert len(result.imports) == 1
    assert result.imports[0].rate_per_min == pytest.approx(20.0)


# --- Alternate recipe gating ---------------------------------------------------


def test_alternate_recipe_unused_when_not_allowed(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Plate_FromOre_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 10.0),))

    assert result.status == "optimal"
    assert len(result.runs) == 1
    assert normalize_class_name(result.runs[0].recipe_class) == normalize_class_name(
        "Recipe_Plate_FromOre_C"
    )
    assert result.imports[0].rate_per_min == pytest.approx(20.0)


def test_alternate_recipe_picked_when_strictly_better(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Plate_FromOre_C", "Recipe_Plate_Efficient_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 10.0),))

    assert result.status == "optimal"
    runs_by_key = {normalize_class_name(run.recipe_class): run.machines_exact for run in result.runs}
    assert normalize_class_name("Recipe_Plate_FromOre_C") not in runs_by_key
    assert runs_by_key[normalize_class_name("Recipe_Plate_Efficient_C")] == pytest.approx(10.0)
    assert result.imports[0].rate_per_min == pytest.approx(10.0)


# --- Infeasible / no_candidates -------------------------------------------------


def test_infeasible_when_only_recipe_not_allowed(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C")

    result = solve_stage(catalog, allowed, (("Desc_Rod_C", 5.0),))

    assert result.status == "infeasible"
    assert result.runs == ()
    assert result.imports == ()
    assert any(normalize_class_name("Desc_Rod_C") in diagnostic for diagnostic in result.diagnostics)
    assert any("closed-gate" in diagnostic for diagnostic in result.diagnostics)


def test_no_candidates_for_empty_allowed_set(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)

    result = solve_stage(catalog, frozenset(), (("Desc_Plate_C", 10.0),))

    assert result.status == "no_candidates"
    assert result.runs == ()
    assert result.imports == ()


# --- Zero demand ----------------------------------------------------------------


def test_zero_demand_returns_optimal_empty(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C")

    result = solve_stage(catalog, allowed, ())

    assert result.status == "optimal"
    assert result.runs == ()
    assert result.imports == ()
    assert result.satisfied_demands == ()


# --- Determinism ------------------------------------------------------------------


def test_determinism_double_run_matches(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Widget_C")
    demands = (("Desc_Plate_C", 10.0), ("Desc_Widget_C", 5.0))

    first = solve_stage(catalog, allowed, demands)
    second = solve_stage(catalog, allowed, demands)

    assert first == second


# --- Real-install integration ----------------------------------------------------


def test_real_install_phase1_smart_plating_solve() -> None:
    """Gated real-install solve: Phase 1 Smart Plating demand, tiers 0-2.

    Skips cleanly when no Satisfactory install can be found on this
    machine (mirrors the discover_docs skip pattern used elsewhere).
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()
    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)
    demand_set = derive_phase_demand(data, 1, 1.0)
    smart_plating_demand = next(
        demand
        for demand in demand_set.demands
        if demand.item_class == "Desc_SpaceElevatorPart_1_C"
    )
    demands = ((smart_plating_demand.item_class, smart_plating_demand.required_rate_per_minute),)

    result = solve_stage(catalog, snapshot.allowed_recipes, demands)

    assert result.status == "optimal"
    assert any(run.display_name == "Smart Plating" for run in result.runs)

    raw_classes = catalog.raw_resource_classes()
    for imported in result.imports:
        assert normalize_class_name(imported.item_class) in raw_classes
    for run in result.runs:
        assert normalize_class_name(run.recipe_class) in snapshot.allowed_recipes


# --- schedule_machines: fractional and exact-integer cases ------------------------


def test_schedule_machines_fractional_case_default_exponent(tmp_path: Path) -> None:
    """2.5 machine-equivalents -> 3 machines at clock 5/6, default 1.6 exponent."""
    catalog = _catalog(tmp_path)
    run = RecipeRun(
        recipe_class="Recipe_Ingot_C",
        display_name="Ingot",
        machines_exact=2.5,
        building_class="Build_SmelterMk1_C",
    )
    result = SolveResult(status="optimal", runs=(run,), imports=(), satisfied_demands=(), diagnostics=())

    nodes, power, diagnostics = schedule_machines(catalog, result)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.node_id == "node_" + normalize_class_name("Recipe_Ingot_C")
    assert node.machine_count == 3
    assert node.machine_count_exact == pytest.approx(2.5)
    assert node.clock == pytest.approx(2.5 / 3)
    # duration 60s, manufacturing_speed 1.0 -> runs_per_min == machines_exact.
    assert node.runs_per_min == pytest.approx(2.5)
    expected_power = round(3 * 4.0 * (2.5 / 3) ** 1.6, 3)
    assert node.power_mw == pytest.approx(expected_power)
    assert power.total_mw == pytest.approx(expected_power)
    assert diagnostics == ()


def test_schedule_machines_exact_integer_case_custom_exponent(tmp_path: Path) -> None:
    """4.0 machine-equivalents -> 4 machines at clock 1.0; proves exponent parsing."""
    catalog = _catalog(tmp_path)
    building = catalog.building("Build_ConstructorMk1_C")
    assert building is not None
    assert building.power_consumption_exponent == pytest.approx(1.3)

    run = RecipeRun(
        recipe_class="Recipe_Rod_C",
        display_name="Rod",
        machines_exact=4.0,
        building_class="Build_ConstructorMk1_C",
    )
    result = SolveResult(status="optimal", runs=(run,), imports=(), satisfied_demands=(), diagnostics=())

    nodes, power, diagnostics = schedule_machines(catalog, result)

    assert len(nodes) == 1
    node = nodes[0]
    assert node.machine_count == 4
    assert node.clock == pytest.approx(1.0)
    assert node.power_mw == pytest.approx(round(4 * 4.0 * 1.0**1.3, 3))
    assert node.power_mw == pytest.approx(16.0)
    assert diagnostics == ()


def test_schedule_machines_zero_power_building_diagnostic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    run = RecipeRun(
        recipe_class="Recipe_Rod_C",
        display_name="Rod",
        machines_exact=1.0,
        building_class="Build_FreeBuilder_C",
    )
    result = SolveResult(status="optimal", runs=(run,), imports=(), satisfied_demands=(), diagnostics=())

    nodes, power, diagnostics = schedule_machines(catalog, result)

    assert len(nodes) == 1
    assert nodes[0].power_mw == pytest.approx(0.0)
    assert power.total_mw == pytest.approx(0.0)
    assert power.by_building == (("Build_FreeBuilder_C", 0.0),)
    assert len(diagnostics) == 1
    assert "Build_FreeBuilder_C" in diagnostics[0]


def test_schedule_machines_power_plan_aggregation(tmp_path: Path) -> None:
    """PowerPlan aggregates across building classes, sorted by MW descending."""
    catalog = _catalog(tmp_path)
    runs = (
        RecipeRun(
            recipe_class="Recipe_Ingot_C",
            display_name="Ingot",
            machines_exact=2.0,
            building_class="Build_SmelterMk1_C",
        ),
        RecipeRun(
            recipe_class="Recipe_Rod_C",
            display_name="Rod",
            machines_exact=1.0,
            building_class="Build_ConstructorMk1_C",
        ),
        RecipeRun(
            recipe_class="Recipe_Widget_C",
            display_name="Widget",
            machines_exact=3.0,
            building_class="Build_ConstructorMk1_C",
        ),
    )
    result = SolveResult(status="optimal", runs=runs, imports=(), satisfied_demands=(), diagnostics=())

    nodes, power, diagnostics = schedule_machines(catalog, result)

    assert len(nodes) == 3
    # Smelter: 2 machines * 4.0 MW * 1.0**1.6 = 8.0. Constructor: (1 + 3)
    # machines * 4.0 MW * 1.0**1.3 = 16.0.
    assert power.by_building == (
        ("Build_ConstructorMk1_C", pytest.approx(16.0)),
        ("Build_SmelterMk1_C", pytest.approx(8.0)),
    )
    assert power.total_mw == pytest.approx(24.0)
    assert diagnostics == ()


def test_schedule_machines_real_install_phase1_round_trips_stage_plan() -> None:
    """Schedule the real-install Phase 1 solve and round-trip it as a StagePlan."""
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()
    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)
    demand_set = derive_phase_demand(data, 1, 1.0)
    smart_plating_demand = next(
        demand
        for demand in demand_set.demands
        if demand.item_class == "Desc_SpaceElevatorPart_1_C"
    )
    demands = ((smart_plating_demand.item_class, smart_plating_demand.required_rate_per_minute),)

    result = solve_stage(catalog, snapshot.allowed_recipes, demands)
    assert result.status == "optimal"

    nodes, power, diagnostics = schedule_machines(catalog, result)

    assert nodes
    for node in nodes:
        recipe = catalog.recipe(node.recipe_class)
        building = catalog.building(node.building_class)
        assert recipe is not None
        assert building is not None
        assert isinstance(node.machine_count, int)
        assert node.machine_count >= 1
        assert 0.0 < node.clock <= 1.0
        expected_runs_per_min = (
            node.machine_count_exact * (60.0 / recipe.duration_seconds) * building.manufacturing_speed
        )
        assert node.runs_per_min == pytest.approx(expected_runs_per_min, abs=1e-6)
    assert power.total_mw > 0.0
    assert isinstance(diagnostics, tuple)

    plan = StagePlan(
        phase=1,
        window_hours=24.0,
        pace_multiplier=1.0,
        demands=((smart_plating_demand.item_class, 1.0, smart_plating_demand.required_rate_per_minute),),
        nodes=nodes,
        sources=(),
        flows=(),
        power=power,
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="2026-07-02", note="fixture"),
        solver_run_id=None,
        revision=1,
        created_at="2026-07-02T00:00:00Z",
    )

    assert stage_plan_from_payload(plan.to_payload()) == plan

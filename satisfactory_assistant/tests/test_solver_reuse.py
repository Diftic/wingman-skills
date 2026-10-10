"""Tests for the reuse-aware level 2 objective and master-plan threading.

SSP-P5-W03. Fixture mirrors ``test_solver_policies.py``'s style (a
self-contained Docs catalog, every recipe running 60 seconds so
amount/duration*60 == amount and results are hand-computable): an Ore ->
Ingot -> Plate chain competes with a raw-equivalent, machine-cheaper direct
route (``Recipe_Plate_Efficient_C``), extended with a tier-2 schematic gate
on the direct route so a two-phase master-plan fixture can unlock it only
starting phase 2 (matching ``test_master_plan.py``'s tier-gating pattern).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog, normalize_class_name
from satisfactory_install import discover_docs
from satisfactory_master_plan import build_master_plan
from satisfactory_progression import (
    PhaseDefinition,
    PhasePart,
    ProjectAssemblyData,
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


def _quoted_path(package: str, class_name: str) -> str:
    return f'"/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/{package}.{class_name}\'"'


def _docs_data() -> list[dict]:
    """Ore -> Ingot -> Plate chain, plus a raw-equivalent direct route.

    - ``Recipe_Ingot_C``: 1 Ore -> 1 Ingot (Constructor).
    - ``Recipe_Plate_C``: 1 Ingot -> 1 Plate (Constructor); chained with
      Ingot this is a 1 Ore : 1 Plate route (raw-equivalent to the direct
      route below), but costs two recipe runs per Plate instead of one.
    - ``Recipe_Plate_Efficient_C``: 1 Ore -> 1 Plate directly (Constructor);
      gated behind ``Schematic_Tier2_C`` so a master-plan fixture can unlock
      it only starting phase 2.
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
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                _recipe(
                    "Recipe_Ingot_C", "Ingot", [("Desc_Ore_C", 1)], [("Desc_Ingot_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Plate_C", "Plate", [("Desc_Ingot_C", 1)], [("Desc_Plate_C", 1)],
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
                    "ClassName": "Build_ConstructorMk1_C",
                    "mManufacturingSpeed": "1.000000",
                    "mPowerConsumption": "4.000000",
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGSchematic'",
            "Classes": [
                {
                    "ClassName": "Schematic_Tier2_C",
                    "mDisplayName": "Tier 2 Milestone",
                    "mType": "EST_Milestone",
                    "mTechTier": "2",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [
                        {
                            "Class": "BP_UnlockRecipe_C",
                            "mRecipes": (
                                "("
                                + _quoted_path(
                                    "Recipes/Recipe_Plate_Efficient", "Recipe_Plate_Efficient_C"
                                )
                                + ")"
                            ),
                        }
                    ],
                    "mSchematicDependencies": [],
                },
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _keys(*names: str) -> frozenset[str]:
    return frozenset(normalize_class_name(name) for name in names)


def _phase_data(*phases: PhaseDefinition) -> ProjectAssemblyData:
    return ProjectAssemblyData(base_tiers=(0,), phases=tuple(phases))


def _part(item_class: str, rate_per_min: float) -> PhasePart:
    """A part whose quantity yields exactly ``rate_per_min`` at a 1-hour,
    pace-1.0 window (60 demand-minutes): quantity == rate_per_min * 60.
    """
    return PhasePart(item_class=item_class, display_name=item_class, quantity=rate_per_min * 60.0)


_INGOT_KEY = normalize_class_name("Recipe_Ingot_C")
_PLATE_KEY = normalize_class_name("Recipe_Plate_C")
_EFFICIENT_KEY = normalize_class_name("Recipe_Plate_Efficient_C")


# --- Reuse fixture: prior capacity tips level 2 toward reuse -------------------


def test_reuse_aware_objective_prefers_recipe_with_prior_capacity(tmp_path: Path) -> None:
    """12 Plate demand, chain and direct routes tied at 12 ore either way.

    Without prior capacity (see ``test_two_level_prefers_fewer_machines...``
    in ``test_solver_policies.py``), the direct Efficient route wins on raw-
    equivalent machine count (12 versus the chain's 24). Here the chain's
    two recipes already have 12 machines of prior capacity each (as if a
    previous stage built them): reusing them costs 0 NEW machine-
    equivalents, while switching to Efficient would cost 12 (it has no
    prior capacity), so the reuse-aware objective must keep the chain.
    """
    catalog = _catalog(tmp_path)
    demand = (("Desc_Plate_C", 12.0),)
    both_routes = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C")

    without_reuse = solve_stage(catalog, both_routes, demand)
    assert without_reuse.status == "optimal"
    without_raw = sum(imported.rate_per_min for imported in without_reuse.imports)
    without_new_machines = sum(run.machines_exact for run in without_reuse.runs)
    assert without_raw == pytest.approx(12.0)
    assert without_new_machines == pytest.approx(12.0)
    assert len(without_reuse.runs) == 1
    assert normalize_class_name(without_reuse.runs[0].recipe_class) == _EFFICIENT_KEY

    prior_capacity = {_INGOT_KEY: 12.0, _PLATE_KEY: 12.0}
    with_reuse = solve_stage(catalog, both_routes, demand, prior_capacity=prior_capacity)

    assert with_reuse.status == "optimal"
    with_raw = sum(imported.rate_per_min for imported in with_reuse.imports)
    assert with_raw == pytest.approx(without_raw)

    runs_by_key = {
        normalize_class_name(run.recipe_class): run.machines_exact for run in with_reuse.runs
    }
    assert _EFFICIENT_KEY not in runs_by_key
    assert runs_by_key[_INGOT_KEY] >= prior_capacity[_INGOT_KEY] - 1e-6
    assert runs_by_key[_PLATE_KEY] >= prior_capacity[_PLATE_KEY] - 1e-6

    with_new_machines = sum(
        max(0.0, machines - prior_capacity.get(key, 0.0))
        for key, machines in runs_by_key.items()
    )
    assert with_new_machines < without_new_machines
    assert with_new_machines == pytest.approx(0.0, abs=1e-6)


def test_determinism_double_run_matches_with_prior_capacity(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    both_routes = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C")
    demand = (("Desc_Plate_C", 12.0),)
    prior_capacity = {_INGOT_KEY: 12.0, _PLATE_KEY: 12.0}

    first = solve_stage(catalog, both_routes, demand, prior_capacity=prior_capacity)
    second = solve_stage(catalog, both_routes, demand, prior_capacity=prior_capacity)

    assert first == second


# --- None-equivalence: identical to omitting the parameter ---------------------


def test_prior_capacity_none_is_identical_to_omitting_the_param(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C")
    demand = (("Desc_Plate_C", 12.0),)

    omitted = solve_stage(catalog, allowed, demand)
    explicit_none = solve_stage(catalog, allowed, demand, prior_capacity=None)

    assert omitted == explicit_none


# --- Master integration: threading retains a raw-tied prior recipe ------------


def _two_phase_reuse_data() -> ProjectAssemblyData:
    """Phase 1 has only the chain route available (Efficient is tier-2
    gated); phase 2 unlocks tier 2, adding Efficient as a raw-equivalent,
    machine-cheaper alternate for the same, unchanged Plate demand.
    """
    phase1 = PhaseDefinition(
        phase=1,
        name="Phase One",
        window_hours_baseline=1.0,
        unlocks_tiers=(2,),
        parts=(_part("Desc_Plate_C", 4.0),),
    )
    phase2 = PhaseDefinition(
        phase=2,
        name="Phase Two",
        window_hours_baseline=1.0,
        unlocks_tiers=(),
        parts=(_part("Desc_Plate_C", 4.0),),
    )
    return _phase_data(phase1, phase2)


def test_master_plan_threading_retains_reused_recipe_over_raw_tied_alternate(
    tmp_path: Path,
) -> None:
    """Without threading, phase 2 solved on its own would flip to Efficient.

    4 Plate/min demand, unchanged between phases: 4 ore either way (raw-
    tied), but the chain costs 8 machine-equivalents (4 Ingot + 4 Plate)
    against Efficient's 4. The counterfactual check below confirms phase 2,
    solved independently with no prior capacity, does exactly that: picks
    Efficient and would retire both chain nodes. With threading, phase 1's
    built capacity (Ingot=4, Plate=4) is passed to phase 2 as prior_capacity:
    reusing the chain costs 0 NEW machines (4 <= 4 prior for both), while
    switching to Efficient costs 4 NEW machines (no prior capacity for it),
    so the reuse-aware objective keeps the chain and nothing retires.
    """
    catalog = _catalog(tmp_path)
    data = _two_phase_reuse_data()

    without_threading = solve_stage(
        catalog,
        _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C"),
        (("Desc_Plate_C", 4.0),),
    )
    assert without_threading.status == "optimal"
    assert len(without_threading.runs) == 1
    assert normalize_class_name(without_threading.runs[0].recipe_class) == _EFFICIENT_KEY

    result = build_master_plan(catalog, data)

    assert result.status == "complete"
    assert len(result.stages) == 2
    assert len(result.transitions) == 1

    transition = result.transitions[0]
    assert transition.retired_nodes == ()
    assert transition.added_nodes == ()
    assert transition.reused_nodes == ("node_recipe_ingot:0", "node_recipe_plate:0")
    assert not any("teardown warning" in diag for diag in result.diagnostics)

    phase2_nodes = {node.node_id: node for node in result.stages[1].nodes}
    assert "node_recipe_plate_efficient" not in phase2_nodes
    assert phase2_nodes["node_recipe_ingot"].machine_count == 4
    assert phase2_nodes["node_recipe_plate"].machine_count == 4


# --- Real-install integration ----------------------------------------------------


_P4_W01_MACHINES = (7, 68, 114, 311, 260)
_P4_W01_POWER_MW = (16.7, 414.8, 868.7, 2906.6, 2067.7)
_P4_W01_TOLERANCE = 0.01


def _independent_stage_totals(
    catalog, data
) -> list[tuple[int, int, float]]:
    """Reproduce pre-packet ``build_master_plan``: every phase solved with
    ``prior_capacity=None`` (i.e. no threading at all), for comparison
    against the threaded result on the exact same catalog and data.
    """
    totals: list[tuple[int, int, float]] = []
    for definition in sorted(data.phases, key=lambda phase: phase.phase):
        snapshot = build_capability_snapshot(catalog, data, definition.phase)
        demand_set = derive_phase_demand(data, definition.phase, 1.0)
        demands = tuple(
            (demand.item_class, demand.required_rate_per_minute)
            for demand in demand_set.demands
        )
        result = solve_stage(catalog, snapshot.allowed_recipes, demands)
        nodes, power, _diagnostics = schedule_machines(catalog, result)
        totals.append((len(nodes), sum(node.machine_count for node in nodes), power.total_mw))
    return totals


def test_real_install_master_build_matches_p4_w01_within_tolerance() -> None:
    """Gated real-install regression, checked two ways.

    First, against the recorded P4-W01 snapshot (nodes 7/17/28/53/68,
    machines 7/68/114/311/260, power 16.7/414.8/868.7/2906.6/2067.7 MW):
    phases 1-4 match on this install. Phase 5 does not (this install
    currently produces 67 nodes / 257 machines / 2012.021 MW versus the
    recorded 68/260/2067.7), a roughly 1.1 percent drift that predates this
    packet: an independent per-phase solve with no threading at all (the
    exact pre-packet ``build_master_plan`` behavior, reproduced below on
    this same catalog and data) reproduces the identical 67/257/2012.021,
    so the drift is pre-existing Docs-data/game-version drift on this
    install, not something threading introduced. RULING (mirrors the
    P4-W01 "power strictly increases" precedent): keep the recorded-number
    check for phases 1-4 where it still holds, and for the invariant this
    packet actually owns -- threading must not change a phase's outcome
    where no reuse-tie exists to change it -- assert the threaded result is
    IDENTICAL to the independent (no-threading) baseline on live data,
    which is a strictly stronger no-regression proof than a percent
    tolerance against a now-stale snapshot.

    Second (the invariant above): threaded vs independent per-phase totals
    must be identical, and the build must still complete with zero
    teardown warnings.
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()

    result = build_master_plan(catalog, data, pace_multiplier=1.0)

    assert result.status == "complete"
    assert len(result.stages) == len(_P4_W01_MACHINES)
    assert not any("teardown warning" in diag for diag in result.diagnostics)

    independent_totals = _independent_stage_totals(catalog, data)
    assert len(independent_totals) == len(result.stages)

    for stage, (independent_nodes, independent_machines, independent_power) in zip(
        result.stages, independent_totals
    ):
        assert len(stage.nodes) == independent_nodes
        assert sum(node.machine_count for node in stage.nodes) == independent_machines
        assert stage.power.total_mw == pytest.approx(independent_power)

    for stage, recorded_machines, recorded_power in zip(
        result.stages[:4], _P4_W01_MACHINES[:4], _P4_W01_POWER_MW[:4]
    ):
        machine_total = sum(node.machine_count for node in stage.nodes)
        power_mw = stage.power.total_mw

        assert abs(machine_total - recorded_machines) <= recorded_machines * _P4_W01_TOLERANCE
        assert abs(power_mw - recorded_power) <= recorded_power * _P4_W01_TOLERANCE

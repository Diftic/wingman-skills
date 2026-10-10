"""Tests for the pure five-stage master plan builder and stage transitions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog, normalize_class_name
from satisfactory_install import discover_docs
from satisfactory_master_plan import MasterPlanResult, build_master_plan, diff_stages
from satisfactory_progression import (
    PhaseDefinition,
    PhasePart,
    ProjectAssemblyData,
    load_project_assembly_phases,
)


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
    return (
        f'"/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/{package}'
        f'.{class_name}\'"'
    )


def _docs_data() -> list[dict]:
    """Fixture catalog: a shared expanding chain, a retiring recipe, an added
    recipe, a reused recipe, and a tier-gated recipe pair that flips which
    recipe satisfies the same demand once a later phase unlocks the tier.

    Every recipe runs 60 seconds with amount-1 ingredients/products, so
    amount == the per-machine item rate per minute and demand rates are
    hand-computable machine counts by inspection (matching the shared
    solver-test fixture convention).
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
                {"ClassName": "Desc_Rod_C", "mDisplayName": "Rod", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Screw_C", "mDisplayName": "Screw", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Widget_C", "mDisplayName": "Widget", "mForm": "RF_SOLID"},
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
                    "Recipe_Rod_C", "Rod", [("Desc_Ore_C", 1)], [("Desc_Rod_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Screw_C", "Screw", [("Desc_Ore_C", 1)], [("Desc_Screw_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
                _recipe(
                    "Recipe_Widget_C", "Widget", [("Desc_Ore_C", 1)], [("Desc_Widget_C", 1)],
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


def _phase_data(*phases: PhaseDefinition) -> ProjectAssemblyData:
    return ProjectAssemblyData(base_tiers=(0,), phases=tuple(phases))


def _part(item_class: str, rate_per_min: float) -> PhasePart:
    """A part whose quantity yields exactly ``rate_per_min`` at a 1-hour,
    pace-1.0 window (60 demand-minutes): quantity == rate_per_min * 60.
    """
    return PhasePart(item_class=item_class, display_name=item_class, quantity=rate_per_min * 60.0)


def _two_phase_data() -> ProjectAssemblyData:
    """Two-phase fixture data covering all five transition categories.

    Phase 1 unlocks tier 2, which is only available while planning phase
    2 (a phase's own unlocks never apply to itself): this is what lets
    ``Recipe_Plate_Efficient_C`` flip the Plate producer between stages
    even though Plate demand never changes.
    """
    phase1 = PhaseDefinition(
        phase=1,
        name="Phase One",
        window_hours_baseline=1.0,
        unlocks_tiers=(2,),
        parts=(
            _part("Desc_Ingot_C", 2.0),  # expands to 4.0 in phase 2
            _part("Desc_Rod_C", 3.0),  # retires: absent in phase 2
            _part("Desc_Screw_C", 1.0),  # reused: unchanged in phase 2
            _part("Desc_Plate_C", 4.0),  # flips producer: same rate, new recipe
        ),
    )
    phase2 = PhaseDefinition(
        phase=2,
        name="Phase Two",
        window_hours_baseline=1.0,
        unlocks_tiers=(),
        parts=(
            _part("Desc_Ingot_C", 4.0),
            _part("Desc_Widget_C", 5.0),  # added: absent in phase 1
            _part("Desc_Screw_C", 1.0),
            _part("Desc_Plate_C", 4.0),
        ),
    )
    return _phase_data(phase1, phase2)


def _node_counts(result: MasterPlanResult, phase: int) -> dict[str, int]:
    stage = next(stage for stage in result.stages if stage.phase == phase)
    return {node.node_id: node.machine_count for node in stage.nodes}


# --- diff_stages / build_master_plan: fixture transitions --------------------


def test_fixture_transitions_classify_all_five_categories(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    result = build_master_plan(catalog, data)

    assert result.status == "complete"
    assert len(result.stages) == 2
    assert len(result.transitions) == 1

    transition = result.transitions[0]
    assert transition.from_phase == 1
    assert transition.to_phase == 2

    assert transition.reused_nodes == ("node_recipe_screw:0",)
    assert transition.expanded_nodes == ("node_recipe_ingot:+2",)
    assert set(transition.added_nodes) == {
        "node_recipe_widget:+5",
        "node_recipe_plate_efficient:+4",
    }
    assert set(transition.retired_nodes) == {
        "node_recipe_rod:-3",
        "node_recipe_plate_fromore:-4",
    }


def test_fixture_reservations_are_exact(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    result = build_master_plan(catalog, data)

    reservations = dict(result.reservations)
    assert dict(reservations[1]) == {
        "node_recipe_ingot": 4,
        "node_recipe_rod": 3,
        "node_recipe_screw": 1,
        "node_recipe_plate_fromore": 4,
        "node_recipe_widget": 5,
        "node_recipe_plate_efficient": 4,
    }
    assert dict(reservations[2]) == {
        "node_recipe_ingot": 4,
        "node_recipe_screw": 1,
        "node_recipe_widget": 5,
        "node_recipe_plate_efficient": 4,
    }


def test_teardown_warning_fires_for_dropped_demand_and_allowed_set_flip(
    tmp_path: Path,
) -> None:
    """Rod retires because demand vanishes; Plate's producer retires because
    a newly unlocked, cheaper alternate wins the independent phase-2 solve
    even though Plate demand is unchanged. Both must surface a warning.
    """
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    result = build_master_plan(catalog, data)

    teardown_diagnostics = [diag for diag in result.diagnostics if "teardown warning" in diag]
    assert len(teardown_diagnostics) == 2
    assert any("node_recipe_rod" in diag for diag in teardown_diagnostics)
    assert any("node_recipe_plate_fromore" in diag for diag in teardown_diagnostics)


def test_diff_stages_reused_expanded_added_retired_encoding_direct(tmp_path: Path) -> None:
    """Exercise diff_stages directly against the two built stages."""
    catalog = _catalog(tmp_path)
    data = _two_phase_data()
    result = build_master_plan(catalog, data)
    previous, current = result.stages

    transition = diff_stages(previous, current)

    assert transition == result.transitions[0]


# --- Failure containment ------------------------------------------------------


def test_stopped_at_phase_preserves_earlier_stages_and_names_the_phase(
    tmp_path: Path,
) -> None:
    catalog = _catalog(tmp_path)
    phase1 = PhaseDefinition(
        phase=1,
        name="Phase One",
        window_hours_baseline=1.0,
        unlocks_tiers=(),
        parts=(_part("Desc_Ingot_C", 2.0),),
    )
    phase2 = PhaseDefinition(
        phase=2,
        name="Phase Two",
        window_hours_baseline=1.0,
        unlocks_tiers=(),
        parts=(_part("Desc_NoRecipe_C", 1.0),),
    )
    data = _phase_data(phase1, phase2)

    result = build_master_plan(catalog, data)

    assert result.status == "stopped_at_phase_2"
    assert len(result.stages) == 1
    assert result.stages[0].phase == 1
    assert result.transitions == ()
    assert any("phase 2" in diag for diag in result.diagnostics)


# --- Determinism ---------------------------------------------------------------


def test_build_master_plan_is_deterministic_across_runs(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    first = build_master_plan(catalog, data)
    second = build_master_plan(catalog, data)

    assert first.status == second.status
    assert first.transitions == second.transitions
    assert first.reservations == second.reservations
    assert [stage.nodes for stage in first.stages] == [stage.nodes for stage in second.stages]
    assert [stage.sources for stage in first.stages] == [stage.sources for stage in second.stages]
    assert [stage.flows for stage in first.stages] == [stage.flows for stage in second.stages]
    assert [stage.power for stage in first.stages] == [stage.power for stage in second.stages]


# --- Real-install integration ----------------------------------------------------


def test_real_install_five_phase_build() -> None:
    """Gated real-install build: full five-phase master plan at pace 1.0."""
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()

    result = build_master_plan(catalog, data, pace_multiplier=1.0)

    assert result.status == "complete"
    assert len(result.stages) == 5
    assert len(result.transitions) == 4

    # Phase 2 must reuse or expand every phase 1 node, never retire one; the
    # bundled data in fact never retires a node at any transition.
    assert result.transitions[0].retired_nodes == ()
    assert all(transition.retired_nodes == () for transition in result.transitions)

    # Deviation from the packet's "power strictly increases" assumption:
    # window_hours_baseline grows faster than part quantities in the bundled
    # data (phase 4 is an 8-hour window, phase 5 a 16-hour window for a less
    # than doubled quantity), so required rate per minute -- and therefore
    # power -- can drop phase-over-phase even though cumulative scope only
    # grows. Node count is the invariant that actually holds: every phase
    # demands new part types on top of the last, and nothing ever retires.
    node_counts = [len(stage.nodes) for stage in result.stages]
    assert node_counts == sorted(node_counts)
    assert len(set(node_counts)) == len(node_counts)
    assert all(stage.power.total_mw > 0.0 for stage in result.stages)

    assert not any("teardown warning" in diag for diag in result.diagnostics)


def test_real_install_node_identity_uses_normalized_recipe_key() -> None:
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()

    result = build_master_plan(catalog, data, pace_multiplier=1.0)

    for stage in result.stages:
        for node in stage.nodes:
            assert node.node_id == "node_" + normalize_class_name(node.recipe_class)

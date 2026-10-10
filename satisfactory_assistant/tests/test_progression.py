"""Tests for Project Assembly phase progression and capability snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import DocsCatalog, ItemDescriptor, load_docs_catalog, normalize_class_name
from satisfactory_install import discover_docs
from satisfactory_progression import (
    available_tiers_for_phase,
    build_capability_snapshot,
    derive_phase_demand,
    load_project_assembly_phases,
    validate_phases_against_docs,
)


_ALL_PART_CLASSES = [f"Desc_SpaceElevatorPart_{n}_C" for n in range(1, 13)]


def _items_catalog(omit: str | None = None) -> DocsCatalog:
    """Build a DocsCatalog with an ItemDescriptor for every bundled part class."""
    items = {}
    for class_name in _ALL_PART_CLASSES:
        if class_name == omit:
            continue
        items[normalize_class_name(class_name)] = ItemDescriptor(
            class_name=class_name,
            display_name=class_name,
            form="RF_SOLID",
        )
    return DocsCatalog(items=items, recipes={}, buildings={})


def _valid_phase_data() -> dict:
    """Minimal, structurally valid phase data for loader tests."""
    return {
        "schema_version": 1,
        "provenance": {"source_url": "https://example.test", "retrieved": "2026-07-01"},
        "base_tiers": [0, 1, 2],
        "phases": [
            {
                "phase": n,
                "name": f"Test Phase {n}",
                "window_hours_baseline": float(n),
                "unlocks_tiers": [],
                "parts": [
                    {
                        "item_class": f"Desc_Test_{n}_C",
                        "display_name": f"Test Part {n}",
                        "quantity": 10,
                    }
                ],
            }
            for n in range(1, 6)
        ],
    }


def _write_data(tmp_path: Path, data: dict, name: str = "phases.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _quoted_path(package: str, class_name: str) -> str:
    """Build a docs-style ``ClassPath'ObjectPath'`` quoted path string."""
    return (
        f'"/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/{package}'
        f'.{class_name}\'"'
    )


def _snapshot_docs_catalog(tmp_path: Path) -> DocsCatalog:
    """W02-style fixture: a tier-2 milestone, a tier-5 milestone, an alternate."""
    data = [
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
                                + _quoted_path("Recipes/Recipe_A", "Recipe_A_C")
                                + ","
                                + _quoted_path("Recipes/Recipe_B", "Recipe_B_C")
                                + ")"
                            ),
                        }
                    ],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_Tier5_C",
                    "mDisplayName": "Tier 5 Milestone",
                    "mType": "EST_Milestone",
                    "mTechTier": "5",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [
                        {
                            "Class": "BP_UnlockRecipe_C",
                            "mRecipes": (
                                "(" + _quoted_path("Recipes/Recipe_C", "Recipe_C_C") + ")"
                            ),
                        }
                    ],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_AlternateD_C",
                    "mDisplayName": "Alternate: D",
                    "mType": "EST_Alternate",
                    "mTechTier": "0",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [
                        {
                            "Class": "BP_UnlockRecipe_C",
                            "mRecipes": (
                                "("
                                + _quoted_path(
                                    "Recipes/Recipe_Alternate_D", "Recipe_Alternate_D_C"
                                )
                                + ")"
                            ),
                        }
                    ],
                    "mSchematicDependencies": [],
                },
            ],
        }
    ]
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(data), encoding="utf-16")
    return load_docs_catalog(path)


# --- Loader -----------------------------------------------------------------


def test_bundled_file_loads() -> None:
    data = load_project_assembly_phases()
    assert data.base_tiers == (0, 1, 2)
    assert [phase.phase for phase in data.phases] == [1, 2, 3, 4, 5]
    assert data.phases[0].name == "Distribution Platform"
    assert data.phases[3].unlocks_tiers == (9,)
    assert data.phases[4].unlocks_tiers == ()


def test_duplicate_phase_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    data["phases"][4]["phase"] = 1
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_missing_phase_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    del data["phases"][4]
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_zero_quantity_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    data["phases"][0]["parts"][0]["quantity"] = 0
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_bad_schema_version_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    data["schema_version"] = 99
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_empty_parts_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    data["phases"][0]["parts"] = []
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_missing_base_tiers_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    del data["base_tiers"]
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_non_list_base_tiers_raises(tmp_path: Path) -> None:
    data = _valid_phase_data()
    data["base_tiers"] = "0,1,2"
    path = _write_data(tmp_path, data)
    with pytest.raises(ValueError):
        load_project_assembly_phases(path)


def test_unreadable_path_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_project_assembly_phases(tmp_path / "does_not_exist.json")


# --- Docs validation ----------------------------------------------------


def test_validate_phases_against_docs_clean_catalog_yields_no_diagnostics() -> None:
    data = load_project_assembly_phases()
    catalog = _items_catalog()
    assert validate_phases_against_docs(data, catalog) == ()


def test_validate_phases_against_docs_missing_class_yields_one_diagnostic() -> None:
    data = load_project_assembly_phases()
    catalog = _items_catalog(omit="Desc_SpaceElevatorPart_7_C")
    diagnostics = validate_phases_against_docs(data, catalog)
    assert len(diagnostics) == 1
    assert "Desc_SpaceElevatorPart_7_C" in diagnostics[0]


# --- Demand math ----------------------------------------------------------


def test_phase1_pace1_demand_matches_exact_rate() -> None:
    data = load_project_assembly_phases()
    demand_set = derive_phase_demand(data, 1, 1.0)
    assert len(demand_set.demands) == 1
    demand = demand_set.demands[0]
    assert demand.item_class == "Desc_SpaceElevatorPart_1_C"
    assert demand.quantity == 50
    assert demand.required_rate_per_minute == pytest.approx(50 / 60)


def test_phase4_pace1_demand_matches_exact_rate() -> None:
    data = load_project_assembly_phases()
    demand_set = derive_phase_demand(data, 4, 1.0)
    assembly_director = next(
        d for d in demand_set.demands if d.item_class == "Desc_SpaceElevatorPart_7_C"
    )
    assert assembly_director.quantity == 500
    assert assembly_director.required_rate_per_minute == pytest.approx(500 / 480)


def test_phase4_pace3_demand_is_one_third_of_pace1() -> None:
    data = load_project_assembly_phases()
    pace1 = derive_phase_demand(data, 4, 1.0)
    pace3 = derive_phase_demand(data, 4, 3.0)
    rate1 = next(
        d.required_rate_per_minute
        for d in pace1.demands
        if d.item_class == "Desc_SpaceElevatorPart_7_C"
    )
    rate3 = next(
        d.required_rate_per_minute
        for d in pace3.demands
        if d.item_class == "Desc_SpaceElevatorPart_7_C"
    )
    assert rate3 == pytest.approx(rate1 / 3.0)
    assert pace3.window_hours == pytest.approx(pace1.window_hours * 3.0)


def test_pace_below_minimum_raises() -> None:
    data = load_project_assembly_phases()
    with pytest.raises(ValueError):
        derive_phase_demand(data, 4, 0.9)


def test_pace_above_maximum_raises() -> None:
    data = load_project_assembly_phases()
    with pytest.raises(ValueError):
        derive_phase_demand(data, 4, 3.1)


def test_unknown_phase_raises() -> None:
    data = load_project_assembly_phases()
    with pytest.raises(ValueError):
        derive_phase_demand(data, 6, 1.0)


# --- Tier availability ------------------------------------------------------


def test_available_tiers_for_phase_1() -> None:
    data = load_project_assembly_phases()
    assert available_tiers_for_phase(data, 1) == frozenset({0, 1, 2})


def test_available_tiers_for_phase_3() -> None:
    data = load_project_assembly_phases()
    assert available_tiers_for_phase(data, 3) == frozenset({0, 1, 2, 3, 4, 5, 6})


def test_available_tiers_for_phase_5() -> None:
    data = load_project_assembly_phases()
    assert available_tiers_for_phase(data, 5) == frozenset(range(10))


# --- Capability snapshot -----------------------------------------------------


def test_snapshot_upcoming_phase1_includes_only_tier2_milestone(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _snapshot_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "schematic_tier2" in snapshot.purchased_schematics
    assert "schematic_tier5" not in snapshot.purchased_schematics
    assert {"recipe_a", "recipe_b"} <= snapshot.allowed_recipes
    assert "recipe_c" not in snapshot.allowed_recipes


def test_snapshot_upcoming_phase3_includes_both_milestones(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _snapshot_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=3)

    assert "schematic_tier2" in snapshot.purchased_schematics
    assert "schematic_tier5" in snapshot.purchased_schematics
    assert {"recipe_a", "recipe_b", "recipe_c"} <= snapshot.allowed_recipes


def test_snapshot_alternate_recipe_excluded_by_default(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _snapshot_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=3)

    assert "recipe_alternate_d" not in snapshot.allowed_recipes


def test_snapshot_alternate_recipe_included_when_opted_in(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _snapshot_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(
        catalog,
        data,
        upcoming_phase=3,
        include_alternates=("Recipe_Alternate_D_C",),
    )

    assert "recipe_alternate_d" in snapshot.allowed_recipes


def test_snapshot_max_tier_matches_available_tiers(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _snapshot_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)
    assert snapshot.max_tier == 2

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=3)
    assert snapshot.max_tier == 6


# --- Real-install integration -------------------------------------------------


def test_real_install_bundled_phases_validate_cleanly() -> None:
    """Bundled Project Assembly data must validate against the real Docs.

    Skips cleanly when no Satisfactory install can be found on this
    machine (mirrors the discover_docs skip pattern used elsewhere).
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()

    diagnostics = validate_phases_against_docs(data, catalog)
    assert diagnostics == ()


# --- Capability snapshot completeness (SSP-P3-W02) ---------------------------


def _produced_in(building_class: str) -> str:
    return f'("/Game/FactoryGame/Buildable/Factory/X/{building_class}.{building_class}")'


def _completeness_docs_catalog(tmp_path: Path) -> DocsCatalog:
    """SSP-P3-W02 fixture: EST_Tutorial/EST_Custom/EST_MAM schematics and base recipes.

    Covers the completeness rules: in-tier EST_Tutorial and EST_Custom
    schematics count as purchased, an above-tier EST_Custom schematic does
    not, EST_MAM never does regardless of tier, an automatable base recipe
    with no unlocking schematic is allowed, and a same-shaped
    ``recipe_alternate_``-prefixed recipe with no unlocking schematic
    stays excluded.
    """
    data = [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGSchematic'",
            "Classes": [
                {
                    "ClassName": "Schematic_TutorialInTier_C",
                    "mDisplayName": "Tutorial In Tier",
                    "mType": "EST_Tutorial",
                    "mTechTier": "0",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_CustomInTier_C",
                    "mDisplayName": "Custom In Tier",
                    "mType": "EST_Custom",
                    "mTechTier": "1",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_CustomAboveTier_C",
                    "mDisplayName": "Custom Above Tier",
                    "mType": "EST_Custom",
                    "mTechTier": "5",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_MamInTier_C",
                    "mDisplayName": "MAM In Tier",
                    "mType": "EST_MAM",
                    "mTechTier": "0",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [],
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                {
                    "ClassName": "Recipe_BaseNoSchematic_C",
                    "mDisplayName": "Base No Schematic",
                    "mIngredients": "",
                    "mProduct": "",
                    "mManufactoringDuration": "1.000000",
                    "mProducedIn": _produced_in("Build_ConstructorMk1_C"),
                },
                {
                    "ClassName": "Recipe_Alternate_NoSchematic_C",
                    "mDisplayName": "Alternate No Schematic",
                    "mIngredients": "",
                    "mProduct": "",
                    "mManufactoringDuration": "1.000000",
                    "mProducedIn": _produced_in("Build_ConstructorMk1_C"),
                },
            ],
        },
        {
            "NativeClass": (
                "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableManufacturer'"
            ),
            "Classes": [
                {"ClassName": "Build_ConstructorMk1_C", "mManufacturingSpeed": "1.000000"},
            ],
        },
    ]
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(data), encoding="utf-16")
    return load_docs_catalog(path)


def test_snapshot_includes_in_tier_tutorial_and_custom_schematics(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _completeness_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "schematic_tutorialintier" in snapshot.purchased_schematics
    assert "schematic_customintier" in snapshot.purchased_schematics


def test_snapshot_excludes_above_tier_custom_schematic(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _completeness_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "schematic_customabovetier" not in snapshot.purchased_schematics


def test_snapshot_excludes_mam_schematic_within_tier(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _completeness_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "schematic_mamintier" not in snapshot.purchased_schematics


def test_snapshot_allows_base_recipe_with_no_unlocking_schematic(tmp_path: Path) -> None:
    data = load_project_assembly_phases()
    catalog = _completeness_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "recipe_basenoschematic" in snapshot.allowed_recipes


def test_snapshot_excludes_alternate_prefixed_recipe_with_no_unlocking_schematic(
    tmp_path: Path,
) -> None:
    data = load_project_assembly_phases()
    catalog = _completeness_docs_catalog(tmp_path)

    snapshot = build_capability_snapshot(catalog, data, upcoming_phase=1)

    assert "recipe_alternate_noschematic" not in snapshot.allowed_recipes

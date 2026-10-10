"""Tests for the schematic and HUB gate dataset in satisfactory_docs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog
from satisfactory_install import discover_docs


def _quoted_path(package: str, class_name: str) -> str:
    """Build a docs-style ``ClassPath'ObjectPath'`` quoted path string."""
    return (
        f'"/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/{package}'
        f'.{class_name}\'"'
    )


def _docs_file(tmp_path: Path) -> Path:
    data = [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGSchematic'",
            "Classes": [
                {
                    "ClassName": "Schematic_Tier3_C",
                    "mDisplayName": "Tier 3: Steel Production",
                    "mType": "EST_Milestone",
                    "mTechTier": "3",
                    "mTimeToComplete": "0.000000",
                    "mCost": (
                        "((ItemClass=\"/Script/Engine.BlueprintGeneratedClass'/Game/"
                        "FactoryGame/Resource/Parts/SteelIngot/Desc_SteelIngot.Desc_SteelIngot_C'\""
                        ",Amount=50),(ItemClass=\"/Script/Engine.BlueprintGeneratedClass'/Game/"
                        "FactoryGame/Resource/Parts/Wire/Desc_Wire.Desc_Wire_C'\",Amount=100))"
                    ),
                    "mUnlocks": [
                        {
                            "Class": "BP_UnlockRecipe_C",
                            "mRecipes": (
                                "("
                                + _quoted_path(
                                    "Recipes/Smelter/Recipe_IngotSteel",
                                    "Recipe_IngotSteel_C",
                                )
                                + ","
                                + _quoted_path(
                                    "Recipes/Constructor/Recipe_SteelBeam",
                                    "Recipe_SteelBeam_C",
                                )
                                + ")"
                            ),
                        },
                        {
                            "Class": "BP_UnlockInfoOnly_C",
                            "mHubName": "Steel Age",
                        },
                    ],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_Alternate_Wire2_C",
                    "mDisplayName": "Alternate: Fused Wire",
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
                                    "Recipes/AlternateRecipes/Parts/Recipe_Alternate_Wire_2",
                                    "Recipe_Alternate_Wire_2_C",
                                )
                                + ")"
                            ),
                        }
                    ],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_ResourceSinkBonus_C",
                    "mDisplayName": "AWESOME Sink Bonus Program",
                    "mType": "EST_ResourceSink",
                    "mTechTier": "0",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [],
                },
                {
                    "ClassName": "Schematic_Tier4_C",
                    "mDisplayName": "Tier 4: Advanced Steel Production",
                    "mType": "EST_Milestone",
                    "mTechTier": "4",
                    "mTimeToComplete": "0.000000",
                    "mCost": "",
                    "mUnlocks": [],
                    "mSchematicDependencies": [
                        {
                            "Class": "BP_SchematicPurchasedDependency_C",
                            "mSchematics": (
                                "("
                                + _quoted_path("Schematics/Schematic_Tier3", "Schematic_Tier3_C")
                                + ")"
                            ),
                            "mRequireAllSchematicsToBePurchased": "True",
                        }
                    ],
                },
                {
                    "ClassName": "Schematic_Malformed_C",
                    "mDisplayName": "Malformed Entry",
                    "mType": "EST_Custom",
                    "mUnlocks": [],
                },
            ],
        }
    ]
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(data), encoding="utf-16")
    return path


def test_milestone_fixture_round_trip(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    schematic = catalog.schematic("Schematic_Tier3")

    assert schematic is not None
    assert schematic.schematic_type == "EST_Milestone"
    assert schematic.tech_tier == 3
    assert {amount.amount for amount in schematic.cost} == {50, 100}
    assert schematic.unlocked_recipes == ("recipe_ingotsteel", "recipe_steelbeam")
    assert schematic.dependency_schematics == ()


def test_unlock_info_only_entries_are_ignored(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    schematic = catalog.schematic("Schematic_Tier3")

    assert schematic is not None
    # Only the BP_UnlockRecipe_C entry contributes recipes; BP_UnlockInfoOnly_C
    # carries no mRecipes field and must not appear or raise.
    assert len(schematic.unlocked_recipes) == 2


def test_milestones_by_tier_returns_matching_tier(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    tier3 = catalog.milestones_by_tier(3)
    assert [s.class_name for s in tier3] == ["Schematic_Tier3_C"]
    assert catalog.milestones_by_tier(9) == ()


def test_schematics_of_type_exact_match(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    resource_sinks = catalog.schematics_of_type("EST_ResourceSink")
    assert [s.class_name for s in resource_sinks] == ["Schematic_ResourceSinkBonus_C"]
    alternates = catalog.schematics_of_type("EST_Alternate")
    assert [s.class_name for s in alternates] == ["Schematic_Alternate_Wire2_C"]


def test_dependency_schematics_parsed(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    schematic = catalog.schematic("Schematic_Tier4")

    assert schematic is not None
    assert schematic.dependency_schematics == ("schematic_tier3",)


def test_malformed_entry_parses_with_defaults_without_raising(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    schematic = catalog.schematic("Schematic_Malformed_C")

    assert schematic is not None
    assert schematic.tech_tier == 0
    assert schematic.time_to_complete == 0.0
    assert schematic.cost == ()
    assert schematic.unlocked_recipes == ()


def test_recipe_unlocked_by_returns_unlocking_schematics(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    assert catalog.recipe_unlocked_by("Recipe_IngotSteel_C") == ("schematic_tier3",)
    assert catalog.recipe_unlocked_by("Recipe_DoesNotExist_C") == ()


def test_is_alternate_recipe_for_alternate_unlocked_recipe(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    assert catalog.is_alternate_recipe("Recipe_Alternate_Wire_2_C") is True


def test_is_alternate_recipe_for_prefix_named_recipe_with_no_schematic(
    tmp_path: Path,
) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    assert catalog.is_alternate_recipe("Recipe_Alternate_NeverUnlocked_C") is True


def test_is_alternate_recipe_false_for_plain_milestone_recipe(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    assert catalog.is_alternate_recipe("Recipe_IngotSteel_C") is False


def test_schematic_count_and_lookup(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))

    assert catalog.schematic_count == 5
    assert catalog.schematic("Schematic_DoesNotExist_C") is None


def test_backward_compatible_construction_without_schematics() -> None:
    """DocsCatalog still constructs with no schematics kwarg (existing call sites)."""
    from satisfactory_docs import DocsCatalog

    catalog = DocsCatalog(items={}, recipes={}, buildings={})
    assert catalog.schematic_count == 0
    assert catalog.schematic("anything") is None
    assert catalog.milestones_by_tier(1) == ()
    assert catalog.is_alternate_recipe("Recipe_Alternate_X_C") is True
    assert catalog.is_alternate_recipe("Recipe_Plain_C") is False


_EST_TYPES = (
    "EST_Custom",
    "EST_Tutorial",
    "EST_ResourceSink",
    "EST_MAM",
    "EST_Milestone",
    "EST_HardDrive",
    "EST_Customization",
    "EST_Alternate",
)


def test_real_install_schematic_dataset() -> None:
    """Integration check against the real Docs export, when present.

    Skips cleanly when no Satisfactory install can be found on this
    machine (mirrors the discover_docs skip pattern used elsewhere).
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)

    for tier in range(1, 10):
        assert len(catalog.milestones_by_tier(tier)) >= 1, f"tier {tier} has no milestones"

    all_schematics = []
    for est_type in _EST_TYPES:
        all_schematics.extend(catalog.schematics_of_type(est_type))

    milestone_count = len(catalog.schematics_of_type("EST_Milestone"))
    alternate_count = len(catalog.schematics_of_type("EST_Alternate"))
    assert milestone_count >= 40
    assert alternate_count >= 100

    # EST_Custom and EST_ResourceSink reward schematics can unlock cosmetic
    # entries (swatches, patterns, skins) that live in the separate
    # FGCustomizationRecipe Docs group, which this packet does not parse
    # (out of scope: only FGRecipe production recipes). Restricting the
    # resolve-rate check to the schematic types that gate production
    # recipes avoids penalizing that intentional scope boundary.
    production_gate_types = (
        "EST_Milestone",
        "EST_Alternate",
        "EST_MAM",
        "EST_HardDrive",
        "EST_Tutorial",
    )
    total_refs = 0
    resolved_refs = 0
    for schematic in all_schematics:
        if schematic.schematic_type not in production_gate_types:
            continue
        for recipe_key in schematic.unlocked_recipes:
            total_refs += 1
            if catalog.recipe(recipe_key) is not None:
                resolved_refs += 1

    assert total_refs > 0
    assert resolved_refs / total_refs >= 0.9

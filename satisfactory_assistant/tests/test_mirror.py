"""Tests for Docs-backed factory mirror calculations."""

from __future__ import annotations

import json
from pathlib import Path

from satisfactory_docs import load_docs_catalog, parse_item_amounts
from satisfactory_mirror import (
    TrendConfig,
    build_factory_mirror,
    calculate_health,
    store_mirror_artifacts,
)


def _docs_file(tmp_path: Path) -> Path:
    data = [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGItemDescriptor'",
            "Classes": [
                {
                    "ClassName": "Desc_IronOre_C",
                    "mDisplayName": "Iron Ore",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_IronIngot_C",
                    "mDisplayName": "Iron Ingot",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_Water_C",
                    "mDisplayName": "Water",
                    "mForm": "RF_LIQUID",
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                {
                    "ClassName": "Recipe_IngotIron_C",
                    "mDisplayName": "Iron Ingot",
                    "mIngredients": "((ItemClass=\"/Script/Engine.BlueprintGeneratedClass'/Game/FactoryGame/Resource/RawResources/Iron/Desc_IronOre.Desc_IronOre_C'\",Amount=1))",
                    "mProduct": "((ItemClass=\"/Script/Engine.BlueprintGeneratedClass'/Game/FactoryGame/Resource/Parts/IronIngot/Desc_IronIngot.Desc_IronIngot_C'\",Amount=1))",
                    "mManufactoringDuration": "2.000000",
                    "mProducedIn": "(\"/Game/FactoryGame/Buildable/Factory/SmelterMk1/Build_SmelterMk1.Build_SmelterMk1_C\")",
                }
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableManufacturer'",
            "Classes": [
                {
                    "ClassName": "Build_SmelterMk1_C",
                    "mDisplayName": "Smelter",
                    "mManufacturingSpeed": "1.000000",
                    "mPowerConsumption": "4.000000",
                }
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableWaterPump'",
            "Classes": [
                {
                    "ClassName": "Build_WaterPump_C",
                    "mDisplayName": "Water Extractor",
                    "mExtractCycleTime": "1.000000",
                    "mItemsPerCycle": "2000",
                    "mPowerConsumption": "20.000000",
                }
            ],
        },
    ]
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(data), encoding="utf-16")
    return path


def test_parse_item_amounts_extracts_trailing_unreal_class() -> None:
    amounts = parse_item_amounts(
        "((ItemClass=\"/Script/Engine.BlueprintGeneratedClass'/Game/X/Desc_IronOre.Desc_IronOre_C'\",Amount=1))"
    )
    assert amounts[0].class_name == "Desc_IronOre_C"
    assert amounts[0].amount == 1


def test_catalog_loads_recipe_and_fluid_units(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    recipe = catalog.recipe("Recipe_IngotIron")
    water = catalog.item("Desc_Water")

    assert recipe is not None
    assert recipe.products[0].class_name == "Desc_IronIngot_C"
    assert water is not None
    assert catalog.rate_amount(type("Amount", (), {"class_name": "Desc_Water_C", "amount": 2000})()) == 2


def test_factory_mirror_calculates_expected_recipe_and_extractor_rates(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    snapshot = {
        "source": {"saveName": "Test"},
        "counts": {"objectsWithCurrentRecipe": 1},
        "machines": [
            {
                "id": "smelter-1",
                "type": "Build_SmelterMk1",
                "kind": "manufacturer",
                "transform": {"translation": {"x": 0, "y": 0, "z": 0}},
                "recipe": {"name": "Recipe_IngotIron"},
                "clock": {"currentPotential": 2.0},
                "state": {
                    "currentProductivityMeasurementDuration": 10,
                    "currentProductivityMeasurementProduceDuration": 5,
                },
            },
            {
                "id": "smelter-2",
                "type": "Build_SmelterMk1",
                "kind": "manufacturer",
                "transform": {"translation": {"x": 2000, "y": 0, "z": 0}},
                "recipe": {"name": "Recipe_IngotIron"},
                "clock": {"currentPotential": 1.0},
                "state": {},
            },
            {
                "id": "pump-1",
                "type": "Build_WaterPump",
                "kind": "extractor",
                "transform": {"translation": {"x": 5000, "y": 0, "z": 0}},
                "extractableResource": {"name": "Desc_Water"},
                "clock": {"currentPotential": 1.0},
                "state": {},
            },
        ],
    }

    mirror = build_factory_mirror(snapshot, catalog, proximity_cm=6000)

    outputs = {row["item"]: row["ratePerMin"] for row in mirror["expectedTotals"]["outputs"]}
    estimates = {
        row["item"]: row["ratePerMin"]
        for row in mirror["observedEstimateTotals"]["outputs"]
    }
    assert outputs["Iron Ingot"] == 90
    assert estimates["Iron Ingot"] == 30
    assert outputs["Water"] == 120
    assert mirror["counts"]["inferredLines"] == 1


def test_health_flags_repeated_zero_and_rolling_deviation(tmp_path: Path) -> None:
    catalog = load_docs_catalog(_docs_file(tmp_path))
    snapshot = {
        "source": {"saveName": "Test"},
        "counts": {"objectsWithCurrentRecipe": 1},
        "machines": [
            {
                "id": "smelter-zero",
                "type": "Build_SmelterMk1",
                "kind": "manufacturer",
                "transform": {"translation": {"x": 0, "y": 0, "z": 0}},
                "recipe": {"name": "Recipe_IngotIron"},
                "clock": {"currentPotential": 1.0},
                "state": {
                    "currentProductivityMeasurementDuration": 10,
                    "currentProductivityMeasurementProduceDuration": 0,
                },
            }
        ],
    }
    config = TrendConfig(window_saves=3, zero_streak_saves=3, deviation_threshold=0.25)

    for _ in range(3):
        mirror = build_factory_mirror(snapshot, catalog)
        info = store_mirror_artifacts(tmp_path, snapshot, mirror, config)

    assert info["health"]["zeroStreakCount"] == 1
    assert info["health"]["deviations"][0]["item"] == "Iron Ingot"


def test_calculate_health_handles_empty_history() -> None:
    assert calculate_health([], TrendConfig())["status"] == "no_observations"


# A valid observation row written in compact form (no spaces after ":"/","),
# which a full json.dumps rewrite would normalise to a spaced form. Seeding the
# file with this lets a test tell an append-only write from a rewrite.
_RAW_ROW = '{"expectedOutputs":[],"estimatedOutputs":[],"zeroMachineIds":[]}\n'


def test_store_mirror_leaves_file_untouched_under_cap(tmp_path: Path) -> None:
    config = TrendConfig(window_saves=3)
    cap = max(50, config.window_saves * 4)

    obs_path = tmp_path / "mirror" / "observations.jsonl"
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    seeded = _RAW_ROW * 3  # well under the cap
    obs_path.write_text(seeded, encoding="utf-8")

    store_mirror_artifacts(tmp_path, {}, {"machines": []}, config)

    text = obs_path.read_text(encoding="utf-8")
    # Under the cap the append is the only write, so the seeded rows survive
    # byte-for-byte; a rewrite would have re-spaced them.
    assert text.startswith(seeded)
    assert text.count("\n") == 4  # three seeded rows plus one appended
    assert cap == 50  # guards the constant this test's row counts rely on


def test_store_mirror_caps_file_over_limit(tmp_path: Path) -> None:
    config = TrendConfig(window_saves=3)
    cap = max(50, config.window_saves * 4)

    obs_path = tmp_path / "mirror" / "observations.jsonl"
    obs_path.parent.mkdir(parents=True, exist_ok=True)
    obs_path.write_text(_RAW_ROW * cap, encoding="utf-8")  # already at the cap

    store_mirror_artifacts(tmp_path, {}, {"machines": []}, config)

    # The append pushed history past the cap, so the file is trimmed back to it.
    assert obs_path.read_text(encoding="utf-8").count("\n") == cap


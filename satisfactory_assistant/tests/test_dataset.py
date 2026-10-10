"""Tests for memoized Docs catalog loading and bounded dataset lookup."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import satisfactory_dataset as ds
from satisfactory_docs import load_docs_catalog
from satisfactory_install import discover_docs


@pytest.fixture(autouse=True)
def _reset_memo():
    ds.clear_dataset_memo()
    yield
    ds.clear_dataset_memo()


def _minimal_docs(item_name: str) -> list[dict]:
    """A single-item Docs fixture, used where only signature behavior matters."""
    return [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGItemDescriptor'",
            "Classes": [
                {
                    "ClassName": f"Desc_{item_name}_C",
                    "mDisplayName": item_name,
                    "mForm": "RF_SOLID",
                },
            ],
        }
    ]


def _amount(class_name: str, amount: float) -> str:
    return (
        f'(ItemClass="/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/'
        f'Resource/Parts/X/Desc_X.{class_name}\'",Amount={amount})'
    )


def _amounts(entries: list[tuple[str, float]]) -> str:
    return "(" + ",".join(_amount(class_name, amount) for class_name, amount in entries) + ")"


def _produced_in(building_class: str) -> str:
    return f'("/Game/FactoryGame/Buildable/Factory/X/{building_class}.{building_class}")'


def _lookup_docs_data() -> list[dict]:
    """Items and recipes covering exact/prefix/substring ranking, the cap,

    the alternate flag, and fluid unit conversion in one catalog.
    """
    return [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGItemDescriptor'",
            "Classes": [
                {"ClassName": "Desc_IronIngot_C", "mDisplayName": "Iron Ingot", "mForm": "RF_SOLID"},
                {
                    "ClassName": "Desc_IronIngotBundle_C",
                    "mDisplayName": "Iron Ingot Bundle",
                    "mForm": "RF_SOLID",
                },
                {
                    "ClassName": "Desc_ReinforcedIronIngot_C",
                    "mDisplayName": "Reinforced Iron Ingot",
                    "mForm": "RF_SOLID",
                },
                {"ClassName": "Desc_IronOre_C", "mDisplayName": "Iron Ore", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_IronPipe_C", "mDisplayName": "Iron Pipe", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_IronPlate_C", "mDisplayName": "Iron Plate", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_IronRod_C", "mDisplayName": "Iron Rod", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_IronScrew_C", "mDisplayName": "Iron Screw", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_CopperOre_C", "mDisplayName": "Copper Ore", "mForm": "RF_SOLID"},
                {"ClassName": "Desc_Water_C", "mDisplayName": "Water", "mForm": "RF_LIQUID"},
                {"ClassName": "Desc_SteelIngot_C", "mDisplayName": "Steel Ingot", "mForm": "RF_SOLID"},
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                {
                    "ClassName": "Recipe_IngotIron_C",
                    "mDisplayName": "Iron Ingot",
                    "mIngredients": _amounts([("Desc_IronOre_C", 30)]),
                    "mProduct": _amounts([("Desc_IronIngot_C", 30)]),
                    "mManufactoringDuration": "2.000000",
                    "mProducedIn": _produced_in("Build_SmelterMk1_C"),
                },
                {
                    "ClassName": "Recipe_Alternate_PureIronIngot_C",
                    "mDisplayName": "Alternate: Pure Iron Ingot",
                    "mIngredients": _amounts(
                        [("Desc_IronOre_C", 35), ("Desc_Water_C", 2000)]
                    ),
                    "mProduct": _amounts([("Desc_IronIngot_C", 65)]),
                    "mManufactoringDuration": "6.000000",
                    "mProducedIn": _produced_in("Build_OilRefinery_C"),
                },
            ],
        },
    ]


def _write_docs(path: Path, data: list[dict]) -> Path:
    path.write_text(json.dumps(data), encoding="utf-16")
    return path


def _lookup_catalog(tmp_path: Path):
    docs_path = _write_docs(tmp_path / "en-US.json", _lookup_docs_data())
    catalog, _ = ds.get_docs_catalog(docs_path)
    return catalog


def _counting_loader(monkeypatch) -> dict[str, int]:
    """Wrap ``satisfactory_dataset.load_docs_catalog`` with a call counter."""
    calls = {"count": 0}
    original = ds.load_docs_catalog

    def counting(path: Path):
        calls["count"] += 1
        return original(path)

    monkeypatch.setattr(ds, "load_docs_catalog", counting)
    return calls


# --- memo hit / invalidation / cap / failure ---


def test_memo_hit_parses_once(tmp_path: Path, monkeypatch) -> None:
    calls = _counting_loader(monkeypatch)
    docs_path = tmp_path / "en-US.json"
    docs_path.write_text(json.dumps(_minimal_docs("Widget")), encoding="utf-8")

    catalog1, info1 = ds.get_docs_catalog(docs_path)
    catalog2, info2 = ds.get_docs_catalog(docs_path)

    assert calls["count"] == 1
    assert catalog1 is catalog2
    assert info1.parse_ms is not None
    assert info2.parse_ms is None
    assert info1.item_count == 1


def test_content_change_triggers_reparse(tmp_path: Path, monkeypatch) -> None:
    calls = _counting_loader(monkeypatch)
    docs_path = tmp_path / "en-US.json"
    docs_path.write_text(json.dumps(_minimal_docs("Widget")), encoding="utf-8")
    os.utime(docs_path, (1_000_000.0, 1_000_000.0))
    catalog1, info1 = ds.get_docs_catalog(docs_path)

    docs_path.write_text(json.dumps(_minimal_docs("WidgetTwo")), encoding="utf-8")
    os.utime(docs_path, (2_000_000.0, 2_000_000.0))
    catalog2, info2 = ds.get_docs_catalog(docs_path)

    assert calls["count"] == 2
    assert catalog1 is not catalog2
    assert info1.sha256 != info2.sha256
    assert info2.parse_ms is not None
    assert catalog1.item("Desc_Widget_C") is not None
    assert catalog2.item("Desc_WidgetTwo_C") is not None


def test_touch_only_change_does_not_reparse_and_refreshes_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _counting_loader(monkeypatch)
    docs_path = tmp_path / "en-US.json"
    docs_path.write_text(json.dumps(_minimal_docs("Widget")), encoding="utf-8")
    os.utime(docs_path, (1_000_000.0, 1_000_000.0))
    catalog1, info1 = ds.get_docs_catalog(docs_path)

    os.utime(docs_path, (2_000_000.0, 2_000_000.0))
    catalog2, info2 = ds.get_docs_catalog(docs_path)

    assert calls["count"] == 1
    assert catalog1 is catalog2
    assert info2.parse_ms is None
    assert info2.sha256 == info1.sha256
    assert info2.mtime_ns != info1.mtime_ns


def test_memo_cap_evicts_oldest_on_fifth_distinct_path(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _counting_loader(monkeypatch)
    paths = []
    for index in range(5):
        sub = tmp_path / f"install_{index}"
        sub.mkdir()
        docs_path = sub / "en-US.json"
        docs_path.write_text(json.dumps(_minimal_docs(f"Item{index}")), encoding="utf-8")
        paths.append(docs_path)
        ds.get_docs_catalog(docs_path)

    assert calls["count"] == 5

    # The oldest (first) path was evicted by the fifth distinct load; reloading
    # it must reparse.
    ds.get_docs_catalog(paths[0])
    assert calls["count"] == 6

    # The most recently loaded path is still cached.
    ds.get_docs_catalog(paths[4])
    assert calls["count"] == 6


def test_missing_file_raises_then_recovers_once_created(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _counting_loader(monkeypatch)
    docs_path = tmp_path / "en-US.json"

    with pytest.raises(OSError):
        ds.get_docs_catalog(docs_path)

    docs_path.write_text(json.dumps(_minimal_docs("Widget")), encoding="utf-8")
    catalog, info = ds.get_docs_catalog(docs_path)

    assert calls["count"] == 1
    assert info.parse_ms is not None
    assert catalog.item_count == 1


def test_invalid_content_raises_then_recovers_on_next_valid_load(
    tmp_path: Path, monkeypatch
) -> None:
    calls = _counting_loader(monkeypatch)
    docs_path = tmp_path / "en-US.json"
    docs_path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")

    with pytest.raises(ValueError):
        ds.get_docs_catalog(docs_path)

    assert calls["count"] == 1

    docs_path.write_text(json.dumps(_minimal_docs("Widget")), encoding="utf-8")
    catalog, info = ds.get_docs_catalog(docs_path)

    assert calls["count"] == 2
    assert info.parse_ms is not None
    assert catalog.item_count == 1


# --- DocsCatalog.all_items / all_recipes accessors ---


def test_all_items_and_all_recipes_return_full_tuples(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)

    items = catalog.all_items()
    recipes = catalog.all_recipes()

    assert isinstance(items, tuple)
    assert isinstance(recipes, tuple)
    assert len(items) == catalog.item_count == 11
    assert len(recipes) == catalog.recipe_count == 2
    assert {item.display_name for item in items} >= {"Iron Ingot", "Steel Ingot", "Water"}
    assert {recipe.display_name for recipe in recipes} == {
        "Iron Ingot",
        "Alternate: Pure Iron Ingot",
    }


# --- lookup_items ---


def test_lookup_items_empty_query_returns_empty_tuple(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    assert ds.lookup_items(catalog, "") == ()
    assert ds.lookup_items(catalog, "   ") == ()


def test_lookup_items_ranking_exact_then_prefix_then_substring(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_items(catalog, "Iron Ingot", limit=5)

    assert [result["item"] for result in results] == [
        "Iron Ingot",
        "Iron Ingot Bundle",
        "Reinforced Iron Ingot",
    ]
    assert results[0] == {"item": "Iron Ingot", "class": "Desc_IronIngot_C", "form": "RF_SOLID"}


def test_lookup_items_limit_clamped_to_five(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_items(catalog, "Iron", limit=100)

    assert len(results) == 5
    assert [result["item"] for result in results] == [
        "Iron Ingot",
        "Iron Ingot Bundle",
        "Iron Ore",
        "Iron Pipe",
        "Iron Plate",
    ]


def test_lookup_items_limit_clamped_to_minimum_one(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_items(catalog, "Iron", limit=0)
    assert len(results) == 1


# --- lookup_recipes ---


def test_lookup_recipes_empty_query_returns_empty_tuple(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    assert ds.lookup_recipes(catalog, "") == ()
    assert ds.lookup_recipes(catalog, "   ") == ()


def test_lookup_recipes_ranking_exact_then_substring(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_recipes(catalog, "Iron Ingot", limit=5)

    assert [result["recipe"] for result in results] == [
        "Iron Ingot",
        "Alternate: Pure Iron Ingot",
    ]


def test_lookup_recipes_ranking_prefix_then_substring(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_recipes(catalog, "Iron", limit=5)

    assert [result["recipe"] for result in results] == [
        "Iron Ingot",
        "Alternate: Pure Iron Ingot",
    ]


def test_lookup_recipes_alternate_flag_duration_and_produced_in(
    tmp_path: Path,
) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_recipes(catalog, "Iron Ingot", limit=5)
    plain = next(result for result in results if result["recipe"] == "Iron Ingot")
    alternate = next(
        result for result in results if result["recipe"] == "Alternate: Pure Iron Ingot"
    )

    assert plain["alternate"] is False
    assert alternate["alternate"] is True
    assert plain["duration_seconds"] == 2.0
    assert plain["produced_in"] == ("Build_SmelterMk1_C",)
    assert plain["class"] == "Recipe_IngotIron_C"


def test_lookup_recipes_fluid_rates_divided_by_1000(tmp_path: Path) -> None:
    catalog = _lookup_catalog(tmp_path)
    results = ds.lookup_recipes(catalog, "Alternate: Pure Iron Ingot", limit=5)

    assert len(results) == 1
    alternate = results[0]
    # 2000 raw units -> 2 m3 per cycle, at (60 / 6s) cycles per minute = 20.
    assert alternate["inputs_per_min"]["Water"] == 20.0
    # 35 solid units per cycle at 10 cycles/min = 350/min.
    assert alternate["inputs_per_min"]["Iron Ore"] == 350.0
    assert alternate["outputs_per_min"]["Iron Ingot"] == 650.0


# --- gated real-install test ---


def test_real_install_memoizes_and_lookup_finds_steel_ingot() -> None:
    """Integration check against the real Docs export, when present.

    Skips cleanly when no Satisfactory install can be found on this
    machine (mirrors the discover_docs skip pattern used elsewhere).
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    docs_path = discovery.docs_path
    catalog1, info1 = ds.get_docs_catalog(docs_path)
    catalog2, info2 = ds.get_docs_catalog(docs_path)

    assert info1.parse_ms is not None
    assert info2.parse_ms is None
    assert catalog1 is catalog2

    direct = load_docs_catalog(docs_path)
    assert catalog1.item_count == direct.item_count
    assert catalog1.recipe_count == direct.recipe_count
    assert catalog1.building_count == direct.building_count
    assert catalog1.schematic_count == direct.schematic_count

    items = ds.lookup_items(catalog1, "Steel Ingot", limit=5)
    assert any(result["item"] == "Steel Ingot" for result in items)

    recipes = ds.lookup_recipes(catalog1, "Steel Ingot", limit=5)
    assert len(recipes) >= 1
    assert any("Steel Ingot" in recipe["outputs_per_min"] for recipe in recipes)

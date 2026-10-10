"""Tests for solver recipe pins/bans and the two-level machine-minimizing objective.

SSP-P5-W02. Fixture mirrors ``test_solver.py``'s style (a self-contained
Docs catalog, every recipe running 60 seconds so amount/duration*60 ==
amount and results are hand-computable), extended with two competing
Plate recipes of different raw efficiency for the ban/pin cases and the
existing Ingot->Plate chain for the two-level case.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog, normalize_class_name
from satisfactory_solver import solve_stage


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
    """Ore -> Ingot -> Plate chain, plus two direct Ore -> Plate alternates.

    - ``Recipe_Ingot_C``: 1 Ore -> 1 Ingot (Smelter).
    - ``Recipe_Plate_C``: 1 Ingot -> 1 Plate (Constructor); chained with
      Ingot this is also a 1 Ore : 1 Plate route, but costs two recipe
      runs (one Ingot, one Plate) per Plate instead of one.
    - ``Recipe_Plate_Efficient_C``: 1 Ore -> 1 Plate directly (Constructor).
    - ``Recipe_Plate_FromOre_C``: 2 Ore -> 1 Plate directly (Constructor);
      the deliberately inefficient alternate for the ban/pin fixtures.
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
                    "Build_SmelterMk1_C",
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
                _recipe(
                    "Recipe_Plate_FromOre_C",
                    "Plate From Ore",
                    [("Desc_Ore_C", 2)],
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
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _keys(*names: str) -> frozenset[str]:
    return frozenset(normalize_class_name(name) for name in names)


# --- Ban: forces the inefficient recipe ---------------------------------------


def test_ban_forces_inefficient_recipe(tmp_path: Path) -> None:
    """Banning the efficient recipe leaves only the 2-ore-per-plate alternate.

    10 plates via ``Recipe_Plate_FromOre_C`` (2 ore/plate) costs 20 ore
    and 10 machine-equivalents; the banned ``Recipe_Plate_Efficient_C``
    (1 ore/plate) would have cost only 10 ore had it been allowed.
    """
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Plate_FromOre_C", "Recipe_Plate_Efficient_C")
    banned = _keys("Recipe_Plate_Efficient_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 10.0),), banned=banned)

    assert result.status == "optimal"
    assert len(result.runs) == 1
    assert normalize_class_name(result.runs[0].recipe_class) == normalize_class_name(
        "Recipe_Plate_FromOre_C"
    )
    assert result.runs[0].machines_exact == pytest.approx(10.0)
    assert len(result.imports) == 1
    assert result.imports[0].rate_per_min == pytest.approx(20.0)


# --- Ban: forces infeasibility, naming the item and the ban -------------------


def test_ban_to_infeasible_names_item_and_ban(tmp_path: Path) -> None:
    """Banning the only Ingot producer strands the Ingot demand specifically.

    An unrelated recipe (``Recipe_Plate_Efficient_C``) stays allowed so the
    candidate set isn't entirely empty; the infeasibility must trace back
    to the banned Ingot recipe, not the blanket "no candidates" case.
    """
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Ingot_C", "Recipe_Plate_Efficient_C")
    banned = _keys("Recipe_Ingot_C")

    result = solve_stage(catalog, allowed, (("Desc_Ingot_C", 5.0),), banned=banned)

    assert result.status == "infeasible"
    assert result.runs == ()
    assert result.imports == ()
    joined = " ".join(result.diagnostics)
    assert normalize_class_name("Desc_Ingot_C") in joined
    assert normalize_class_name("Recipe_Ingot_C") in joined
    assert "banned" in joined


# --- Pin: selects the pinned recipe over a cheaper competitor -----------------


def test_pin_selects_pinned_recipe_over_cheaper_competitor(tmp_path: Path) -> None:
    """Pinning the inefficient recipe bans its competitor via the primary-product rule.

    Both recipes share Plate as their (only, first-listed) product, so
    pinning ``Recipe_Plate_FromOre_C`` auto-bans ``Recipe_Plate_Efficient_C``
    even though the latter is strictly cheaper in raw ore.
    """
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Plate_FromOre_C", "Recipe_Plate_Efficient_C")
    pinned = _keys("Recipe_Plate_FromOre_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 10.0),), pinned=pinned)

    assert result.status == "optimal"
    assert len(result.runs) == 1
    assert normalize_class_name(result.runs[0].recipe_class) == normalize_class_name(
        "Recipe_Plate_FromOre_C"
    )
    assert result.imports[0].rate_per_min == pytest.approx(20.0)


# --- Pin: a recipe outside allowed_recipes is infeasible ----------------------


def test_pin_of_non_allowed_recipe_is_infeasible(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys("Recipe_Plate_Efficient_C")
    pinned = _keys("Recipe_Plate_FromOre_C")

    result = solve_stage(catalog, allowed, (("Desc_Plate_C", 10.0),), pinned=pinned)

    assert result.status == "infeasible"
    assert result.runs == ()
    assert result.imports == ()
    joined = " ".join(result.diagnostics)
    assert normalize_class_name("Recipe_Plate_FromOre_C") in joined
    assert "not in allowed_recipes" in joined


# --- Two-level: fewer machines wins among raw-equivalent solutions -----------


def test_two_level_prefers_fewer_machines_among_raw_equivalent_solutions(
    tmp_path: Path,
) -> None:
    """Chain and direct routes tie exactly on raw ore but differ in machine count.

    For 12 Plate demand: the chain (Ingot then Plate) needs 12 Ore -> 12
    Ingot -> 12 Plate, i.e. 12 ore and 12 + 12 = 24 total machine-
    equivalents. The direct Efficient recipe needs the same 12 ore but
    only 12 machine-equivalents (one recipe run per plate instead of
    two). Both are raw-equivalent (12 ore either way); the two-level
    objective must pick the 12-machine solution.
    """
    catalog = _catalog(tmp_path)
    demand = (("Desc_Plate_C", 12.0),)

    chain_only = _keys("Recipe_Ingot_C", "Recipe_Plate_C")
    chain_result = solve_stage(catalog, chain_only, demand)
    assert chain_result.status == "optimal"
    chain_raw_total = sum(imported.rate_per_min for imported in chain_result.imports)
    chain_machines_total = sum(run.machines_exact for run in chain_result.runs)
    assert chain_raw_total == pytest.approx(12.0)
    assert chain_machines_total == pytest.approx(24.0)

    both_routes = _keys("Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C")
    combined_result = solve_stage(catalog, both_routes, demand)
    assert combined_result.status == "optimal"
    combined_raw_total = sum(imported.rate_per_min for imported in combined_result.imports)
    combined_machines_total = sum(run.machines_exact for run in combined_result.runs)

    assert combined_raw_total == pytest.approx(chain_raw_total)
    assert combined_machines_total < chain_machines_total
    assert combined_machines_total == pytest.approx(12.0)
    assert len(combined_result.runs) == 1
    assert normalize_class_name(combined_result.runs[0].recipe_class) == normalize_class_name(
        "Recipe_Plate_Efficient_C"
    )


# --- Determinism with pins/bans applied ---------------------------------------


def test_determinism_double_run_matches_with_pins_and_bans(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    allowed = _keys(
        "Recipe_Ingot_C", "Recipe_Plate_C", "Recipe_Plate_Efficient_C", "Recipe_Plate_FromOre_C"
    )
    pinned = _keys("Recipe_Plate_FromOre_C")
    demand = (("Desc_Plate_C", 10.0),)

    first = solve_stage(catalog, allowed, demand, pinned=pinned)
    second = solve_stage(catalog, allowed, demand, pinned=pinned)

    assert first == second

"""Tests for the pure pace-scenario comparison module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satisfactory_docs import load_docs_catalog
from satisfactory_install import discover_docs
from satisfactory_progression import (
    PhaseDefinition,
    PhasePart,
    ProjectAssemblyData,
    load_project_assembly_phases,
)
from satisfactory_scenarios import ScenarioComparison, compare_pace_scenarios


# --- Fixture Docs catalog: one ore, one recipe, one building ----------------


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
    """One producible chain: Ore -> Ingot, 1:1, 60 seconds, power exponent 1.0
    so power scales linearly with clock and is hand-computable from the rate.
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
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                _recipe(
                    "Recipe_Ingot_C",
                    "Ingot",
                    [("Desc_Ore_C", 1)],
                    [("Desc_Ingot_C", 1)],
                    "Build_ConstructorMk1_C",
                ),
            ],
        },
        {
            "NativeClass": (
                "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableManufacturer'"
            ),
            "Classes": [
                {
                    "ClassName": "Build_ConstructorMk1_C",
                    "mManufacturingSpeed": "1.000000",
                    "mPowerConsumption": "4.000000",
                    "mPowerConsumptionExponent": "1.000000",
                },
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _phase_data(quantity: float = 180.0) -> ProjectAssemblyData:
    """A single-phase fixture: 180 Ingot over a 1-hour baseline window.

    At pace 1.0: 60 demand-minutes, rate 180/60 = 3.0/min, machines_exact 3.0
    (3 machines at clock 1.0). At pace 2.0: 120 demand-minutes, rate 1.5/min
    (2 machines at clock 0.75). At pace 3.0: 180 demand-minutes, rate 1.0/min
    (1 machine at clock 1.0). Ore is consumed 1:1 with Ingot, so the raw
    import rate always equals the Ingot rate.
    """
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=(
            PhaseDefinition(
                phase=1,
                name="Test Phase",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(item_class="Desc_Ingot_C", display_name="Ingot", quantity=quantity),
                ),
            ),
        ),
    )


# --- Validation ---------------------------------------------------------------


def test_empty_paces_raises_value_error(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    with pytest.raises(ValueError, match="1 to 4"):
        compare_pace_scenarios(catalog, data, (), phase=1)


def test_more_than_four_distinct_paces_raises_value_error(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    with pytest.raises(ValueError, match="1 to 4"):
        compare_pace_scenarios(catalog, data, (1.0, 1.5, 2.0, 2.5, 3.0), phase=1)


@pytest.mark.parametrize("pace", [0.5, 3.5, -1.0])
def test_out_of_range_pace_raises_value_error(tmp_path: Path, pace: float) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    with pytest.raises(ValueError, match=r"\[1\.0, 3\.0\]"):
        compare_pace_scenarios(catalog, data, (pace,), phase=1)


def test_duplicate_paces_are_deduplicated_preserving_order(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    comparison = compare_pace_scenarios(catalog, data, (2.0, 1.0, 2.0), phase=1)

    assert [row.pace for row in comparison.rows] == [2.0, 1.0]


def test_unknown_phase_raises_value_error(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    with pytest.raises(ValueError, match="Unknown phase"):
        compare_pace_scenarios(catalog, data, (1.0,), phase=99)


# --- Stage rows: hand-computed exact values -----------------------------------


def test_stage_rows_exact_at_paces_1_2_3(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data(quantity=180.0)

    comparison = compare_pace_scenarios(catalog, data, (1.0, 2.0, 3.0), phase=1)

    assert isinstance(comparison, ScenarioComparison)
    assert [row.pace for row in comparison.rows] == [1.0, 2.0, 3.0]
    assert all(row.status == "optimal" for row in comparison.rows)
    assert all(row.node_count == 1 for row in comparison.rows)

    pace1, pace2, pace3 = comparison.rows

    # Machine counts drop as pace grows: 3 -> 2 -> 1 (hand-computed above).
    assert pace1.machine_count == 3
    assert pace2.machine_count == 2
    assert pace3.machine_count == 1

    # Raw (Ore) import rate mirrors the Ingot rate: 3.0 -> 1.5 -> 1.0/min.
    assert pace1.raw_imports == (("Desc_Ore_C", 3.0),)
    assert pace2.raw_imports == (("Desc_Ore_C", 1.5),)
    assert pace3.raw_imports == (("Desc_Ore_C", 1.0),)
    # Pace 2.0 halves pace 1.0's rate; pace 3.0 is one third of pace 1.0's.
    assert pace2.raw_imports[0][1] == pytest.approx(pace1.raw_imports[0][1] / 2.0)
    assert pace3.raw_imports[0][1] == pytest.approx(pace1.raw_imports[0][1] / 3.0)

    # Power exponent 1.0: power = machine_count * 4.0 MW * clock == rate * 4.0 MW.
    assert pace1.power_mw == pytest.approx(12.0)
    assert pace2.power_mw == pytest.approx(6.0)
    assert pace3.power_mw == pytest.approx(4.0)

    assert pace1.window_text == "1.000h"
    assert pace2.window_text == "2.000h"
    assert pace3.window_text == "3.000h"


def test_stage_row_infeasible_solve_reports_status_and_diagnostic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    comparison = compare_pace_scenarios(
        catalog, data, (1.0,), phase=1, banned=("Recipe_Ingot_C",)
    )

    row = comparison.rows[0]
    assert row.status != "optimal"
    assert row.machine_count == 0
    assert row.raw_imports == ()
    assert any("pace 1.0" in diag for diag in comparison.diagnostics)


# --- Determinism ---------------------------------------------------------------


def test_compare_pace_scenarios_is_deterministic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _phase_data()

    first = compare_pace_scenarios(catalog, data, (1.0, 2.0, 3.0), phase=1)
    second = compare_pace_scenarios(catalog, data, (1.0, 2.0, 3.0), phase=1)

    assert first == second


# --- Master rows: two-phase fixture, coherence checks -------------------------


def _two_phase_data() -> ProjectAssemblyData:
    """A minimal two-phase fixture sharing the single Ingot recipe."""
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=(
            PhaseDefinition(
                phase=1,
                name="Phase One",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(item_class="Desc_Ingot_C", display_name="Ingot", quantity=60.0),
                ),
            ),
            PhaseDefinition(
                phase=2,
                name="Phase Two",
                window_hours_baseline=2.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(item_class="Desc_Ingot_C", display_name="Ingot", quantity=240.0),
                ),
            ),
        ),
    )


def test_master_rows_are_coherent_across_paces(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    comparison = compare_pace_scenarios(catalog, data, (1.0, 2.0), phase=None)

    assert [row.pace for row in comparison.rows] == [1.0, 2.0]
    for row in comparison.rows:
        assert row.status == "complete"
        assert row.node_count == 2  # one node per phase, same recipe both phases
        assert row.machine_count > 0
        assert row.power_mw > 0.0
        assert "phase(s)" in row.window_text
        assert row.raw_imports == (("Desc_Ore_C", pytest.approx(row.power_mw / 4.0)),)

    # Higher pace widens every phase's window, so both phases need fewer
    # machines and less power at pace 2.0 than at pace 1.0.
    pace1, pace2 = comparison.rows
    assert pace2.machine_count <= pace1.machine_count
    assert pace2.power_mw <= pace1.power_mw


def test_master_rows_are_deterministic(tmp_path: Path) -> None:
    catalog = _catalog(tmp_path)
    data = _two_phase_data()

    first = compare_pace_scenarios(catalog, data, (1.0, 2.0), phase=None)
    second = compare_pace_scenarios(catalog, data, (1.0, 2.0), phase=None)

    assert first == second


# --- Real-install integration ---------------------------------------------------


def test_real_install_phase_1_monotonic_and_one_third_rate() -> None:
    """Gated real-install check: phase 1 at paces 1.0/2.0/3.0.

    Machine totals and power must never increase as pace grows (a wider
    window needs the same total quantity at a lower rate), and the raw
    import rate at pace 3.0 must be one third of pace 1.0's (the window
    scales linearly with pace, so rate scales inversely).
    """
    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog = load_docs_catalog(discovery.docs_path)
    data = load_project_assembly_phases()

    comparison = compare_pace_scenarios(catalog, data, (1.0, 2.0, 3.0), phase=1)

    pace1, pace2, pace3 = comparison.rows
    assert pace1.status == "optimal"
    assert pace2.status == "optimal"
    assert pace3.status == "optimal"

    assert pace2.machine_count <= pace1.machine_count
    assert pace3.machine_count <= pace2.machine_count
    assert pace2.power_mw <= pace1.power_mw
    assert pace3.power_mw <= pace2.power_mw

    raw1 = dict(pace1.raw_imports)
    raw3 = dict(pace3.raw_imports)
    assert raw1, "phase 1 at pace 1.0 should have at least one raw import"
    for item_class, rate1 in raw1.items():
        rate3 = raw3.get(item_class, 0.0)
        assert rate3 == pytest.approx(rate1 / 3.0, rel=1e-6)

"""Tests for the actuals-versus-plan audit (satisfactory_actuals)."""

from __future__ import annotations

from satisfactory_actuals import ActualsRow, compare_actuals


def _node(recipe_class: str, machine_count_exact: float) -> dict:
    return {"recipe_class": recipe_class, "machine_count_exact": machine_count_exact}


def _stage_payload(nodes: list[dict], phase: int = 2, revision: int = 3) -> dict:
    return {"phase": phase, "revision": revision, "nodes": nodes}


def _machine(recipe: str | None, clock: object) -> dict:
    return {"recipe": recipe, "clock": clock, "confidence": "high"}


# --- Fixture: one of each classification, plus a tied-shortfall pair --------


def _fixture_stage_payload() -> dict:
    return _stage_payload(
        [
            _node("Recipe_IronPlate_C", 2.0),
            _node("Recipe_Screw_C", 3.0),
            _node("Recipe_Rotor_C", 1.0),
            _node("Recipe_ModularFrame_C", 2.0),
        ]
    )


def _fixture_mirror_machines() -> list[dict]:
    return [
        _machine("Recipe_IronPlate_C", 1.0),
        _machine("Recipe_IronPlate_C", 1.0),
        _machine("Recipe_Screw_C", 1.0),
        _machine("Recipe_Rotor_C", 1.0),
        _machine("Recipe_Rotor_C", 1.0),
        _machine("Recipe_Plate_C", 1.5),
        _machine("Recipe_Plate_C", None),  # unknown clock -> assumed 1.0
        _machine(None, 1.0),  # extractor/no-recipe machine: excluded entirely
    ]


def test_classification_and_capacity_math() -> None:
    comparison = compare_actuals(
        _fixture_mirror_machines(), _fixture_stage_payload(), save_name="Test Save"
    )

    by_key = {row.recipe_key: row for row in comparison.rows}
    assert by_key["recipe_ironplate"].classification == "matched"
    assert by_key["recipe_ironplate"].planned_capacity == 2.0
    assert by_key["recipe_ironplate"].actual_capacity == 2.0
    assert by_key["recipe_ironplate"].delta == 0.0

    assert by_key["recipe_screw"].classification == "missing"
    assert by_key["recipe_screw"].planned_capacity == 3.0
    assert by_key["recipe_screw"].actual_capacity == 1.0
    assert by_key["recipe_screw"].delta == -2.0

    assert by_key["recipe_rotor"].classification == "surplus"
    assert by_key["recipe_rotor"].planned_capacity == 1.0
    assert by_key["recipe_rotor"].actual_capacity == 2.0
    assert by_key["recipe_rotor"].delta == 1.0

    assert by_key["recipe_modularframe"].classification == "missing"
    assert by_key["recipe_modularframe"].planned_capacity == 2.0
    assert by_key["recipe_modularframe"].actual_capacity == 0.0

    assert by_key["recipe_plate"].classification == "unplanned"
    assert by_key["recipe_plate"].planned_capacity == 0.0
    assert by_key["recipe_plate"].actual_capacity == 2.5  # 1.5 known + 1.0 unknown-defaulted

    assert comparison.planned_total == 8.0
    assert comparison.actual_total == 7.5
    assert comparison.save_name == "Test Save"
    assert comparison.plan_phase == 2
    assert comparison.plan_revision == 3


def test_unknown_clock_counts_as_one_and_notes_it() -> None:
    comparison = compare_actuals(_fixture_mirror_machines(), _fixture_stage_payload())

    assert len(comparison.diagnostics) == 1
    assert "1 machine(s)" in comparison.diagnostics[0]
    assert "assumed 1.0" in comparison.diagnostics[0]


def test_machines_without_a_recipe_are_excluded() -> None:
    """An extractor (no ``recipe``) never contributes actual capacity to any key."""
    comparison = compare_actuals(
        [_machine(None, 1.0), _machine("", 1.0)], _stage_payload([])
    )

    assert comparison.rows == ()
    assert comparison.actual_total == 0.0


# --- Sorting and determinism --------------------------------------------------


def test_sort_order_missing_then_unplanned_surplus_matched() -> None:
    comparison = compare_actuals(_fixture_mirror_machines(), _fixture_stage_payload())

    classifications = [row.classification for row in comparison.rows]
    assert classifications == ["missing", "missing", "unplanned", "surplus", "matched"]


def test_missing_rows_sorted_by_largest_shortfall_first_tie_broken_alphabetically() -> None:
    """Screw and ModularFrame both have a shortfall of 2.0: alphabetical tiebreak applies."""
    comparison = compare_actuals(_fixture_mirror_machines(), _fixture_stage_payload())

    missing_keys = [row.recipe_key for row in comparison.rows if row.classification == "missing"]
    assert missing_keys == ["recipe_modularframe", "recipe_screw"]


def test_missing_rows_sorted_by_largest_shortfall_when_distinct() -> None:
    stage_payload = _stage_payload(
        [_node("Recipe_A_C", 5.0), _node("Recipe_B_C", 1.0)]
    )
    mirror_machines = [_machine("Recipe_A_C", 1.0), _machine("Recipe_B_C", 0.5)]

    comparison = compare_actuals(mirror_machines, stage_payload)

    missing_keys = [row.recipe_key for row in comparison.rows if row.classification == "missing"]
    # Recipe_A shortfall = 4.0, Recipe_B shortfall = 0.5: A's larger shortfall sorts first.
    assert missing_keys == ["recipe_a", "recipe_b"]


def test_determinism_regardless_of_input_order() -> None:
    stage_payload = _fixture_stage_payload()
    machines = _fixture_mirror_machines()

    first = compare_actuals(machines, stage_payload)
    second = compare_actuals(list(reversed(machines)), stage_payload)

    assert first.rows == second.rows
    assert first.planned_total == second.planned_total
    assert first.actual_total == second.actual_total


# --- Recipe key normalization: full class paths and casing collapse --------


def test_recipe_key_normalization_matches_full_class_paths() -> None:
    stage_payload = _stage_payload([_node("Recipe_IronPlate_C", 1.0)])
    mirror_machines = [
        _machine(
            "/Game/FactoryGame/Recipes/Parts/Recipe_IronPlate.Recipe_IronPlate_C", 1.0
        )
    ]

    comparison = compare_actuals(mirror_machines, stage_payload)

    assert len(comparison.rows) == 1
    assert comparison.rows[0].classification == "matched"
    assert comparison.rows[0].recipe_key == "recipe_ironplate"


# --- Empty-mirror and empty-plan edges ---------------------------------------


def test_empty_mirror_classifies_every_planned_node_missing_with_zero_actual() -> None:
    stage_payload = _fixture_stage_payload()

    comparison = compare_actuals([], stage_payload)

    assert len(comparison.rows) == 4
    assert all(row.classification == "missing" for row in comparison.rows)
    assert all(row.actual_capacity == 0.0 for row in comparison.rows)
    assert comparison.actual_total == 0.0
    assert comparison.planned_total == 8.0
    assert comparison.diagnostics == ()


def test_empty_plan_classifies_every_actual_machine_unplanned() -> None:
    mirror_machines = [_machine("Recipe_IronPlate_C", 1.0), _machine("Recipe_Screw_C", 2.0)]

    comparison = compare_actuals(mirror_machines, _stage_payload([]))

    assert len(comparison.rows) == 2
    assert all(row.classification == "unplanned" for row in comparison.rows)
    assert comparison.planned_total == 0.0
    assert comparison.actual_total == 3.0


def test_both_empty_yields_no_rows() -> None:
    comparison = compare_actuals([], _stage_payload([]))

    assert comparison.rows == ()
    assert comparison.planned_total == 0.0
    assert comparison.actual_total == 0.0
    assert comparison.diagnostics == ()


def test_missing_nodes_key_treated_as_no_planned_nodes() -> None:
    """A stage payload with no ``nodes`` key at all degrades to an empty plan."""
    comparison = compare_actuals(
        [_machine("Recipe_IronPlate_C", 1.0)], {"phase": 1, "revision": 1}
    )

    assert len(comparison.rows) == 1
    assert comparison.rows[0].classification == "unplanned"


# --- Frozen dataclass sanity --------------------------------------------------


def test_actuals_row_is_frozen() -> None:
    row = ActualsRow(
        recipe_key="recipe_x",
        planned_capacity=1.0,
        actual_capacity=1.0,
        delta=0.0,
        classification="matched",
    )
    try:
        row.classification = "missing"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("ActualsRow must be frozen")

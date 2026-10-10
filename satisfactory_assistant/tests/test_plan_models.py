"""Tests for the typed plan models (satisfactory_plan_models)."""

from __future__ import annotations

import pytest

from satisfactory_plan_models import (
    DataProvenance,
    Diagnostic,
    FactoryMasterPlan,
    ItemFlow,
    PacePolicy,
    PowerPlan,
    ProcessNode,
    RecipePolicy,
    ResourceSource,
    StagePlan,
    StageTransition,
    data_provenance_from_payload,
    diagnostic_from_payload,
    factory_master_plan_from_payload,
    item_flow_from_payload,
    pace_policy_from_payload,
    power_plan_from_payload,
    process_node_from_payload,
    recipe_policy_from_payload,
    resource_source_from_payload,
    stage_plan_from_payload,
    stage_transition_from_payload,
)


# --- Round trip: simple models ---


def test_diagnostic_round_trip() -> None:
    original = Diagnostic(
        severity="warning", code="low_power", message="Power margin thin", subject="Phase 2"
    )
    assert diagnostic_from_payload(original.to_payload()) == original


def test_data_provenance_round_trip() -> None:
    original = DataProvenance(
        source="Docs.json", retrieved="2026-07-01T00:00:00", note="bundled catalog"
    )
    assert data_provenance_from_payload(original.to_payload()) == original


def test_pace_policy_round_trip() -> None:
    original = PacePolicy(multiplier=1.5, window_hours=12.0)
    assert pace_policy_from_payload(original.to_payload()) == original


def test_recipe_policy_round_trip() -> None:
    original = RecipePolicy(
        mode="extended",
        pinned=("Recipe_IronPlate_C",),
        banned=("Recipe_Alternate_PureIronIngot_C",),
        allowed_alternates=("Recipe_Alternate_SteelCastedPlate_C",),
    )
    assert recipe_policy_from_payload(original.to_payload()) == original


def test_process_node_round_trip() -> None:
    original = ProcessNode(
        node_id="node_1",
        recipe_class="Recipe_IronPlate_C",
        building_class="Build_ConstructorMk1_C",
        runs_per_min=30.0,
        machine_count_exact=2.5,
        machine_count=3,
        clock=100.0,
        power_mw=12.0,
    )
    assert process_node_from_payload(original.to_payload()) == original


def test_resource_source_round_trip() -> None:
    original = ResourceSource(
        node_id="source_1",
        item_class="Desc_OreIron_C",
        rate_per_min=480.0,
        extractor_class="Build_MinerMk2_C",
        extractor_count=2,
    )
    assert resource_source_from_payload(original.to_payload()) == original


def test_item_flow_round_trip() -> None:
    original = ItemFlow(
        item_class="Desc_IronPlate_C",
        rate_per_min=60.0,
        source_id="node_1",
        dest_id="external_demand",
    )
    assert item_flow_from_payload(original.to_payload()) == original


def test_power_plan_round_trip() -> None:
    original = PowerPlan(
        total_mw=45.5,
        by_building=(("Build_ConstructorMk1_C", 20.0), ("Build_SmelterMk1_C", 25.5)),
    )
    assert power_plan_from_payload(original.to_payload()) == original


def test_stage_transition_round_trip() -> None:
    original = StageTransition(
        from_phase=1,
        to_phase=2,
        reused_nodes=("node_1",),
        expanded_nodes=("node_2",),
        added_nodes=("node_3",),
        retired_nodes=(),
    )
    assert stage_transition_from_payload(original.to_payload()) == original


def test_factory_master_plan_round_trip() -> None:
    original = FactoryMasterPlan(
        plan_id="plan_1",
        name="Phase 2 assembly",
        created_at="2026-07-01T00:00:00",
        updated_at="2026-07-01T00:00:00",
    )
    assert factory_master_plan_from_payload(original.to_payload()) == original


# --- Round trip: composite model ---


def _sample_stage_plan(solver_run_id: str | None = "run_1") -> StagePlan:
    return StagePlan(
        phase=2,
        window_hours=12.0,
        pace_multiplier=1.5,
        demands=(("Desc_IronPlate_C", 100.0, 8.33),),
        nodes=(
            ProcessNode(
                node_id="node_1",
                recipe_class="Recipe_IronPlate_C",
                building_class="Build_ConstructorMk1_C",
                runs_per_min=30.0,
                machine_count_exact=2.5,
                machine_count=3,
                clock=100.0,
                power_mw=12.0,
            ),
        ),
        sources=(
            ResourceSource(
                node_id="source_1",
                item_class="Desc_OreIron_C",
                rate_per_min=480.0,
                extractor_class="Build_MinerMk2_C",
                extractor_count=2,
            ),
        ),
        flows=(
            ItemFlow(
                item_class="Desc_IronPlate_C",
                rate_per_min=60.0,
                source_id="node_1",
                dest_id="external_demand",
            ),
        ),
        power=PowerPlan(total_mw=12.0, by_building=(("Build_ConstructorMk1_C", 12.0),)),
        recipe_policy=RecipePolicy(
            mode="standard", pinned=(), banned=(), allowed_alternates=()
        ),
        diagnostics=(
            Diagnostic(
                severity="info", code="ok", message="Solved cleanly", subject="Phase 2"
            ),
        ),
        assumptions=("Base tiers only",),
        provenance=DataProvenance(
            source="Docs.json", retrieved="2026-07-01T00:00:00", note=""
        ),
        solver_run_id=solver_run_id,
        revision=1,
        created_at="2026-07-01T00:00:00",
    )


def test_stage_plan_round_trip() -> None:
    original = _sample_stage_plan()
    assert stage_plan_from_payload(original.to_payload()) == original


def test_stage_plan_round_trip_with_none_solver_run_id() -> None:
    original = _sample_stage_plan(solver_run_id=None)
    payload = original.to_payload()
    assert payload["solver_run_id"] is None
    assert stage_plan_from_payload(payload) == original


def test_stage_plan_to_payload_uses_lists_not_tuples() -> None:
    payload = _sample_stage_plan().to_payload()
    assert isinstance(payload["demands"], list)
    assert isinstance(payload["nodes"], list)
    assert isinstance(payload["assumptions"], list)
    assert isinstance(payload["power"]["by_building"], list)


# --- Unknown keys ignored ---


def test_diagnostic_from_payload_ignores_unknown_keys() -> None:
    payload = {
        "severity": "error",
        "code": "no_power",
        "message": "Insufficient power",
        "subject": "Phase 3",
        "future_field": "should be ignored",
    }
    result = diagnostic_from_payload(payload)
    assert result == Diagnostic(
        severity="error", code="no_power", message="Insufficient power", subject="Phase 3"
    )


def test_recipe_policy_from_payload_ignores_unknown_keys() -> None:
    payload = {
        "mode": "standard",
        "pinned": [],
        "banned": [],
        "allowed_alternates": [],
        "extra_metadata": {"nested": True},
    }
    result = recipe_policy_from_payload(payload)
    assert result == RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=())


def test_stage_plan_from_payload_ignores_unknown_keys() -> None:
    payload = _sample_stage_plan().to_payload()
    payload["unexpected_top_level_key"] = "ignore me"
    payload["power"]["unexpected_nested_key"] = "ignore me too"
    result = stage_plan_from_payload(payload)
    assert result == _sample_stage_plan()


# --- Tuple coercion on read ---


def test_recipe_policy_from_payload_coerces_lists_to_tuples() -> None:
    payload = {
        "mode": "extended",
        "pinned": ["Recipe_A_C", "Recipe_B_C"],
        "banned": ["Recipe_C_C"],
        "allowed_alternates": ["Recipe_D_C"],
    }
    result = recipe_policy_from_payload(payload)
    assert result.pinned == ("Recipe_A_C", "Recipe_B_C")
    assert isinstance(result.pinned, tuple)
    assert isinstance(result.banned, tuple)
    assert isinstance(result.allowed_alternates, tuple)


def test_stage_plan_from_payload_coerces_lists_to_tuples() -> None:
    payload = _sample_stage_plan().to_payload()
    result = stage_plan_from_payload(payload)
    assert isinstance(result.demands, tuple)
    assert isinstance(result.demands[0], tuple)
    assert isinstance(result.nodes, tuple)
    assert isinstance(result.sources, tuple)
    assert isinstance(result.flows, tuple)
    assert isinstance(result.diagnostics, tuple)
    assert isinstance(result.assumptions, tuple)
    assert isinstance(result.power.by_building, tuple)
    assert isinstance(result.power.by_building[0], tuple)


def test_power_plan_from_payload_coerces_by_building_to_tuple_of_tuples() -> None:
    payload = {"total_mw": 10.0, "by_building": [["Build_A_C", 5.0], ["Build_B_C", 5.0]]}
    result = power_plan_from_payload(payload)
    assert result.by_building == (("Build_A_C", 5.0), ("Build_B_C", 5.0))


def test_stage_transition_from_payload_coerces_lists_to_tuples() -> None:
    payload = {
        "from_phase": 1,
        "to_phase": 2,
        "reused_nodes": ["node_1", "node_2"],
        "expanded_nodes": [],
        "added_nodes": [],
        "retired_nodes": [],
    }
    result = stage_transition_from_payload(payload)
    assert isinstance(result.reused_nodes, tuple)
    assert result.reused_nodes == ("node_1", "node_2")


# --- Invalid enum values raise ValueError at construction ---


def test_diagnostic_invalid_severity_raises() -> None:
    with pytest.raises(ValueError):
        Diagnostic(severity="critical", code="x", message="x", subject="x")


def test_diagnostic_valid_severities_accepted() -> None:
    for severity in ("info", "warning", "error"):
        Diagnostic(severity=severity, code="x", message="x", subject="x")


def test_recipe_policy_invalid_mode_raises() -> None:
    with pytest.raises(ValueError):
        RecipePolicy(mode="hardcore", pinned=(), banned=(), allowed_alternates=())


def test_recipe_policy_valid_modes_accepted() -> None:
    for mode in ("standard", "extended"):
        RecipePolicy(mode=mode, pinned=(), banned=(), allowed_alternates=())


def test_diagnostic_from_payload_invalid_severity_raises() -> None:
    with pytest.raises(ValueError):
        diagnostic_from_payload(
            {"severity": "critical", "code": "x", "message": "x", "subject": "x"}
        )


def test_recipe_policy_from_payload_invalid_mode_raises() -> None:
    with pytest.raises(ValueError):
        recipe_policy_from_payload(
            {"mode": "hardcore", "pinned": [], "banned": [], "allowed_alternates": []}
        )

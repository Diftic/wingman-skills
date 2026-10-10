"""Tests for the calculate_satisfactory_plan tool (plan and audit modes).

main.py imports the Wingman app (api.*, skills.skill_base), so the repo root
must be importable. The test skips gracefully if those modules are unavailable.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

main = pytest.importorskip("skills.satisfactory_assistant.main")

from satisfactory_dataset import DatasetInfo  # noqa: E402
from satisfactory_docs import load_docs_catalog  # noqa: E402
from satisfactory_install import DocsDiscovery  # noqa: E402
from satisfactory_models import ActiveSaveResult  # noqa: E402
from satisfactory_progression import (  # noqa: E402
    PhaseDefinition,
    PhasePart,
    ProjectAssemblyData,
)
from satisfactory_store import SaveStore  # noqa: E402
from satisfactory_workspace import SaveWorkspace  # noqa: E402


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
    """One producible chain: Ore -> Plate. Every recipe runs 60 seconds."""
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
                {"ClassName": "Desc_Plate_C", "mDisplayName": "Plate", "mForm": "RF_SOLID"},
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                _recipe(
                    "Recipe_Plate_C",
                    "Plate",
                    [("Desc_Ore_C", 1)],
                    [("Desc_Plate_C", 1)],
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
                    "mPowerConsumptionExponent": "1.300000",
                },
            ],
        },
    ]


def _catalog(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data()), encoding="utf-16")
    return load_docs_catalog(path)


def _fake_dataset_info(path: Path) -> DatasetInfo:
    return DatasetInfo(
        docs_path=str(path),
        size_bytes=1,
        mtime_ns=1,
        sha256="deadbeef",
        parse_ms=1.23,
        loaded_at="2026-07-02T00:00:00",
        item_count=1,
        recipe_count=1,
        building_count=1,
        schematic_count=0,
    )


def _phase_data(phase: int = 1) -> ProjectAssemblyData:
    """A single-phase fixture whose one part matches ``_docs_data``'s Plate."""
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=(
            PhaseDefinition(
                phase=phase,
                name="Test Phase",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(
                        item_class="Desc_Plate_C", display_name="Plate", quantity=60.0
                    ),
                ),
            ),
        ),
    )


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, phase: int = 1
) -> None:
    """Monkeypatch the module-level docs/phase-data functions ``main`` calls."""
    docs_path = tmp_path / "en-US.json"
    catalog = _catalog(tmp_path)

    def fake_discover_docs(**kwargs: object) -> DocsDiscovery:
        return DocsDiscovery(
            docs_path=docs_path, locale="en-US", source="configured_file", searched=()
        )

    def fake_get_docs_catalog(path: Path):
        return catalog, _fake_dataset_info(path)

    monkeypatch.setattr(main, "discover_docs", fake_discover_docs)
    monkeypatch.setattr(main, "get_docs_catalog", fake_get_docs_catalog)
    monkeypatch.setattr(main, "load_project_assembly_phases", lambda: _phase_data(phase))


class _PlanToolStub:
    """Minimal stand-in exposing what ``calculate_satisfactory_plan`` reads."""

    def __init__(
        self,
        base: Path,
        save_name: str = "Test Save",
        save_file: Path | None = None,
    ) -> None:
        self.workspace = SaveWorkspace(base, "test-save")
        self._save_name = save_name
        self._save_file = save_file
        self.diagnostics: list[str] = []
        self.audit_calls: list[tuple[ActiveSaveResult, SaveWorkspace, int]] = []

    def _resolve(self) -> ActiveSaveResult:
        return ActiveSaveResult(
            status="ok", save_name=self._save_name, save_file=self._save_file
        )

    def _status_message(self, result: ActiveSaveResult) -> str | None:
        return None

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        return self.workspace

    def _diag(self, message: str) -> None:
        self.diagnostics.append(message)

    def _docs_file(self) -> str:
        return ""

    def _install_dir(self) -> str:
        return ""

    def _docs_locale(self) -> str:
        return "en-US"

    def _run_factory_audit(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        self.audit_calls.append((result, ws, phase))
        return "AUDIT RESULT"


class _NoSaveStub(_PlanToolStub):
    """Stub simulating no active save resolved."""

    def _status_message(self, result: ActiveSaveResult) -> str | None:
        return "No Satisfactory log folder found."


def _run_plan(stub: _PlanToolStub, **kwargs: object) -> str:
    return asyncio.run(main.SatisfactoryAssistant.calculate_satisfactory_plan(stub, **kwargs))


def _open_store(stub: _PlanToolStub) -> SaveStore:
    return SaveStore.open(stub.workspace.dir / "planning.sqlite3")


# --- Validation failures: fatal message, nothing persisted -------------------


@pytest.mark.parametrize("pace", [0.5, 3.5])
def test_bad_pace_returns_value_error_and_persists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pace: float
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=pace)

    assert "pace_multiplier" in result
    assert "out of range" in result
    store = _open_store(stub)
    try:
        assert store.get_master_plan("master") is None
    finally:
        store.close()


@pytest.mark.parametrize("phase", [0, 6])
def test_bad_phase_returns_value_error_and_persists_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, phase: int
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)  # fixture only defines phase 1

    result = _run_plan(stub, phase=phase, pace_multiplier=1.0)

    assert "Unknown phase" in result
    store = _open_store(stub)
    try:
        assert store.get_master_plan("master") is None
    finally:
        store.close()


# --- Active-save / docs resolution refusals ----------------------------------


def test_no_active_save_returns_standard_refusal(tmp_path: Path) -> None:
    stub = _NoSaveStub(tmp_path)

    result = _run_plan(stub, phase=1)

    assert result == "No Satisfactory log folder found."
    assert not (stub.workspace.dir / "planning.sqlite3").exists()


def test_docs_missing_returns_hint_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)

    def fake_discover_docs(**kwargs: object) -> DocsDiscovery:
        return DocsDiscovery(
            docs_path=None,
            locale="en-US",
            source="configured_file",
            searched=("place a", "place b"),
        )

    monkeypatch.setattr(main, "discover_docs", fake_discover_docs)

    result = _run_plan(stub, phase=1)

    assert "Docs file not found" in result
    assert "place a; place b" in result


def test_docs_invalid_returns_tool_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    docs_path = tmp_path / "bad-docs.json"
    docs_path.write_text("{}", encoding="utf-8")

    def fake_discover_docs(**kwargs: object) -> DocsDiscovery:
        return DocsDiscovery(
            docs_path=docs_path, locale="en-US", source="configured_file", searched=()
        )

    def fake_get_docs_catalog(path: Path):
        raise ValueError("Unexpected docs JSON root")

    monkeypatch.setattr(main, "discover_docs", fake_discover_docs)
    monkeypatch.setattr(main, "get_docs_catalog", fake_get_docs_catalog)

    result = _run_plan(stub, phase=1)

    assert "Could not load the Satisfactory Docs file" in result
    assert "Unexpected docs JSON root" in result
    assert stub.diagnostics


# --- Happy path: response shape, persistence, artifacts ----------------------


def test_happy_path_plan_response_and_persistence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True)

    assert "Phase 1 plan" in result
    assert "Demands:" in result
    assert "Plate" in result  # display name, per SSP-P3-W05 ruling
    assert "Production" in result
    assert "Power total:" in result
    assert len(result) <= 3200

    store = _open_store(stub)
    try:
        plan = store.get_master_plan("master")
        assert plan is not None
        assert plan["name"] == "Test Save"
        stage_payload = store.load_stage_plan("master", 1)
        assert stage_payload is not None
        assert stage_payload["revision"] == 1
        solver_run_id = stage_payload["solver_run_id"]
        assert isinstance(solver_run_id, str)
        assert solver_run_id.startswith("run_1_1_")
        assert store.get_solver_run(solver_run_id) is not None
    finally:
        store.close()

    plans_dir = stub.workspace.dir / "plans"
    artifact_files = list(plans_dir.rglob("*.md")) + list(plans_dir.rglob("*.json"))
    assert artifact_files
    for path in artifact_files:
        assert stub.workspace.dir in path.parents


def test_persist_false_leaves_store_and_artifacts_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=False)

    assert "not persisted" in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()
    assert not (stub.workspace.dir / "plans").exists()


def test_second_identical_call_persists_revision_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    first = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True)
    second = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True)

    assert "revision 1" in first
    assert "revision 2" in second
    store = _open_store(stub)
    try:
        assert store.list_stage_revisions("master", 1) == [1, 2]
    finally:
        store.close()


# --- mode="audit" dispatch ----------------------------------------------------


def test_audit_mode_dispatches_to_helper(tmp_path: Path) -> None:
    """The no-phase call (phase omitted, defaulting to 0) still dispatches
    to the helper, now carrying phase=0 (classic audit) alongside it."""
    stub = _PlanToolStub(tmp_path, save_file=tmp_path / "Save.sav")

    result = _run_plan(stub, mode="audit")

    assert result == "AUDIT RESULT"
    assert len(stub.audit_calls) == 1
    called_result, called_ws, called_phase = stub.audit_calls[0]
    assert called_result.save_name == "Test Save"
    assert called_ws is stub.workspace
    assert called_phase == 0


# --- SSP-P8-W02: mode="audit" forwards phase to the helper (append-only) ----


def test_audit_mode_forwards_phase_to_helper(tmp_path: Path) -> None:
    stub = _PlanToolStub(tmp_path, save_file=tmp_path / "Save.sav")

    result = _run_plan(stub, mode="audit", phase=2)

    assert result == "AUDIT RESULT"
    assert len(stub.audit_calls) == 1
    _called_result, _called_ws, called_phase = stub.audit_calls[0]
    assert called_phase == 2


def test_audit_mode_without_save_file_refuses(tmp_path: Path) -> None:
    stub = _PlanToolStub(tmp_path, save_file=None)

    result = _run_plan(stub, phase=1, mode="audit")

    assert "physical .sav file is not" in result
    assert not stub.audit_calls


# --- Tool surface: exactly three @tool methods -------------------------------


def test_exactly_three_tool_methods() -> None:
    tool_methods = [
        name
        for name, value in vars(main.SatisfactoryAssistant).items()
        if callable(value) and hasattr(value, "_tool_definition")
    ]
    assert set(tool_methods) == {
        "get_satisfactory_context",
        "update_satisfactory_plan",
        "calculate_satisfactory_plan",
    }
    assert len(tool_methods) == 3


# --- Display names: format_plan_response substitutes mapped names ------------


def _display_name_fixture_stage():
    """A one-demand, one-import stage plan for exercising display_names."""
    from satisfactory_plan_models import (
        DataProvenance,
        PowerPlan,
        ProcessNode,
        RecipePolicy,
        ResourceSource,
        StagePlan,
    )

    return StagePlan(
        phase=1,
        window_hours=1.0,
        pace_multiplier=1.0,
        demands=(("Desc_IronPlate_C", 60.0, 1.0),),
        nodes=(
            ProcessNode(
                node_id="node_1",
                recipe_class="Recipe_IronPlate_C",
                building_class="Build_ConstructorMk1_C",
                runs_per_min=1.0,
                machine_count_exact=2.0,
                machine_count=2,
                clock=100.0,
                power_mw=8.0,
            ),
        ),
        sources=(
            ResourceSource(
                node_id="source_1",
                item_class="Desc_OreIron_C",
                rate_per_min=30.0,
                extractor_class="Build_MinerMk2_C",
                extractor_count=1,
            ),
        ),
        flows=(),
        power=PowerPlan(total_mw=8.0, by_building=(("Build_ConstructorMk1_C", 8.0),)),
        recipe_policy=RecipePolicy(
            mode="standard", pinned=(), banned=(), allowed_alternates=()
        ),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="2026-07-02T00:00:00", note=""),
        solver_run_id=None,
        revision=1,
        created_at="2026-07-02T00:00:00",
    )


def test_format_plan_response_uses_display_names_when_present() -> None:
    from satisfactory_docs import normalize_class_name
    from satisfactory_reports import format_plan_response

    stage = _display_name_fixture_stage()

    without_names = format_plan_response(stage, artifact_paths=None)
    assert "Desc_IronPlate_C" in without_names
    assert "Desc_OreIron_C" in without_names

    display_names = {
        normalize_class_name("Desc_IronPlate_C"): "Iron Plate",
        normalize_class_name("Desc_OreIron_C"): "Iron Ore",
    }
    with_names = format_plan_response(stage, artifact_paths=None, display_names=display_names)
    assert "Iron Plate" in with_names
    assert "Iron Ore" in with_names
    assert "Desc_IronPlate_C" not in with_names
    assert "Desc_OreIron_C" not in with_names


def test_format_plan_response_falls_back_to_class_name_when_unmapped() -> None:
    from satisfactory_reports import format_plan_response

    stage = _display_name_fixture_stage()

    result = format_plan_response(
        stage, artifact_paths=None, display_names={"some_other_item": "Something Else"}
    )

    assert "Desc_IronPlate_C" in result
    assert "Desc_OreIron_C" in result


# --- SSP-P5-W01: extraction wiring through the tool (append-only) -----------


def _docs_data_with_extractor() -> list[dict]:
    """``_docs_data()`` plus a miner so the raw Ore import resolves a real extractor."""
    return _docs_data() + [
        {
            "NativeClass": (
                "/Script/CoreUObject.Class'/Script/FactoryGame.FGBuildableResourceExtractor'"
            ),
            "Classes": [
                {
                    "ClassName": "Build_MinerMk2_C",
                    "mDisplayName": "Miner Mk.2",
                    "mExtractCycleTime": "1.000000",
                    "mItemsPerCycle": "1",
                    "mPowerConsumption": "15.000000",
                    "mAllowedResources": _produced_in("Desc_Ore_C"),
                },
            ],
        },
    ]


def _catalog_with_extractor(tmp_path: Path):
    path = tmp_path / "en-US.json"
    path.write_text(json.dumps(_docs_data_with_extractor()), encoding="utf-16")
    return load_docs_catalog(path)


def _phase_data_high_demand(phase: int = 1) -> ProjectAssemblyData:
    """Like ``_phase_data`` but a larger Plate quantity: a multi-machine extractor count."""
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=(
            PhaseDefinition(
                phase=phase,
                name="Test Phase",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(item_class="Desc_Plate_C", display_name="Plate", quantity=6000.0),
                ),
            ),
        ),
    )


def _patch_pipeline_with_extractor(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, phase: int = 1
) -> None:
    """Like ``_patch_pipeline`` but the docs/phase data include a real extractor."""
    docs_path = tmp_path / "en-US.json"
    catalog = _catalog_with_extractor(tmp_path)

    def fake_discover_docs(**kwargs: object) -> DocsDiscovery:
        return DocsDiscovery(
            docs_path=docs_path, locale="en-US", source="configured_file", searched=()
        )

    def fake_get_docs_catalog(path: Path):
        return catalog, _fake_dataset_info(path)

    monkeypatch.setattr(main, "discover_docs", fake_discover_docs)
    monkeypatch.setattr(main, "get_docs_catalog", fake_get_docs_catalog)
    monkeypatch.setattr(
        main, "load_project_assembly_phases", lambda: _phase_data_high_demand(phase)
    )


def test_happy_path_plan_response_includes_extractor_via_text_and_power(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSP-P5-W01: raw imports are no longer free; the response names the extractor."""
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline_with_extractor(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True)

    assert "via" in result
    assert "Build_MinerMk2_C" in result

    store = _open_store(stub)
    try:
        payload = store.load_stage_plan("master", 1)
    finally:
        store.close()

    assert payload is not None
    sources = payload["sources"]
    assert len(sources) == 1
    assert sources[0]["extractor_class"] == "Build_MinerMk2_C"
    assert sources[0]["extractor_count"] >= 1

    by_building = dict(payload["power"]["by_building"])
    assert by_building.get("Build_MinerMk2_C", 0.0) > 0.0
    assert payload["power"]["total_mw"] >= by_building["Build_MinerMk2_C"]


# --- SSP-P5-W01: real-install extraction (append-only, gated) ---------------


def test_real_install_master_build_extraction_resolved(tmp_path: Path) -> None:
    """Gated: phase 3 of a real-install master build resolves real extractors."""
    from satisfactory_adapter import run_master_calculation
    from satisfactory_dataset import get_docs_catalog
    from satisfactory_install import discover_docs
    from satisfactory_progression import load_project_assembly_phases

    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog, dataset_info = get_docs_catalog(discovery.docs_path)
    phase_data = load_project_assembly_phases()

    result = ActiveSaveResult(
        status="ok", save_name="Real Install Extraction Test", save_file=None
    )
    workspace = SaveWorkspace(tmp_path, "real-install-extraction")

    run_master_calculation(
        result=result,
        get_workspace_dir=lambda: workspace.dir,
        catalog=catalog,
        dataset_info=dataset_info,
        phase_data=phase_data,
        pace_multiplier=1.0,
        include_alternates="",
        persist=True,
    )

    store = SaveStore.open(workspace.dir / "planning.sqlite3")
    try:
        payload = store.load_stage_plan("master", 3)
    finally:
        store.close()

    assert payload is not None
    sources = payload["sources"]
    assert sources, "phase 3 master build should have at least one raw import"
    for source in sources:
        assert source["extractor_class"], f"unresolved extractor for {source['item_class']}"
        assert source["extractor_count"] > 0

    known_extractor_classes = {
        "Build_MinerMk1_C",
        "Build_MinerMk2_C",
        "Build_MinerMk3_C",
        "Build_WaterPump_C",
        "Build_OilPump_C",
    }
    by_building = dict(payload["power"]["by_building"])
    extraction_power = {
        building_class: mw
        for building_class, mw in by_building.items()
        if building_class in known_extractor_classes
    }
    assert extraction_power, "expected at least one extraction building in the power plan"
    assert all(mw > 0.0 for mw in extraction_power.values())

    unknown_extractor_diagnostics = [
        diag for diag in payload["diagnostics"] if diag.get("code") == "unknown_extractor"
    ]
    assert unknown_extractor_diagnostics == []


# --- SSP-P5-W02: ban_recipes reaches the solver (append-only) ----------------


def test_ban_recipes_changes_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Banning the fixture's only Plate recipe flips the response from optimal to failed.

    ``_docs_data`` defines exactly one recipe producing Plate
    (``Recipe_Plate_C``); banning it removes the only candidate, so
    ``ban_recipes`` must reach ``solve_stage`` and change the tool's
    output from the happy-path plan to a solver-status failure message.
    """
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    baseline = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=False)
    assert "Phase 1 plan" in baseline
    assert "Production" in baseline

    banned = _run_plan(
        stub, phase=1, pace_multiplier=1.0, persist=False, ban_recipes="Recipe_Plate_C"
    )

    assert banned != baseline
    assert "solver status" in banned
    assert "Nothing persisted" in banned


# --- SSP-P5-W04: logistics wiring (append-only) ------------------------------


def test_fixture_response_unaffected_by_logistics_wiring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``_docs_data()`` defines no belt/pipe/schematic groups, so ``check_logistics``
    must degrade to a no-op: no logistics diagnostic ever appears, and the plan
    response still renders without error (no crash from the missing logistics data).
    """
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=False)

    assert "Phase 1 plan" in result
    for logistics_code in (
        "logistics_multi_line",
        "logistics_capacity_warning",
        "logistics_tier_fallback",
        "byproduct_surplus",
    ):
        assert logistics_code not in result


def test_real_install_master_build_logistics_diagnostics(tmp_path: Path) -> None:
    """Gated: a real-install master build's persisted stages carry belt/pipe
    logistics assumptions, proving ``check_logistics`` reaches both the
    single-stage and master-plan assembly points.
    """
    from satisfactory_adapter import run_master_calculation
    from satisfactory_dataset import get_docs_catalog
    from satisfactory_install import discover_docs
    from satisfactory_progression import load_project_assembly_phases

    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog, dataset_info = get_docs_catalog(discovery.docs_path)
    phase_data = load_project_assembly_phases()

    result = ActiveSaveResult(
        status="ok", save_name="Real Install Logistics Test", save_file=None
    )
    workspace = SaveWorkspace(tmp_path, "real-install-logistics")

    run_master_calculation(
        result=result,
        get_workspace_dir=lambda: workspace.dir,
        catalog=catalog,
        dataset_info=dataset_info,
        phase_data=phase_data,
        pace_multiplier=1.0,
        include_alternates="",
        persist=True,
    )

    store = SaveStore.open(workspace.dir / "planning.sqlite3")
    try:
        payload = store.load_stage_plan("master", 3)
    finally:
        store.close()

    assert payload is not None
    assumptions = payload["assumptions"]
    assert any(a.startswith("belt logistics gated to") for a in assumptions)
    assert any(a.startswith("pipe logistics gated to") for a in assumptions)


# --- SSP-P6-W01: construction bill wiring (append-only) ----------------------


def test_default_response_byte_unchanged_without_construction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """include_construction defaults to False: no 'Construction:' section at all."""
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=False)

    assert "Construction:" not in result


def test_include_construction_appends_section_and_writes_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub, phase=1, pace_multiplier=1.0, persist=True, include_construction=True
    )

    assert "Construction:" in result
    assert "Tasks (" in result
    assert "Bill of materials (" in result
    assert "Construction artifact:" in result

    plans_dir = stub.workspace.dir / "plans"
    construction_files = list(plans_dir.rglob("*_construction.md"))
    assert len(construction_files) == 1
    assert stub.workspace.dir in construction_files[0].parents


def test_include_construction_false_persist_true_writes_no_construction_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub, phase=1, pace_multiplier=1.0, persist=True, include_construction=False
    )

    assert "Construction:" not in result
    plans_dir = stub.workspace.dir / "plans"
    construction_files = list(plans_dir.rglob("*_construction.md"))
    assert construction_files == []


def test_include_construction_without_persist_appends_section_without_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub, phase=1, pace_multiplier=1.0, persist=False, include_construction=True
    )

    assert "Construction:" in result
    assert "Construction artifact:" not in result
    assert not (stub.workspace.dir / "plans").exists()


# --- SSP-P6-W02: create_build_todos gating and journal wiring ---------------


class _PlanToolStubWithWrites(_PlanToolStub):
    """Adds ``_allow_plan_writes`` for exercising the create_build_todos gate."""

    def __init__(self, base: Path, allow_plan_writes: bool = True) -> None:
        super().__init__(base)
        self._allow_writes = allow_plan_writes

    def _allow_plan_writes(self) -> bool:
        return self._allow_writes


def test_create_build_todos_creates_todos_when_flags_align(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStubWithWrites(tmp_path, allow_plan_writes=True)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub,
        phase=1,
        pace_multiplier=1.0,
        persist=True,
        include_construction=True,
        create_build_todos=True,
    )

    assert "Created 1 build todos." in result
    todos = stub.workspace._read("todos")
    assert len(todos) == 1
    assert todos[0]["title"].startswith("Build ")
    assert "task_id=" in todos[0]["details"]
    assert "stage phase 1 revision 1" in todos[0]["details"]


def test_create_build_todos_not_created_when_include_construction_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStubWithWrites(tmp_path, allow_plan_writes=True)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub,
        phase=1,
        pace_multiplier=1.0,
        persist=True,
        include_construction=False,
        create_build_todos=True,
    )

    assert "Created" not in result
    assert stub.workspace._read("todos") == []


def test_create_build_todos_refused_when_plan_writes_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStubWithWrites(tmp_path, allow_plan_writes=False)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub,
        phase=1,
        pace_multiplier=1.0,
        persist=True,
        include_construction=True,
        create_build_todos=True,
    )

    assert "Plan writes are disabled in skill settings." in result
    assert stub.workspace._read("todos") == []


def test_create_build_todos_not_created_when_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStubWithWrites(tmp_path, allow_plan_writes=True)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub,
        phase=1,
        pace_multiplier=1.0,
        persist=False,
        include_construction=True,
        create_build_todos=True,
    )

    assert "Created" not in result
    assert stub.workspace._read("todos") == []


def test_create_build_task_todos_caps_at_twenty_with_overflow(tmp_path: Path) -> None:
    """25 build tasks only create 20 todos; the rest overflow (SSP-P6-W02 cap)."""
    from datetime import datetime as _datetime

    from satisfactory_adapter import create_build_task_todos
    from satisfactory_docs import DocsCatalog
    from satisfactory_plan_models import (
        BuildTask,
        DataProvenance,
        PowerPlan,
        RecipePolicy,
        StagePlan,
    )

    catalog = DocsCatalog(items={}, recipes={}, buildings={})
    tasks = tuple(
        BuildTask(
            task_id=f"task_{i}_node_{i}",
            order_index=i,
            node_id=f"node_{i}",
            building_class="Build_ConstructorMk1_C",
            count=1,
            materials=(),
            depends_on=(),
        )
        for i in range(25)
    )
    stage = StagePlan(
        phase=1,
        window_hours=1.0,
        pace_multiplier=1.0,
        demands=(),
        nodes=(),
        sources=(),
        flows=(),
        power=PowerPlan(total_mw=0.0, by_building=()),
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="", note=""),
        solver_run_id=None,
        revision=1,
        created_at="2026-07-02T00:00:00",
    )
    workspace = SaveWorkspace(tmp_path, "todo-cap-test")

    created, overflow = create_build_task_todos(
        workspace, tasks, stage, catalog, _datetime(2026, 7, 2)
    )

    assert created == 20
    assert overflow == 5
    todos = workspace._read("todos")
    assert len(todos) == 20


# --- SSP-P7-W01: pace_scenarios tool wiring (append-only) --------------------


def test_pace_scenarios_stage_scope_bounded_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(
        stub, phase=1, pace_multiplier=1.0, persist=True, pace_scenarios="1.0;2.0;3.0"
    )

    assert "Pace scenario comparison" in result
    assert "scope=stage, phase=1" in result
    assert "Nothing persisted" in result
    assert len(result) <= 3200
    assert not (stub.workspace.dir / "planning.sqlite3").exists()
    assert not (stub.workspace.dir / "plans").exists()


def test_pace_scenarios_master_scope_bounded_not_persisted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, scope="master", persist=True, pace_scenarios="1.0;2.0")

    assert "Pace scenario comparison" in result
    assert "scope=master" in result
    assert "Nothing persisted" in result
    assert len(result) <= 3200
    assert not (stub.workspace.dir / "planning.sqlite3").exists()
    assert not (stub.workspace.dir / "plans").exists()


def test_pace_scenarios_invalid_value_returns_error_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_scenarios="not-a-number")

    assert "Invalid pace_scenarios" in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()


def test_pace_scenarios_out_of_range_returns_error_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_scenarios="0.5;5.0")

    assert "[1.0, 3.0]" in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()


def test_pace_scenarios_blank_falls_back_to_normal_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty/blank pace_scenarios must not change the default plan path."""
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, phase=1)

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True, pace_scenarios="  ")

    assert "Phase 1 plan" in result
    assert "Pace scenario comparison" not in result
    assert (stub.workspace.dir / "planning.sqlite3").exists()


# --- SSP-P8-W02: actuals-vs-plan audit integration (append-only) ------------
#
# These exercise satisfactory_adapter.run_factory_audit_pipeline directly
# (like test_real_install_master_build_extraction_resolved does for
# run_master_calculation above), faking only the save-parsing/docs I/O
# boundary so the pipeline runs against synthetic mirror machines without a
# real .sav file or Node runtime. main.py's own audit call site
# (_run_factory_audit) never passes phase, so calculate_satisfactory_plan's
# mode="audit" behavior is unaffected by this packet regardless of what
# phase the caller passes; test_audit_mode_dispatches_to_helper above still
# covers that tool-level seam unchanged.


def _fake_audit_pipeline_io(monkeypatch: pytest.MonkeyPatch, mirror_machines: list) -> None:
    """Fake save-parsing/docs so run_factory_audit_pipeline runs on synthetic data."""
    import contextlib

    import satisfactory_adapter as adapter

    @contextlib.contextmanager
    def fake_copied_save(save_file: Path, dest_dir: Path):
        yield save_file

    def fake_extract_save_snapshot(save_copy: Path, parser_runtime_dir: str, summary_only: bool):
        return {"source": {}, "header": {}, "counts": {}, "machines": []}

    def fake_get_docs_catalog(docs_path: Path):
        from satisfactory_docs import DocsCatalog

        return DocsCatalog(items={}, recipes={}, buildings={}), _fake_dataset_info(docs_path)

    def fake_build_factory_mirror(snapshot: dict, catalog: object, **kwargs: object) -> dict:
        return {
            "schemaVersion": 1,
            "createdAt": "2026-07-02T00:00:00+00:00",
            "source": snapshot.get("source", {}),
            "header": {},
            "counts": {},
            "expectedTotals": {"inputs": [], "outputs": []},
            "observedEstimateTotals": {"outputs": []},
            "machines": mirror_machines,
            "lines": [],
        }

    monkeypatch.setattr(adapter, "copied_save", fake_copied_save)
    monkeypatch.setattr(adapter, "extract_save_snapshot", fake_extract_save_snapshot)
    monkeypatch.setattr(adapter, "get_docs_catalog", fake_get_docs_catalog)
    monkeypatch.setattr(adapter, "build_factory_mirror", fake_build_factory_mirror)


def _run_audit_pipeline(tmp_path: Path, workspace_dir: Path, **kwargs: object) -> str:
    from satisfactory_adapter import run_factory_audit_pipeline
    from satisfactory_mirror import TrendConfig

    return run_factory_audit_pipeline(
        save_file=tmp_path / "Test Save.sav",
        workspace_dir=workspace_dir,
        docs_path=tmp_path / "en-US.json",
        parser_runtime_dir="",
        trend_config=TrendConfig(),
        **kwargs,
    )


def test_audit_without_phase_is_byte_identical_to_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Omitting ``phase`` (every caller before this packet) must not change the
    audit response at all, even when a stored plan exists for some phase."""
    from datetime import datetime as _datetime

    import shutil

    workspace_dir = tmp_path / "ws"
    _fake_audit_pipeline_io(monkeypatch, [{"recipe": "Recipe_IronPlate_C", "clock": 1.0}])

    store = SaveStore.open(workspace_dir / "planning.sqlite3")
    try:
        store.upsert_master_plan(
            {
                "plan_id": "master",
                "name": "Test Save",
                "created_at": _datetime(2026, 7, 2).isoformat(),
                "updated_at": _datetime(2026, 7, 2).isoformat(),
            }
        )
        store.save_stage_plan(
            "master",
            {"nodes": [{"recipe_class": "Recipe_IronPlate_C", "machine_count_exact": 2.0}]},
            1,
            _datetime(2026, 7, 2),
        )
    finally:
        store.close()

    with_no_phase_kwarg = _run_audit_pipeline(tmp_path, workspace_dir)

    # store_mirror_artifacts appends an observation row per call; reset that
    # rolling history so the second run's response (same workspace, so the
    # "Artifacts:" path line matches too) differs only by the phase argument
    # actually under test here, not by an unrelated sample-count drift.
    shutil.rmtree(workspace_dir / "mirror")

    with_phase_zero = _run_audit_pipeline(tmp_path, workspace_dir, phase=0)

    assert "Plan vs actual" not in with_no_phase_kwarg
    assert with_no_phase_kwarg == with_phase_zero


def test_audit_with_phase_and_stored_plan_appends_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime as _datetime

    workspace_dir = tmp_path / "ws"
    _fake_audit_pipeline_io(
        monkeypatch,
        [
            {"recipe": "Recipe_IronPlate_C", "clock": 1.0},
            {"recipe": "Recipe_IronPlate_C", "clock": 1.0},
        ],
    )

    store = SaveStore.open(workspace_dir / "planning.sqlite3")
    try:
        store.upsert_master_plan(
            {
                "plan_id": "master",
                "name": "Test Save",
                "created_at": _datetime(2026, 7, 2).isoformat(),
                "updated_at": _datetime(2026, 7, 2).isoformat(),
            }
        )
        store.save_stage_plan(
            "master",
            {"nodes": [{"recipe_class": "Recipe_IronPlate_C", "machine_count_exact": 4.0}]},
            3,
            _datetime(2026, 7, 2),
        )
    finally:
        store.close()

    result = _run_audit_pipeline(tmp_path, workspace_dir, phase=3)

    assert "Plan vs actual (phase 3 rev 1):" in result
    assert "build 2.000 more recipe_ironplate" in result


def test_audit_with_phase_but_no_stored_plan_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_dir = tmp_path / "ws"
    _fake_audit_pipeline_io(monkeypatch, [])

    result = _run_audit_pipeline(tmp_path, workspace_dir, phase=2)

    assert "no stored plan found for phase 2" in result
    assert "build" not in result
    assert "unplanned" not in result

"""Tests for the calculate_satisfactory_plan tool's scope="master" master-plan
exposure, and the pure format_master_response / export_master_summary helpers.

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
from satisfactory_master_plan import MasterPlanResult, diff_stages  # noqa: E402
from satisfactory_models import ActiveSaveResult  # noqa: E402
from satisfactory_plan_models import (  # noqa: E402
    DataProvenance,
    PowerPlan,
    ProcessNode,
    RecipePolicy,
    StagePlan,
)
from satisfactory_progression import (  # noqa: E402
    PhaseDefinition,
    PhasePart,
    ProjectAssemblyData,
)
from satisfactory_reports import export_master_summary, format_master_response  # noqa: E402
from satisfactory_store import SaveStore  # noqa: E402
from satisfactory_workspace import SaveWorkspace  # noqa: E402


# --- Fixture Docs catalog: one ore, one recipe, one building (same shape as
# tests/test_plan_tool.py, duplicated here rather than imported to keep this
# file's fixtures self-contained and independently readable) ------------------


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


def _five_phase_data() -> ProjectAssemblyData:
    """Five phases, all demanding the fixture's one producible part (Plate),
    at a different quantity each, so every phase solves under the same
    single-recipe chain and revisions are easy to reason about.
    """
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=tuple(
            PhaseDefinition(
                phase=phase,
                name=f"Test Phase {phase}",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(
                        item_class="Desc_Plate_C",
                        display_name="Plate",
                        quantity=60.0 * phase,
                    ),
                ),
            )
            for phase in range(1, 6)
        ),
    )


def _stopped_at_phase_2_data() -> ProjectAssemblyData:
    """Phase 1 solves; phase 2 demands a part with no recipe in the fixture
    catalog, so ``build_master_plan`` stops there.
    """
    return ProjectAssemblyData(
        base_tiers=(0,),
        phases=(
            PhaseDefinition(
                phase=1,
                name="Test Phase 1",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(item_class="Desc_Plate_C", display_name="Plate", quantity=60.0),
                ),
            ),
            PhaseDefinition(
                phase=2,
                name="Test Phase 2",
                window_hours_baseline=1.0,
                unlocks_tiers=(),
                parts=(
                    PhasePart(
                        item_class="Desc_NoRecipe_C", display_name="Unbuildable", quantity=60.0
                    ),
                ),
            ),
        ),
    )


def _patch_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, phase_data: ProjectAssemblyData
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
    monkeypatch.setattr(main, "load_project_assembly_phases", lambda: phase_data)


class _PlanToolStub:
    """Minimal stand-in exposing what ``calculate_satisfactory_plan`` reads."""

    def __init__(self, base: Path, save_name: str = "Test Save") -> None:
        self.workspace = SaveWorkspace(base, "test-save")
        self._save_name = save_name
        self.diagnostics: list[str] = []

    def _resolve(self) -> ActiveSaveResult:
        return ActiveSaveResult(status="ok", save_name=self._save_name, save_file=None)

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


def _run_plan(stub: _PlanToolStub, **kwargs: object) -> str:
    return asyncio.run(main.SatisfactoryAssistant.calculate_satisfactory_plan(stub, **kwargs))


def _open_store(stub: _PlanToolStub) -> SaveStore:
    return SaveStore.open(stub.workspace.dir / "planning.sqlite3")


# --- scope="master": phase validation -----------------------------------------


@pytest.mark.parametrize("phase", [1, 5])
def test_master_scope_with_nonzero_phase_returns_validation_message(
    tmp_path: Path, phase: int
) -> None:
    stub = _PlanToolStub(tmp_path)

    result = _run_plan(stub, phase=phase, scope="master")

    assert "scope='master'" in result
    assert str(phase) in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()


# --- scope="master": happy path -----------------------------------------------


def test_master_happy_path_persists_five_stages_and_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, _five_phase_data())

    result = _run_plan(stub, pace_multiplier=1.0, persist=True, scope="master")

    assert "Master plan: status 'complete'" in result
    assert "Stages:" in result
    for phase in range(1, 6):
        assert f"Phase {phase}" in result
    assert "Transitions:" in result
    assert "Artifact:" in result
    assert len(result) <= 3200

    store = _open_store(stub)
    try:
        plan = store.get_master_plan("master")
        assert plan is not None
        assert plan["name"] == "Test Save"
        for phase in range(1, 6):
            assert store.list_stage_revisions("master", phase) == [1]
            stage_payload = store.load_stage_plan("master", phase)
            assert stage_payload is not None
            assert stage_payload["revision"] == 1
            solver_run_id = stage_payload["solver_run_id"]
            assert isinstance(solver_run_id, str)
            assert solver_run_id.startswith(f"run_m{phase}_1_")
            assert store.get_solver_run(solver_run_id) is not None
    finally:
        store.close()

    plans_dir = stub.workspace.dir / "plans"
    md_files = list(plans_dir.rglob("*.md"))
    json_files = list(plans_dir.rglob("*.json"))
    # Five per-stage exports (md + json each) plus one master_summary.md.
    assert len(md_files) == 6
    assert len(json_files) == 5
    for path in md_files + json_files:
        assert stub.workspace.dir in path.parents
    assert any(path.name == "master_summary.md" for path in md_files)


def test_master_second_call_persists_revision_two_across_phases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, _five_phase_data())

    first = _run_plan(stub, pace_multiplier=1.0, persist=True, scope="master")
    second = _run_plan(stub, pace_multiplier=1.0, persist=True, scope="master")

    assert "rev 1" in first
    assert "rev 2" in second

    store = _open_store(stub)
    try:
        for phase in range(1, 6):
            assert store.list_stage_revisions("master", phase) == [1, 2]
    finally:
        store.close()


def test_master_persist_false_leaves_store_and_artifacts_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, _five_phase_data())

    result = _run_plan(stub, pace_multiplier=1.0, persist=False, scope="master")

    assert "not persisted" in result
    assert "Artifact:" not in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()
    assert not (stub.workspace.dir / "plans").exists()


def test_master_stopped_at_phase_persists_nothing_and_names_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, _stopped_at_phase_2_data())

    result = _run_plan(stub, pace_multiplier=1.0, persist=True, scope="master")

    assert "stopped_at_phase_2" in result
    assert "phase 2" in result
    assert not (stub.workspace.dir / "planning.sqlite3").exists()
    assert not (stub.workspace.dir / "plans").exists()


# --- scope="stage": regression (behavior byte-unchanged) ----------------------


def test_stage_scope_regression_still_produces_a_stage_plan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _PlanToolStub(tmp_path)
    _patch_pipeline(monkeypatch, tmp_path, _five_phase_data())

    result = _run_plan(stub, phase=1, pace_multiplier=1.0, persist=True)

    assert "Phase 1 plan" in result
    assert "Demands:" in result
    store = _open_store(stub)
    try:
        stage_payload = store.load_stage_plan("master", 1)
        assert stage_payload is not None
        assert stage_payload["revision"] == 1
    finally:
        store.close()


# --- Tool surface: exactly three @tool methods --------------------------------


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


# --- Pure format_master_response / export_master_summary tests ---------------


def _fixture_stage(phase: int, revision: int, machine_count: int, power_mw: float) -> StagePlan:
    return StagePlan(
        phase=phase,
        window_hours=1.0,
        pace_multiplier=1.0,
        demands=(("Desc_Plate_C", 60.0, 1.0),),
        nodes=(
            ProcessNode(
                node_id=f"node_recipe_plate_{phase}",
                recipe_class="Recipe_Plate_C",
                building_class="Build_ConstructorMk1_C",
                runs_per_min=1.0,
                machine_count_exact=float(machine_count),
                machine_count=machine_count,
                clock=1.0,
                power_mw=power_mw,
            ),
        ),
        sources=(),
        flows=(),
        power=PowerPlan(total_mw=power_mw, by_building=(("Build_ConstructorMk1_C", power_mw),)),
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="2026-07-02T00:00:00", note=""),
        solver_run_id=None,
        revision=revision,
        created_at="2026-07-02T00:00:00",
    )


def _two_stage_result(diagnostics: tuple[str, ...] = ()) -> MasterPlanResult:
    stages = (_fixture_stage(1, 1, 2, 8.0), _fixture_stage(2, 1, 3, 12.0))
    transitions = (diff_stages(stages[0], stages[1]),)
    return MasterPlanResult(
        status="complete",
        stages=stages,
        transitions=transitions,
        reservations=(),
        diagnostics=diagnostics,
    )


def test_format_master_response_renders_fixed_sections_and_stays_bounded() -> None:
    result = _two_stage_result(diagnostics=("phase 2: note",))

    text = format_master_response(result, artifact_path="C:/ws/plans/master/master_summary.md")

    assert "Master plan: status 'complete'" in text
    assert "Phase 1" in text and "Phase 2" in text
    assert "Transitions:" in text
    assert "Phase 1->2:" in text
    assert "Diagnostics:" in text
    assert "phase 2: note" in text
    assert "Artifact: C:/ws/plans/master/master_summary.md" in text
    assert len(text) <= 3200


def test_format_master_response_omits_artifact_line_when_none() -> None:
    result = _two_stage_result()

    text = format_master_response(result, artifact_path=None)

    assert "Artifact:" not in text


def test_format_master_response_empty_stages_status_names_phase() -> None:
    result = MasterPlanResult(
        status="stopped_at_phase_1",
        stages=(),
        transitions=(),
        reservations=(),
        diagnostics=("phase 1: stage solve stopped (infeasible)",),
    )

    text = format_master_response(result, artifact_path=None)

    assert "stopped_at_phase_1" in text
    assert "pace n/a" in text
    assert "(none)" in text
    assert "phase 1: stage solve stopped" in text


def test_export_master_summary_writes_contained_file(tmp_path: Path) -> None:
    result = _two_stage_result()

    path = export_master_summary(tmp_path, "master", result)

    written = Path(path)
    assert written.is_file()
    assert tmp_path in written.parents
    content = written.read_text(encoding="utf-8")
    assert "Status: complete" in content
    assert "# Master Plan:" in content
    assert "## Transitions" in content
    assert "## Reservations" in content


def test_export_master_summary_hostile_plan_id_is_contained(tmp_path: Path) -> None:
    result = _two_stage_result()
    hostile_id = "../../../../etc/passwd"

    path = export_master_summary(tmp_path, hostile_id, result)

    written = Path(path).resolve()
    assert written.is_relative_to(tmp_path.resolve())
    assert not (tmp_path.parent / "etc").exists()
    assert written.is_file()

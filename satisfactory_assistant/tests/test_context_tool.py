"""Tests for the get_satisfactory_context tool (lookup and plan-status sections).

main.py imports the Wingman app (api.*, skills.skill_base), so the repo root
must be importable. The test skips gracefully if those modules are unavailable.
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime
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
from satisfactory_plan_models import (  # noqa: E402
    DataProvenance,
    PowerPlan,
    ProcessNode,
    RecipePolicy,
    StagePlan,
)
from satisfactory_store import SaveStore  # noqa: E402
from satisfactory_workspace import SaveWorkspace  # noqa: E402


# Mirrors satisfactory_workspace._CONTEXT_CHAR_BUDGET (the hard ceiling
# format_context enforces); duplicated here since that name is private.
_CONTEXT_CHAR_BUDGET = 2800


# --- Fixture Docs catalog: two items, one recipe -----------------------------


def _amount(class_name: str, amount: float) -> str:
    return (
        f'(ItemClass="/Script/Engine.BlueprintGeneratedClass\'/Game/FactoryGame/'
        f'Resource/Parts/X/Desc_X.{class_name}\'",Amount={amount})'
    )


def _amounts(entries: list[tuple[str, float]]) -> str:
    return "(" + ",".join(_amount(class_name, amount) for class_name, amount in entries) + ")"


def _produced_in(building_class: str) -> str:
    return f'("/Game/FactoryGame/Buildable/Factory/X/{building_class}.{building_class}")'


def _docs_data() -> list[dict]:
    """One producible chain: Iron Ore -> Iron Plate. Recipe runs 60 seconds."""
    return [
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGResourceDescriptor'",
            "Classes": [
                {
                    "ClassName": "Desc_OreIron_C",
                    "mDisplayName": "Iron Ore",
                    "mForm": "RF_SOLID",
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGItemDescriptor'",
            "Classes": [
                {
                    "ClassName": "Desc_IronPlate_C",
                    "mDisplayName": "Iron Plate",
                    "mForm": "RF_SOLID",
                },
            ],
        },
        {
            "NativeClass": "/Script/CoreUObject.Class'/Script/FactoryGame.FGRecipe'",
            "Classes": [
                {
                    "ClassName": "Recipe_IronPlate_C",
                    "mDisplayName": "Iron Plate",
                    "mIngredients": _amounts([("Desc_OreIron_C", 30)]),
                    "mProduct": _amounts([("Desc_IronPlate_C", 20)]),
                    "mManufactoringDuration": "60.000000",
                    "mProducedIn": _produced_in("Build_ConstructorMk1_C"),
                },
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
        item_count=2,
        recipe_count=1,
        building_count=1,
        schematic_count=0,
    )


def _patch_docs_available(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Monkeypatch discovery/parsing so the lookup section resolves the fixture."""
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


def _patch_docs_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_discover_docs(**kwargs: object) -> DocsDiscovery:
        return DocsDiscovery(
            docs_path=None, locale="en-US", source="configured_file", searched=("a", "b")
        )

    monkeypatch.setattr(main, "discover_docs", fake_discover_docs)


class _ContextToolStub:
    """Minimal stand-in exposing what ``get_satisfactory_context`` reads."""

    def __init__(self, base: Path, save_name: str = "Test Save") -> None:
        self.workspace = SaveWorkspace(base, "test-save")
        self._save_name = save_name
        self.diagnostics: list[str] = []

    def _resolve(self) -> ActiveSaveResult:
        return ActiveSaveResult(status="ok", save_name=self._save_name)

    def _status_message(self, result: ActiveSaveResult) -> str | None:
        return None

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        return self.workspace

    def _diag(self, message: str) -> None:
        self.diagnostics.append(message)

    def _max_response_items(self) -> int:
        return 12

    def _docs_file(self) -> str:
        return ""

    def _install_dir(self) -> str:
        return ""

    def _docs_locale(self) -> str:
        return "en-US"

    # Exercised directly (not re-implemented) so the tests track real behavior.
    _lookup_lines = main.SatisfactoryAssistant._lookup_lines
    _plan_status_lines = main.SatisfactoryAssistant._plan_status_lines


def _run_context(stub: _ContextToolStub, **kwargs: object) -> str:
    return asyncio.run(main.SatisfactoryAssistant.get_satisfactory_context(stub, **kwargs))


def _stage_plan(phase: int, revision: int) -> StagePlan:
    """A minimal, deterministic stage plan for plan-status fixtures."""
    return StagePlan(
        phase=phase,
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
        sources=(),
        flows=(),
        power=PowerPlan(total_mw=8.0, by_building=(("Build_ConstructorMk1_C", 8.0),)),
        recipe_policy=RecipePolicy(
            mode="standard", pinned=(), banned=(), allowed_alternates=()
        ),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="2026-07-02T00:00:00", note=""),
        solver_run_id=None,
        revision=revision,
        created_at="2026-07-02T00:00:00",
    )


def _persist_stage(workspace: SaveWorkspace, phase: int, revision_count: int = 1) -> None:
    """Persist ``revision_count`` revisions of one phase's stage plan, plus its master row."""
    now = datetime(2026, 7, 2, 0, 0, 0)
    store = SaveStore.open(workspace.dir / "planning.sqlite3")
    try:
        store.upsert_master_plan(
            {
                "plan_id": "master",
                "name": "Test Save",
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        for revision in range(1, revision_count + 1):
            store.save_stage_plan(
                "master", _stage_plan(phase, revision).to_payload(), phase, now
            )
    finally:
        store.close()


# --- Lookup section -----------------------------------------------------------


def test_lookup_renders_capped_items_and_recipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _ContextToolStub(tmp_path)
    _patch_docs_available(monkeypatch, tmp_path)

    result = _run_context(stub, lookup="iron")

    assert "Lookup 'iron':" in result
    assert "Items:" in result
    assert "Iron Ore" in result
    assert "Iron Plate" in result
    assert "Recipes:" in result
    assert len(result) <= _CONTEXT_CHAR_BUDGET


def test_lookup_unavailable_line_when_docs_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _ContextToolStub(tmp_path)
    _patch_docs_missing(monkeypatch)

    result = _run_context(stub, lookup="iron")

    assert "Lookup 'iron': unavailable" in result


def test_lookup_unavailable_line_when_docs_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _ContextToolStub(tmp_path)
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

    result = _run_context(stub, lookup="iron")

    assert "Lookup 'iron': unavailable (could not load Docs file)." in result
    assert stub.diagnostics


def test_lookup_no_matches_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stub = _ContextToolStub(tmp_path)
    _patch_docs_available(monkeypatch, tmp_path)

    result = _run_context(stub, lookup="zzz_no_such_item")

    assert "no matching items or recipes" in result


def test_no_lookup_param_has_no_lookup_section(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)

    result = _run_context(stub)

    assert "Lookup" not in result


# --- Plan-status section ------------------------------------------------------


def test_plan_status_absent_for_fresh_workspace(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)

    result = _run_context(stub)

    assert "Plan status" not in result


def test_plan_status_appears_after_persisted_plan(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    _persist_stage(stub.workspace, phase=1, revision_count=1)

    result = _run_context(stub)

    assert "Plan status (master):" in result
    assert "Phase 1: revision 1" in result
    assert "2 machines" in result
    assert "8.000 MW" in result


def test_plan_status_shows_latest_revision(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    _persist_stage(stub.workspace, phase=1, revision_count=2)

    result = _run_context(stub)

    assert "Phase 1: revision 2" in result
    assert "revision 1" not in result


def test_plan_status_capped_at_five_lines(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    for phase in range(1, 6):
        _persist_stage(stub.workspace, phase=phase, revision_count=1)

    result = _run_context(stub)

    assert result.count("- Phase") == 5


# --- Response budget -----------------------------------------------------------


def test_response_with_lookup_and_plan_status_stays_within_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stub = _ContextToolStub(tmp_path)
    _patch_docs_available(monkeypatch, tmp_path)
    _persist_stage(stub.workspace, phase=1, revision_count=1)

    result = _run_context(stub, lookup="iron")

    assert "Lookup 'iron':" in result
    assert "Plan status (master):" in result
    assert len(result) <= _CONTEXT_CHAR_BUDGET


# --- Locate section (SSP-P9-W01) -----------------------------------------------


def _fixture_mirror() -> dict:
    return {
        "lines": [
            {
                "id": "line_0001",
                "machineCount": 4,
                "confidence": "probable",
                "primaryOutput": {"item": "Iron Ingot", "ratePerMin": 270.0},
                "centroid": {"x": 1000.0, "y": 0.0, "z": 0.0},
                "grossInputs": [],
                "grossOutputs": [],
                "machineIds": [],
            }
        ],
        "machines": [
            {
                "id": "m1",
                "type": "Build_SmelterMk1_C",
                "location": {"x": 1000.0, "y": 0.0, "z": 0.0},
                "recipe": "Recipe_IngotIron_C",
                "resource": "",
                "clock": 1.0,
            }
        ],
    }


def _plant_mirror(workspace: SaveWorkspace) -> None:
    mirror_dir = workspace.dir / "mirror"
    mirror_dir.mkdir(parents=True, exist_ok=True)
    (mirror_dir / "latest_mirror.json").write_text(
        json.dumps(_fixture_mirror()), encoding="utf-8"
    )


def test_locate_renders_locations_with_fixture_mirror(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    _plant_mirror(stub.workspace)

    result = _run_context(stub, locate="iron")

    assert "Locations 'iron':" in result
    assert "Iron Ingot line" in result
    assert "Recipe_IngotIron_C" in result
    assert "distance" in result


def test_locate_absent_mirror_explains_to_run_audit_first(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)

    result = _run_context(stub, locate="iron")

    assert "no factory mirror yet" in result
    assert "audit" in result


def test_no_locate_param_has_no_locations_section(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    _plant_mirror(stub.workspace)

    result = _run_context(stub)

    assert "Locations" not in result


def test_response_with_locate_stays_within_budget(tmp_path: Path) -> None:
    stub = _ContextToolStub(tmp_path)
    _plant_mirror(stub.workspace)

    result = _run_context(stub, locate="iron")

    assert len(result) <= _CONTEXT_CHAR_BUDGET

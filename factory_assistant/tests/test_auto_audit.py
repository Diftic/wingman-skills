"""Tests for startup, save-change, and periodic automatic mirror audits."""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import pytest


main = pytest.importorskip("skills.factory_assistant.main")
game = pytest.importorskip("factory_games.satisfactory.game")

from factory_games.satisfactory.reader.models import (  # noqa: E402
    STATUS_NO_ACTIVE_SAVE,
    STATUS_OK,
    ActiveSaveResult,
)
from factory_shared.workspace import SaveWorkspace  # noqa: E402


def _active_result(tmp_path: Path, save_name: str = "Test Save") -> ActiveSaveResult:
    root = tmp_path / "Saved"
    save_dir = root / "SaveGames" / "profile"
    log_dir = root / "Logs"
    save_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    save_file = save_dir / f"{save_name}.sav"
    log_file = log_dir / "FactoryGame.log"
    save_file.write_bytes(b"save-v1")
    log_file.write_text("active", encoding="utf-8")
    return ActiveSaveResult(
        status=STATUS_OK,
        save_name=save_name,
        session_name="Test Session",
        save_file=save_file,
        save_file_found=True,
        log_file=log_file,
        root=root,
    )


class _AutoAuditStub:
    def __init__(self, base: Path, result: ActiveSaveResult) -> None:
        self.result = result
        self.workspace = SaveWorkspace(base, "test-save")
        self._auto_audit_has_run = False
        self._auto_audit_observation = None
        self.audit_calls: list[tuple[str | None, int]] = []
        self.diagnostics: list[str] = []

    def _resolve(self) -> ActiveSaveResult:
        return self.result

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        self.workspace.ensure()
        return self.workspace

    def _diag(self, message: str) -> None:
        self.diagnostics.append(message)

    async def _run_factory_audit_async(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        self.audit_calls.append((result.save_name, phase))
        mirror_dir = ws.dir / "mirror"
        mirror_dir.mkdir(parents=True, exist_ok=True)
        (mirror_dir / "latest_mirror.json").write_text(
            f'{{"run": {len(self.audit_calls)}}}', encoding="utf-8"
        )
        return "Factory audit complete."


def _run_once(stub: _AutoAuditStub) -> None:
    asyncio.run(game.SatisfactoryHandler._auto_audit_once(stub))


def test_save_tree_marker_detects_direct_and_profile_saves(tmp_path: Path) -> None:
    root = tmp_path / "Saved"
    direct = root / "SaveGames" / "Direct.sav"
    nested = root / "SaveGames" / "profile" / "Nested.sav"
    direct.parent.mkdir(parents=True)
    nested.parent.mkdir()
    direct.write_bytes(b"a")
    nested.write_bytes(b"bb")

    marker = game._save_tree_marker(root)

    assert [entry[0] for entry in marker] == ["Direct.sav", str(Path("profile/Nested.sav"))]
    assert [entry[2] for entry in marker] == [1, 2]


def test_first_detection_audits_once_until_save_changes(tmp_path: Path) -> None:
    stub = _AutoAuditStub(tmp_path / "generated", _active_result(tmp_path))

    _run_once(stub)
    _run_once(stub)
    _run_once(stub)

    assert len(stub.audit_calls) == 1
    assert "startup" in stub.diagnostics[0]


def test_save_file_change_refreshes_before_interval(tmp_path: Path) -> None:
    result = _active_result(tmp_path)
    stub = _AutoAuditStub(tmp_path / "generated", result)
    _run_once(stub)

    result.save_file.write_bytes(b"save-v2-with-more-data")
    _run_once(stub)

    assert len(stub.audit_calls) == 2
    assert any("save changed" in line for line in stub.diagnostics)


def test_new_save_file_refreshes_current_active_save(tmp_path: Path) -> None:
    result = _active_result(tmp_path)
    stub = _AutoAuditStub(tmp_path / "generated", result)
    _run_once(stub)

    added = result.root / "SaveGames" / "profile" / "Autosave_0.sav"
    added.write_bytes(b"autosave")
    _run_once(stub)

    assert len(stub.audit_calls) == 2
    assert stub.audit_calls[-1][0] == "Test Save"


def test_unrelated_game_log_growth_does_not_trigger_extra_audit(tmp_path: Path) -> None:
    result = _active_result(tmp_path)
    stub = _AutoAuditStub(tmp_path / "generated", result)
    _run_once(stub)

    result.log_file.write_text("active\nroutine game log line", encoding="utf-8")
    _run_once(stub)

    assert len(stub.audit_calls) == 1


def test_active_save_returning_after_absence_audits_immediately(tmp_path: Path) -> None:
    active = _active_result(tmp_path)
    stub = _AutoAuditStub(tmp_path / "generated", active)
    _run_once(stub)

    stub.result = ActiveSaveResult(status=STATUS_NO_ACTIVE_SAVE, root=active.root)
    _run_once(stub)
    assert stub._auto_audit_observation is None

    stub.result = active
    _run_once(stub)

    assert len(stub.audit_calls) == 2
    assert any("active save detected" in line for line in stub.diagnostics)


class _SerializedAuditStub:
    def __init__(self) -> None:
        self._audit_lock = None
        self.concurrent = 0
        self.max_concurrent = 0
        self.guard = threading.Lock()
        self.diagnostics: list[str] = []

    def _run_factory_audit(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        with self.guard:
            self.concurrent += 1
            self.max_concurrent = max(self.max_concurrent, self.concurrent)
        time.sleep(0.03)
        with self.guard:
            self.concurrent -= 1
        return "done"

    def _diag(self, message: str) -> None:
        self.diagnostics.append(message)

    _run_factory_audit_async = game.SatisfactoryHandler._run_factory_audit_async


def test_manual_and_automatic_audits_are_serialized(tmp_path: Path) -> None:
    stub = _SerializedAuditStub()
    result = _active_result(tmp_path)
    workspace = SaveWorkspace(tmp_path / "generated", "test-save")

    async def run_both() -> tuple[str, str]:
        return await asyncio.gather(
            stub._run_factory_audit_async(result, workspace),
            stub._run_factory_audit_async(result, workspace),
        )

    assert asyncio.run(run_both()) == ["done", "done"]
    assert stub.max_concurrent == 1


def test_default_config_starts_watcher_and_routes_locations_to_locate() -> None:
    config = Path(main.__file__).with_name("default_config.yaml").read_text(encoding="utf-8")

    assert "auto_activate: true" in config
    assert "Never use lookup for a location request" in config

"""Satisfactory GameHandler: the only Satisfactory module the Orchestrator reaches.

It owns the Satisfactory Reader (``reader/``) and Handler (``handler/``) and
implements :class:`factory_shared.contract.GameHandler`. The method bodies come
from the 0.9.1 ``main.py`` without logic changes; Wingman services arrive through
the :class:`HandlerContext` callbacks.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from factory_games.satisfactory.handler.locate import query_targets_machine_type
from factory_games.satisfactory.handler.pipeline import (
    _save_file_note,
    build_locate_lines,
    build_lookup_lines,
    build_plan_status_lines,
    format_docs_missing_message,
    run_factory_audit_pipeline,
    run_master_calculation,
    run_plan_calculation,
    run_scenario_comparison,
)
from factory_games.satisfactory.handler.reference import (
    project_assembly_reference_lines,
)
from factory_games.satisfactory.reader.active_save import resolve_active_save
from factory_games.satisfactory.reader.dataset import get_docs_catalog
from factory_games.satisfactory.reader.install import discover_docs
from factory_games.satisfactory.reader.mirror import TrendConfig
from factory_games.satisfactory.reader.models import (
    STATUS_NO_ACTIVE_SAVE,
    STATUS_NO_LOG_FOLDER,
    ActiveSaveResult,
)
from factory_games.satisfactory.reader.progression import load_project_assembly_phases
from factory_shared.coerce import coerce_int as _coerce_int
from factory_shared.contract import (
    PLAN_OPTIONS,
    ActiveSave,
    GameHandler,
    HandlerContext,
)
from factory_shared.journal import apply_journal_update
from factory_shared.workspace import (
    SaveWorkspace,
    adopt_legacy_workspace,
    clip,
    format_context,
    safe_save_key,
    slugify,
    stable_workspace_key,
)

_SaveTreeMarker = tuple[tuple[str, int, int], ...]
_AutoAuditObservation = tuple[str, str, str, int, int, _SaveTreeMarker]

_PROMPT = """\
Satisfactory notes:
In Satisfactory, "phase" or "stage" usually means a Space Elevator / Project
Assembly phase (1-5). Pass it as stage in calculate_factory_plan.
The skill can calculate a Project Assembly phase plan for the active save
(machines needed, power draw, and required inputs) using its planning tools;
phase deliverable requirements come from verified bundled game data, not guesswork.
If the player asks to finish a phase, plan around that phase's deliverables
unless they explicitly mean a custom project phase.
Alternate recipes go in allow_recipes, for example "Alternate: Steel Rod".
Speech recognition may render "oil extractors" as "oilless extractors"; still
use the map tool."""


def _save_tree_marker(root: Path | None) -> _SaveTreeMarker:
    """Return a deterministic marker for direct and per-profile save files."""
    if root is None:
        return ()
    save_games = root / "SaveGames"
    try:
        if not save_games.is_dir():
            return ()
        candidates = [path for path in save_games.glob("*.sav") if path.is_file()]
        for profile in save_games.iterdir():
            if profile.is_dir():
                candidates.extend(path for path in profile.glob("*.sav") if path.is_file())
    except OSError:
        return ()

    marker: list[tuple[str, int, int]] = []
    for path in candidates:
        try:
            stat = path.stat()
            relative = str(path.relative_to(save_games))
        except (OSError, ValueError):
            continue
        marker.append((relative, stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(marker))


def _active_save_observation(result: ActiveSaveResult) -> _AutoAuditObservation | None:
    """Build the file/log marker that decides whether an audit is due."""
    if not result.confirmed or result.save_file is None:
        return None
    try:
        save_stat = result.save_file.stat()
    except OSError:
        return None

    return (
        str(result.root or ""),
        str(result.save_name or ""),
        str(result.save_file),
        save_stat.st_mtime_ns,
        save_stat.st_size,
        _save_tree_marker(result.root),
    )


class SatisfactoryHandler(GameHandler):
    """Per-save factory planning for Satisfactory, scoped to the active save."""

    game_id = "satisfactory"
    display_name = "Satisfactory"
    setting_ids = (
        "satisfactory_install_dir",
        "mirror_trend_window_saves",
        "mirror_zero_streak_saves",
        "mirror_deviation_threshold_percent",
    )

    def __init__(self, ctx: HandlerContext) -> None:
        super().__init__(ctx)
        self._audit_lock: asyncio.Lock | None = None
        self._auto_audit_has_run = False
        self._auto_audit_observation: _AutoAuditObservation | None = None

    # --- contract: identity and selection ---

    def capabilities(self) -> frozenset[str]:
        return frozenset(PLAN_OPTIONS)

    def prompt(self) -> str:
        return _PROMPT

    def active_save(self) -> ActiveSave:
        result = self._resolve()
        return ActiveSave(
            game_id=self.game_id,
            confirmed=result.confirmed,
            save_name=result.save_name,
            detected_at=result.log_mtime,
            status=result.status,
        )

    # --- just-in-time config accessors (never cached) ---

    def _saved_dir(self) -> str:
        return ""

    def _docs_file(self) -> str:
        return ""

    def _install_dir(self) -> str:
        return self._ctx.setting("satisfactory_install_dir") or ""

    def _docs_locale(self) -> str:
        return "en-US"

    def _parser_runtime_dir(self) -> str:
        return ""

    def _max_response_items(self) -> int:
        return self._ctx.max_response_items()

    def _mirror_trend_window_saves(self) -> int:
        return _coerce_int(self._ctx.setting("mirror_trend_window_saves"), default=5, minimum=1)

    def _mirror_zero_streak_saves(self) -> int:
        return _coerce_int(self._ctx.setting("mirror_zero_streak_saves"), default=3, minimum=1)

    def _mirror_deviation_threshold(self) -> float:
        value = self._ctx.setting("mirror_deviation_threshold_percent")
        try:
            percent = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            percent = 25.0
        return max(0.0, min(percent, 100.0)) / 100.0

    def _allow_plan_writes(self) -> bool:
        return self._ctx.allow_plan_writes()

    def _generated_dir(self) -> Path:
        return Path(self._ctx.generated_dir())

    def _map_background_image(self) -> Path | None:
        path = self._generated_dir() / "assets" / "satisfactory_world_map.png"
        return path if path.is_file() else None

    # --- helpers ---

    def _resolve(self) -> ActiveSaveResult:
        return resolve_active_save(configured_dir=self._saved_dir())

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        # Identity is based on stable logical evidence (Saved root + save name),
        # never the volatile .sav path, so the same save resolves to the same
        # workspace whether or not the file is currently found on disk.
        base = self._generated_dir()
        key = stable_workspace_key(result.root, result.save_name)
        # Older workspaces were keyed on the .sav path; when a concrete save
        # file exists, adopt that legacy workspace's records under the stable
        # key so plans created before this fix do not appear to vanish.
        if result.save_file is not None:
            legacy_key = safe_save_key(result.save_name or "save", str(result.save_file))
            if legacy_key != key:
                adopt_legacy_workspace(base, key, legacy_key)
        ws = SaveWorkspace(base, key)
        ws.ensure()
        return ws

    def _status_message(self, result: ActiveSaveResult) -> str | None:
        if result.status == STATUS_NO_LOG_FOLDER:
            return (
                "I couldn't find Satisfactory's save data yet. Start the game "
                "once, then try again."
            )
        if result.status == STATUS_NO_ACTIVE_SAVE:
            return (
                "Found the newest Satisfactory log, but no active save was "
                "detected. Load a save in Satisfactory first."
            )
        return None

    def _diag(self, message: str) -> None:
        self._ctx.diag(message)

    def _show_map_path(self, image_path: Path) -> str:
        return self._ctx.show_map(image_path)

    def _latest_map_path(self, ws: SaveWorkspace) -> Path | None:
        mirror_dir = ws.dir / "mirror"
        try:
            candidates = [path for path in mirror_dir.glob("location_*.png") if path.is_file()]
            return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None
        except OSError:
            return None

    def _show_locate_result(self, ws: SaveWorkspace, query: str) -> str | None:
        image_path = ws.dir / "mirror" / f"location_{slugify(query)}.png"
        if not image_path.is_file():
            return None
        return self._show_map_path(image_path)

    async def _run_factory_audit_async(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        """Run one serialized audit off the event loop.

        Shielding the worker means unload waits for an in-flight save parse to
        finish instead of leaving a thread writing mirror artifacts after the
        skill has been torn down.
        """
        if self._audit_lock is None:
            self._audit_lock = asyncio.Lock()
        async with self._audit_lock:
            worker = asyncio.create_task(
                asyncio.to_thread(self._run_factory_audit, result, ws, phase)
            )
            try:
                return await asyncio.shield(worker)
            except asyncio.CancelledError:
                try:
                    await worker
                except Exception as exc:  # pragma: no cover - diagnostic on shutdown
                    self._diag(f"[Satisfactory] audit worker failed during shutdown: {exc}")
                raise

    async def auto_refresh_once(self) -> None:
        await self._auto_audit_once()

    async def _auto_audit_once(self) -> None:
        """Run an automatic audit on first detection or a save-file change."""
        result = self._resolve()
        observation = _active_save_observation(result)
        if observation is None:
            # Resetting makes a save that disappears and later returns trigger
            # immediately, even when its file marker is unchanged.
            self._auto_audit_observation = None
            return

        if not self._auto_audit_has_run:
            reason = "startup"
        elif self._auto_audit_observation is None:
            reason = "active save detected"
        elif observation != self._auto_audit_observation:
            reason = "save changed"
        else:
            return

        ws = self._workspace_for(result)
        mirror_path = ws.dir / "mirror" / "latest_mirror.json"
        try:
            before_mtime_ns = mirror_path.stat().st_mtime_ns
        except OSError:
            before_mtime_ns = None

        self._diag(
            f"[Satisfactory] automatic audit starting ({reason}) for "
            f"{result.save_name}."
        )
        try:
            output = await self._run_factory_audit_async(result, ws)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._diag(f"[Satisfactory] automatic audit failed: {clip(str(exc), 240)}")
        else:
            try:
                after_mtime_ns = mirror_path.stat().st_mtime_ns
            except OSError:
                after_mtime_ns = None
            if after_mtime_ns is not None and after_mtime_ns != before_mtime_ns:
                self._diag(
                    f"[Satisfactory] automatic audit completed for {result.save_name}."
                )
            else:
                compact = clip(" ".join(output.splitlines()), 240)
                self._diag(
                    f"[Satisfactory] automatic audit did not build a mirror: {compact}"
                )
        finally:
            # A failure retries on the next save update instead of flooding
            # logs on every inexpensive watcher poll.
            self._auto_audit_has_run = True
            self._auto_audit_observation = observation

    def _lookup_lines(self, query: str) -> list[str]:
        """Return bounded Docs lookup lines for ``query`` (items then recipes).

        Capped at 5 items and 5 recipes (``dataset``'s own clamp). Any failure
        to reach or read the Docs catalog degrades to one short "unavailable"
        line rather than raising.
        """
        discovery = discover_docs(
            configured_file=self._docs_file(),
            configured_install_dir=self._install_dir(),
            locale=self._docs_locale(),
        )
        if discovery.docs_path is None:
            return ["I couldn't look that up because I couldn't find Satisfactory's game data."]
        try:
            catalog, _ = get_docs_catalog(discovery.docs_path)
        except (OSError, ValueError) as exc:
            self._diag(f"[Satisfactory] lookup failed to load Docs: {exc}")
            return ["I couldn't look that up because Satisfactory's game data would not open."]
        return build_lookup_lines(catalog, query)

    def _plan_status_lines(self, ws: SaveWorkspace) -> list[str]:
        """Return up to 5 compact lines describing persisted master-plan stages.

        Reads only; never creates a store. Absent store, absent master plan,
        or no stage revisions yet all degrade to no section rather than an error.
        """
        return build_plan_status_lines(ws.dir / "planning.sqlite3")

    # --- contract: tools ---

    async def context(self, focus: str = "", lookup: str = "", locate: str = "") -> str:
        """Return the active save identity and a compact planning summary."""
        result = self._resolve()
        message = self._status_message(result)
        if message:
            self._diag(f"[Satisfactory] context unavailable: {result.status}")
            return message

        ws = self._workspace_for(result)
        # Focus is applied inside summary() BEFORE capping, so a matching older
        # record is not hidden behind newer unrelated records.
        summary = ws.summary(self._max_response_items(), focus=focus)

        header_lines: list[str] = [f"Active save: {result.save_name}"]
        if result.session_name:
            header_lines.append(f"Session: {result.session_name}")
        note = _save_file_note(result)
        if note:
            header_lines.append(note)
        if result.log_mtime:
            header_lines.append(
                f"Detected from {result.log_file.name} ({result.log_mtime:%Y-%m-%d %H:%M})"
            )
        header_lines.extend(project_assembly_reference_lines(focus))
        if lookup.strip():
            header_lines.extend(self._lookup_lines(lookup.strip()))
        locate_query = locate.strip()
        # Defensive routing for model calls that put a recognized production
        # building in `focus` despite a spoken where/map request. This happened
        # live when Faster Whisper transcribed "oil extractors" as "oilless
        # extractors" and the model selected context instead of the map tool.
        if not locate_query and focus.strip() and query_targets_machine_type(focus):
            locate_query = focus.strip()
        if locate_query:
            background_getter = getattr(self, "_map_background_image", None)
            background = background_getter() if callable(background_getter) else None
            header_lines.extend(build_locate_lines(ws.dir, locate_query, background))
            show_locate = getattr(self, "_show_locate_result", None)
            popup_status = show_locate(ws, locate_query) if callable(show_locate) else None
            if popup_status:
                header_lines.append(popup_status)
        header_lines.extend(self._plan_status_lines(ws))

        # format_context de-duplicates blocked flows and enforces a hard global
        # character budget so the return stays under the low-token target.
        return format_context(header_lines, summary)

    async def show_map(self, query: str = "") -> str:
        """Find ``query`` on the factory mirror and open the map popup."""
        result = self._resolve()
        message = self._status_message(result)
        if message:
            return message
        ws = self._workspace_for(result)

        locate_query = query.strip()
        if not locate_query:
            latest = self._latest_map_path(ws)
            if latest is None:
                return "I don't have a map to reopen yet. Tell me what you want to find."
            return self._show_map_path(latest)

        background_getter = getattr(self, "_map_background_image", None)
        background = background_getter() if callable(background_getter) else None
        lines = build_locate_lines(ws.dir, locate_query, background)
        popup_status = self._show_locate_result(ws, locate_query)
        if popup_status:
            lines.append(popup_status)
        return "\n".join(lines)

    async def update_journal(self, action: str, **fields: Any) -> str:
        """Add or update a planning record for the active save."""
        if not self._allow_plan_writes():
            return "Saving notes and plans is turned off in the skill settings."

        result = self._resolve()
        message = self._status_message(result)
        if message:
            return message

        ws = self._workspace_for(result)
        known = {
            "title", "details", "item_id", "inputs", "outputs", "status",
            "area", "recipe", "machines", "constraints", "clear_fields",
        }
        kwargs = {key: str(value) for key, value in fields.items() if key in known}
        extra = {key: value for key, value in fields.items() if key not in known}
        return apply_journal_update(ws, result.save_name, action, extra=extra, **kwargs)

    def _run_factory_audit(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        """Locate the Docs file, then hand off to the pure audit pipeline.

        The caller has already resolved the active save, confirmed its ``.sav``
        file exists, and validated ``phase`` (0 or 1-5).
        """
        discovery = discover_docs(
            configured_file=self._docs_file(),
            configured_install_dir=self._install_dir(),
            locale=self._docs_locale(),
        )
        if discovery.docs_path is None:
            return format_docs_missing_message(discovery.searched)

        return run_factory_audit_pipeline(
            save_file=result.save_file,
            workspace_dir=ws.dir,
            docs_path=discovery.docs_path,
            parser_runtime_dir=self._parser_runtime_dir(),
            trend_config=TrendConfig(
                window_saves=self._mirror_trend_window_saves(),
                zero_streak_saves=self._mirror_zero_streak_saves(),
                deviation_threshold=self._mirror_deviation_threshold(),
            ),
            diag=self._diag,
            phase=phase,
        )

    async def calculate(
        self,
        mode: str = "plan",
        stage: int = 0,
        pace_multiplier: float = 1.0,
        allow_recipes: str = "",
        persist: bool = True,
        scope: str = "stage",
        pin_recipes: str = "",
        ban_recipes: str = "",
        include_construction: bool = False,
        create_build_todos: bool = False,
        pace_scenarios: str = "",
        **_ignored: Any,
    ) -> str:
        """Compute (and usually persist) a Project Assembly stage plan, or audit the save.

        ``stage`` is the Project Assembly phase (1-5); ``allow_recipes`` are the
        alternate recipes to unlock beyond the default gate.
        """
        phase = stage
        include_alternates = allow_recipes
        result = self._resolve()
        message = self._status_message(result)
        if message:
            if mode == "audit":
                self._diag(f"[Satisfactory] factory audit unavailable: {result.status}")
            else:
                self._diag(f"[Satisfactory] plan unavailable: {result.status}")
            return message

        if mode == "audit":
            if phase != 0 and not (1 <= phase <= 5):
                return (
                    f"For a factory check, choose phase 1 to 5 or leave it at 0. "
                    f"I received {phase}."
                )
            if result.save_file is None:
                note = _save_file_note(result)
                return (
                    "I found the active game, but I couldn't read its save file. "
                    f"{note or ''}"
                ).strip()
            ws = self._workspace_for(result)
            return await self._run_factory_audit_async(result, ws, phase)

        if scope == "master" and phase != 0:
            return (
                f"A full-game plan already covers every phase, so leave the phase at 0. "
                f"I received {phase}."
            )

        discovery = discover_docs(
            configured_file=self._docs_file(),
            configured_install_dir=self._install_dir(),
            locale=self._docs_locale(),
        )
        if discovery.docs_path is None:
            return format_docs_missing_message(discovery.searched)

        try:
            catalog, dataset_info = get_docs_catalog(discovery.docs_path)
        except (OSError, ValueError) as exc:
            self._diag(f"[Satisfactory] plan failed to load Docs: {exc}")
            return f"I couldn't read Satisfactory's game data: {clip(str(exc), 240)}"

        try:
            phase_data = load_project_assembly_phases()
        except ValueError as exc:
            self._diag(f"[Satisfactory] plan phase data invalid: {exc}")
            return str(exc)

        if pace_scenarios.strip():
            return run_scenario_comparison(
                catalog=catalog,
                phase_data=phase_data,
                scope=scope,
                phase=phase,
                pace_scenarios=pace_scenarios,
                include_alternates=include_alternates,
                pin_recipes=pin_recipes,
                ban_recipes=ban_recipes,
            )

        if scope == "master":
            return run_master_calculation(
                result=result,
                get_workspace_dir=lambda: self._workspace_for(result).dir,
                catalog=catalog,
                dataset_info=dataset_info,
                phase_data=phase_data,
                pace_multiplier=pace_multiplier,
                include_alternates=include_alternates,
                persist=persist,
                pin_recipes=pin_recipes,
                ban_recipes=ban_recipes,
            )

        return run_plan_calculation(
            result=result,
            get_workspace_dir=lambda: self._workspace_for(result).dir,
            catalog=catalog,
            dataset_info=dataset_info,
            phase_data=phase_data,
            phase=phase,
            pace_multiplier=pace_multiplier,
            include_alternates=include_alternates,
            persist=persist,
            pin_recipes=pin_recipes,
            ban_recipes=ban_recipes,
            include_construction=include_construction,
            create_build_todos=create_build_todos,
            get_workspace=lambda: self._workspace_for(result),
            get_allow_plan_writes=lambda: self._allow_plan_writes(),
        )

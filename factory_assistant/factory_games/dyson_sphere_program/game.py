"""Dyson Sphere Program GameHandler: the only DSP module the Orchestrator reaches.

Short-reader version: production, consumption, power and research speed from
the game's own statistics in the newest save. No factory layout or map yet.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from factory_games.dyson_sphere_program.handler.report import (
    DEFAULT_WINDOW_MINUTES,
    audit_report,
    header_lines,
    lookup_lines,
    planet_lines,
    power_lines,
    production_lines,
)
from factory_games.dyson_sphere_program.reader.catalog import Catalog, load_catalog
from factory_games.dyson_sphere_program.reader.save_file import (
    DspSaveError,
    DspSaveSummary,
    read_save,
)
from factory_games.dyson_sphere_program.reader.saves import (
    STATUS_NO_SAVE,
    STATUS_NO_SAVE_FOLDER,
    ActiveSaveFile,
    find_active_save,
)
from factory_shared.coerce import coerce_int
from factory_shared.contract import ActiveSave, GameHandler, HandlerContext
from factory_shared.journal import apply_journal_update
from factory_shared.workspace import SaveWorkspace, clip, format_context, safe_save_key

_WINDOWS = (1, 10, 60, 600)
_KNOWN_FIELDS = {
    "title", "details", "item_id", "inputs", "outputs", "status",
    "area", "recipe", "machines", "constraints", "clear_fields",
}

_PROMPT = """\
Dyson Sphere Program notes:
The numbers come from the game's own production statistics in the newest save,
so they are measured rates, not estimates. They are as new as the last autosave
(the autosave interval is a game setting).
"Using more than you make" means the factory draws that item from storage or
belts; it runs out unless production goes up. Matrices (blue, red, yellow,
purple, green, white) are the research cubes.
Planets are numbered in save order; their names are not available yet.
The map popup and production planning are not available for Dyson Sphere
Program yet; use calculate_factory_plan with mode "audit" for a full report."""


class DysonSphereProgramHandler(GameHandler):
    """Dyson Sphere Program, scoped to the newest (active) save."""

    game_id = "dyson_sphere_program"
    display_name = "Dyson Sphere Program"
    setting_ids = ("dsp_save_dir", "dsp_rate_window_minutes")

    def __init__(self, ctx: HandlerContext) -> None:
        super().__init__(ctx)
        self._cache_key: tuple[str, int, int] | None = None
        self._cache: DspSaveSummary | None = None
        self._last_refresh_key: tuple[str, int, int] | None = None

    # --- settings ---

    def _save_dir_setting(self) -> str:
        return str(self._ctx.setting("dsp_save_dir") or "")

    def _window_minutes(self) -> int:
        value = coerce_int(self._ctx.setting("dsp_rate_window_minutes"), default=DEFAULT_WINDOW_MINUTES, minimum=1)
        return value if value in _WINDOWS else DEFAULT_WINDOW_MINUTES

    # --- contract: identity ---

    def prompt(self) -> str:
        return _PROMPT

    def _active_file(self) -> ActiveSaveFile:
        return find_active_save(self._save_dir_setting())

    def active_save(self) -> ActiveSave:
        found = self._active_file()
        return ActiveSave(
            game_id=self.game_id,
            confirmed=found.confirmed,
            save_name=found.path.stem if found.path else None,
            detected_at=found.modified,
            status=found.status,
        )

    # --- reading ---

    def _status_message(self, found: ActiveSaveFile) -> str | None:
        if found.status == STATUS_NO_SAVE_FOLDER:
            return (
                "I couldn't find Dyson Sphere Program's save folder. Save the game once, "
                "or set the save folder in the skill settings."
            )
        if found.status == STATUS_NO_SAVE:
            return "I found the Dyson Sphere Program save folder, but no saves yet. Save the game first."
        return None

    def _summary(self, found: ActiveSaveFile) -> DspSaveSummary:
        assert found.path is not None
        key = (str(found.path), int(found.modified.timestamp() * 1e6) if found.modified else 0, found.size)
        if key != self._cache_key or self._cache is None:
            self._cache = read_save(found.path)
            self._cache_key = key
        return self._cache

    def _load(self) -> tuple[DspSaveSummary | None, str | None]:
        """Return (summary, None) or (None, player-facing message)."""
        found = self._active_file()
        message = self._status_message(found)
        if message:
            return None, message
        try:
            return self._summary(found), None
        except DspSaveError as exc:
            if found.settling:
                return None, "The game is writing a save right now. Ask again in a few seconds."
            return None, f"I couldn't read the newest save ({found.path.name}): {exc}"
        except OSError as exc:
            return None, f"I couldn't open the newest save: {clip(str(exc), 200)}"

    def _catalog(self) -> Catalog:
        return load_catalog()

    def _workspace_for(self, summary: DspSaveSummary) -> SaveWorkspace:
        base = Path(self._ctx.generated_dir()) / self.game_id
        ws = SaveWorkspace(base, safe_save_key(f"galaxy-{summary.galaxy_seed}", summary.identity))
        ws.ensure()
        return ws

    # --- contract: tools ---

    async def context(self, focus: str = "", lookup: str = "", locate: str = "") -> str:
        summary, message = self._load()
        if summary is None:
            return message or ""
        ws = self._workspace_for(summary)
        catalog = self._catalog()
        window = self._window_minutes()
        lines = header_lines(summary)
        lines.extend(power_lines(summary, window))
        lines.extend(production_lines(summary, catalog, window, self._ctx.max_response_items(), focus))
        if lookup.strip():
            lines.extend(lookup_lines(catalog, lookup.strip()))
        if locate.strip():
            lines.append("Finding buildings on the map is not available for Dyson Sphere Program yet.")
        lines.extend(planet_lines(summary, window, 3))
        return format_context(lines, ws.summary(self._ctx.max_response_items(), focus=focus))

    async def show_map(self, query: str = "") -> str:
        return (
            "The map is not available for Dyson Sphere Program yet. I can tell you "
            "what each planet makes and uses instead."
        )

    async def update_journal(self, action: str, **fields: Any) -> str:
        if not self._ctx.allow_plan_writes():
            return "Saving notes and plans is turned off in the skill settings."
        summary, message = self._load()
        if summary is None:
            return message or ""
        ws = self._workspace_for(summary)
        kwargs = {key: str(value) for key, value in fields.items() if key in _KNOWN_FIELDS}
        extra = {key: value for key, value in fields.items() if key not in _KNOWN_FIELDS}
        return apply_journal_update(ws, summary.path.stem, action, extra=extra, **kwargs)

    async def calculate(self, mode: str = "plan", **options: Any) -> str:
        if mode != "audit":
            return (
                "Production planning is not available for Dyson Sphere Program yet. "
                "I can give a full production report: use the audit mode."
            )
        summary, message = self._load()
        if summary is None:
            return message or ""
        return audit_report(summary, self._catalog(), self._window_minutes(), self._ctx.max_response_items())

    async def auto_refresh_once(self) -> None:
        """Read each new autosave once, so tool answers are instant and problems show early."""
        found = self._active_file()
        if not found.confirmed or found.settling or found.path is None:
            return
        key = (str(found.path), int(found.modified.timestamp() * 1e6) if found.modified else 0, found.size)
        if key == self._last_refresh_key:
            return
        self._last_refresh_key = key
        try:
            summary = await asyncio.to_thread(self._summary, found)
        except (DspSaveError, OSError) as exc:
            self._ctx.diag(f"[DSP] could not read {found.path.name}: {exc}")
            return
        self._ctx.diag(
            f"[DSP] read {found.path.name}: {len(summary.factories)} planets with statistics, "
            f"game {summary.version_text}."
        )

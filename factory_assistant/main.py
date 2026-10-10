"""FactoryAssistant - Wingman AI skill (Layer 1: the single Orchestrator).

Owns everything Wingman-facing for every supported factory game: the tools, the
settings, the lifecycle, the map popup and the background refresh loop. All game
work goes to a :class:`factory_shared.contract.GameHandler` from the game
registry; this module never imports a game module.

Author: ShipBit
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from api.enums import LogType
from api.interface import SettingsConfig, SkillConfig, WingmanInitializationError
from skills.skill_base import Skill, tool

# Allow importing the sibling packages when loaded as a skill.
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from factory_orchestrator.map_overlay import MapOverlay  # noqa: E402
from factory_orchestrator.registry import (  # noqa: E402
    AUTO,
    GAMES,
    load_handlers,
    select_handler,
)
from factory_shared.coerce import coerce_bool, coerce_int  # noqa: E402
from factory_shared.contract import GameHandler, HandlerContext  # noqa: E402
from factory_shared.journal import JOURNAL_ACTIONS  # noqa: E402

if TYPE_CHECKING:
    from wingmen.open_ai_wingman import OpenAiWingman

# Background refresh. The watcher checks cheaply every five seconds so the
# in-game autosave cadence controls the expensive parse/audit work.
_AUTO_AUDIT_POLL_SECONDS = 5.0

JournalAction = Literal[
    "add_note",
    "add_todo",
    "complete_todo",
    "add_goal",
    "add_flow",
    "update_flow",
    "archive_item",
]
assert tuple(JournalAction.__args__) == JOURNAL_ACTIONS  # type: ignore[attr-defined]


class FactoryAssistant(Skill):
    """One Orchestrator for all factory games, scoped to the active save."""

    def __init__(
        self,
        config: SkillConfig,
        settings: SettingsConfig,
        wingman: "OpenAiWingman",
    ) -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)
        self._auto_audit_task: asyncio.Task[None] | None = None
        self._map_overlay: MapOverlay | None = None
        self._handler_cache: dict[str, GameHandler] | None = None

    async def validate(self) -> list[WingmanInitializationError]:
        errors = await super().validate()
        self.retrieve_custom_property_value("game", errors)
        self.retrieve_custom_property_value("max_response_items", errors)
        self.retrieve_custom_property_value("allow_plan_writes", errors)
        self.retrieve_custom_property_value("map_overlay_enabled", errors)
        self.retrieve_custom_property_value("map_overlay_display", errors)
        self.retrieve_custom_property_value("map_overlay_size", errors)
        self.retrieve_custom_property_value("map_overlay_duration_seconds", errors)
        self.retrieve_custom_property_value("map_overlay_position", errors)
        for handler in self._handlers().values():
            for setting_id in handler.setting_ids:
                self.retrieve_custom_property_value(setting_id, errors)
        return errors

    async def prepare(self) -> None:
        await super().prepare()
        self._start_map_overlay()
        if self._auto_audit_task is None or self._auto_audit_task.done():
            self._auto_audit_task = asyncio.create_task(self._auto_audit_loop())

    async def unload(self) -> None:
        task = self._auto_audit_task
        self._auto_audit_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        for handler in (self._handler_cache or {}).values():
            await handler.close()
        overlay = self._map_overlay
        self._map_overlay = None
        if overlay is not None:
            overlay.stop()
        await super().unload()

    # --- just-in-time config accessors (never cached) ---

    def _setting(self, key: str) -> Any:
        return self.retrieve_custom_property_value(key, [])

    def _game_choice(self) -> str:
        value = str(self._setting("game") or AUTO).strip().lower()
        return value if value == AUTO or value in GAMES else AUTO

    def _max_response_items(self) -> int:
        return coerce_int(self._setting("max_response_items"), default=12, minimum=1)

    def _allow_plan_writes(self) -> bool:
        return coerce_bool(self._setting("allow_plan_writes"), default=True)

    def _map_overlay_enabled(self) -> bool:
        return coerce_bool(self._setting("map_overlay_enabled"), default=True)

    def _map_overlay_display(self) -> int:
        return coerce_int(self._setting("map_overlay_display"), default=1, minimum=1)

    def _map_overlay_size(self) -> int:
        return min(1200, coerce_int(self._setting("map_overlay_size"), default=520, minimum=240))

    def _map_overlay_duration_seconds(self) -> float:
        try:
            duration = float(self._setting("map_overlay_duration_seconds"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            duration = 15.0
        return max(0.0, min(duration, 3600.0))

    def _map_overlay_position(self) -> str:
        value = str(self._setting("map_overlay_position") or "top_center").strip().lower()
        return value if value in {"top_left", "top_center", "top_right"} else "top_center"

    # --- game handlers ---

    def _handler_context(self) -> HandlerContext:
        return HandlerContext(
            generated_dir=lambda: Path(self.get_generated_files_dir()),
            setting=self._setting,
            diag=self._diag,
            show_map=self._show_map_path,
            max_response_items=self._max_response_items,
            allow_plan_writes=self._allow_plan_writes,
        )

    def _handlers(self) -> dict[str, GameHandler]:
        if self._handler_cache is None:
            self._handler_cache = load_handlers(self._handler_context())
        return self._handler_cache

    def _active_handler(self) -> GameHandler:
        return select_handler(self._handlers(), self._game_choice())

    def _refresh_handlers(self) -> list[GameHandler]:
        """Handlers that the background loop keeps current (one game, or all in auto)."""
        handlers = self._handlers()
        choice = self._game_choice()
        return [handlers[choice]] if choice in handlers else list(handlers.values())

    # --- Orchestrator services ---

    def _diag(self, message: str) -> None:
        self.printr.print(message, color=LogType.SYSTEM, server_only=True)

    def _start_map_overlay(self) -> None:
        if self._map_overlay is not None:
            self._map_overlay.stop()
            self._map_overlay = None
        if not self._map_overlay_enabled():
            return
        overlay = MapOverlay(
            size=self._map_overlay_size(),
            display=self._map_overlay_display(),
            duration_s=self._map_overlay_duration_seconds(),
            position=self._map_overlay_position(),
        )
        if overlay.start():
            self._map_overlay = overlay
            self._diag("[Factory] standalone map popup ready.")
        else:
            self._diag(
                "[Factory] map popup unavailable: "
                f"{overlay.failed_reason or 'unknown reason'}."
            )

    def _show_map_path(self, image_path: Path) -> str:
        if not self._map_overlay_enabled():
            return "Map popup is disabled in the skill settings."
        if self._map_overlay is None:
            self._start_map_overlay()
        overlay = self._map_overlay
        if overlay is None or not overlay.show(image_path):
            reason = overlay.failed_reason if overlay is not None else "could not start"
            return f"I made the map, but couldn't open the popup ({reason})."
        return "Opened the map popup."

    async def _auto_audit_loop(self) -> None:
        """Keep save-derived data current for the game(s) in scope."""
        while True:
            for handler in self._refresh_handlers():
                try:
                    await handler.auto_refresh_once()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # pragma: no cover - defensive background guard
                    self._diag(f"[Factory] {handler.display_name} refresh error: {exc}")
            await asyncio.sleep(_AUTO_AUDIT_POLL_SECONDS)

    async def get_prompt(self) -> str | None:
        base = self.config.prompt or ""
        try:
            game_prompt = self._active_handler().prompt()
        except Exception as exc:  # pragma: no cover - prompt must never break the turn
            self._diag(f"[Factory] game prompt unavailable: {exc}")
            game_prompt = ""
        return "\n\n".join(part for part in (base.strip(), game_prompt.strip()) if part) or None

    # --- tools (game-neutral; the active game's handler does the work) ---

    @tool(
        description=(
            "Check the current factory game save for saved jobs, notes, goals, "
            "production setups, recipes, or locations. Use lookup for general "
            "item and recipe facts. Use locate for something built in this save; "
            "it also opens the map. Prefer show_factory_map for direct map requests."
        ),
        wait_response=True,
    )
    async def get_factory_context(
        self, focus: str = "", lookup: str = "", locate: str = ""
    ) -> str:
        """Return the active save identity and a compact planning summary.

        Args:
            focus: Optional keyword to filter records (matched across title,
                details, inputs, and outputs) before they are capped.
            lookup: Optional item or recipe name to look up in the game's
                item and recipe data (capped at 5 items and 5 recipes).
            locate: Optional item, recipe, or resource name to find in the
                save's factory scan. Returns coordinates for up to 5 matches
                and opens a location map for the top match.
        """
        return await self._active_handler().context(focus=focus, lookup=lookup, locate=locate)

    @tool(
        description=(
            "Open or close the factory map popup. Use this whenever the player "
            "asks where something is. Show with a query to find it, show without a "
            "query to reopen the last map, or hide to close the popup."
        ),
        wait_response=True,
    )
    async def show_factory_map(
        self,
        query: str = "",
        action: Literal["show", "hide"] = "show",
    ) -> str:
        """Control the standalone map popup.

        Args:
            query: Item, recipe, resource, line, or machine to locate. Omit to
                reopen the latest location map.
            action: "show" to find/open the map or "hide" to close it.
        """
        if action == "hide":
            if self._map_overlay is not None:
                self._map_overlay.hide()
            return "Closed the map popup."
        return await self._active_handler().show_map(query=query)

    @tool(
        description=(
            "Save or update a note, job, goal, or production setup for the current "
            "factory game save. Use when the player asks to remember something, "
            "add a job, mark work done, or change a planned production setup."
        ),
        wait_response=True,
    )
    async def update_factory_plan(
        self,
        action: JournalAction,
        title: str = "",
        details: str = "",
        item_id: str = "",
        inputs: str = "",
        outputs: str = "",
        status: str = "",
        area: str = "",
        recipe: str = "",
        machines: str = "",
        constraints: str = "",
        clear_fields: str = "",
        **kwargs: Any,
    ) -> str:
        """Add or update a planning record for the active save.

        Args:
            action: The operation to perform.
            title: Title for new notes, todos, goals, or flows.
            details: Optional extra detail; preserves the player's own wording.
            item_id: Id of an existing item (for complete_todo, archive_item, update_flow).
            inputs: Semicolon-separated input materials for a flow, e.g. "Iron Ore 240/min; Coal 240/min".
            outputs: Semicolon-separated output materials for a flow, e.g. "Steel Ingot 360/min".
            status: Optional flow status: planned, building, blocked, balanced, done, archived.
            area: Optional map area/location for a flow, e.g. "Northern Forest".
            recipe: Optional recipe name for a flow, e.g. "Steel Beam (Foundry)".
            machines: Optional machine list/counts for a flow, e.g. "Foundry x8; Constructor x4".
            constraints: Optional constraint note for a flow, e.g. "power<=200MW".
            clear_fields: For update_flow only. Comma/semicolon-separated fields to
                reset (empty strings otherwise mean "leave unchanged"). Allowed:
                details, area, recipe, machines, constraints, inputs, outputs.
        """
        return await self._active_handler().update_journal(
            action,
            title=title,
            details=details,
            item_id=item_id,
            inputs=inputs,
            outputs=outputs,
            status=status,
            area=area,
            recipe=recipe,
            machines=machines,
            constraints=constraints,
            clear_fields=clear_fields,
            **kwargs,
        )

    @tool(
        description=(
            "Plan production or check the current factory. Use plan for a game "
            "stage (for example a Satisfactory Space Elevator phase), machine counts, "
            "power, or a full build order. Use audit to read what is actually in the "
            "current save. Stage scope handles one stage; master handles all stages. "
            "Recipe choices, build steps, saved jobs, and pace comparisons are optional."
        ),
        wait_response=True,
    )
    async def calculate_factory_plan(
        self,
        stage: int = 0,
        pace_multiplier: float = 1.0,
        allow_recipes: str = "",
        persist: bool = True,
        mode: Literal["plan", "audit"] = "plan",
        scope: Literal["stage", "master"] = "stage",
        pin_recipes: str = "",
        ban_recipes: str = "",
        include_construction: bool = False,
        create_build_todos: bool = False,
        pace_scenarios: str = "",
    ) -> str:
        """Compute (and usually persist) a stage plan, or audit the save.

        Args:
            stage: Game progression stage for scope="stage" (Satisfactory:
                Project Assembly phase 1-5); 0 for scope="master". For
                mode="audit", optional: 0 runs the factory scan only; a stage
                also compares the scan against that stage's latest stored plan.
            pace_multiplier: Window-hours multiplier in [1.0, 3.0]. Ignored
                for mode="audit".
            allow_recipes: Semicolon-separated extra (alternate) recipe names
                to allow beyond the default gate. Ignored for mode="audit".
            persist: When True (default), save the computed stage(s) as new
                revision(s) of the save's master plan and export artifacts.
                Ignored for mode="audit".
            mode: "plan" to compute a stage plan (default), or "audit" to
                scan the current factory from the save.
            scope: "stage" to plan a single stage (default), or "master" to
                plan every stage at once. Ignored for mode="audit".
            pin_recipes: Semicolon-separated recipe names to force; each must
                already be allowed. Ignored for mode="audit".
            ban_recipes: Semicolon-separated recipe names to exclude, even
                if otherwise unlocked. Ignored for mode="audit".
            include_construction: When True, append a construction bill and
                build sequence to the response. Ignored for mode="audit" and
                scope="master".
            create_build_todos: When True, add a journal job per build task
                (capped at 20). Needs include_construction=True, persist=True
                and plan writes allowed. Ignored for mode="audit" and scope="master".
            pace_scenarios: Semicolon-separated pace multipliers (1-4 distinct
                values, each in [1.0, 3.0]), e.g. "1.0;2.0;3.0". Computes an
                unsaved side-by-side comparison instead of a normal plan.
                Ignored for mode="audit".
        """
        return await self._active_handler().calculate(
            mode=mode,
            stage=stage,
            pace_multiplier=pace_multiplier,
            allow_recipes=allow_recipes,
            persist=persist,
            scope=scope,
            pin_recipes=pin_recipes,
            ban_recipes=ban_recipes,
            include_construction=include_construction,
            create_build_todos=create_build_todos,
            pace_scenarios=pace_scenarios,
        )

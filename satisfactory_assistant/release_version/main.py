"""SatisfactoryAssistant - Wingman AI skill.

Helps Satisfactory players plan and maintain factories for the currently active
save only. The active save is identified strictly from the newest game log; the
skill never mixes data between saves and only writes inside a generated,
per-save workspace.

Author: ShipBit
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from api.enums import LogType
from api.interface import SettingsConfig, SkillConfig, WingmanInitializationError
from skills.skill_base import Skill, tool

# Allow importing the sibling pure-logic modules when loaded as a skill.
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from satisfactory_active_save import resolve_active_save  # noqa: E402
from satisfactory_adapter import (  # noqa: E402
    _coerce_bool as _coerce_bool,
    _coerce_int as _coerce_int,
    _normalize_rate_aliases,
    _parse_rates,
    _resolve_status_target as _resolve_status_target,
    _save_file_note as _save_file_note,
    build_locate_lines,
    build_lookup_lines,
    build_plan_status_lines,
    format_docs_missing_message,
    run_factory_audit_pipeline,
    run_master_calculation,
    run_plan_calculation,
    run_scenario_comparison,
)
from satisfactory_dataset import get_docs_catalog  # noqa: E402
from satisfactory_install import discover_docs  # noqa: E402
from satisfactory_mirror import TrendConfig  # noqa: E402
from satisfactory_models import (  # noqa: E402
    STATUS_NO_ACTIVE_SAVE,
    STATUS_NO_LOG_FOLDER,
    ActiveSaveResult,
)
from satisfactory_progression import load_project_assembly_phases  # noqa: E402
from satisfactory_reference import project_assembly_reference_lines  # noqa: E402
from satisfactory_workspace import (  # noqa: E402
    FLOW_STATUSES,
    STATUS_ARCHIVED,
    STATUS_DONE,
    SaveWorkspace,
    adopt_legacy_workspace,
    clip,
    format_context,
    parse_clear_fields,
    safe_save_key,
    stable_workspace_key,
)

# Clip titles echoed in write-tool acknowledgements (stored titles are kept in
# full); keeps tool responses short even for long natural-language titles.
_ACK_TITLE_MAX = 60

if TYPE_CHECKING:
    from wingmen.open_ai_wingman import OpenAiWingman


class SatisfactoryAssistant(Skill):
    """Per-save factory planning for Satisfactory, scoped to the active save."""

    def __init__(
        self,
        config: SkillConfig,
        settings: SettingsConfig,
        wingman: "OpenAiWingman",
    ) -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)

    async def validate(self) -> list[WingmanInitializationError]:
        errors = await super().validate()
        self.retrieve_custom_property_value("satisfactory_saved_dir", errors)
        self.retrieve_custom_property_value("satisfactory_docs_file", errors)
        self.retrieve_custom_property_value("satisfactory_install_dir", errors)
        self.retrieve_custom_property_value("satisfactory_docs_locale", errors)
        self.retrieve_custom_property_value("satisfactory_parser_runtime_dir", errors)
        self.retrieve_custom_property_value("max_response_items", errors)
        self.retrieve_custom_property_value("allow_plan_writes", errors)
        self.retrieve_custom_property_value("mirror_trend_window_saves", errors)
        self.retrieve_custom_property_value("mirror_zero_streak_saves", errors)
        self.retrieve_custom_property_value("mirror_deviation_threshold_percent", errors)
        return errors

    async def prepare(self) -> None:
        await super().prepare()

    async def unload(self) -> None:
        await super().unload()

    # --- just-in-time config accessors (never cached) ---

    def _saved_dir(self) -> str:
        return self.retrieve_custom_property_value("satisfactory_saved_dir", []) or ""

    def _docs_file(self) -> str:
        return self.retrieve_custom_property_value("satisfactory_docs_file", []) or ""

    def _install_dir(self) -> str:
        return self.retrieve_custom_property_value("satisfactory_install_dir", []) or ""

    def _docs_locale(self) -> str:
        return (
            self.retrieve_custom_property_value("satisfactory_docs_locale", [])
            or "en-US"
        )

    def _parser_runtime_dir(self) -> str:
        return (
            self.retrieve_custom_property_value("satisfactory_parser_runtime_dir", [])
            or ""
        )

    def _max_response_items(self) -> int:
        value = self.retrieve_custom_property_value("max_response_items", [])
        return _coerce_int(value, default=12, minimum=1)

    def _mirror_trend_window_saves(self) -> int:
        value = self.retrieve_custom_property_value("mirror_trend_window_saves", [])
        return _coerce_int(value, default=5, minimum=1)

    def _mirror_zero_streak_saves(self) -> int:
        value = self.retrieve_custom_property_value("mirror_zero_streak_saves", [])
        return _coerce_int(value, default=3, minimum=1)

    def _mirror_deviation_threshold(self) -> float:
        value = self.retrieve_custom_property_value(
            "mirror_deviation_threshold_percent", []
        )
        try:
            percent = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            percent = 25.0
        return max(0.0, min(percent, 100.0)) / 100.0

    def _allow_plan_writes(self) -> bool:
        value = self.retrieve_custom_property_value("allow_plan_writes", [])
        return _coerce_bool(value, default=True)

    # --- helpers ---

    def _resolve(self) -> ActiveSaveResult:
        return resolve_active_save(configured_dir=self._saved_dir())

    def _workspace_for(self, result: ActiveSaveResult) -> SaveWorkspace:
        # Identity is based on stable logical evidence (Saved root + save name),
        # never the volatile .sav path, so the same save resolves to the same
        # workspace whether or not the file is currently found on disk.
        base = Path(self.get_generated_files_dir())
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
                "No Satisfactory log folder found. Configure the Satisfactory "
                "Saved directory in skill settings, or start the game once."
            )
        if result.status == STATUS_NO_ACTIVE_SAVE:
            return (
                "Found the newest Satisfactory log, but no active save was "
                "detected. Load a save in Satisfactory first."
            )
        return None

    def _diag(self, message: str) -> None:
        self.printr.print(message, color=LogType.SYSTEM, server_only=True)

    def _lookup_lines(self, query: str) -> list[str]:
        """Return bounded Docs lookup lines for ``query`` (items then recipes).

        Capped at 5 items and 5 recipes (``satisfactory_dataset``'s own
        clamp). Any failure to reach or read the Docs catalog degrades to
        one short "unavailable" line rather than raising.
        """
        discovery = discover_docs(
            configured_file=self._docs_file(),
            configured_install_dir=self._install_dir(),
            locale=self._docs_locale(),
        )
        if discovery.docs_path is None:
            return [f"Lookup '{query}': unavailable (Docs file not found)."]
        try:
            catalog, _ = get_docs_catalog(discovery.docs_path)
        except (OSError, ValueError) as exc:
            self._diag(f"[Satisfactory] lookup failed to load Docs: {exc}")
            return [f"Lookup '{query}': unavailable (could not load Docs file)."]
        return build_lookup_lines(catalog, query)

    def _plan_status_lines(self, ws: SaveWorkspace) -> list[str]:
        """Return up to 5 compact lines describing persisted master-plan stages.

        Sourced via ``SaveStore.list_stage_revisions`` and
        ``load_stage_plan`` for plan "master". Reads only; never creates a
        store. Absent store, absent master plan, or no stage revisions
        yet all degrade to no section rather than an error.
        """
        return build_plan_status_lines(ws.dir / "planning.sqlite3")

    @tool(
        description=(
            "Get compact Satisfactory planning context for the active save. "
            "WHEN TO USE: user asks about current factory plans, todos, notes, "
            "production goals, which save is active, wants a bounded lookup "
            "of an item or recipe name from the game's Docs data, or asks "
            "where something is / wants it shown on a map."
        ),
        wait_response=True,
    )
    async def get_satisfactory_context(
        self, focus: str = "", lookup: str = "", locate: str = ""
    ) -> str:
        """Return the active save identity and a compact planning summary.

        Args:
            focus: Optional keyword to filter records (matched across title,
                details, inputs, and outputs) before they are capped.
            lookup: Optional item or recipe name to look up in the bundled
                Docs catalog (capped at 5 items and 5 recipes).
            locate: Optional item, recipe, or resource name to find on the
                save's factory mirror (from the last audit). Returns
                coordinates for up to 5 matches and renders a schematic map
                PNG for the top match; absent mirror explains how to build
                one.
        """
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
        if locate.strip():
            header_lines.extend(build_locate_lines(ws.dir, locate.strip()))
        header_lines.extend(self._plan_status_lines(ws))

        # format_context de-duplicates blocked flows and enforces a hard global
        # character budget so the return stays under the low-token target; the
        # lookup and plan-status lines above are folded into header_lines so
        # they are accounted for by that same budget, not appended around it.
        return format_context(header_lines, summary)

    @tool(
        description=(
            "Update Satisfactory planning for the active save: notes, todos, "
            "production goals, and production flows (lines with item inputs, "
            "outputs, rates, recipes, machines). WHEN TO USE: user asks to "
            "remember, add, update, complete, or remove a current-save todo, "
            "note, goal, or factory production line."
        ),
        wait_response=True,
    )
    async def update_satisfactory_plan(
        self,
        action: Literal[
            "add_note",
            "add_todo",
            "complete_todo",
            "add_goal",
            "add_flow",
            "update_flow",
            "archive_item",
        ],
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
        if not self._allow_plan_writes():
            return "Plan writes are disabled in skill settings."

        result = self._resolve()
        message = self._status_message(result)
        if message:
            return message

        ws = self._workspace_for(result)
        now = datetime.now()
        inputs, outputs = _normalize_rate_aliases(inputs, outputs, kwargs)

        if action in ("complete_todo", "archive_item"):
            if not item_id:
                return f"An item_id is required for {action}."
            kind, target_error = _resolve_status_target(action, item_id)
            if target_error:
                return target_error
            new_status = STATUS_DONE if action == "complete_todo" else STATUS_ARCHIVED
            if not ws.set_status_for_kind(kind, item_id, new_status, now):
                return f"No item found with id '{item_id}'."
            ws.add_item("changes", f"{action}: {item_id}", "", now)
            return f"Marked {item_id} as {new_status}."

        flow_status = status.strip().lower() if status.strip() else None
        if flow_status and flow_status not in FLOW_STATUSES:
            return f"Invalid status '{status}'. Use one of: {', '.join(FLOW_STATUSES)}."

        if action == "update_flow":
            if not item_id:
                return "An item_id is required for update_flow."
            try:
                to_clear = parse_clear_fields(clear_fields)
            except ValueError as exc:
                return str(exc)
            found = ws.update_flow(
                item_id,
                now,
                title=title or None,
                details=details or None,
                inputs=_parse_rates(inputs) if inputs.strip() else None,
                outputs=_parse_rates(outputs) if outputs.strip() else None,
                status=flow_status,
                area=area or None,
                recipe=recipe or None,
                machines=machines or None,
                constraints=constraints or None,
                clear_fields=to_clear,
            )
            if not found:
                return f"No production flow found with id '{item_id}'."
            ws.add_item("changes", f"update_flow: {item_id}", "", now)
            return f"Updated flow {item_id}."

        if not title.strip():
            return f"A title is required for {action}."

        # Full title is stored; only the echoed acknowledgement is clipped.
        title_disp = clip(title.strip(), _ACK_TITLE_MAX)

        if action == "add_flow":
            new_id = ws.add_item(
                "flows",
                title,
                details,
                now,
                extra={
                    "inputs": _parse_rates(inputs),
                    "outputs": _parse_rates(outputs),
                    "area": area.strip(),
                    "recipe": recipe.strip(),
                    "machines": machines.strip(),
                    "constraints": constraints.strip(),
                },
                status=flow_status or "planned",
            )
            ws.add_item("changes", f"add_flow: {title.strip()}", "", now)
            return f"Added production flow '{title_disp}' ({new_id}) to {result.save_name}."

        kind = {"add_note": "notes", "add_todo": "todos", "add_goal": "goals"}[action]
        new_id = ws.add_item(kind, title, details, now)
        ws.add_item("changes", f"{action}: {title.strip()}", "", now)
        return f"Added {kind[:-1]} '{title_disp}' ({new_id}) to {result.save_name}."

    def _run_factory_audit(
        self, result: ActiveSaveResult, ws: SaveWorkspace, phase: int = 0
    ) -> str:
        """Locate the Docs file, then hand off to the pure audit pipeline.

        Reachable via ``calculate_satisfactory_plan(mode="audit")``. The caller
        has already resolved the active save, confirmed its ``.sav`` file
        exists, and validated ``phase`` (0 or 1-5).
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

    @tool(
        description=(
            "Plan or audit a Satisfactory factory for the active save. "
            "mode='plan' computes a Project Assembly phase stage plan "
            "(demand, recipes, machines, power) and persists it by default; "
            "mode='audit' mirrors the current factory from the save. "
            "scope='stage' plans one phase (default); scope='master' plans "
            "all five phases. WHEN TO USE: user asks to plan production for "
            "a phase, size machines/power, plan the whole build order, or "
            "audit the current factory. pin_recipes/ban_recipes force or "
            "exclude specific recipes. include_construction=True adds a "
            "construction bill and build order for scope=stage. "
            "create_build_todos=True files a build todo per task, requiring "
            "persist and plan writes allowed. pace_scenarios (1-4 "
            "semicolon-separated paces) returns an unpersisted comparison, "
            "overriding persist."
        ),
        wait_response=True,
    )
    async def calculate_satisfactory_plan(
        self,
        phase: int = 0,
        pace_multiplier: float = 1.0,
        include_alternates: str = "",
        persist: bool = True,
        mode: Literal["plan", "audit"] = "plan",
        scope: Literal["stage", "master"] = "stage",
        pin_recipes: str = "",
        ban_recipes: str = "",
        include_construction: bool = False,
        create_build_todos: bool = False,
        pace_scenarios: str = "",
    ) -> str:
        """Compute (and usually persist) a Project Assembly stage plan, or audit the save.

        Args:
            phase: Project Assembly phase number (1-5) for scope="stage"
                (the default); must be omitted or 0 for scope="master"
                (which plans every phase at once). For mode="audit",
                optional: 0 (default) runs the classic factory mirror only,
                1-5 additionally compares the mirror against that phase's
                latest stored master-plan revision when one exists.
            pace_multiplier: Window-hours multiplier in [1.0, 3.0]. Ignored
                for mode="audit".
            include_alternates: Semicolon-separated alternate recipe names to
                allow beyond the default gate, e.g. "Alternate: Steel Rod".
                Ignored for mode="audit".
            persist: When True (default), save the computed stage(s) as new
                revision(s) of the save's master plan and export artifacts.
                Ignored for mode="audit".
            mode: "plan" to compute a stage plan (default), or "audit" to
                mirror the current factory from the save.
            scope: "stage" to plan a single phase (default), or "master" to
                build and persist all five Project Assembly phases at once.
                Ignored for mode="audit".
            pin_recipes: Semicolon-separated recipe names to force; each
                must already be reachable via the default gate or
                include_alternates. Ignored for mode="audit".
            ban_recipes: Semicolon-separated recipe names to exclude, even
                if otherwise unlocked. Ignored for mode="audit".
            include_construction: When True, append a construction bill and
                dependency-ordered build sequence to the response and write
                a third artifact. Defaults to False (response unchanged).
                Ignored for mode="audit" and scope="master".
            create_build_todos: When True, add a journal todo per build task
                (capped at 20). Only meaningful with include_construction=True,
                persist=True, and plan writes allowed in skill settings;
                otherwise a no-op (or a refusal line when plan writes are
                disabled). Ignored for mode="audit" and scope="master".
            pace_scenarios: Semicolon-separated pace multipliers (1-4 distinct
                values, each in [1.0, 3.0]), e.g. "1.0;2.0;3.0". When set,
                computes an unpersisted side-by-side comparison across those
                paces instead of a normal plan; overrides persist (nothing is
                ever saved) and never touches the store or workspace. Works
                with scope="stage" (uses phase) or scope="master". Ignored
                for mode="audit".
        """
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
                    f"mode='audit' accepts phase 0 (classic audit) or 1-5 "
                    f"(audit with plan comparison), got {phase}."
                )
            if result.save_file is None:
                note = _save_file_note(result)
                return (
                    "Active save was detected, but the physical .sav file is not "
                    f"available for parsing. {note or ''}"
                ).strip()
            ws = self._workspace_for(result)
            return self._run_factory_audit(result, ws, phase)

        if scope == "master" and phase != 0:
            return (
                f"scope='master' plans every phase; phase must be omitted or 0, got {phase}."
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
            return f"Could not load the Satisfactory Docs file: {clip(str(exc), 240)}"

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

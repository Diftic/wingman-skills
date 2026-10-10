"""Pure pipeline logic for the SatisfactoryAssistant skill.

Split out of ``main.py`` (SSP-MNT-W01) to keep the Wingman-coupled Skill class
thin. Nothing here imports ``api.*``, ``skills.skill_base``, or ``wingmen.*``;
every function takes explicit inputs and is unit-testable without a running
Wingman app. Imports its sibling pure modules directly, since it is only ever
imported after ``main.py``'s sys.path bootstrap has run (or via the tests'
``conftest.py`` sys.path setup).
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from satisfactory_actuals import compare_actuals
from satisfactory_construction import build_construction_plan
from satisfactory_dataset import DatasetInfo, get_docs_catalog, lookup_items, lookup_recipes
from satisfactory_docs import DocsCatalog, normalize_class_name
from satisfactory_extraction import DEFAULT_MINER_MARK, plan_extraction
from satisfactory_logistics import check_logistics
from satisfactory_map import LocationHit, find_locations, render_map
from satisfactory_master_plan import build_master_plan
from satisfactory_mirror import (
    TrendConfig,
    build_factory_mirror,
    format_factory_audit,
    store_mirror_artifacts,
)
from satisfactory_models import ActiveSaveResult
from satisfactory_plan_models import (
    EXTERNAL_DEMAND_NODE_ID,
    RAW_IMPORT_NODE_ID,
    BuildTask,
    DataProvenance,
    Diagnostic,
    ItemFlow,
    PowerPlan,
    RecipePolicy,
    ResourceSource,
    StagePlan,
)
from satisfactory_progression import (
    ProjectAssemblyData,
    build_capability_snapshot,
    derive_phase_demand,
    load_project_assembly_phases,
    validate_phases_against_docs,
)
from satisfactory_reports import (
    export_construction_artifact,
    export_master_summary,
    export_stage_artifacts,
    format_actuals_section,
    format_master_response,
    format_plan_response,
    format_scenarios_response,
)
from satisfactory_save_parser import SaveParserError, copied_save, extract_save_snapshot
from satisfactory_scenarios import compare_pace_scenarios
from satisfactory_solver import RawImport, schedule_machines, solve_stage
from satisfactory_store import SaveStore
from satisfactory_workspace import SaveWorkspace, kind_for_id, slugify


def _parse_rates(raw: str) -> list[str]:
    """Split a semicolon-separated material-rate string into a clean list."""
    return [part.strip() for part in raw.split(";") if part.strip()]


def _append_rate_alias(materials: str, rate: Any) -> str:
    """Fold common LLM-invented rate aliases into the existing material field."""
    rate_text = str(rate).strip() if rate is not None else ""
    materials = materials.strip()
    if not rate_text:
        return materials
    if not materials:
        return rate_text
    if rate_text.lower() in materials.lower():
        return materials
    return f"{materials} {rate_text}"


def _normalize_rate_aliases(
    inputs: str, outputs: str, kwargs: dict[str, Any]
) -> tuple[str, str]:
    for key in ("input_rate", "input_rates"):
        inputs = _append_rate_alias(inputs, kwargs.get(key))
    for key in ("output_rate", "output_rates"):
        outputs = _append_rate_alias(outputs, kwargs.get(key))
    return inputs, outputs


_MAX_SOLVE_FAILURE_DIAGNOSTICS = 5
_MAX_PLAN_STATUS_LINES = 5
_MAX_CONSTRUCTION_TASK_LINES = 10
_MAX_CONSTRUCTION_BOM_LINES = 10
_MAX_BUILD_TODOS = 20
_PLAN_WRITES_DISABLED_MESSAGE = "Plan writes are disabled in skill settings."


def _construction_task_line(task: BuildTask) -> str:
    depends_on = ", ".join(task.depends_on) if task.depends_on else "(none)"
    return (
        f"  - [{task.order_index}] {task.node_id}: {task.building_class} "
        f"x{task.count} (depends on: {depends_on})"
    )


def _construction_bom_line(entry: tuple[str, float]) -> str:
    item_class, quantity = entry
    return f"  - {item_class}: {quantity:.3f}"


def format_construction_section(
    tasks: tuple[BuildTask, ...],
    bom: tuple[tuple[str, float], ...],
    diagnostics: tuple[Diagnostic, ...],
    artifact_path: str | None,
) -> str:
    """Render the opt-in "Construction:" section appended to a stage plan response.

    Bounded the same way the rest of this module's compact summaries are:
    at most 10 commissioning-order lines and 10 bill-of-materials lines,
    each with a trailing "+N more" count when truncated. The full task
    list and bill of materials always live in the construction artifact,
    never only in this section.
    """
    lines = ["", "Construction:", f"Tasks ({len(tasks)}, extractors first):"]
    shown_tasks = tasks[:_MAX_CONSTRUCTION_TASK_LINES]
    lines.extend(_construction_task_line(task) for task in shown_tasks)
    if len(shown_tasks) < len(tasks):
        lines.append(f"  +{len(tasks) - len(shown_tasks)} more")

    lines.append(f"Bill of materials ({len(bom)} items):")
    shown_bom = bom[:_MAX_CONSTRUCTION_BOM_LINES]
    lines.extend(_construction_bom_line(entry) for entry in shown_bom)
    if len(shown_bom) < len(bom):
        lines.append(f"  +{len(bom) - len(shown_bom)} more")

    if diagnostics:
        lines.append(f"Construction diagnostics: {len(diagnostics)}")

    if artifact_path:
        lines.append(f"Construction artifact: {artifact_path}")

    return "\n".join(lines)


def _building_display_name(catalog: DocsCatalog, building_class: str) -> str:
    """Resolve a building's display name, falling back to its raw class name."""
    building = catalog.building(building_class)
    if building is not None and building.display_name:
        return building.display_name
    return building_class


def create_build_task_todos(
    workspace: SaveWorkspace,
    tasks: tuple[BuildTask, ...],
    stage: StagePlan,
    catalog: DocsCatalog,
    now: datetime,
) -> tuple[int, int]:
    """Add a journal todo for each of the first ``_MAX_BUILD_TODOS`` build tasks.

    Every todo's title names the count and building, and its details name
    the task id and the stage's phase/revision so it can be traced back to
    the plan node it came from. Returns ``(created, overflow)``: the number
    of todos actually added, and how many remaining tasks beyond the cap
    were skipped.

    Calling this again for the same tasks (for example, re-running the same
    plan calculation with ``create_build_todos=True``) creates duplicate
    todos: deduplication is journal-domain work, out of scope here.
    """
    capped = tasks[:_MAX_BUILD_TODOS]
    for task in capped:
        building_name = _building_display_name(catalog, task.building_class)
        title = f"Build {task.count} x {building_name} ({task.node_id})"
        details = f"task_id={task.task_id}; stage phase {stage.phase} revision {stage.revision}"
        workspace.add_item("todos", title, details, now)
    return len(capped), len(tasks) - len(capped)


def _format_lookup_recipe(recipe: dict[str, Any]) -> str:
    """Render one ``lookup_recipes`` result as a single compact bullet line."""
    inputs = ", ".join(f"{name} {rate}/min" for name, rate in recipe["inputs_per_min"].items())
    outputs = ", ".join(f"{name} {rate}/min" for name, rate in recipe["outputs_per_min"].items())
    tag = " (alt)" if recipe["alternate"] else ""
    produced_in = ", ".join(recipe["produced_in"]) or "(unknown building)"
    return (
        f"  - {recipe['recipe']}{tag}: {inputs or '(none)'} -> {outputs or '(none)'} "
        f"in {produced_in}"
    )


def _format_solve_failure(phase: int, status: str, diagnostics: tuple[str, ...]) -> str:
    """Render a compact, bounded message for a non-optimal solve; nothing persists."""
    lines = [f"Phase {phase} plan: solver status '{status}'."]
    shown = diagnostics[:_MAX_SOLVE_FAILURE_DIAGNOSTICS]
    if shown:
        lines.append("Diagnostics:")
        lines.extend(f"- {diagnostic}" for diagnostic in shown)
        remaining = len(diagnostics) - len(shown)
        if remaining > 0:
            lines.append(f"+{remaining} more")
    lines.append("Nothing persisted.")
    return "\n".join(lines)


def format_docs_missing_message(searched: tuple[str, ...]) -> str:
    """Render the standard "Docs file not found" refusal with a bounded search hint."""
    searched_hint = "; ".join(searched[:6])
    return (
        "Satisfactory Docs file not found. Configure 'Satisfactory Docs "
        "File' or 'Satisfactory Install Directory' in skill settings. "
        f"Searched: {searched_hint}"
    )


def build_lookup_lines(catalog: DocsCatalog, query: str) -> list[str]:
    """Assemble bounded Docs lookup lines for ``query`` from an already-loaded catalog.

    Capped at 5 items and 5 recipes (``satisfactory_dataset``'s own clamp).
    """
    items = lookup_items(catalog, query)
    recipes = lookup_recipes(catalog, query)
    if not items and not recipes:
        return [f"Lookup '{query}': no matching items or recipes."]

    lines = [f"Lookup '{query}':"]
    if items:
        lines.append("Items:")
        lines.extend(
            f"  - {item['item']} ({item['class']}, {item['form']})" for item in items
        )
    if recipes:
        lines.append("Recipes:")
        lines.extend(_format_lookup_recipe(recipe) for recipe in recipes)
    return lines


def _is_within(base: Path, target: Path) -> bool:
    """True if resolved ``target`` is inside (or equal to) resolved ``base``.

    Reimplemented locally rather than imported from ``satisfactory_reports``
    (itself a local reimplementation of ``satisfactory_workspace``'s private
    helper) since neither is exported from its module; behavior is kept
    identical, including the Windows case-insensitive fallback.
    """
    try:
        target.relative_to(base)
        return True
    except ValueError:
        if os.name != "nt":
            return False
        base_str = str(base).lower().rstrip("\\/")
        target_str = str(target).lower()
        return target_str == base_str or target_str.startswith(base_str + "\\") or target_str.startswith(
            base_str + "/"
        )


def _mirror_points(mirror: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    """Collect every machine's (x, y) world-cm location for the map's bounding box."""
    points = []
    for machine in mirror.get("machines", []) or []:
        location = machine.get("location")
        if location and location.get("x") is not None and location.get("y") is not None:
            points.append((float(location["x"]), float(location["y"])))
    return tuple(points)


def _locate_hit_line(hit: LocationHit) -> str:
    distance_m = math.hypot(hit.x, hit.y) / 100.0
    if hit.machine_count is not None:
        extra = f", {hit.machine_count} machines"
    elif hit.clock is not None:
        extra = f", clock {hit.clock * 100.0:.0f}%"
    else:
        extra = ""
    return (
        f"  - {hit.label} ({hit.kind}): x={hit.x / 100.0:.1f}m y={hit.y / 100.0:.1f}m "
        f"z={hit.z / 100.0:.1f}m, distance {distance_m:.1f}m from origin{extra}"
    )


def build_locate_lines(workspace_dir: Path, query: str) -> list[str]:
    """Assemble the "Locations:" section for ``get_satisfactory_context``'s ``locate`` param.

    Reads ``workspace_dir/mirror/latest_mirror.json`` read-only (never
    creates it); an absent or unreadable mirror degrades to one line
    pointing at the factory audit tool instead of raising. On a match,
    renders a schematic PNG for the top hit to
    ``workspace_dir/mirror/location_<slug(query)>.png`` (same containment
    idiom as ``export_stage_artifacts``) and appends its path plus a HUD
    markdown-image display hint line; a Pillow-less environment degrades
    that to a coordinates-only note instead of failing.
    """
    mirror_path = workspace_dir / "mirror" / "latest_mirror.json"
    if not mirror_path.is_file():
        return [
            f"Locations '{query}': no factory mirror yet. Run "
            "calculate_satisfactory_plan(mode='audit') first."
        ]
    try:
        mirror = json.loads(mirror_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"Locations '{query}': could not read factory mirror ({exc})."]

    hits = find_locations(mirror, query)
    if not hits:
        return [f"Locations '{query}': no matching lines or machines in the factory mirror."]

    lines = [f"Locations '{query}':"]
    lines.extend(_locate_hit_line(hit) for hit in hits)

    base = workspace_dir.resolve()
    out_path = (base / "mirror" / f"location_{slugify(query)}.png").resolve()
    if not _is_within(base, out_path):
        lines.append(f"Map artifact: refused outside workspace for {query!r}.")
        return lines

    top_hit = hits[0]
    rendered = render_map(hits, _mirror_points(mirror), out_path, highlight_index=0)
    if rendered:
        lines.append(f"Map artifact: {out_path}")
        lines.append(f"Display hint (HUD markdown image): ![{top_hit.label}]({out_path})")
    else:
        lines.append("Map artifact: unavailable (Pillow not installed); coordinates only.")
    return lines


def build_plan_status_lines(db_path: Path) -> list[str]:
    """Return up to 5 compact lines describing persisted master-plan stages.

    Sourced via ``SaveStore.list_stage_revisions`` and ``load_stage_plan`` for
    plan "master". Reads only; never creates a store. Absent store, absent
    master plan, or no stage revisions yet all degrade to no section rather
    than an error.
    """
    if not db_path.exists():
        return []
    plan_id = "master"
    store = SaveStore.open(db_path)
    try:
        if store.get_master_plan(plan_id) is None:
            return []
        try:
            phases = load_project_assembly_phases().phases
        except ValueError:
            return []

        lines: list[str] = []
        for phase_def in phases:
            if len(lines) >= _MAX_PLAN_STATUS_LINES:
                break
            revisions = store.list_stage_revisions(plan_id, phase_def.phase)
            if not revisions:
                continue
            payload = store.load_stage_plan(plan_id, phase_def.phase)
            if payload is None:
                continue
            machines = sum(
                int(node.get("machine_count", 0)) for node in payload.get("nodes", [])
            )
            power_total = payload.get("power", {}).get("total_mw", 0.0)
            lines.append(
                f"  - Phase {phase_def.phase}: revision {payload.get('revision')}, "
                f"{machines} machines, {power_total:.3f} MW"
            )
        if not lines:
            return []
        return ["Plan status (master):"] + lines
    finally:
        store.close()


def _resolve_status_target(action: str, item_id: str) -> tuple[str | None, str | None]:
    """Resolve which record kind a status action may touch, enforcing type safety.

    Returns ``(kind, None)`` when the action is allowed for ``item_id``'s kind, or
    ``(None, error_message)`` when it is not (so the caller mutates nothing):

    - ``complete_todo`` only accepts a ``todo_`` id and only touches ``todos``.
    - ``archive_item`` accepts note/todo/goal/flow ids; it rejects ``chg_``
      change-log ids (append-only audit history) and unknown prefixes.
    """
    kind = kind_for_id(item_id)
    if action == "complete_todo":
        if kind != "todos":
            return None, f"complete_todo needs a todo id (todo_...), not '{item_id}'."
        return "todos", None
    if kind is None or kind == "changes":
        return None, (
            f"archive_item needs a note, todo, goal, or flow id, not '{item_id}'."
        )
    return kind, None


def _save_file_note(result: ActiveSaveResult) -> str | None:
    """Build the optional save-file status line for the context header.

    Ambiguity (multiple profiles hold a save with this name) takes precedence
    over a plain not-found note, because "not found" would misdescribe a
    too-many-found state. The note also makes clear that planning is keyed on
    the active-log save identity only, never on a guessed ``.sav`` path. Returns
    ``None`` when a single save file resolved cleanly.
    """
    if result.save_file_ambiguity:
        return (
            f"(ambiguous save file: {result.save_file_ambiguity}; "
            "planning uses the active-log save name only)"
        )
    if not result.save_file_found:
        return "(save file not found on disk; planning still available)"
    return None


def _coerce_int(value: object, default: int, minimum: int) -> int:
    """Coerce a config value to an int, clamped to a sane minimum.

    Falls back to ``default`` when the value is missing or non-numeric, so a
    manually-edited or stringified config cannot crash the skill.
    """
    try:
        result = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return max(minimum, result)


def _coerce_bool(value: object, default: bool) -> bool:
    """Coerce a config value to a bool, parsing strings explicitly.

    Guards against ``bool("false") is True`` when the UI yields a string.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("true", "1", "yes", "on"):
            return True
        if text in ("false", "0", "no", "off", ""):
            return False
    return default


def _resolve_extraction(
    catalog: DocsCatalog, imports: tuple[RawImport, ...]
) -> tuple[
    tuple[ResourceSource, ...], tuple[tuple[str, float], ...], list[Diagnostic], tuple[str, ...]
]:
    """Run ``plan_extraction`` and translate its outputs into adapter-level pieces.

    Shared by both assembly points (the single-stage calculator and the
    master-plan builder) so each folds an identical extraction result into
    its own construction path: ``sources`` ready to drop into a
    ``StagePlan``, ``power_additions`` to merge via
    :func:`_merge_extraction_power`, unresolved-extractor diagnostics
    already wrapped as :class:`Diagnostic`, and the purity/miner-mark
    assumption strings to append.
    """
    sources, power_additions, extraction_diagnostics = plan_extraction(catalog, imports)
    diagnostics = [
        Diagnostic(
            severity="warning", code="unknown_extractor", message=diag, subject="extraction"
        )
        for diag in extraction_diagnostics
    ]
    assumptions = (
        "raw-resource extraction assumes normal purity (1.0x) for every node",
        f"raw-resource extraction uses miner_mark='{DEFAULT_MINER_MARK}' for solid "
        "resources without per-node data",
    )
    return sources, power_additions, diagnostics, assumptions


def _merge_extraction_power(
    power: PowerPlan, additions: tuple[tuple[str, float], ...]
) -> PowerPlan:
    """Fold extraction's per-building power additions into an existing PowerPlan.

    Re-aggregates ``by_building`` from scratch (never sums an addition
    twice) so a building class that happens to appear in both the recipe
    power and the extraction power additions is combined into one entry,
    same as ``total_mw`` is a fresh sum rather than an increment.
    """
    by_building: dict[str, float] = dict(power.by_building)
    for building_class, mw in additions:
        by_building[building_class] = by_building.get(building_class, 0.0) + mw
    return PowerPlan(
        total_mw=round(sum(by_building.values()), 3),
        by_building=tuple(sorted(by_building.items(), key=lambda entry: (-entry[1], entry[0]))),
    )


def _apply_stage_extraction(catalog: DocsCatalog, stage: StagePlan) -> StagePlan:
    """Fold real extractor machines/power into an already-built master-plan stage.

    ``build_master_plan`` (out of this packet's edit scope) still stamps
    every stage with blank ``ResourceSource.extractor_class``/``count`` and
    the now-inaccurate "extractors not modeled" assumption. This
    reconstructs each source's :class:`RawImport` (``display_name`` is
    unused by ``plan_extraction``, carried only for interface symmetry with
    ``solve_stage``'s own output) and replaces the stage's sources, power,
    diagnostics, and assumptions with the resolved extraction result,
    dropping the stale assumption string.
    """
    imports = tuple(
        RawImport(
            item_class=source.item_class,
            display_name=catalog.item_display_name(source.item_class),
            rate_per_min=source.rate_per_min,
        )
        for source in stage.sources
    )
    sources, power_additions, diagnostics, assumptions = _resolve_extraction(catalog, imports)
    return replace(
        stage,
        sources=sources,
        power=_merge_extraction_power(stage.power, power_additions),
        diagnostics=stage.diagnostics + tuple(diagnostics),
        assumptions=(
            tuple(
                assumption
                for assumption in stage.assumptions
                if assumption != "extractors not modeled"
            )
            + assumptions
        ),
    )


def _apply_stage_logistics(
    catalog: DocsCatalog,
    phase_data: ProjectAssemblyData,
    alternates: tuple[str, ...],
    stage: StagePlan,
) -> StagePlan:
    """Fold belt/pipe capacity and byproduct-surplus diagnostics into a stage.

    ``build_master_plan`` (out of this packet's edit scope) does not run
    logistics checks itself, so this recomputes the same capability
    snapshot it built internally for the stage's phase (deterministic from
    ``phase_data``/``stage.phase``/``alternates``) and applies
    :func:`check_logistics` after the fact, mirroring how
    :func:`_apply_stage_extraction` patches extraction data onto an
    already-built stage.
    """
    snapshot = build_capability_snapshot(
        catalog, phase_data, stage.phase, include_alternates=alternates
    )
    demands = tuple((item_class, rate) for item_class, _quantity, rate in stage.demands)
    logistics_diagnostics, logistics_assumptions = check_logistics(
        catalog, snapshot, stage.nodes, stage.sources, demands
    )
    return replace(
        stage,
        diagnostics=stage.diagnostics + logistics_diagnostics,
        assumptions=stage.assumptions + logistics_assumptions,
    )


def _append_actuals_comparison(
    response: str,
    workspace_dir: Path,
    mirror: dict[str, Any],
    phase: int,
) -> str:
    """Append a bounded "Plan vs actual" section to an audit response, if applicable.

    A no-op (returns ``response`` unchanged) whenever ``phase`` is 0 (the
    tool's classic-audit default) or outside 1-5, which is exactly what
    every caller passed before this packet, keeping mode="audit" byte-
    identical to prior behavior unless a caller explicitly opts in with a
    Project Assembly phase. When ``phase`` is 1-5 but the save's planning
    store has no persisted "master" plan revision for it, a single
    explanatory line is appended instead of the comparison section.
    """
    if phase < 1 or phase > 5:
        return response

    db_path = workspace_dir / "planning.sqlite3"
    payload: dict[str, Any] | None = None
    if db_path.exists():
        store = SaveStore.open(db_path)
        try:
            payload = store.load_stage_plan("master", phase)
        finally:
            store.close()

    if payload is None:
        return (
            f"{response}\n\nPlan vs actual (phase {phase}): "
            f"no stored plan found for phase {phase}."
        )

    save_name = str((mirror.get("source") or {}).get("saveName") or "")
    comparison = compare_actuals(mirror.get("machines", []), payload, save_name=save_name)
    return f"{response}\n\n{format_actuals_section(comparison)}"


def run_factory_audit_pipeline(
    save_file: Path,
    workspace_dir: Path,
    docs_path: Path,
    parser_runtime_dir: str,
    trend_config: TrendConfig,
    diag: Callable[[str], None] | None = None,
    phase: int = 0,
) -> str:
    """Parse the active save and return a compact factory mirror summary.

    Moved out of the former standalone ``audit_satisfactory_factory`` tool
    (same behavior, same messages, same artifacts); reachable now via
    ``calculate_satisfactory_plan(mode="audit")``. The caller has already
    resolved the active save, confirmed its ``.sav`` file exists, and located
    the Docs file.

    ``phase`` defaults to 0 (classic audit, no comparison); every current
    caller omits it, so the response is unaffected by this packet's addition.
    Passing a Project Assembly phase (1-5) appends a bounded plan-versus-
    actual section via :func:`_append_actuals_comparison`.
    """
    try:
        # Parse a private copy: the game can autosave-write the live .sav
        # file while the Node subprocess is still reading it.
        with copied_save(save_file, workspace_dir / "mirror") as save_copy:
            snapshot = extract_save_snapshot(
                save_copy,
                parser_runtime_dir=parser_runtime_dir,
                summary_only=False,
            )
        src = snapshot.get("source")
        if isinstance(src, dict):
            src["saveName"] = save_file.stem
            src["fileName"] = save_file.name
        catalog, dataset_info = get_docs_catalog(docs_path)
        if dataset_info.parse_ms is not None and diag is not None:
            diag(
                f"[Satisfactory] docs catalog parsed in "
                f"{dataset_info.parse_ms:.1f} ms "
                f"({dataset_info.item_count} items, "
                f"{dataset_info.recipe_count} recipes)"
            )
        mirror = build_factory_mirror(snapshot, catalog)
        artifact_info = store_mirror_artifacts(workspace_dir, snapshot, mirror, trend_config)
    except (OSError, SaveParserError, ValueError) as exc:
        if diag is not None:
            diag(f"[Satisfactory] factory audit failed: {exc}")
        return f"Factory audit failed: {exc}"

    response = format_factory_audit(mirror, artifact_info)
    return _append_actuals_comparison(response, workspace_dir, mirror, phase)


def run_plan_calculation(
    result: ActiveSaveResult,
    get_workspace_dir: Callable[[], Path],
    catalog: DocsCatalog,
    dataset_info: DatasetInfo,
    phase_data: ProjectAssemblyData,
    phase: int,
    pace_multiplier: float,
    include_alternates: str,
    persist: bool,
    pin_recipes: str = "",
    ban_recipes: str = "",
    include_construction: bool = False,
    create_build_todos: bool = False,
    get_workspace: Callable[[], SaveWorkspace] | None = None,
    get_allow_plan_writes: Callable[[], bool] = lambda: True,
) -> str:
    """Compute (and usually persist) a Project Assembly stage plan.

    ``get_workspace_dir`` is only called when ``persist`` is True, matching
    the pre-split behavior of never creating/touching the save's workspace
    directory for an unpersisted plan. ``include_construction`` is opt-in
    (default False keeps the response byte-unchanged): when True, the
    construction bill and commissioning order are computed from the
    already-built ``stage`` (never folded into its persisted diagnostics or
    assumptions, so the stage's own artifacts stay identical either way), a
    third artifact is written alongside the stage's own exports when
    ``persist`` is True, and a bounded "Construction:" section is appended
    to the response.

    ``create_build_todos`` is only meaningful when ``include_construction``
    is True, ``persist`` is True, and ``get_allow_plan_writes()`` is True;
    it is silently a no-op otherwise, except that a disabled
    ``get_allow_plan_writes()`` appends the standard plan-writes-disabled
    refusal line so the caller knows why nothing was created. When every
    condition holds, ``get_workspace`` (only ever called in that case) is
    used to add one journal todo per build task (capped, with a "+N more"
    note beyond the cap) and the response gains a "Created N build todos."
    line.
    """
    phase_diagnostics = validate_phases_against_docs(phase_data, catalog)
    current_phase_missing = [
        diag for diag in phase_diagnostics if diag.startswith(f"Phase {phase} (")
    ]
    if current_phase_missing:
        return (
            f"Cannot plan phase {phase}: required item(s) are missing from "
            "the Docs catalog.\n"
            + "\n".join(f"- {diag}" for diag in current_phase_missing)
        )
    other_diagnostics = [
        diag for diag in phase_diagnostics if diag not in current_phase_missing
    ]

    try:
        demand_set = derive_phase_demand(phase_data, phase, pace_multiplier)
    except ValueError as exc:
        return str(exc)

    alternates = tuple(_parse_rates(include_alternates))
    snapshot = build_capability_snapshot(
        catalog, phase_data, phase, include_alternates=alternates
    )

    pinned = frozenset(
        normalize_class_name(entry) for entry in _parse_rates(pin_recipes)
    )
    banned = frozenset(
        normalize_class_name(entry) for entry in _parse_rates(ban_recipes)
    )

    demands = tuple(
        (demand.item_class, demand.required_rate_per_minute)
        for demand in demand_set.demands
    )
    solve_result = solve_stage(
        catalog, snapshot.allowed_recipes, demands, pinned=pinned, banned=banned
    )
    if solve_result.status != "optimal":
        return _format_solve_failure(phase, solve_result.status, solve_result.diagnostics)

    nodes, power, schedule_diagnostics = schedule_machines(catalog, solve_result)

    diagnostics: list[Diagnostic] = [
        Diagnostic(
            severity="warning",
            code="phase_data_mismatch",
            message=diag,
            subject="docs_catalog",
        )
        for diag in other_diagnostics
    ]
    diagnostics.extend(
        Diagnostic(
            severity="warning", code="unpowered_building", message=diag, subject="schedule"
        )
        for diag in schedule_diagnostics
    )
    diagnostics.extend(
        Diagnostic(severity="warning", code="solver_residual", message=diag, subject="solver")
        for diag in solve_result.diagnostics
    )

    sources, extraction_power_additions, extraction_diagnostics, extraction_assumptions = (
        _resolve_extraction(catalog, solve_result.imports)
    )
    diagnostics.extend(extraction_diagnostics)
    power = _merge_extraction_power(power, extraction_power_additions)

    logistics_diagnostics, logistics_assumptions = check_logistics(
        catalog, snapshot, nodes, sources, demands
    )
    diagnostics.extend(logistics_diagnostics)

    flows = tuple(
        ItemFlow(
            item_class=demand.item_class,
            rate_per_min=demand.required_rate_per_minute,
            source_id="",
            dest_id=EXTERNAL_DEMAND_NODE_ID,
        )
        for demand in demand_set.demands
    ) + tuple(
        ItemFlow(
            item_class=imported.item_class,
            rate_per_min=imported.rate_per_min,
            source_id=RAW_IMPORT_NODE_ID,
            dest_id="",
        )
        for imported in solve_result.imports
    )

    now = datetime.now()
    provenance = DataProvenance(
        source=(
            f"Docs catalog: {dataset_info.docs_path}; "
            "Project Assembly phase data: bundled"
        ),
        retrieved=dataset_info.loaded_at,
        note=(
            f"parsed in {dataset_info.parse_ms:.1f} ms"
            if dataset_info.parse_ms is not None
            else "reused memoized Docs parse"
        ),
    )

    stage = StagePlan(
        phase=phase,
        window_hours=demand_set.window_hours,
        pace_multiplier=pace_multiplier,
        demands=tuple(
            (demand.item_class, demand.quantity, demand.required_rate_per_minute)
            for demand in demand_set.demands
        ),
        nodes=nodes,
        sources=sources,
        flows=flows,
        power=power,
        recipe_policy=RecipePolicy(
            mode="standard",
            pinned=tuple(sorted(pinned)),
            banned=tuple(sorted(banned)),
            allowed_alternates=alternates,
        ),
        diagnostics=tuple(diagnostics),
        assumptions=(
            ("clock 1.0 baseline",) + extraction_assumptions + logistics_assumptions
        ),
        provenance=provenance,
        solver_run_id=None,
        revision=0,
        created_at=now.isoformat(),
    )

    artifact_paths: dict[str, str] | None = None
    if persist:
        workspace_dir = get_workspace_dir()
        plan_id = "master"
        store = SaveStore.open(workspace_dir / "planning.sqlite3")
        try:
            store.upsert_master_plan(
                {
                    "plan_id": plan_id,
                    "name": result.save_name,
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                }
            )
            revision = store.next_stage_revision(plan_id, phase)
            utcstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            run_id = f"run_{phase}_{revision}_{utcstamp}"
            stage = replace(stage, revision=revision, solver_run_id=run_id)
            store.save_stage_plan(plan_id, stage.to_payload(), phase, now, revision=revision)
            store.record_solver_run(
                run_id,
                plan_id,
                phase,
                "optimal",
                {
                    "runs": [
                        {
                            "recipe_class": run.recipe_class,
                            "display_name": run.display_name,
                            "machines_exact": run.machines_exact,
                            "building_class": run.building_class,
                        }
                        for run in solve_result.runs
                    ],
                    "imports": [
                        {
                            "item_class": imported.item_class,
                            "display_name": imported.display_name,
                            "rate_per_min": imported.rate_per_min,
                        }
                        for imported in solve_result.imports
                    ],
                    "diagnostics": list(solve_result.diagnostics),
                },
                now,
            )
        finally:
            store.close()
        artifact_paths = export_stage_artifacts(workspace_dir, plan_id, stage)

    # Display names for demand items come from the phase demand set;
    # raw-import classes are not part of that set, so those fall back to
    # the Docs catalog (which itself falls back to the class name).
    display_names: dict[str, str] = {
        normalize_class_name(demand.item_class): demand.display_name
        for demand in demand_set.demands
    }
    for imported in solve_result.imports:
        key = normalize_class_name(imported.item_class)
        display_names.setdefault(key, catalog.item_display_name(imported.item_class))

    response = format_plan_response(stage, artifact_paths, display_names=display_names)

    if include_construction:
        tasks, stage_bom, construction_diagnostics, construction_assumptions = (
            build_construction_plan(catalog, stage)
        )
        construction_artifact_path: str | None = None
        if persist:
            construction_artifact_path = export_construction_artifact(
                catalog,
                workspace_dir,
                plan_id,
                stage,
                tasks,
                stage_bom,
                construction_diagnostics,
                construction_assumptions,
            )
        response += format_construction_section(
            tasks, stage_bom, construction_diagnostics, construction_artifact_path
        )

        if create_build_todos:
            if not get_allow_plan_writes():
                response += f"\n{_PLAN_WRITES_DISABLED_MESSAGE}"
            elif persist and get_workspace is not None:
                created, overflow = create_build_task_todos(
                    get_workspace(), tasks, stage, catalog, now
                )
                if created:
                    overflow_note = f" (+{overflow} more)" if overflow else ""
                    response += f"\nCreated {created} build todos.{overflow_note}"

    return response


def run_master_calculation(
    result: ActiveSaveResult,
    get_workspace_dir: Callable[[], Path],
    catalog: DocsCatalog,
    dataset_info: DatasetInfo,
    phase_data: ProjectAssemblyData,
    pace_multiplier: float,
    include_alternates: str,
    persist: bool,
    pin_recipes: str = "",
    ban_recipes: str = "",
) -> str:
    """Compute (and usually persist) the full five-stage Project Assembly master plan.

    Mirrors ``run_plan_calculation``'s dependency style, but there is no
    single ``phase``: every phase in ``phase_data.phases`` is solved via
    ``build_master_plan``. ``get_workspace_dir`` is only called when
    ``persist`` is True and the build reached status ``"complete"``,
    matching the never-touch-the-workspace-when-unpersisted contract used
    elsewhere in this module. A ``stopped_at_phase_N`` build persists
    nothing, even for the phases that solved before the failure, so a
    master-plan revision always represents every phase or none of them.
    """
    alternates = tuple(_parse_rates(include_alternates))
    pinned = tuple(sorted(normalize_class_name(entry) for entry in _parse_rates(pin_recipes)))
    banned = tuple(sorted(normalize_class_name(entry) for entry in _parse_rates(ban_recipes)))
    try:
        master_result = build_master_plan(
            catalog,
            phase_data,
            pace_multiplier=pace_multiplier,
            include_alternates=alternates,
            pinned=pinned,
            banned=banned,
        )
    except ValueError as exc:
        return str(exc)

    master_result = replace(
        master_result,
        stages=tuple(_apply_stage_extraction(catalog, stage) for stage in master_result.stages),
    )
    master_result = replace(
        master_result,
        stages=tuple(
            _apply_stage_logistics(catalog, phase_data, alternates, stage)
            for stage in master_result.stages
        ),
    )

    if not persist or master_result.status != "complete":
        return format_master_response(master_result, artifact_path=None)

    plan_id = "master"
    now = datetime.now()
    workspace_dir = get_workspace_dir()
    store = SaveStore.open(workspace_dir / "planning.sqlite3")
    persisted_stages: list[StagePlan] = []
    try:
        store.upsert_master_plan(
            {
                "plan_id": plan_id,
                "name": result.save_name,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        )
        for stage in master_result.stages:
            revision = store.next_stage_revision(plan_id, stage.phase)
            utcstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            run_id = f"run_m{stage.phase}_{revision}_{utcstamp}"
            stage = replace(stage, revision=revision, solver_run_id=run_id)
            store.save_stage_plan(
                plan_id, stage.to_payload(), stage.phase, now, revision=revision
            )
            store.record_solver_run(
                run_id,
                plan_id,
                stage.phase,
                "optimal",
                {
                    "runs": [
                        {
                            "recipe_class": node.recipe_class,
                            "building_class": node.building_class,
                            "machines_exact": node.machine_count_exact,
                        }
                        for node in stage.nodes
                    ],
                    "imports": [
                        {"item_class": source.item_class, "rate_per_min": source.rate_per_min}
                        for source in stage.sources
                    ],
                    "diagnostics": [diagnostic.message for diagnostic in stage.diagnostics],
                },
                now,
            )
            persisted_stages.append(stage)
    finally:
        store.close()

    for stage in persisted_stages:
        export_stage_artifacts(workspace_dir, plan_id, stage)
    master_result = replace(master_result, stages=tuple(persisted_stages))
    summary_path = export_master_summary(workspace_dir, plan_id, master_result)
    return format_master_response(master_result, artifact_path=summary_path)


def run_scenario_comparison(
    catalog: DocsCatalog,
    phase_data: ProjectAssemblyData,
    scope: str,
    phase: int,
    pace_scenarios: str,
    include_alternates: str,
    pin_recipes: str = "",
    ban_recipes: str = "",
) -> str:
    """Compute an unpersisted side-by-side pace comparison; never touches the store.

    Exploratory only: unlike ``run_plan_calculation``/``run_master_calculation``,
    this never calls ``get_workspace_dir`` or opens a ``SaveStore``, so it is safe
    to call before any workspace has been resolved. ``scope="master"`` compares
    the full five-phase build at each pace; any other scope compares the single
    ``phase`` stage.

    Args:
        catalog: Docs catalog providing items, recipes, and buildings.
        phase_data: Project Assembly phase data.
        scope: "master" to compare the full build, anything else to compare
            a single stage (``phase``).
        phase: The 1-5 phase number to compare when ``scope`` is not "master".
        pace_scenarios: Semicolon-separated pace multipliers, e.g. "1.0;2.0;3.0".
        include_alternates: Semicolon-separated alternate recipe names to
            allow beyond the default gate.
        pin_recipes: Semicolon-separated recipe names to force.
        ban_recipes: Semicolon-separated recipe names to exclude.

    Returns:
        The formatted comparison, or a plain-text error message if
        ``pace_scenarios`` does not parse to numbers or the comparison
        itself raises (bad pace count/range, unknown phase).
    """
    raw_paces = _parse_rates(pace_scenarios)
    try:
        paces = tuple(float(entry) for entry in raw_paces)
    except ValueError:
        return (
            f"Invalid pace_scenarios value(s): {pace_scenarios!r}; expected "
            "semicolon-separated numbers, e.g. '1.0;2.0;3.0'."
        )

    alternates = tuple(_parse_rates(include_alternates))
    pinned = tuple(normalize_class_name(entry) for entry in _parse_rates(pin_recipes))
    banned = tuple(normalize_class_name(entry) for entry in _parse_rates(ban_recipes))
    scenario_phase = None if scope == "master" else phase

    try:
        comparison = compare_pace_scenarios(
            catalog,
            phase_data,
            paces,
            phase=scenario_phase,
            include_alternates=alternates,
            pinned=pinned,
            banned=banned,
        )
    except ValueError as exc:
        return str(exc)

    return format_scenarios_response(comparison, scope=scope, phase=scenario_phase)

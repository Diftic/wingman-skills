"""Plan artifact exports for the Project Assembly factory solver.

Pure report generation for a persisted ``StagePlan``: deterministic Markdown
and canonical JSON artifacts, written inside the per-save workspace so a
later solver step can reference them by path. This module defines rendering
only; it does not run the solver or touch the workspace's record store.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from satisfactory_actuals import ActualsComparison, ActualsRow
from satisfactory_docs import DocsCatalog, normalize_class_name
from satisfactory_master_plan import MasterPlanResult
from satisfactory_plan_models import (
    EXTERNAL_DEMAND_NODE_ID,
    RAW_IMPORT_NODE_ID,
    BuildTask,
    Diagnostic,
    FactoryMasterPlan,
    ItemFlow,
    PowerPlan,
    ProcessNode,
    ResourceSource,
    StagePlan,
    StageTransition,
)
from satisfactory_scenarios import ScenarioComparison, ScenarioRow

# Reused rather than duplicated: satisfactory_workspace does not import this
# module, so importing its slugify here creates no cycle, and it keeps a
# hostile plan id slugified identically everywhere it is used.
from satisfactory_workspace import slugify


_MAX_POWER_BUILDINGS = 5
_FLUID_FORMS = frozenset({"RF_LIQUID", "RF_GAS"})


def _fmt_rate(value: float) -> str:
    """Format a rate/power value to the 3-decimal Markdown convention."""
    return f"{value:.3f}"


def _fmt_clock(value: float) -> str:
    """Format a clock percentage to the 4-decimal Markdown convention."""
    return f"{value:.4f}"


def _table_or_none(headers: tuple[str, ...], rows: list[tuple[str, ...]]) -> list[str]:
    if not rows:
        return ["(none)"]
    lines = [f"| {' | '.join(headers)} |", f"| {' | '.join('---' for _ in headers)} |"]
    lines.extend(f"| {' | '.join(row)} |" for row in rows)
    return lines


def _bulleted_or_none(items: tuple[str, ...]) -> list[str]:
    if not items:
        return ["(none)"]
    return [f"- {item}" for item in items]


def _diagnostics_lines(diagnostics: tuple[Diagnostic, ...]) -> list[str]:
    if not diagnostics:
        return ["(none)"]
    return [
        f"- [{diagnostic.severity.upper()}] {diagnostic.code}: {diagnostic.message} "
        f"(subject: {diagnostic.subject})"
        for diagnostic in diagnostics
    ]


def _power_lines(power: PowerPlan) -> list[str]:
    lines = [f"- Total: {_fmt_rate(power.total_mw)} MW"]
    if not power.by_building:
        lines.append("- Top building classes: none")
        return lines
    ranked = sorted(power.by_building, key=lambda pair: (-pair[1], pair[0]))
    top = ", ".join(f"{name} {_fmt_rate(mw)} MW" for name, mw in ranked[:_MAX_POWER_BUILDINGS])
    lines.append(f"- Top building classes: {top}")
    return lines


def _flow_summary_lines(flows: tuple[ItemFlow, ...]) -> list[str]:
    external: dict[str, float] = {}
    raw_imports: dict[str, float] = {}
    internal_count = 0
    for flow in flows:
        is_external = flow.dest_id == EXTERNAL_DEMAND_NODE_ID
        is_raw_import = flow.source_id == RAW_IMPORT_NODE_ID
        if is_external:
            external[flow.item_class] = external.get(flow.item_class, 0.0) + flow.rate_per_min
        if is_raw_import:
            raw_imports[flow.item_class] = (
                raw_imports.get(flow.item_class, 0.0) + flow.rate_per_min
            )
        if not is_external and not is_raw_import:
            internal_count += 1

    def render(bucket: dict[str, float]) -> str:
        if not bucket:
            return "none"
        return ", ".join(f"{item} {_fmt_rate(rate)}/min" for item, rate in sorted(bucket.items()))

    return [
        f"- External demand satisfied: {render(external)}",
        f"- Raw imports: {render(raw_imports)}",
        f"- Internal edges: {internal_count}",
    ]


def stage_plan_to_json(stage: StagePlan) -> str:
    """Render ``stage`` as canonical, pretty-printed JSON.

    Parsing the result and calling ``stage_plan_from_payload`` reproduces an
    equal ``StagePlan``, since sorting keys only reorders dict output and
    never touches list element order.
    """
    return json.dumps(stage.to_payload(), indent=2, sort_keys=True)


def stage_plan_to_markdown(stage: StagePlan) -> str:
    """Render ``stage`` as deterministic, ASCII-only Markdown.

    Section order is fixed: title, summary, demands, production, resource
    sources, flows, power, diagnostics, assumptions, provenance. Empty
    collections render a "(none)" line rather than an empty table so the
    document never crashes or looks broken for a minimal plan.
    """
    lines: list[str] = [f"# Stage Plan - Phase {stage.phase} (Revision {stage.revision})", ""]

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Window: {_fmt_rate(stage.window_hours)} hours")
    lines.append(f"- Pace multiplier: {_fmt_rate(stage.pace_multiplier)}")
    lines.append(f"- Solver run: {stage.solver_run_id or 'none'}")
    lines.append(f"- Created: {stage.created_at}")
    lines.append("")

    lines.append("## Demands")
    lines.append("")
    lines.extend(
        _table_or_none(
            ("Item", "Quantity", "Rate/min"),
            [
                (item_class, _fmt_rate(quantity), _fmt_rate(rate_per_min))
                for item_class, quantity, rate_per_min in stage.demands
            ],
        )
    )
    lines.append("")

    lines.append("## Production")
    lines.append("")
    lines.extend(
        _table_or_none(
            ("Node ID", "Recipe", "Building", "Machines (exact)", "Machines (int)", "Clock", "Power (MW)"),
            [
                (
                    node.node_id,
                    node.recipe_class,
                    node.building_class,
                    _fmt_rate(node.machine_count_exact),
                    str(node.machine_count),
                    _fmt_clock(node.clock),
                    _fmt_rate(node.power_mw),
                )
                for node in stage.nodes
            ],
        )
    )
    lines.append("")

    lines.append("## Resource Sources")
    lines.append("")
    lines.extend(
        _table_or_none(
            ("Node ID", "Item", "Rate/min", "Extractor", "Count"),
            [
                (
                    source.node_id,
                    source.item_class,
                    _fmt_rate(source.rate_per_min),
                    source.extractor_class,
                    str(source.extractor_count),
                )
                for source in stage.sources
            ],
        )
    )
    lines.append("")

    lines.append("## Flows")
    lines.append("")
    lines.extend(_flow_summary_lines(stage.flows))
    lines.append("")

    lines.append("## Power")
    lines.append("")
    lines.extend(_power_lines(stage.power))
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    lines.extend(_diagnostics_lines(stage.diagnostics))
    lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    lines.extend(_bulleted_or_none(stage.assumptions))
    lines.append("")

    lines.append("## Provenance")
    lines.append("")
    lines.append(f"- Source: {stage.provenance.source or '(none)'}")
    lines.append(f"- Retrieved: {stage.provenance.retrieved or '(none)'}")
    lines.append(f"- Note: {stage.provenance.note or '(none)'}")

    return "\n".join(lines) + "\n"


_MAX_PLAN_NODES = 10
_MAX_PLAN_DIAGNOSTICS = 5


def _display_name_for(item_class: str, display_names: dict[str, str] | None) -> str:
    """Resolve a display name for ``item_class``, falling back to the class name.

    The mapping is keyed by normalized class name (see
    ``satisfactory_docs.normalize_class_name``) so callers do not need to
    match raw Unreal class/path casing.
    """
    if not display_names:
        return item_class
    return display_names.get(normalize_class_name(item_class), item_class)


def _plan_demand_line(
    demand: tuple[str, float, float], display_names: dict[str, str] | None = None
) -> str:
    item_class, quantity, rate_per_min = demand
    name = _display_name_for(item_class, display_names)
    return f"- {name} {_fmt_rate(quantity)} ({_fmt_rate(rate_per_min)}/min)"


def _plan_node_line(node: ProcessNode) -> str:
    return (
        f"- {node.recipe_class} x{node.machine_count} @ {_fmt_clock(node.clock)} clock, "
        f"{_fmt_rate(node.power_mw)} MW"
    )


def _plan_import_line(
    source: ResourceSource, display_names: dict[str, str] | None = None
) -> str:
    name = _display_name_for(source.item_class, display_names)
    line = f"- {name} {_fmt_rate(source.rate_per_min)}/min"
    if source.extractor_class and source.extractor_count > 0:
        line += f" via {source.extractor_count} x {source.extractor_class}"
    return line


def _plan_diagnostic_line(diagnostic: Diagnostic) -> str:
    return f"- [{diagnostic.severity.upper()}] {diagnostic.code}: {diagnostic.message}"


def _render_plan_response(
    stage: StagePlan,
    artifact_paths: dict[str, str] | None,
    node_limit: int,
    demand_limit: int,
    display_names: dict[str, str] | None = None,
) -> str:
    """Render one candidate layout of the plan summary at given cutoffs."""
    revision_text = f"revision {stage.revision}" if stage.revision > 0 else "not persisted"
    lines = [
        f"Phase {stage.phase} plan ({revision_text}): window "
        f"{_fmt_rate(stage.window_hours)}h, pace x{_fmt_rate(stage.pace_multiplier)}",
        "",
        "Demands:",
    ]
    shown_demands = stage.demands[:demand_limit]
    if shown_demands:
        lines.extend(_plan_demand_line(demand, display_names) for demand in shown_demands)
    else:
        lines.append("(none)")
    if demand_limit < len(stage.demands):
        lines.append(f"+{len(stage.demands) - demand_limit} more")

    ranked_nodes = sorted(stage.nodes, key=lambda node: (-node.power_mw, node.node_id))
    lines.append("")
    lines.append(f"Production ({len(ranked_nodes)} nodes):")
    shown_nodes = ranked_nodes[:node_limit]
    if shown_nodes:
        lines.extend(_plan_node_line(node) for node in shown_nodes)
    else:
        lines.append("(none)")
    if node_limit < len(ranked_nodes):
        lines.append(f"+{len(ranked_nodes) - node_limit} more")

    lines.append("")
    lines.append("Raw imports:")
    if stage.sources:
        lines.extend(_plan_import_line(source, display_names) for source in stage.sources)
    else:
        lines.append("(none)")

    lines.append("")
    lines.append(f"Power total: {_fmt_rate(stage.power.total_mw)} MW")

    diagnostics = stage.diagnostics[:_MAX_PLAN_DIAGNOSTICS]
    lines.append("")
    lines.append("Diagnostics:")
    if diagnostics:
        lines.extend(_plan_diagnostic_line(diagnostic) for diagnostic in diagnostics)
    else:
        lines.append("(none)")
    if len(diagnostics) < len(stage.diagnostics):
        lines.append(f"+{len(stage.diagnostics) - len(diagnostics)} more")

    if artifact_paths:
        markdown_path = artifact_paths.get("markdown_path", "")
        if markdown_path:
            lines.append("")
            lines.append(f"Artifact: {markdown_path}")

    return "\n".join(lines)


def format_plan_response(
    stage: StagePlan,
    artifact_paths: dict[str, str] | None,
    char_budget: int = 3200,
    display_names: dict[str, str] | None = None,
) -> str:
    """Render a compact, deterministic, ASCII plan summary for a tool return.

    Section order is fixed: header (phase, window, pace, revision), demand
    lines, top production nodes (recipe, machines, clock, power; capped at
    10, ranked by descending power), raw imports, total power, diagnostics
    (capped at 5), and an artifact path line when ``artifact_paths`` is
    given. If the rendered text still exceeds ``char_budget`` after those
    fixed caps, node lines are dropped first, then demand lines (each
    replaced by an updated "+N more" count), never cutting a line
    mid-way, until the result fits.

    Args:
        stage: The stage plan to summarize.
        artifact_paths: Export artifact paths from ``export_stage_artifacts``
            (uses "markdown_path" when present), or None when the plan was
            not persisted.
        char_budget: Hard character ceiling for the returned string.
        display_names: Optional mapping from normalized class name (see
            ``satisfactory_docs.normalize_class_name``) to a player-facing
            display name. Demand and raw-import lines use the mapped name
            when present, the class name otherwise.

    Returns:
        The formatted summary, always under ``char_budget`` for realistic
        stage sizes.
    """
    node_limit = min(_MAX_PLAN_NODES, len(stage.nodes))
    demand_limit = len(stage.demands)

    text = _render_plan_response(stage, artifact_paths, node_limit, demand_limit, display_names)
    while len(text) > char_budget and (node_limit > 0 or demand_limit > 0):
        if node_limit > 0:
            node_limit -= 1
        else:
            demand_limit -= 1
        text = _render_plan_response(
            stage, artifact_paths, node_limit, demand_limit, display_names
        )
    return text


def master_plan_summary_markdown(
    plan: FactoryMasterPlan, stages: tuple[StagePlan, ...]
) -> str:
    """Render a one-row-per-stage Markdown summary table for a master plan."""
    lines = [f"# Master Plan: {plan.name}", ""]
    headers = ("Phase", "Revision", "Window (hrs)", "Machines", "Power (MW)", "Diagnostics")
    rows = [
        (
            str(stage.phase),
            str(stage.revision),
            _fmt_rate(stage.window_hours),
            str(sum(node.machine_count for node in stage.nodes)),
            _fmt_rate(stage.power.total_mw),
            str(len(stage.diagnostics)),
        )
        for stage in stages
    ]
    lines.extend(_table_or_none(headers, rows))
    return "\n".join(lines) + "\n"


def _is_within(base: Path, target: Path) -> bool:
    """True if resolved ``target`` is inside (or equal to) resolved ``base``.

    Reimplemented locally rather than imported from
    ``satisfactory_workspace._is_within`` since that helper is private to
    its module; behavior is kept identical, including the Windows
    case-insensitive fallback (NTFS paths compare case-insensitively, so a
    case-different sibling would otherwise be wrongly treated as contained
    only on POSIX).
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


def export_stage_artifacts(workspace_dir: Path, plan_id: str, stage: StagePlan) -> dict[str, str]:
    """Write Markdown and JSON export artifacts for one stage plan.

    Writes ``plans/<slug(plan_id)>/phase<phase>_rev<revision>.md`` and
    ``.json`` under ``workspace_dir``, creating directories as needed, and
    returns the two written paths as strings. Writes are plain (not
    atomic-replace): the artifacts are derived, regenerable data, matching
    the mirror artifact precedent in ``satisfactory_mirror.py``.

    Raises:
        ValueError: If either resolved output path would land outside
            ``workspace_dir``.
    """
    base = workspace_dir.resolve()
    slug = slugify(plan_id)
    plan_dir = (base / "plans" / slug).resolve()
    base_name = f"phase{stage.phase}_rev{stage.revision}"
    markdown_path = (plan_dir / f"{base_name}.md").resolve()
    json_path = (plan_dir / f"{base_name}.json").resolve()
    if not (_is_within(base, markdown_path) and _is_within(base, json_path)):
        raise ValueError(f"Refusing plan export outside workspace: {plan_id!r}")

    plan_dir.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(stage_plan_to_markdown(stage), encoding="utf-8")
    json_path.write_text(stage_plan_to_json(stage), encoding="utf-8")
    return {"markdown_path": str(markdown_path), "json_path": str(json_path)}


def _construction_task_line(task: BuildTask) -> tuple[str, ...]:
    depends_on = ", ".join(task.depends_on) if task.depends_on else "(none)"
    return (str(task.order_index), task.node_id, task.building_class, str(task.count), depends_on)


def _commissioning_check_line(
    catalog: DocsCatalog, stage: StagePlan, task: BuildTask
) -> str:
    """Render one task's deterministic commissioning-check line.

    A task whose ``node_id`` matches a production ``ProcessNode`` lists the
    recipe's input items, its output items, the node's clock, and its power
    draw. A task whose ``node_id`` matches an extraction ``ResourceSource``
    instead lists the resource being targeted and whether it routes to a
    belt or a pipe, per the item's Docs form.
    """
    node = next((node for node in stage.nodes if node.node_id == task.node_id), None)
    if node is not None:
        recipe = catalog.recipe(node.recipe_class)
        if recipe is not None:
            inputs = ", ".join(
                catalog.item_display_name(item.class_name) for item in recipe.ingredients
            ) or "(none)"
            outputs = ", ".join(
                catalog.item_display_name(item.class_name) for item in recipe.products
            ) or "(none)"
        else:
            inputs = outputs = "(unresolved recipe)"
        return (
            f"- {task.task_id} ({task.node_id}): inputs connected {inputs}; "
            f"output routed {outputs}; clock set to {_fmt_clock(node.clock)}%; "
            f"power available {_fmt_rate(node.power_mw)} MW"
        )

    source = next((source for source in stage.sources if source.node_id == task.node_id), None)
    if source is not None:
        item = catalog.item(source.item_class)
        belt_or_pipe = "pipe" if item is not None and item.form in _FLUID_FORMS else "belt"
        target = catalog.item_display_name(source.item_class)
        return (
            f"- {task.task_id} ({task.node_id}): resource target {target}; "
            f"output routed via {belt_or_pipe}"
        )

    return f"- {task.task_id} ({task.node_id}): (no matching plan node or source)"


def _commissioning_check_lines(
    catalog: DocsCatalog, stage: StagePlan, tasks: tuple[BuildTask, ...]
) -> list[str]:
    if not tasks:
        return ["(none)"]
    return [_commissioning_check_line(catalog, stage, task) for task in tasks]


def construction_plan_to_markdown(
    catalog: DocsCatalog,
    stage: StagePlan,
    tasks: tuple[BuildTask, ...],
    bom: tuple[tuple[str, float], ...],
    diagnostics: tuple[Diagnostic, ...] = (),
    assumptions: tuple[str, ...] = (),
) -> str:
    """Render a stage's construction bill and commissioning order as ASCII Markdown.

    Section order is fixed: title, commissioning order (one row per task:
    order index, node id, building, count, depends-on), commissioning
    checks (one deterministic line per task: connected inputs, routed
    outputs, clock, and power for a production task; resource target and
    belt/pipe routing for an extractor task), bill of materials (one row
    per item), diagnostics, assumptions. Empty collections render a
    "(none)" line, matching ``stage_plan_to_markdown``'s convention.

    Args:
        catalog: Docs catalog used to resolve each task's recipe inputs
            and outputs, and each extracted item's belt/pipe form.
    """
    lines: list[str] = [
        f"# Construction Plan - Phase {stage.phase} (Revision {stage.revision})",
        "",
        "## Commissioning Order",
        "",
    ]
    lines.extend(
        _table_or_none(
            ("Order", "Node ID", "Building", "Count", "Depends On"),
            [_construction_task_line(task) for task in tasks],
        )
    )
    lines.append("")

    lines.append("## Commissioning Checks")
    lines.append("")
    lines.extend(_commissioning_check_lines(catalog, stage, tasks))
    lines.append("")

    lines.append("## Bill of Materials")
    lines.append("")
    lines.extend(
        _table_or_none(
            ("Item", "Quantity"),
            [(item_class, _fmt_rate(quantity)) for item_class, quantity in bom],
        )
    )
    lines.append("")

    lines.append("## Diagnostics")
    lines.append("")
    lines.extend(_diagnostics_lines(diagnostics))
    lines.append("")

    lines.append("## Assumptions")
    lines.append("")
    lines.extend(_bulleted_or_none(assumptions))

    return "\n".join(lines) + "\n"


def export_construction_artifact(
    catalog: DocsCatalog,
    workspace_dir: Path,
    plan_id: str,
    stage: StagePlan,
    tasks: tuple[BuildTask, ...],
    bom: tuple[tuple[str, float], ...],
    diagnostics: tuple[Diagnostic, ...] = (),
    assumptions: tuple[str, ...] = (),
) -> str:
    """Write the construction bill/commissioning-order artifact and return its path.

    Writes ``plans/<slug(plan_id)>/phase<phase>_rev<revision>_construction.md``
    under ``workspace_dir`` (same containment idiom as
    ``export_stage_artifacts``): a plain, regenerable write, not
    atomic-replace.

    Raises:
        ValueError: If the resolved output path would land outside
            ``workspace_dir``.
    """
    base = workspace_dir.resolve()
    slug = slugify(plan_id)
    plan_dir = (base / "plans" / slug).resolve()
    path = (plan_dir / f"phase{stage.phase}_rev{stage.revision}_construction.md").resolve()
    if not _is_within(base, path):
        raise ValueError(f"Refusing plan export outside workspace: {plan_id!r}")

    plan_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(
        construction_plan_to_markdown(catalog, stage, tasks, bom, diagnostics, assumptions),
        encoding="utf-8",
    )
    return str(path)


_MAX_MASTER_DIAGNOSTICS = 5
_MAX_TRANSITION_DELTAS = 8


def _master_stage_line(stage: StagePlan) -> str:
    revision_text = f"rev {stage.revision}" if stage.revision > 0 else "not persisted"
    machines = sum(node.machine_count for node in stage.nodes)
    return (
        f"- Phase {stage.phase} ({revision_text}): {len(stage.nodes)} nodes, "
        f"{machines} machines, {_fmt_rate(stage.power.total_mw)} MW"
    )


def _master_transition_line(transition: StageTransition) -> str:
    return (
        f"- Phase {transition.from_phase}->{transition.to_phase}: reused "
        f"{len(transition.reused_nodes)}, expanded {len(transition.expanded_nodes)}, "
        f"added {len(transition.added_nodes)}, retired {len(transition.retired_nodes)}"
    )


def _render_master_response(
    result: MasterPlanResult,
    artifact_path: str | None,
    stage_limit: int,
    transition_limit: int,
) -> str:
    """Render one candidate layout of the master summary at given cutoffs."""
    pace = result.stages[0].pace_multiplier if result.stages else None
    pace_text = f"pace x{_fmt_rate(pace)}" if pace is not None else "pace n/a"
    lines = [f"Master plan: status '{result.status}', {pace_text}", "", "Stages:"]

    shown_stages = result.stages[:stage_limit]
    if shown_stages:
        lines.extend(_master_stage_line(stage) for stage in shown_stages)
    else:
        lines.append("(none)")
    if stage_limit < len(result.stages):
        lines.append(f"+{len(result.stages) - stage_limit} more")

    lines.append("")
    lines.append("Transitions:")
    shown_transitions = result.transitions[:transition_limit]
    if shown_transitions:
        lines.extend(_master_transition_line(transition) for transition in shown_transitions)
    else:
        lines.append("(none)")
    if transition_limit < len(result.transitions):
        lines.append(f"+{len(result.transitions) - transition_limit} more")

    diagnostics = result.diagnostics[:_MAX_MASTER_DIAGNOSTICS]
    lines.append("")
    lines.append("Diagnostics:")
    if diagnostics:
        lines.extend(f"- {diagnostic}" for diagnostic in diagnostics)
    else:
        lines.append("(none)")
    if len(diagnostics) < len(result.diagnostics):
        lines.append(f"+{len(result.diagnostics) - len(diagnostics)} more")

    if artifact_path:
        lines.append("")
        lines.append(f"Artifact: {artifact_path}")

    return "\n".join(lines)


def format_master_response(
    result: MasterPlanResult,
    artifact_path: str | None,
    display_names: dict[str, str] | None = None,
    char_budget: int = 3200,
) -> str:
    """Render a compact, deterministic, ASCII master-plan summary for a tool return.

    Section order is fixed: header (status, pace multiplier), one line per
    built stage (phase, revision, node count, total machines, power), one
    line per stage transition (reused/expanded/added/retired counts),
    diagnostics (capped at 5), and an artifact path line when
    ``artifact_path`` is given. If the rendered text still exceeds
    ``char_budget`` after those fixed caps, transition lines are dropped
    first, then stage lines (each replaced by an updated "+N more" count),
    never cutting a line mid-way, until the result fits.

    Args:
        result: The five-stage master plan build result.
        artifact_path: Path to the written master summary artifact from
            ``export_master_summary``, or None when the plan was not
            persisted.
        display_names: Accepted for interface symmetry with
            ``format_plan_response``; unused today because this summary
            names phases and node counts, not individual demand or import
            items.
        char_budget: Hard character ceiling for the returned string.

    Returns:
        The formatted summary, always under ``char_budget`` for realistic
        master plan sizes.
    """
    stage_limit = len(result.stages)
    transition_limit = len(result.transitions)

    text = _render_master_response(result, artifact_path, stage_limit, transition_limit)
    while len(text) > char_budget and (stage_limit > 0 or transition_limit > 0):
        if transition_limit > 0:
            transition_limit -= 1
        else:
            stage_limit -= 1
        text = _render_master_response(result, artifact_path, stage_limit, transition_limit)
    return text


def _master_summary_transition_block(transition: StageTransition) -> list[str]:
    """Render one transition's Markdown block: category counts plus up to 8 deltas."""
    lines = [
        f"## Phase {transition.from_phase} -> {transition.to_phase}",
        "",
        f"- Reused: {len(transition.reused_nodes)}",
        f"- Expanded: {len(transition.expanded_nodes)}",
        f"- Added: {len(transition.added_nodes)}",
        f"- Retired: {len(transition.retired_nodes)}",
        "",
    ]
    deltas = transition.expanded_nodes + transition.added_nodes + transition.retired_nodes
    shown = deltas[:_MAX_TRANSITION_DELTAS]
    lines.extend(_bulleted_or_none(shown))
    if len(shown) < len(deltas):
        lines.append(f"- +{len(deltas) - len(shown)} more")
    lines.append("")
    return lines


def _master_summary_markdown(plan_id: str, result: MasterPlanResult) -> str:
    """Render the full master-plan summary artifact Markdown."""
    plan = FactoryMasterPlan(plan_id=plan_id, name=plan_id, created_at="", updated_at="")
    stage_table = master_plan_summary_markdown(plan, result.stages).rstrip("\n")
    lines = [f"Status: {result.status}", "", stage_table, ""]

    lines.append("## Transitions")
    lines.append("")
    if not result.transitions:
        lines.append("(none)")
        lines.append("")
    else:
        for transition in result.transitions:
            lines.extend(_master_summary_transition_block(transition))

    lines.append("## Reservations")
    lines.append("")
    lines.append(
        "Informational future-machine-count envelope per stage; see the "
        "per-stage export artifacts for the full per-node detail."
    )

    return "\n".join(lines) + "\n"


def export_master_summary(
    workspace_dir: Path,
    plan_id: str,
    result: MasterPlanResult,
    display_names: dict[str, str] | None = None,
) -> str:
    """Write the master-plan summary export artifact and return its path.

    Writes ``plans/<slug(plan_id)>/master_summary.md`` under
    ``workspace_dir`` (same containment idiom as ``export_stage_artifacts``),
    containing the per-stage table (via ``master_plan_summary_markdown``), a
    transitions section (per transition: category counts plus up to 8 delta
    entries), and a reservations note.

    Args:
        workspace_dir: The per-save workspace root.
        plan_id: Master plan id (only "master" is used today); slugified for
            the directory name and used verbatim as the artifact's title,
            since this pure module has no store access to look up the
            plan's display name.
        result: The five-stage master plan build to summarize.
        display_names: Accepted for interface symmetry with
            ``export_stage_artifacts``'s callers; unused today because this
            summary does not name individual demand or import items.

    Raises:
        ValueError: If the resolved output path would land outside
            ``workspace_dir``.
    """
    base = workspace_dir.resolve()
    slug = slugify(plan_id)
    plan_dir = (base / "plans" / slug).resolve()
    summary_path = (plan_dir / "master_summary.md").resolve()
    if not _is_within(base, summary_path):
        raise ValueError(f"Refusing plan export outside workspace: {plan_id!r}")

    plan_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(_master_summary_markdown(plan_id, result), encoding="utf-8")
    return str(summary_path)


_MAX_SCENARIO_RAW_IMPORTS = 5
_MAX_SCENARIO_DIAGNOSTICS = 5


def _percent_delta(baseline: float, value: float) -> str:
    """Render ``value`` as a signed percentage change from ``baseline``.

    Returns "n/a" when ``baseline`` is zero and ``value`` is also zero (no
    change to report), or "+inf%" when ``baseline`` is zero but ``value``
    is not (a change from nothing is not a finite percentage).
    """
    if baseline == 0.0:
        return "n/a" if value == 0.0 else "+inf%"
    percent = (value - baseline) / baseline * 100.0
    sign = "+" if percent >= 0 else ""
    return f"{sign}{percent:.1f}%"


def _scenario_delta_line(first: ScenarioRow, row: ScenarioRow) -> str:
    if row is first:
        return f"- Delta vs pace x{_fmt_rate(first.pace)}: baseline"
    machines_delta = _percent_delta(first.machine_count, row.machine_count)
    power_delta = _percent_delta(first.power_mw, row.power_mw)
    return (
        f"- Delta vs pace x{_fmt_rate(first.pace)}: machines {machines_delta}, "
        f"power {power_delta}"
    )


def _scenario_row_lines(row: ScenarioRow, import_limit: int) -> list[str]:
    lines = [
        f"Pace x{_fmt_rate(row.pace)} (status: {row.status}):",
        f"- Window: {row.window_text}",
        f"- Nodes: {row.node_count}, Machines: {row.machine_count}, "
        f"Power: {_fmt_rate(row.power_mw)} MW",
    ]
    shown_imports = row.raw_imports[:import_limit]
    if shown_imports:
        lines.append(
            "- Raw imports: "
            + ", ".join(f"{item} {_fmt_rate(rate)}/min" for item, rate in shown_imports)
        )
        if import_limit < len(row.raw_imports):
            lines.append(f"  +{len(row.raw_imports) - import_limit} more")
    else:
        lines.append("- Raw imports: (none)")
    return lines


def _render_scenarios_response(
    comparison: ScenarioComparison,
    scope: str,
    phase: int | None,
    row_limit: int,
    import_limit: int,
    diagnostic_limit: int,
) -> str:
    """Render one candidate layout of the scenario comparison at given cutoffs."""
    scope_text = "scope=master" if phase is None else f"scope=stage, phase={phase}"
    lines = [
        f"Pace scenario comparison ({scope_text}).",
        "Nothing persisted: scenarios are exploratory only.",
        "",
    ]

    shown_rows = comparison.rows[:row_limit]
    first = comparison.rows[0] if comparison.rows else None
    for row in shown_rows:
        lines.extend(_scenario_row_lines(row, import_limit))
        if first is not None:
            lines.append(_scenario_delta_line(first, row))
        lines.append("")
    if row_limit < len(comparison.rows):
        lines.append(f"+{len(comparison.rows) - row_limit} more scenarios")
        lines.append("")

    diagnostics = comparison.diagnostics[:diagnostic_limit]
    lines.append("Diagnostics:")
    if diagnostics:
        lines.extend(f"- {diagnostic}" for diagnostic in diagnostics)
    else:
        lines.append("(none)")
    if diagnostic_limit < len(comparison.diagnostics):
        lines.append(f"+{len(comparison.diagnostics) - diagnostic_limit} more")

    return "\n".join(lines).rstrip("\n")


def format_scenarios_response(
    comparison: ScenarioComparison,
    scope: str,
    phase: int | None,
    char_budget: int = 3200,
) -> str:
    """Render a compact, deterministic, ASCII pace-scenario comparison for a tool return.

    Section order is fixed: header (scope, phase, a note that nothing is
    persisted), one block per scenario (pace, status, window, node/machine/
    power totals, up to 5 raw imports, a "delta vs first scenario" line
    comparing machines and power as signed percentages), and diagnostics
    (capped at 5). If the rendered text still exceeds ``char_budget`` after
    those fixed caps, diagnostics are dropped first, then raw-import lines,
    then whole scenario blocks (each replaced by an updated "+N more"
    count), never cutting a line mid-way, until the result fits.

    Args:
        comparison: The pace comparison to summarize.
        scope: "stage" or "master", echoed in the header.
        phase: The phase compared for scope="stage", or None for scope="master".
        char_budget: Hard character ceiling for the returned string.

    Returns:
        The formatted summary, always under ``char_budget`` for realistic
        scenario counts (at most 4 paces).
    """
    row_limit = len(comparison.rows)
    import_limit = max((len(row.raw_imports) for row in comparison.rows), default=0)
    diagnostic_limit = len(comparison.diagnostics)

    text = _render_scenarios_response(
        comparison, scope, phase, row_limit, import_limit, diagnostic_limit
    )
    while len(text) > char_budget and (
        diagnostic_limit > 0 or import_limit > 0 or row_limit > 0
    ):
        if diagnostic_limit > 0:
            diagnostic_limit -= 1
        elif import_limit > 0:
            import_limit -= 1
        else:
            row_limit -= 1
        text = _render_scenarios_response(
            comparison, scope, phase, row_limit, import_limit, diagnostic_limit
        )
    return text


_MAX_ACTUALS_MISSING = 5
_MAX_ACTUALS_UNPLANNED = 3
_MAX_ACTUALS_SURPLUS = 3


def _actuals_name(recipe_key: str, display_names: dict[str, str] | None) -> str:
    if not display_names:
        return recipe_key
    return display_names.get(recipe_key, recipe_key)


def _actuals_missing_line(row: ActualsRow, display_names: dict[str, str] | None) -> str:
    name = _actuals_name(row.recipe_key, display_names)
    shortfall = row.planned_capacity - row.actual_capacity
    return (
        f"  - build {_fmt_rate(shortfall)} more {name} (planned "
        f"{_fmt_rate(row.planned_capacity)}, actual {_fmt_rate(row.actual_capacity)})"
    )


def _actuals_unplanned_line(row: ActualsRow, display_names: dict[str, str] | None) -> str:
    name = _actuals_name(row.recipe_key, display_names)
    return f"  - unplanned {name}: actual {_fmt_rate(row.actual_capacity)}"


def _actuals_surplus_line(row: ActualsRow, display_names: dict[str, str] | None) -> str:
    name = _actuals_name(row.recipe_key, display_names)
    return (
        f"  - surplus {name}: planned {_fmt_rate(row.planned_capacity)}, "
        f"actual {_fmt_rate(row.actual_capacity)}"
    )


def _render_actuals_section(
    comparison: ActualsComparison,
    display_names: dict[str, str] | None,
    missing_limit: int,
    unplanned_limit: int,
    surplus_limit: int,
) -> str:
    """Render one candidate layout of the actuals section at given cutoffs."""
    missing = [row for row in comparison.rows if row.classification == "missing"]
    unplanned = [row for row in comparison.rows if row.classification == "unplanned"]
    surplus = [row for row in comparison.rows if row.classification == "surplus"]
    matched_count = sum(1 for row in comparison.rows if row.classification == "matched")

    lines = [f"Plan vs actual (phase {comparison.plan_phase} rev {comparison.plan_revision}):"]

    shown_missing = missing[:missing_limit]
    lines.extend(_actuals_missing_line(row, display_names) for row in shown_missing)
    if missing_limit < len(missing):
        lines.append(f"  +{len(missing) - missing_limit} more missing")

    shown_unplanned = unplanned[:unplanned_limit]
    lines.extend(_actuals_unplanned_line(row, display_names) for row in shown_unplanned)
    if unplanned_limit < len(unplanned):
        lines.append(f"  +{len(unplanned) - unplanned_limit} more unplanned")

    shown_surplus = surplus[:surplus_limit]
    lines.extend(_actuals_surplus_line(row, display_names) for row in shown_surplus)
    if surplus_limit < len(surplus):
        lines.append(f"  +{len(surplus) - surplus_limit} more surplus")

    lines.append(f"  - {matched_count} recipe(s) matched plan")

    if comparison.diagnostics:
        lines.append(f"  Diagnostics: {'; '.join(comparison.diagnostics)}")

    return "\n".join(lines)


def format_actuals_section(
    comparison: ActualsComparison,
    display_names: dict[str, str] | None = None,
    char_budget: int = 1200,
) -> str:
    """Render a bounded "Plan vs actual" section appended to an audit response.

    Section order is fixed: header (phase, revision), up to 5 missing rows
    ("build N more <recipe>" with planned/actual capacity), up to 3 unplanned
    rows, up to 3 surplus rows, one matched-count summary line, and a
    diagnostics line when ``comparison.diagnostics`` is non-empty. If the
    rendered text still exceeds ``char_budget`` after those fixed caps,
    surplus lines are dropped first, then unplanned, then missing (each
    replaced by an updated "+N more" count), never cutting a line mid-way,
    until the result fits.

    Args:
        comparison: The planned-versus-actual comparison to summarize.
        display_names: Optional mapping from normalized recipe key (see
            ``satisfactory_docs.normalize_class_name``) to a player-facing
            display name. Falls back to the recipe key when unmapped.
        char_budget: Hard character ceiling for the returned string.

    Returns:
        The formatted section, always under ``char_budget`` for realistic
        comparison sizes.
    """
    missing_total = sum(1 for row in comparison.rows if row.classification == "missing")
    unplanned_total = sum(1 for row in comparison.rows if row.classification == "unplanned")
    surplus_total = sum(1 for row in comparison.rows if row.classification == "surplus")
    missing_limit = min(_MAX_ACTUALS_MISSING, missing_total)
    unplanned_limit = min(_MAX_ACTUALS_UNPLANNED, unplanned_total)
    surplus_limit = min(_MAX_ACTUALS_SURPLUS, surplus_total)

    text = _render_actuals_section(
        comparison, display_names, missing_limit, unplanned_limit, surplus_limit
    )
    while len(text) > char_budget and (
        surplus_limit > 0 or unplanned_limit > 0 or missing_limit > 0
    ):
        if surplus_limit > 0:
            surplus_limit -= 1
        elif unplanned_limit > 0:
            unplanned_limit -= 1
        else:
            missing_limit -= 1
        text = _render_actuals_section(
            comparison, display_names, missing_limit, unplanned_limit, surplus_limit
        )
    return text

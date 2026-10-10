"""Pure pace-scenario comparison for the Project Assembly factory solver.

Pure module: no Wingman imports, stdlib only besides the sibling docs,
progression, solver, and master-plan modules. Exploratory only: nothing
built here is ever persisted. Solves the same stage (``phase`` given) or
the full five-phase master build (``phase`` omitted) at up to four pace
multipliers and reports a compact, deterministic side-by-side comparison
of windows, machines, power, and raw-resource totals per scenario.
"""

from __future__ import annotations

from dataclasses import dataclass

from satisfactory_docs import DocsCatalog, normalize_class_name
from satisfactory_master_plan import build_master_plan
from satisfactory_progression import (
    ProjectAssemblyData,
    build_capability_snapshot,
    derive_phase_demand,
)
from satisfactory_solver import schedule_machines, solve_stage


_MIN_SCENARIOS = 1
_MAX_SCENARIOS = 4
_MIN_PACE_MULTIPLIER = 1.0
_MAX_PACE_MULTIPLIER = 3.0


@dataclass(frozen=True)
class ScenarioRow:
    """One pace's solved totals: a single line in a side-by-side comparison.

    ``window_text`` is the stage's window in hours for a single-phase
    scenario, or the cumulative window across every built phase (plus the
    phase count) for a master scenario, both pre-formatted for display.
    ``raw_imports`` is sorted by normalized item class key, matching
    :func:`~satisfactory_solver.solve_stage`'s own ordering.
    """

    pace: float
    window_text: str
    node_count: int
    machine_count: int
    power_mw: float
    raw_imports: tuple[tuple[str, float], ...]
    status: str


@dataclass(frozen=True)
class ScenarioComparison:
    """A full pace comparison: one row per requested pace, plus shared diagnostics.

    ``diagnostics`` aggregates every scenario's solver/schedule notes, each
    string prefixed with the pace it concerns, mirroring the phase-prefixed
    convention used by :mod:`satisfactory_master_plan`.
    """

    rows: tuple[ScenarioRow, ...]
    diagnostics: tuple[str, ...]


def _fmt_hours(value: float) -> str:
    return f"{value:.3f}h"


def _validate_and_dedupe_paces(paces: tuple[float, ...]) -> tuple[float, ...]:
    """Dedupe ``paces`` preserving first-seen order, then validate count and bounds.

    Raises:
        ValueError: If, after deduplication, there are not 1 to 4 paces, or
            any pace falls outside [1.0, 3.0].
    """
    deduped: list[float] = []
    seen: set[float] = set()
    for pace in paces:
        if pace in seen:
            continue
        seen.add(pace)
        deduped.append(pace)

    if not (_MIN_SCENARIOS <= len(deduped) <= _MAX_SCENARIOS):
        raise ValueError(
            f"pace scenarios must contain {_MIN_SCENARIOS} to {_MAX_SCENARIOS} "
            f"distinct paces after deduplication, got {len(deduped)}"
        )

    out_of_range = [
        pace for pace in deduped
        if not (_MIN_PACE_MULTIPLIER <= pace <= _MAX_PACE_MULTIPLIER)
    ]
    if out_of_range:
        raise ValueError(
            f"pace scenario values must be in [{_MIN_PACE_MULTIPLIER}, "
            f"{_MAX_PACE_MULTIPLIER}], got {out_of_range}"
        )
    return tuple(deduped)


def _build_stage_scenario_row(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    phase: int,
    pace: float,
    include_alternates: tuple[str, ...],
    pinned: tuple[str, ...],
    banned: tuple[str, ...],
) -> tuple[ScenarioRow, tuple[str, ...]]:
    """Solve one phase at one pace and summarize it as a :class:`ScenarioRow`.

    Reuses the same pipeline pieces the calculator tool assembles by hand
    (``derive_phase_demand -> build_capability_snapshot -> solve_stage ->
    schedule_machines``); nothing here is persisted.
    """
    demand_set = derive_phase_demand(data, phase, pace)
    snapshot = build_capability_snapshot(catalog, data, phase, include_alternates=include_alternates)
    demands = tuple(
        (demand.item_class, demand.required_rate_per_minute) for demand in demand_set.demands
    )
    solve_result = solve_stage(
        catalog,
        snapshot.allowed_recipes,
        demands,
        pinned=frozenset(pinned),
        banned=frozenset(banned),
    )

    if solve_result.status != "optimal":
        message = f"pace {pace}: stage solve stopped ({solve_result.status})"
        detail = "; ".join(solve_result.diagnostics)
        if detail:
            message = f"{message}: {detail}"
        row = ScenarioRow(
            pace=pace,
            window_text=_fmt_hours(demand_set.window_hours),
            node_count=0,
            machine_count=0,
            power_mw=0.0,
            raw_imports=(),
            status=solve_result.status,
        )
        return row, (message,)

    nodes, power, schedule_diagnostics = schedule_machines(catalog, solve_result)
    raw_imports = tuple(
        (imported.item_class, imported.rate_per_min) for imported in solve_result.imports
    )
    row = ScenarioRow(
        pace=pace,
        window_text=_fmt_hours(demand_set.window_hours),
        node_count=len(nodes),
        machine_count=sum(node.machine_count for node in nodes),
        power_mw=power.total_mw,
        raw_imports=raw_imports,
        status=solve_result.status,
    )
    row_diagnostics = tuple(f"pace {pace}: {diag}" for diag in schedule_diagnostics)
    return row, row_diagnostics


def _build_master_scenario_row(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    pace: float,
    include_alternates: tuple[str, ...],
    pinned: tuple[str, ...],
    banned: tuple[str, ...],
) -> tuple[ScenarioRow, tuple[str, ...]]:
    """Build every phase in ``data.phases`` at one pace and summarize the total.

    Reuses :func:`~satisfactory_master_plan.build_master_plan` directly
    (extraction/logistics resolution is adapter-level wiring, out of scope
    for this exploratory comparison). A failed later phase still yields a
    row summarizing whatever built before the stop.
    """
    result = build_master_plan(
        catalog,
        data,
        pace_multiplier=pace,
        include_alternates=include_alternates,
        pinned=pinned,
        banned=banned,
    )

    total_window = sum(stage.window_hours for stage in result.stages)
    node_count = sum(len(stage.nodes) for stage in result.stages)
    machine_count = sum(
        node.machine_count for stage in result.stages for node in stage.nodes
    )
    power_mw = round(sum(stage.power.total_mw for stage in result.stages), 3)

    raw_totals: dict[str, float] = {}
    raw_display: dict[str, str] = {}
    for stage in result.stages:
        for source in stage.sources:
            key = normalize_class_name(source.item_class)
            raw_totals[key] = raw_totals.get(key, 0.0) + source.rate_per_min
            raw_display.setdefault(key, source.item_class)
    raw_imports = tuple(
        (raw_display[key], round(raw_totals[key], 6)) for key in sorted(raw_totals)
    )

    row = ScenarioRow(
        pace=pace,
        window_text=f"{_fmt_hours(total_window)} across {len(result.stages)} phase(s)",
        node_count=node_count,
        machine_count=machine_count,
        power_mw=power_mw,
        raw_imports=raw_imports,
        status=result.status,
    )
    row_diagnostics = tuple(f"pace {pace}: {diag}" for diag in result.diagnostics)
    return row, row_diagnostics


def compare_pace_scenarios(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    paces: tuple[float, ...],
    phase: int | None = None,
    include_alternates: tuple[str, ...] = (),
    pinned: tuple[str, ...] = (),
    banned: tuple[str, ...] = (),
) -> ScenarioComparison:
    """Solve one phase (or the full master build) at up to four paces.

    Args:
        catalog: Docs catalog providing items, recipes, and buildings.
        data: Project Assembly phase data.
        paces: Pace multipliers to compare. Deduplicated preserving first-seen
            order; 1 to 4 distinct values must remain, each in [1.0, 3.0].
        phase: The 1-5 phase number to compare as a single stage, or None to
            compare the full five-phase master build at each pace.
        include_alternates: Alternate recipe class names to allow in every
            scenario's capability snapshot, beyond the default gate.
        pinned: Recipe class names forced in every scenario's solve.
        banned: Recipe class names removed from every scenario's candidate set.

    Returns:
        A :class:`ScenarioComparison` with one :class:`ScenarioRow` per
        distinct pace, in the same (deduplicated) order as ``paces``.

    Raises:
        ValueError: If ``paces`` does not reduce to 1-4 distinct values in
            [1.0, 3.0], or the underlying stage/master build raises (for
            example, an unknown ``phase``).
    """
    deduped_paces = _validate_and_dedupe_paces(paces)

    rows: list[ScenarioRow] = []
    diagnostics: list[str] = []
    for pace in deduped_paces:
        if phase is None:
            row, row_diagnostics = _build_master_scenario_row(
                catalog, data, pace, include_alternates, pinned, banned
            )
        else:
            row, row_diagnostics = _build_stage_scenario_row(
                catalog, data, phase, pace, include_alternates, pinned, banned
            )
        rows.append(row)
        diagnostics.extend(row_diagnostics)

    return ScenarioComparison(rows=tuple(rows), diagnostics=tuple(diagnostics))

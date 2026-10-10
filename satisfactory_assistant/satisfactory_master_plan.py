"""Pure five-stage Project Assembly master plan builder.

Pure module: no Wingman imports, stdlib only besides the sibling
progression, solver, plan-model, and docs modules. Composes the same
per-phase pipeline the calculator tool assembles by hand
(``snapshot -> demand -> solve_stage -> schedule_machines -> StagePlan``)
across every phase in the supplied :class:`~satisfactory_progression.
ProjectAssemblyData`, then classifies how the plan graph changes between
consecutive stages.

Scope: the pure engine only. Checkpoints, tool/persistence wiring, and
reuse-aware (cross-stage) objectives are later packets; each stage here
is solved independently under its own capability gate, using the same
recipe policy every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from satisfactory_docs import DocsCatalog, normalize_class_name
from satisfactory_plan_models import (
    EXTERNAL_DEMAND_NODE_ID,
    RAW_IMPORT_NODE_ID,
    DataProvenance,
    Diagnostic,
    ItemFlow,
    RecipePolicy,
    ResourceSource,
    StagePlan,
    StageTransition,
)
from satisfactory_progression import (
    ProjectAssemblyData,
    build_capability_snapshot,
    derive_phase_demand,
)
from satisfactory_solver import schedule_machines, solve_stage


# Sentinel values stamped on every stage a master plan build produces: a
# master-plan stage is a preview, not a persisted revision, so it is never
# confused with a store-assigned revision or solver run id.
_MASTER_PLAN_REVISION = 0
_MASTER_PLAN_SOLVER_RUN_ID = ""

_STAGE_ASSUMPTIONS = ("clock 1.0 baseline", "extractors not modeled")


@dataclass(frozen=True)
class MasterPlanResult:
    """The full five-stage build: every solved phase plus its cross-stage view.

    ``stages`` holds one :class:`StagePlan` per successfully solved phase,
    in phase order; a failed phase stops the build, so ``stages`` may be
    shorter than the input data's phase count. ``transitions`` holds one
    :class:`StageTransition` per consecutive pair of built stages (always
    ``len(stages) - 1`` entries). ``reservations`` is the informational
    future-demand envelope, one entry per built stage. ``diagnostics``
    aggregates every phase's solver/schedule diagnostics plus teardown
    warnings, each string prefixed with the phase it concerns.
    """

    status: str
    stages: tuple[StagePlan, ...]
    transitions: tuple[StageTransition, ...]
    reservations: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]
    diagnostics: tuple[str, ...]


def _delta_token(node_id: str, delta: int) -> str:
    if delta > 0:
        return f"{node_id}:+{delta}"
    if delta < 0:
        return f"{node_id}:{delta}"
    return f"{node_id}:0"


def diff_stages(previous: StagePlan, current: StagePlan) -> StageTransition:
    """Classify how the plan graph changes between two consecutive stages.

    Node identity is the recipe-keyed ``node_id`` assigned by
    :func:`~satisfactory_solver.schedule_machines` (``"node_" + normalized
    recipe key``): the same recipe running in both stages is the same
    logical module, regardless of where in the factory it sits.

    Every entry in all four result tuples is a ``"node_id:+delta"`` /
    ``"node_id:0"`` / ``"node_id:-delta"`` string, where ``delta`` is the
    change in integer ``machine_count`` for that node between the two
    stages. This lets ``expanded_nodes`` carry both machine-count
    increases (``+delta``) and decreases (``-delta``) without adding a
    fifth category: a node present in both stages with an unchanged count
    goes to ``reused_nodes`` (always ``:0``); a node present in both with
    a changed count, up or down, goes to ``expanded_nodes``; a node only
    in ``current`` goes to ``added_nodes`` (delta is its full count); a
    node only in ``previous`` goes to ``retired_nodes`` (delta is the
    negative of its former count).

    Args:
        previous: The earlier stage's plan.
        current: The later stage's plan.

    Returns:
        The classified :class:`StageTransition` from ``previous.phase``
        to ``current.phase``.
    """
    prev_counts = {node.node_id: node.machine_count for node in previous.nodes}
    curr_counts = {node.node_id: node.machine_count for node in current.nodes}

    reused: list[str] = []
    expanded: list[str] = []
    added: list[str] = []
    retired: list[str] = []

    for node_id in sorted(set(prev_counts) | set(curr_counts)):
        prev_count = prev_counts.get(node_id)
        curr_count = curr_counts.get(node_id)
        if prev_count is not None and curr_count is not None:
            delta = curr_count - prev_count
            (reused if delta == 0 else expanded).append(_delta_token(node_id, delta))
        elif curr_count is not None:
            added.append(_delta_token(node_id, curr_count))
        else:
            retired.append(_delta_token(node_id, -prev_count))

    return StageTransition(
        from_phase=previous.phase,
        to_phase=current.phase,
        reused_nodes=tuple(reused),
        expanded_nodes=tuple(expanded),
        added_nodes=tuple(added),
        retired_nodes=tuple(retired),
    )


def _teardown_warning(from_phase: int, to_phase: int, retired_token: str) -> str:
    """Build a teardown-warning diagnostic for one retired transition entry.

    Guardrail: stages are solved independently, so an equally-valid
    recipe swap (a newly unlocked alternate outcompeting the old choice,
    for instance) can retire a node even though nothing stopped demanding
    its output. Prefer reuse is the goal, not the rule the solver
    enforces this packet, so every such retirement must stay visible
    here rather than being optimized away silently.
    """
    node_id, _, _delta = retired_token.rpartition(":")
    return (
        f"phase {to_phase}: teardown warning: node '{node_id}' was active in "
        f"phase {from_phase} but is retired in phase {to_phase}"
    )


def _build_reservations(
    stages: tuple[StagePlan, ...],
) -> tuple[tuple[int, tuple[tuple[str, int], ...]], ...]:
    """Compute the informational future-reservation envelope per stage.

    The envelope is backward-looking demand awareness only: per node_id,
    the maximum machine_count required by the current stage or any later
    stage. It is reported so a later, reuse-aware pass can plan ahead for
    it, but this packet never treats it as a constraint on the stage it
    is attached to.

    Args:
        stages: The successfully built stages, in phase order.

    Returns:
        One ``(phase, ((node_id, future_max_machines), ...))`` entry per
        stage, the inner tuple sorted by node_id.
    """
    reservations: list[tuple[int, tuple[tuple[str, int], ...]]] = []
    for index, stage in enumerate(stages):
        future_max: dict[str, int] = {}
        for later_stage in stages[index:]:
            for node in later_stage.nodes:
                future_max[node.node_id] = max(
                    future_max.get(node.node_id, 0), node.machine_count
                )
        reservations.append((stage.phase, tuple(sorted(future_max.items()))))
    return tuple(reservations)


def _build_stage(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    phase: int,
    pace_multiplier: float,
    include_alternates: tuple[str, ...],
    pinned: tuple[str, ...],
    banned: tuple[str, ...],
    prior_capacity: dict[str, float] | None,
) -> tuple[StagePlan | None, tuple[str, ...]]:
    """Solve and assemble one phase's :class:`StagePlan`.

    Returns ``(None, diagnostics)`` naming the phase when the stage does
    not solve to ``"optimal"``, or ``(stage, diagnostics)`` on success,
    where ``diagnostics`` are the phase-prefixed solver/schedule notes
    (empty on a clean solve).
    """
    demand_set = derive_phase_demand(data, phase, pace_multiplier)
    snapshot = build_capability_snapshot(
        catalog, data, phase, include_alternates=include_alternates
    )
    demands = tuple(
        (demand.item_class, demand.required_rate_per_minute) for demand in demand_set.demands
    )
    solve_result = solve_stage(
        catalog,
        snapshot.allowed_recipes,
        demands,
        pinned=frozenset(pinned),
        banned=frozenset(banned),
        prior_capacity=prior_capacity,
    )
    if solve_result.status != "optimal":
        detail = "; ".join(solve_result.diagnostics)
        message = f"phase {phase}: stage solve stopped ({solve_result.status})"
        if detail:
            message = f"{message}: {detail}"
        return None, (message,)

    nodes, power, schedule_diagnostics = schedule_machines(catalog, solve_result)

    diagnostics = [
        Diagnostic(
            severity="warning", code="unpowered_building", message=diag, subject="schedule"
        )
        for diag in schedule_diagnostics
    ]
    diagnostics.extend(
        Diagnostic(severity="warning", code="solver_residual", message=diag, subject="solver")
        for diag in solve_result.diagnostics
    )

    sources = tuple(
        ResourceSource(
            node_id=f"raw_{normalize_class_name(imported.item_class)}",
            item_class=imported.item_class,
            rate_per_min=imported.rate_per_min,
            extractor_class="",
            extractor_count=0,
        )
        for imported in solve_result.imports
    )
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

    now = datetime.now().isoformat()
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
            pinned=tuple(pinned),
            banned=tuple(banned),
            allowed_alternates=tuple(include_alternates),
        ),
        diagnostics=tuple(diagnostics),
        assumptions=_STAGE_ASSUMPTIONS,
        provenance=DataProvenance(
            source="master plan build: caller-provided Docs catalog and bundled phase data",
            retrieved=now,
            note=f"phase {phase} solved independently under its own capability gate",
        ),
        solver_run_id=_MASTER_PLAN_SOLVER_RUN_ID,
        revision=_MASTER_PLAN_REVISION,
        created_at=now,
    )
    stage_prefixed = tuple(f"phase {phase}: {diag.message}" for diag in diagnostics)
    return stage, stage_prefixed


def build_master_plan(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    pace_multiplier: float = 1.0,
    include_alternates: tuple[str, ...] = (),
    pinned: tuple[str, ...] = (),
    banned: tuple[str, ...] = (),
) -> MasterPlanResult:
    """Solve every Project Assembly phase and classify stage-to-stage change.

    Each phase is solved independently (its own capability snapshot, the
    same recipe policy every time): snapshot -> demand -> solve_stage ->
    schedule_machines -> :class:`StagePlan`. A phase that does not solve
    to ``"optimal"`` stops the build; every stage solved before it is
    kept, and the result names the failing phase.

    Args:
        catalog: Docs catalog providing items, recipes, and buildings.
        data: Project Assembly phase data to build stages for, in
            ``data.phases`` order (the bundled file is phases 1-5, but
            this function does not require exactly five).
        pace_multiplier: Window-hours multiplier in [1.0, 3.0], applied
            identically to every phase.
        include_alternates: Alternate recipe class names to allow in
            every phase's capability snapshot, beyond the default gate.
        pinned: Recipe class names forced in every phase's solve; passed
            through to :func:`~satisfactory_solver.solve_stage` unchanged.
        banned: Recipe class names removed from every phase's candidate
            set; passed through to :func:`~satisfactory_solver.solve_stage`
            unchanged.

    Returns:
        A :class:`MasterPlanResult` with status ``"complete"`` when every
        phase in ``data.phases`` solved, or ``"stopped_at_phase_N"`` when
        phase ``N`` was the first to fail.
    """
    stages: list[StagePlan] = []
    diagnostics: list[str] = []
    status = "complete"
    # Reuse-aware threading: each built stage's per-recipe machines_exact
    # (from its nodes) becomes the next stage's prior_capacity, so the next
    # phase's level 2 objective prefers reusing this stage's machines over
    # building new ones. Phase 1 has no previous stage, so it solves with
    # prior_capacity=None -- identical to today's level 2.
    prior_capacity: dict[str, float] | None = None

    for definition in sorted(data.phases, key=lambda phase: phase.phase):
        stage, stage_diagnostics = _build_stage(
            catalog,
            data,
            definition.phase,
            pace_multiplier,
            include_alternates,
            pinned,
            banned,
            prior_capacity,
        )
        diagnostics.extend(stage_diagnostics)
        if stage is None:
            status = f"stopped_at_phase_{definition.phase}"
            break
        stages.append(stage)
        prior_capacity = {
            normalize_class_name(node.recipe_class): node.machine_count_exact
            for node in stage.nodes
        }

    transitions: list[StageTransition] = []
    for previous, current in zip(stages, stages[1:]):
        transition = diff_stages(previous, current)
        transitions.append(transition)
        diagnostics.extend(
            _teardown_warning(transition.from_phase, transition.to_phase, token)
            for token in transition.retired_nodes
        )

    return MasterPlanResult(
        status=status,
        stages=tuple(stages),
        transitions=tuple(transitions),
        reservations=_build_reservations(tuple(stages)),
        diagnostics=tuple(diagnostics),
    )

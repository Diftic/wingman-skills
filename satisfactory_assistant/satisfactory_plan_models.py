"""Typed plan models for the Project Assembly factory solver.

Pure module: no Wingman imports, stdlib only. Every model is a frozen
dataclass with a ``to_payload()`` method producing a plain, JSON-able dict
and a module-level ``<snake_name>_from_payload(payload)`` function that
rebuilds the dataclass from such a dict. Unknown keys in a payload are
tolerated (ignored) rather than fatal, so a payload written by a newer
version of this module can still be read by an older one. Reading always
coerces JSON arrays back into tuples, so the round-trip invariant
``x_from_payload(x.to_payload()) == x`` holds under dataclass equality for
every model here.

These models are the typed output home for the Phase 3 solver; this packet
only defines the shapes and their payload round-trip, not the solver logic
that produces them.
"""

from __future__ import annotations

from dataclasses import dataclass


# Sentinel node ids an ItemFlow may reference in place of a real
# ProcessNode/ResourceSource node_id.
EXTERNAL_DEMAND_NODE_ID = "external_demand"
RAW_IMPORT_NODE_ID = "raw_import"

_DIAGNOSTIC_SEVERITIES = frozenset({"info", "warning", "error"})
_RECIPE_POLICY_MODES = frozenset({"standard", "extended"})


@dataclass(frozen=True)
class Diagnostic:
    """A single solver/validation diagnostic surfaced to the player."""

    severity: str
    code: str
    message: str
    subject: str

    def __post_init__(self) -> None:
        if self.severity not in _DIAGNOSTIC_SEVERITIES:
            raise ValueError(
                f"Diagnostic.severity must be one of "
                f"{sorted(_DIAGNOSTIC_SEVERITIES)}, got {self.severity!r}"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "subject": self.subject,
        }


def diagnostic_from_payload(payload: dict[str, object]) -> Diagnostic:
    return Diagnostic(
        severity=str(payload["severity"]),
        code=str(payload["code"]),
        message=str(payload["message"]),
        subject=str(payload["subject"]),
    )


@dataclass(frozen=True)
class DataProvenance:
    """Where a plan's source data came from, for display and audit."""

    source: str
    retrieved: str
    note: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source": self.source,
            "retrieved": self.retrieved,
            "note": self.note,
        }


def data_provenance_from_payload(payload: dict[str, object]) -> DataProvenance:
    return DataProvenance(
        source=str(payload["source"]),
        retrieved=str(payload["retrieved"]),
        note=str(payload["note"]),
    )


@dataclass(frozen=True)
class PacePolicy:
    """The pace at which a stage's demand window is planned."""

    multiplier: float
    window_hours: float

    def to_payload(self) -> dict[str, object]:
        return {
            "multiplier": self.multiplier,
            "window_hours": self.window_hours,
        }


def pace_policy_from_payload(payload: dict[str, object]) -> PacePolicy:
    return PacePolicy(
        multiplier=float(payload["multiplier"]),
        window_hours=float(payload["window_hours"]),
    )


@dataclass(frozen=True)
class RecipePolicy:
    """Recipe selection constraints applied by the solver for a stage."""

    mode: str
    pinned: tuple[str, ...]
    banned: tuple[str, ...]
    allowed_alternates: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.mode not in _RECIPE_POLICY_MODES:
            raise ValueError(
                f"RecipePolicy.mode must be one of {sorted(_RECIPE_POLICY_MODES)}, "
                f"got {self.mode!r}"
            )

    def to_payload(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "pinned": list(self.pinned),
            "banned": list(self.banned),
            "allowed_alternates": list(self.allowed_alternates),
        }


def recipe_policy_from_payload(payload: dict[str, object]) -> RecipePolicy:
    return RecipePolicy(
        mode=str(payload["mode"]),
        pinned=tuple(str(key) for key in payload.get("pinned", [])),
        banned=tuple(str(key) for key in payload.get("banned", [])),
        allowed_alternates=tuple(
            str(key) for key in payload.get("allowed_alternates", [])
        ),
    )


@dataclass(frozen=True)
class ProcessNode:
    """One production step: a recipe running on a building at some clock."""

    node_id: str
    recipe_class: str
    building_class: str
    runs_per_min: float
    machine_count_exact: float
    machine_count: int
    clock: float
    power_mw: float

    def to_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "recipe_class": self.recipe_class,
            "building_class": self.building_class,
            "runs_per_min": self.runs_per_min,
            "machine_count_exact": self.machine_count_exact,
            "machine_count": self.machine_count,
            "clock": self.clock,
            "power_mw": self.power_mw,
        }


def process_node_from_payload(payload: dict[str, object]) -> ProcessNode:
    return ProcessNode(
        node_id=str(payload["node_id"]),
        recipe_class=str(payload["recipe_class"]),
        building_class=str(payload["building_class"]),
        runs_per_min=float(payload["runs_per_min"]),
        machine_count_exact=float(payload["machine_count_exact"]),
        machine_count=int(payload["machine_count"]),
        clock=float(payload["clock"]),
        power_mw=float(payload["power_mw"]),
    )


@dataclass(frozen=True)
class ResourceSource:
    """A raw resource extraction point feeding the plan."""

    node_id: str
    item_class: str
    rate_per_min: float
    extractor_class: str
    extractor_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "node_id": self.node_id,
            "item_class": self.item_class,
            "rate_per_min": self.rate_per_min,
            "extractor_class": self.extractor_class,
            "extractor_count": self.extractor_count,
        }


def resource_source_from_payload(payload: dict[str, object]) -> ResourceSource:
    return ResourceSource(
        node_id=str(payload["node_id"]),
        item_class=str(payload["item_class"]),
        rate_per_min=float(payload["rate_per_min"]),
        extractor_class=str(payload["extractor_class"]),
        extractor_count=int(payload["extractor_count"]),
    )


@dataclass(frozen=True)
class ItemFlow:
    """An item rate moving between two nodes in the plan graph.

    ``source_id``/``dest_id`` reference a ``ProcessNode`` or
    ``ResourceSource`` node_id, or one of the sentinels
    ``EXTERNAL_DEMAND_NODE_ID`` / ``RAW_IMPORT_NODE_ID``.
    """

    item_class: str
    rate_per_min: float
    source_id: str
    dest_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "item_class": self.item_class,
            "rate_per_min": self.rate_per_min,
            "source_id": self.source_id,
            "dest_id": self.dest_id,
        }


def item_flow_from_payload(payload: dict[str, object]) -> ItemFlow:
    return ItemFlow(
        item_class=str(payload["item_class"]),
        rate_per_min=float(payload["rate_per_min"]),
        source_id=str(payload["source_id"]),
        dest_id=str(payload["dest_id"]),
    )


@dataclass(frozen=True)
class PowerPlan:
    """Aggregate power draw for a stage, broken down by building class."""

    total_mw: float
    by_building: tuple[tuple[str, float], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "total_mw": self.total_mw,
            "by_building": [[building_class, mw] for building_class, mw in self.by_building],
        }


def power_plan_from_payload(payload: dict[str, object]) -> PowerPlan:
    return PowerPlan(
        total_mw=float(payload["total_mw"]),
        by_building=tuple(
            (str(building_class), float(mw))
            for building_class, mw in payload.get("by_building", [])
        ),
    )


@dataclass(frozen=True)
class BuildTask:
    """One construction step: build ``count`` of a building at ``node_id``.

    ``node_id`` mirrors the underlying ``ProcessNode``/``ResourceSource``
    node id this task builds out. ``materials`` is the per-build cost times
    ``count`` for every build-gun recipe ingredient (empty when the build
    recipe could not be resolved for this building). ``depends_on`` lists
    the node ids of production nodes whose recipe output this task's recipe
    consumes (direct topological predecessors only, never the transitive
    closure); extractor tasks always have an empty ``depends_on`` since
    they are ordered first, ahead of every production node.
    """

    task_id: str
    order_index: int
    node_id: str
    building_class: str
    count: int
    materials: tuple[tuple[str, float], ...]
    depends_on: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "order_index": self.order_index,
            "node_id": self.node_id,
            "building_class": self.building_class,
            "count": self.count,
            "materials": [
                [item_class, quantity] for item_class, quantity in self.materials
            ],
            "depends_on": list(self.depends_on),
        }


def build_task_from_payload(payload: dict[str, object]) -> BuildTask:
    return BuildTask(
        task_id=str(payload["task_id"]),
        order_index=int(payload["order_index"]),
        node_id=str(payload["node_id"]),
        building_class=str(payload["building_class"]),
        count=int(payload["count"]),
        materials=tuple(
            (str(item_class), float(quantity))
            for item_class, quantity in payload.get("materials", [])
        ),
        depends_on=tuple(str(node_id) for node_id in payload.get("depends_on", [])),
    )


@dataclass(frozen=True)
class StagePlan:
    """A complete, immutable solve for one Project Assembly phase.

    ``demands`` is a tuple of ``(item_class, quantity, rate_per_min)``
    triples. ``solver_run_id`` is None for a plan not tied to a recorded
    solver run (for example, a manual override). ``revision`` and
    ``created_at`` mirror the values assigned by the store on save; they
    are carried on the model so a loaded payload round-trips exactly.
    """

    phase: int
    window_hours: float
    pace_multiplier: float
    demands: tuple[tuple[str, float, float], ...]
    nodes: tuple[ProcessNode, ...]
    sources: tuple[ResourceSource, ...]
    flows: tuple[ItemFlow, ...]
    power: PowerPlan
    recipe_policy: RecipePolicy
    diagnostics: tuple[Diagnostic, ...]
    assumptions: tuple[str, ...]
    provenance: DataProvenance
    solver_run_id: str | None
    revision: int
    created_at: str

    def to_payload(self) -> dict[str, object]:
        return {
            "phase": self.phase,
            "window_hours": self.window_hours,
            "pace_multiplier": self.pace_multiplier,
            "demands": [list(demand) for demand in self.demands],
            "nodes": [node.to_payload() for node in self.nodes],
            "sources": [source.to_payload() for source in self.sources],
            "flows": [flow.to_payload() for flow in self.flows],
            "power": self.power.to_payload(),
            "recipe_policy": self.recipe_policy.to_payload(),
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "assumptions": list(self.assumptions),
            "provenance": self.provenance.to_payload(),
            "solver_run_id": self.solver_run_id,
            "revision": self.revision,
            "created_at": self.created_at,
        }


def stage_plan_from_payload(payload: dict[str, object]) -> StagePlan:
    solver_run_id = payload.get("solver_run_id")
    return StagePlan(
        phase=int(payload["phase"]),
        window_hours=float(payload["window_hours"]),
        pace_multiplier=float(payload["pace_multiplier"]),
        demands=tuple(
            (str(item_class), float(quantity), float(rate_per_min))
            for item_class, quantity, rate_per_min in payload.get("demands", [])
        ),
        nodes=tuple(process_node_from_payload(node) for node in payload.get("nodes", [])),
        sources=tuple(
            resource_source_from_payload(source) for source in payload.get("sources", [])
        ),
        flows=tuple(item_flow_from_payload(flow) for flow in payload.get("flows", [])),
        power=power_plan_from_payload(payload["power"]),
        recipe_policy=recipe_policy_from_payload(payload["recipe_policy"]),
        diagnostics=tuple(
            diagnostic_from_payload(diagnostic) for diagnostic in payload.get("diagnostics", [])
        ),
        assumptions=tuple(str(item) for item in payload.get("assumptions", [])),
        provenance=data_provenance_from_payload(payload["provenance"]),
        solver_run_id=str(solver_run_id) if solver_run_id is not None else None,
        revision=int(payload["revision"]),
        created_at=str(payload["created_at"]),
    )


@dataclass(frozen=True)
class StageTransition:
    """How the plan graph changes between two consecutive phases.

    Minimal today (node-id bookkeeping only); Phase 4 grows this with
    richer diffing once cross-stage queries are needed.
    """

    from_phase: int
    to_phase: int
    reused_nodes: tuple[str, ...]
    expanded_nodes: tuple[str, ...]
    added_nodes: tuple[str, ...]
    retired_nodes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "from_phase": self.from_phase,
            "to_phase": self.to_phase,
            "reused_nodes": list(self.reused_nodes),
            "expanded_nodes": list(self.expanded_nodes),
            "added_nodes": list(self.added_nodes),
            "retired_nodes": list(self.retired_nodes),
        }


def stage_transition_from_payload(payload: dict[str, object]) -> StageTransition:
    return StageTransition(
        from_phase=int(payload["from_phase"]),
        to_phase=int(payload["to_phase"]),
        reused_nodes=tuple(str(node_id) for node_id in payload.get("reused_nodes", [])),
        expanded_nodes=tuple(str(node_id) for node_id in payload.get("expanded_nodes", [])),
        added_nodes=tuple(str(node_id) for node_id in payload.get("added_nodes", [])),
        retired_nodes=tuple(str(node_id) for node_id in payload.get("retired_nodes", [])),
    )


@dataclass(frozen=True)
class FactoryMasterPlan:
    """The top-level plan record a save's stages and solver runs hang off."""

    plan_id: str
    name: str
    created_at: str
    updated_at: str

    def to_payload(self) -> dict[str, object]:
        return {
            "plan_id": self.plan_id,
            "name": self.name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def factory_master_plan_from_payload(payload: dict[str, object]) -> FactoryMasterPlan:
    return FactoryMasterPlan(
        plan_id=str(payload["plan_id"]),
        name=str(payload["name"]),
        created_at=str(payload["created_at"]),
        updated_at=str(payload["updated_at"]),
    )

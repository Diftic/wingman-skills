"""Compare a save-derived factory mirror against a persisted stage plan.

Pure module: only stdlib plus ``satisfactory_docs.normalize_class_name`` (the
same recipe-key normalization ``schedule_machines`` uses to build a
``ProcessNode.node_id``), so a mirror machine's current recipe and a plan
node's ``recipe_class`` land on the same key. Both inputs are plain dicts
(a mirror's ``machines`` list and a stored ``StagePlan`` payload) rather
than typed models, matching how the audit pipeline already has them: a
freshly built mirror and a payload loaded straight from the store, with no
need to round-trip either through their owning module's dataclasses.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from satisfactory_docs import normalize_class_name

_CLASSIFICATION_TOLERANCE = 1e-3
_CATEGORY_ORDER = {"missing": 0, "unplanned": 1, "surplus": 2, "matched": 3}


@dataclass(frozen=True)
class ActualsRow:
    """One recipe key's planned-versus-actual capacity comparison.

    ``planned_capacity`` and ``actual_capacity`` are both machine-equivalent
    counts (the same unit as ``ProcessNode.machine_count_exact``): a machine
    running at half clock contributes 0.5 machine-equivalents, not 1.
    """

    recipe_key: str
    planned_capacity: float
    actual_capacity: float
    delta: float
    classification: str


@dataclass(frozen=True)
class ActualsComparison:
    """The full planned-versus-actual audit for one stage plan revision."""

    rows: tuple[ActualsRow, ...]
    planned_total: float
    actual_total: float
    save_name: str
    plan_phase: int
    plan_revision: int
    diagnostics: tuple[str, ...]


def _planned_capacity_by_key(stage_payload: dict[str, Any]) -> dict[str, float]:
    planned: dict[str, float] = {}
    for node in stage_payload.get("nodes", []):
        key = normalize_class_name(node.get("recipe_class"))
        planned[key] = planned.get(key, 0.0) + float(node.get("machine_count_exact", 0.0))
    return planned


def _machine_clock(machine: dict[str, Any]) -> tuple[float, bool]:
    """Return ``(clock, was_unknown)`` for one mirror machine dict.

    A machine at 0.5 clock contributes 0.5 machine-equivalents to its
    recipe's actual capacity; a missing, non-numeric, or non-positive clock
    is unknowable, so it counts as a full machine-equivalent (1.0) and is
    flagged so the caller can surface a note rather than silently trusting
    fabricated data.
    """
    raw = machine.get("clock")
    try:
        if raw is None:
            return 1.0, True
        value = float(raw)
    except (TypeError, ValueError):
        return 1.0, True
    if not math.isfinite(value) or value <= 0:
        return 1.0, True
    return value, False


def _actual_capacity_by_key(mirror_machines: list[dict[str, Any]]) -> tuple[dict[str, float], int]:
    actual: dict[str, float] = {}
    unknown_count = 0
    for machine in mirror_machines:
        recipe_name = machine.get("recipe")
        if not recipe_name:
            # Extractors and idle machines carry no recipe; resource-well
            # actuals are tracked separately (still a TODO), not compared here.
            continue
        key = normalize_class_name(recipe_name)
        clock, was_unknown = _machine_clock(machine)
        actual[key] = actual.get(key, 0.0) + clock
        if was_unknown:
            unknown_count += 1
    return actual, unknown_count


def _classify(key: str, planned: float, actual: float, planned_capacity: dict[str, float]) -> str:
    if key not in planned_capacity:
        return "unplanned"
    if actual < planned - _CLASSIFICATION_TOLERANCE:
        return "missing"
    if abs(actual - planned) <= _CLASSIFICATION_TOLERANCE:
        return "matched"
    return "surplus"


def _sort_key(row: ActualsRow) -> tuple[int, float, str]:
    order = _CATEGORY_ORDER[row.classification]
    if row.classification == "missing":
        shortfall = row.planned_capacity - row.actual_capacity
        return (order, -shortfall, row.recipe_key)
    return (order, 0.0, row.recipe_key)


def compare_actuals(
    mirror_machines: list[dict[str, Any]],
    stage_payload: dict[str, Any],
    *,
    save_name: str = "",
) -> ActualsComparison:
    """Compare a mirror's machines against a stored stage plan's nodes.

    Per normalized recipe key (``satisfactory_docs.normalize_class_name``,
    matching the key ``schedule_machines`` embeds in ``ProcessNode.node_id``):
    planned capacity is the summed ``machine_count_exact`` of every plan node
    with that key; actual capacity is the summed clock of every mirror
    machine whose current recipe normalizes to that key. A key with a
    planned node but zero matching machines classifies "missing" with an
    actual capacity of 0.0.

    Args:
        mirror_machines: The mirror's ``machines`` list (each a dict with
            ``recipe``, ``clock``, and ``confidence`` fields, per
            ``satisfactory_mirror.machine_expected_state``).
        stage_payload: A stored ``StagePlan`` payload (``StagePlan.to_payload()``
            shape, e.g. as returned by ``SaveStore.load_stage_plan``).
        save_name: Optional save name to carry as provenance; the caller
            supplies it since neither input above names the save.

    Returns:
        An ``ActualsComparison`` with rows sorted missing (largest shortfall
        first), then unplanned, surplus, matched (each group alphabetical by
        recipe key for determinism).
    """
    planned_capacity = _planned_capacity_by_key(stage_payload)
    actual_capacity, unknown_clock_count = _actual_capacity_by_key(mirror_machines)

    keys = set(planned_capacity) | set(actual_capacity)
    rows = []
    for key in keys:
        planned = planned_capacity.get(key, 0.0)
        actual = actual_capacity.get(key, 0.0)
        classification = _classify(key, planned, actual, planned_capacity)
        rows.append(
            ActualsRow(
                recipe_key=key,
                planned_capacity=planned,
                actual_capacity=actual,
                delta=actual - planned,
                classification=classification,
            )
        )
    rows.sort(key=_sort_key)

    diagnostics: list[str] = []
    if unknown_clock_count:
        diagnostics.append(
            f"{unknown_clock_count} machine(s) had unresolved clock data; assumed 1.0 (100%)."
        )

    return ActualsComparison(
        rows=tuple(rows),
        planned_total=sum(planned_capacity.values()),
        actual_total=sum(actual_capacity.values()),
        save_name=save_name,
        plan_phase=int(stage_payload.get("phase", 0)),
        plan_revision=int(stage_payload.get("revision", 0)),
        diagnostics=tuple(diagnostics),
    )

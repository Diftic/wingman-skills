"""Belt/pipe capacity checks and byproduct surplus detection.

Pure module: no Wingman imports, stdlib only besides its sibling pure
modules. Mirrors the per-item rate math ``satisfactory_solver`` uses
(``catalog.rate_amount(item) * node.runs_per_min``) instead of importing the
solver's own private helpers, so this module has no dependency on solver
internals.
"""

from __future__ import annotations

import math

from satisfactory_docs import DocsCatalog, Logistics, normalize_class_name
from satisfactory_plan_models import Diagnostic, ProcessNode, ResourceSource
from satisfactory_progression import CapabilitySnapshot


_FLUID_FORMS = frozenset({"RF_LIQUID", "RF_GAS"})
_MULTI_LINE_WARNING_THRESHOLD = 4
_SURPLUS_EPSILON = 1e-6
_LINE_COUNT_NUDGE = 1e-9


def _unlock_recipe_key(class_name: str) -> str:
    """Derive the build-gun recipe key that unlocks a belt/pipe buildable.

    Every ``FGBuildableConveyorBelt``/``FGBuildablePipeline`` class name
    follows the Docs' ``Build_<Suffix>`` convention with a matching
    ``Recipe_<Suffix>`` build-gun recipe (verified against every belt and
    pipe tier in the real Satisfactory Docs: e.g. ``Build_ConveyorBeltMk4_C``
    / ``Recipe_ConveyorBeltMk4_C`` and ``Build_PipelineMK2_C`` /
    ``Recipe_PipelineMK2_C``).
    """
    key = normalize_class_name(class_name)
    if key.startswith("build_"):
        return "recipe_" + key[len("build_") :]
    return key


def _is_tier_available(
    catalog: DocsCatalog, snapshot: CapabilitySnapshot, entry: Logistics
) -> bool:
    """True when ``entry``'s unlocking schematic (if any) is purchased.

    A tier with no unlocking schematic at all is always available, mirroring
    ``build_capability_snapshot``'s treatment of ungated base recipes.
    """
    unlocking = catalog.recipe_unlocked_by(_unlock_recipe_key(entry.class_name))
    if not unlocking:
        return True
    return any(key in snapshot.purchased_schematics for key in unlocking)


def _resolve_best_tier(
    catalog: DocsCatalog, snapshot: CapabilitySnapshot, tiers: tuple[Logistics, ...]
) -> tuple[Logistics | None, str | None]:
    """Return the highest-capacity tier available to ``snapshot``.

    ``tiers`` is expected sorted ascending by capacity (as ``belts()``/
    ``pipes()`` return them). Returns ``(None, None)`` when the Docs catalog
    parsed no tiers of this kind at all (a partial/fixture Docs file), which
    degrades every downstream check to a no-op rather than raising. Falls
    back to the lowest tier with a diagnostic when tiers exist but none
    resolve as unlocked for this snapshot.
    """
    if not tiers:
        return None, None
    for entry in reversed(tiers):
        if _is_tier_available(catalog, snapshot, entry):
            return entry, None
    fallback = tiers[0]
    return fallback, (
        f"no belt/pipe tier resolved as unlocked for this snapshot; defaulting "
        f"to the lowest tier '{fallback.display_name}'"
    )


def _tier_for_item(
    catalog: DocsCatalog,
    item_key: str,
    belt_tier: Logistics | None,
    pipe_tier: Logistics | None,
) -> Logistics | None:
    item = catalog.item(item_key)
    is_pipe = item is not None and item.form in _FLUID_FORMS
    return pipe_tier if is_pipe else belt_tier


def _line_diagnostics(
    subject: str, item_display: str, rate: float, tier: Logistics
) -> tuple[Diagnostic, ...]:
    lines_needed = math.ceil(rate / tier.capacity - _LINE_COUNT_NUDGE)
    if lines_needed <= 1:
        return ()
    diagnostics = [
        Diagnostic(
            severity="info",
            code="logistics_multi_line",
            message=(
                f"{subject}: item {item_display} needs {lines_needed} lines of "
                f"{tier.display_name}"
            ),
            subject="logistics",
        )
    ]
    if lines_needed > _MULTI_LINE_WARNING_THRESHOLD:
        diagnostics.append(
            Diagnostic(
                severity="warning",
                code="logistics_capacity_warning",
                message=(
                    f"{subject}: item {item_display} needs {lines_needed} lines of "
                    f"{tier.display_name}, exceeding the "
                    f"{_MULTI_LINE_WARNING_THRESHOLD}-line visibility threshold"
                ),
                subject="logistics",
            )
        )
    return tuple(diagnostics)


def _node_line_diagnostics(
    catalog: DocsCatalog,
    node: ProcessNode,
    belt_tier: Logistics | None,
    pipe_tier: Logistics | None,
) -> tuple[Diagnostic, ...]:
    """Recompute a node's per-item rates (mirrors the solver's own math) and check them."""
    recipe = catalog.recipe(node.recipe_class)
    if recipe is None:
        return ()
    diagnostics: list[Diagnostic] = []
    for item_amount in (*recipe.products, *recipe.ingredients):
        item_key = normalize_class_name(item_amount.class_name)
        tier = _tier_for_item(catalog, item_key, belt_tier, pipe_tier)
        if tier is None:
            continue
        rate = catalog.rate_amount(item_amount) * node.runs_per_min
        if rate <= 0.0:
            continue
        diagnostics.extend(
            _line_diagnostics(
                f"node {node.node_id}", catalog.item_display_name(item_key), rate, tier
            )
        )
    return tuple(diagnostics)


def _source_line_diagnostics(
    catalog: DocsCatalog,
    source: ResourceSource,
    belt_tier: Logistics | None,
    pipe_tier: Logistics | None,
) -> tuple[Diagnostic, ...]:
    if source.rate_per_min <= 0.0:
        return ()
    item_key = normalize_class_name(source.item_class)
    tier = _tier_for_item(catalog, item_key, belt_tier, pipe_tier)
    if tier is None:
        return ()
    return _line_diagnostics(
        f"source {source.node_id}",
        catalog.item_display_name(item_key),
        source.rate_per_min,
        tier,
    )


def _aggregate_item_flows(
    catalog: DocsCatalog, nodes: tuple[ProcessNode, ...]
) -> dict[str, tuple[float, float]]:
    """Return normalized item key -> (produced_per_min, consumed_per_min) across all nodes."""
    flows: dict[str, list[float]] = {}
    for node in nodes:
        recipe = catalog.recipe(node.recipe_class)
        if recipe is None:
            continue
        for product in recipe.products:
            key = normalize_class_name(product.class_name)
            flows.setdefault(key, [0.0, 0.0])[0] += (
                catalog.rate_amount(product) * node.runs_per_min
            )
        for ingredient in recipe.ingredients:
            key = normalize_class_name(ingredient.class_name)
            flows.setdefault(key, [0.0, 0.0])[1] += (
                catalog.rate_amount(ingredient) * node.runs_per_min
            )
    return {key: (produced, consumed) for key, (produced, consumed) in flows.items()}


def _surplus_diagnostics(
    catalog: DocsCatalog,
    nodes: tuple[ProcessNode, ...],
    demands: tuple[tuple[str, float], ...],
) -> tuple[Diagnostic, ...]:
    """Emit one diagnostic per item whose production exceeds consumption plus demand."""
    flows = _aggregate_item_flows(catalog, nodes)
    demand_by_item: dict[str, float] = {}
    for item_class, rate in demands:
        key = normalize_class_name(item_class)
        demand_by_item[key] = demand_by_item.get(key, 0.0) + rate

    diagnostics: list[Diagnostic] = []
    for item_key in sorted(flows):
        produced, consumed = flows[item_key]
        surplus = produced - consumed - demand_by_item.get(item_key, 0.0)
        if surplus > _SURPLUS_EPSILON:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="byproduct_surplus",
                    message=(
                        f"surplus: {catalog.item_display_name(item_key)} at "
                        f"{surplus:.3f}/min; route to sink or storage"
                    ),
                    subject="logistics",
                )
            )
    return tuple(diagnostics)


def check_logistics(
    catalog: DocsCatalog,
    snapshot: CapabilitySnapshot,
    nodes: tuple[ProcessNode, ...],
    sources: tuple[ResourceSource, ...],
    demands: tuple[tuple[str, float], ...] = (),
) -> tuple[tuple[Diagnostic, ...], tuple[str, ...]]:
    """Check every node/source item rate against the best gated logistics tier.

    Gates the highest belt/pipe tier whose build-gun recipe is unlocked by
    ``snapshot`` (falling back to the lowest tier with a diagnostic if none
    resolve), recomputes each :class:`ProcessNode`'s per-item production and
    consumption rates the same way the solver derives them
    (``catalog.rate_amount(item) * node.runs_per_min``), and checks every
    node and :class:`ResourceSource` rate against that tier's capacity.
    Also computes per-item surplus (production - consumption - demand)
    across every node and flags anything left over as an unmodeled
    byproduct.

    A Docs catalog with no parsed belts or pipes (a partial/fixture catalog)
    degrades every check for that kind to a no-op instead of raising.

    Args:
        catalog: Docs catalog providing recipes, items, and logistics tiers.
        snapshot: Capability snapshot gating which belt/pipe tier is unlocked.
        nodes: Solved process nodes for this stage.
        sources: Solved raw-resource extraction sources for this stage.
        demands: ``(item_class, rate_per_min)`` pairs this stage must
            satisfy externally, used only for surplus detection.

    Returns:
        A ``(diagnostics, assumptions)`` pair. ``assumptions`` always notes
        which tier was gated for belts/pipes that resolved, plus the
        surplus-handling assumption when any surplus diagnostic fired.
    """
    belt_tier, belt_fallback_diag = _resolve_best_tier(catalog, snapshot, catalog.belts())
    pipe_tier, pipe_fallback_diag = _resolve_best_tier(catalog, snapshot, catalog.pipes())

    diagnostics: list[Diagnostic] = []
    for message in (belt_fallback_diag, pipe_fallback_diag):
        if message is not None:
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="logistics_tier_fallback",
                    message=message,
                    subject="logistics",
                )
            )

    for node in nodes:
        diagnostics.extend(_node_line_diagnostics(catalog, node, belt_tier, pipe_tier))
    for source in sources:
        diagnostics.extend(_source_line_diagnostics(catalog, source, belt_tier, pipe_tier))

    surplus_diagnostics = _surplus_diagnostics(catalog, nodes, demands)
    diagnostics.extend(surplus_diagnostics)

    assumptions: list[str] = []
    if belt_tier is not None:
        assumptions.append(
            f"belt logistics gated to '{belt_tier.display_name}' for this snapshot"
        )
    if pipe_tier is not None:
        assumptions.append(
            f"pipe logistics gated to '{pipe_tier.display_name}' for this snapshot"
        )
    if surplus_diagnostics:
        assumptions.append("surpluses require sink or storage (unmodeled)")

    return tuple(diagnostics), tuple(assumptions)

"""Construction bill of materials and commissioning order for a stage plan.

Pure module: no Wingman imports, stdlib only besides its sibling pure
modules. For an already-solved ``StagePlan``, resolves each node/source's
build-gun recipe into a scaled materials list, aggregates the stage-wide
bill of materials, and orders every build task deterministically:
extractor sources first, then production nodes in the topological order
of the recipe graph (an edge runs from node A to node B when A's recipe
outputs an item B's recipe consumes).

Belt, pipe, and foundation costs are out of scope here (those lengths are
a layout concern, tracked for Phase 9), and power-first staging is
recorded only as an assumption string, since generator buildings are not
modeled by this solver.
"""

from __future__ import annotations

from satisfactory_docs import DocsCatalog, Recipe, normalize_class_name
from satisfactory_plan_models import BuildTask, Diagnostic, ProcessNode, StagePlan


_BUILD_PREFIX = "build_"
_RECIPE_PREFIX = "recipe_"
_DESC_PREFIX = "desc_"
_MATERIAL_DECIMALS = 3

_CONSTRUCTION_ASSUMPTIONS = (
    "belt, pipe, and foundation construction costs are not included in "
    "any bill of materials here (lengths are a layout concern, tracked "
    "for Phase 9)",
    "commissioning order assumes power-first staging; generator "
    "buildings are unmodeled by this solver",
)


def _expected_product_suffix(building_class: str) -> str | None:
    """Return the normalized suffix a ``building_class``'s own item descriptor must match.

    None when ``building_class`` does not follow the ``Build_<Suffix>_C``
    convention at all (nothing to resolve).
    """
    key = normalize_class_name(building_class)
    if not key.startswith(_BUILD_PREFIX):
        return None
    return key[len(_BUILD_PREFIX) :]


def _produces_building(recipe: Recipe, suffix: str) -> bool:
    """True when ``recipe``'s sole product is the building matching ``suffix``."""
    if len(recipe.products) != 1:
        return False
    product_key = normalize_class_name(recipe.products[0].class_name)
    if product_key.startswith(_DESC_PREFIX):
        product_key = product_key[len(_DESC_PREFIX) :]
    return product_key == suffix


def _resolve_build_recipe(catalog: DocsCatalog, building_class: str) -> Recipe | None:
    """Resolve ``building_class``'s build-gun recipe, verified by product identity.

    Tries the "build_x" -> "recipe_x" convention first (confirmed for belts
    and pipes in P5-W04, and independently confirmed against the real Docs
    for Constructor, Assembler, MinerMk2, OilPump, and WaterPump ahead of
    this packet), requiring the resolved recipe's sole product to actually
    be this building. That convention is not reliable on its own, though:
    the real Docs' ``Recipe_SmelterMk1_C`` key-collides with the Foundry's
    build recipe (a stale class name left over from an earlier game
    version, still producing ``Desc_FoundryMk1_C``), while the Smelter's
    real build recipe lives at a differently-named class,
    ``Recipe_SmelterBasicMk1_C``. So when the keyed lookup misses or fails
    the product check, fall back to scanning every recipe in the catalog
    for one whose sole product is this building's own item descriptor,
    picking the lexicographically smallest class name when more than one
    matches (recipe class names are unique in practice, but this keeps the
    choice deterministic either way). Only when both paths fail is the
    build recipe treated as unresolved.
    """
    suffix = _expected_product_suffix(building_class)
    if suffix is None:
        return None

    keyed_recipe = catalog.recipe(_RECIPE_PREFIX + suffix)
    if keyed_recipe is not None and _produces_building(keyed_recipe, suffix):
        return keyed_recipe

    candidates = sorted(
        (recipe for recipe in catalog.all_recipes() if _produces_building(recipe, suffix)),
        key=lambda recipe: recipe.class_name,
    )
    return candidates[0] if candidates else None


def _resolve_materials(
    catalog: DocsCatalog, building_class: str, count: int, subject: str
) -> tuple[tuple[tuple[str, float], ...], tuple[Diagnostic, ...]]:
    """Resolve one build task's materials, scaled by ``count``.

    Returns an empty materials tuple and a diagnostic (never raises) when
    ``building_class``'s build-gun recipe cannot be resolved.
    """
    recipe = _resolve_build_recipe(catalog, building_class)
    if recipe is None:
        return (), (
            Diagnostic(
                severity="warning",
                code="missing_build_recipe",
                message=(
                    f"{subject}: no build-gun recipe resolved for "
                    f"'{building_class}'; materials list left empty"
                ),
                subject="construction",
            ),
        )
    materials = tuple(
        (ingredient.class_name, round(catalog.rate_amount(ingredient) * count, _MATERIAL_DECIMALS))
        for ingredient in recipe.ingredients
    )
    return materials, ()


def _recipe_item_sets(
    catalog: DocsCatalog, node: ProcessNode
) -> tuple[frozenset[str], frozenset[str]]:
    """Return a node's (normalized products, normalized ingredients) item keys."""
    recipe = catalog.recipe(node.recipe_class)
    if recipe is None:
        return frozenset(), frozenset()
    products = frozenset(normalize_class_name(item.class_name) for item in recipe.products)
    ingredients = frozenset(
        normalize_class_name(item.class_name) for item in recipe.ingredients
    )
    return products, ingredients


def _build_recipe_graph_edges(
    catalog: DocsCatalog, nodes: tuple[ProcessNode, ...]
) -> tuple[tuple[str, str], ...]:
    """Return every (a, b) edge where node a's recipe output feeds node b's recipe."""
    item_sets = {node.node_id: _recipe_item_sets(catalog, node) for node in nodes}
    edges: set[tuple[str, str]] = set()
    for a in nodes:
        a_products, _ = item_sets[a.node_id]
        if not a_products:
            continue
        for b in nodes:
            if a.node_id == b.node_id:
                continue
            _, b_ingredients = item_sets[b.node_id]
            if a_products & b_ingredients:
                edges.add((a.node_id, b.node_id))
    return tuple(sorted(edges))


def _topological_order(
    node_ids: tuple[str, ...], edges: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, ...], tuple[Diagnostic, ...]]:
    """Order ``node_ids`` so every edge's source precedes its destination.

    Classic Kahn's algorithm, picking the lexicographically smallest ready
    node at each step so ties resolve deterministically by node id. A
    remaining cycle (every node still has an unresolved predecessor) is
    broken by discarding the lexicographically smallest back-edge still
    inside the remaining subgraph and recording a diagnostic, then
    resuming; this always terminates since each break strictly shrinks the
    edge set, and repeated runs on the same graph produce the same order
    and the same diagnostics.
    """
    adjacency: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
    indegree: dict[str, int] = dict.fromkeys(node_ids, 0)
    for a, b in edges:
        if b not in adjacency[a]:
            adjacency[a].add(b)
            indegree[b] += 1

    remaining = set(node_ids)
    order: list[str] = []
    diagnostics: list[Diagnostic] = []
    while remaining:
        ready = sorted(node_id for node_id in remaining if indegree[node_id] == 0)
        if not ready:
            cycle_edges = sorted(
                (a, b) for a in remaining for b in adjacency[a] if b in remaining
            )
            broken_a, broken_b = cycle_edges[0]
            adjacency[broken_a].discard(broken_b)
            indegree[broken_b] -= 1
            diagnostics.append(
                Diagnostic(
                    severity="warning",
                    code="construction_order_cycle",
                    message=(
                        f"recipe dependency cycle detected in the commissioning "
                        f"order; broke edge {broken_a} -> {broken_b} to continue"
                    ),
                    subject="construction",
                )
            )
            continue
        node_id = ready[0]
        order.append(node_id)
        remaining.discard(node_id)
        for successor in adjacency[node_id]:
            if successor in remaining:
                indegree[successor] -= 1
    return tuple(order), tuple(diagnostics)


def _predecessor_map(
    node_ids: tuple[str, ...], edges: tuple[tuple[str, str], ...]
) -> dict[str, tuple[str, ...]]:
    """Map each node id to its direct predecessor node ids, sorted."""
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for a, b in edges:
        predecessors[b].append(a)
    return {node_id: tuple(sorted(preds)) for node_id, preds in predecessors.items()}


def _accumulate_bom(
    bom: dict[str, float],
    canonical_names: dict[str, str],
    materials: tuple[tuple[str, float], ...],
) -> None:
    for item_class, quantity in materials:
        key = normalize_class_name(item_class)
        bom[key] = bom.get(key, 0.0) + quantity
        canonical_names.setdefault(key, item_class)


def build_construction_plan(
    catalog: DocsCatalog, stage: StagePlan
) -> tuple[
    tuple[BuildTask, ...], tuple[tuple[str, float], ...], tuple[Diagnostic, ...], tuple[str, ...]
]:
    """Compute construction bills and commissioning order for ``stage``.

    Ordering: every resolved extractor ``ResourceSource`` first (sorted by
    node id), then every ``ProcessNode`` in topological order of the
    recipe graph (ties broken by node id; cycles broken deterministically,
    see :func:`_topological_order`). A ``ResourceSource`` with no resolved
    extractor (``extractor_class`` empty or ``extractor_count`` <= 0, per
    ``plan_extraction``'s degraded-extraction shape) contributes no build
    task, since there is nothing to construct for it yet.

    Args:
        catalog: Docs catalog providing recipes and build-gun recipes.
        stage: A solved stage plan (nodes, sources) to build tasks for.

    Returns:
        A ``(tasks, stage_bom, diagnostics, assumptions)`` tuple:
        ``tasks`` in commissioning order, ``stage_bom`` as normalized-key-
        deduplicated ``(item_class, quantity)`` pairs sorted by item class,
        ``diagnostics`` for any unresolved build recipe or broken cycle,
        and ``assumptions`` noting the belt/pipe/foundation and
        power-first exclusions (always present, even with no tasks).
    """
    diagnostics: list[Diagnostic] = []
    tasks: list[BuildTask] = []
    bom: dict[str, float] = {}
    canonical_names: dict[str, str] = {}
    order_index = 0

    resolved_sources = [
        source
        for source in stage.sources
        if source.extractor_class and source.extractor_count > 0
    ]
    for source in sorted(resolved_sources, key=lambda source: source.node_id):
        materials, task_diagnostics = _resolve_materials(
            catalog, source.extractor_class, source.extractor_count, f"source {source.node_id}"
        )
        diagnostics.extend(task_diagnostics)
        tasks.append(
            BuildTask(
                task_id=f"task_{order_index}_{source.node_id}",
                order_index=order_index,
                node_id=source.node_id,
                building_class=source.extractor_class,
                count=source.extractor_count,
                materials=materials,
                depends_on=(),
            )
        )
        _accumulate_bom(bom, canonical_names, materials)
        order_index += 1

    node_ids = tuple(sorted(node.node_id for node in stage.nodes))
    edges = _build_recipe_graph_edges(catalog, stage.nodes)
    node_order, cycle_diagnostics = _topological_order(node_ids, edges)
    diagnostics.extend(cycle_diagnostics)
    depends_on_map = _predecessor_map(node_ids, edges)
    nodes_by_id = {node.node_id: node for node in stage.nodes}

    for node_id in node_order:
        node = nodes_by_id[node_id]
        materials, task_diagnostics = _resolve_materials(
            catalog, node.building_class, node.machine_count, f"node {node.node_id}"
        )
        diagnostics.extend(task_diagnostics)
        tasks.append(
            BuildTask(
                task_id=f"task_{order_index}_{node.node_id}",
                order_index=order_index,
                node_id=node.node_id,
                building_class=node.building_class,
                count=node.machine_count,
                materials=materials,
                depends_on=depends_on_map.get(node.node_id, ()),
            )
        )
        _accumulate_bom(bom, canonical_names, materials)
        order_index += 1

    stage_bom = tuple(
        (canonical_names[key], round(quantity, _MATERIAL_DECIMALS))
        for key, quantity in sorted(bom.items())
    )
    return tuple(tasks), stage_bom, tuple(diagnostics), _CONSTRUCTION_ASSUMPTIONS

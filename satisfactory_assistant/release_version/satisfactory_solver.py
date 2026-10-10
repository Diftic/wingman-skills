"""Solver core: gated candidate graph and material-balance LP.

Pure module: no Wingman runtime imports. ``scipy`` is imported lazily
inside :func:`solve_stage` so this module always imports cleanly even on
an install missing scipy; the function returns a diagnostic result
instead of crashing in that case. ``numpy`` is a hard dependency (already
required by the rest of the skill) and is imported at module level.

Scope: recipe run rates (``machines_exact``, a machine-equivalent scale
factor at a fixed clock of 1.0) and raw-resource imports from
:func:`solve_stage`; integer machine schedules, group underclocking, and
power budgets from :func:`schedule_machines`.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np

from satisfactory_docs import Building, DocsCatalog, ItemAmount, Recipe, normalize_class_name
from satisfactory_plan_models import PowerPlan, ProcessNode


_CLAMP_EPSILON = 1e-6
_RESIDUAL_TOLERANCE = -1e-5
_RECIPE_STABILITY_WEIGHT = 1e-6
_RAW_IMPORT_WEIGHT = 1.0
_NON_AUTOMATABLE_BUILDING_MARKERS = ("workbench", "workshop")
_MACHINE_CEIL_NUDGE = 1e-9
_CLOCK_FLOOR = 0.01
_POWER_DECIMALS = 3
_LEVEL2_RAW_TOLERANCE = 1e-9


@dataclass(frozen=True)
class RecipeRun:
    """One candidate recipe's solved run rate.

    ``machines_exact`` is machine-equivalents at 100 percent clock (the LP
    coefficient basis), not a runs-per-minute figure; :func:`schedule_machines`
    turns it into an integer machine count, a clock, and a true
    runs-per-minute rate.
    """

    recipe_class: str
    display_name: str
    machines_exact: float
    building_class: str


@dataclass(frozen=True)
class RawImport:
    """One raw resource's solved import rate."""

    item_class: str
    display_name: str
    rate_per_min: float


@dataclass(frozen=True)
class SolveResult:
    """Result of :func:`solve_stage`.

    Attributes:
        status: One of ``"optimal"``, ``"infeasible"``, ``"no_candidates"``.
        runs: Non-zero recipe runs, sorted by normalized class key.
        imports: Non-zero raw imports, sorted by normalized class key.
        satisfied_demands: Normalized demand item keys satisfied by this
            result; empty unless status is ``"optimal"``.
        diagnostics: Human-readable diagnostic strings; never fabricated,
            only describing what the solver actually observed.
    """

    status: str
    runs: tuple[RecipeRun, ...]
    imports: tuple[RawImport, ...]
    satisfied_demands: tuple[str, ...]
    diagnostics: tuple[str, ...]


def _resolve_building(catalog: DocsCatalog, recipe: Recipe) -> Building | None:
    """Return the recipe's building: its first automatable produced_in entry.

    Mirrors the automatable-building filter used by
    ``DocsCatalog.automatable_recipes()``, but walks ``produced_in`` in its
    original (not sorted) order since only the first match determines
    which building's ``manufacturing_speed`` applies to this recipe.
    """
    for path in recipe.produced_in:
        key = normalize_class_name(path)
        if not key.startswith("build_"):
            continue
        if any(marker in key for marker in _NON_AUTOMATABLE_BUILDING_MARKERS):
            continue
        building = catalog.building(key)
        if building is not None:
            return building
    return None


def _item_rate(catalog: DocsCatalog, amount: ItemAmount, recipe: Recipe, building: Building) -> float:
    """Item flow rate per unit of recipe run-rate, in items (or m3) per minute.

    ``amount / duration_seconds * 60`` is one building's natural output at
    its ``manufacturing_speed`` (clock fixed at 1.0 this packet); the LP
    variable scales this per-building rate, so this is the constraint
    coefficient for that (recipe, item) pair.
    """
    return catalog.rate_amount(amount) / recipe.duration_seconds * 60.0 * building.manufacturing_speed


def _diagnose_unproducible(
    catalog: DocsCatalog,
    item_key: str,
    allowed_recipes: frozenset[str],
    effective_banned: frozenset[str],
) -> str:
    """Explain why a demand item is unproducible: banned, closed-gate, or no-recipe.

    Distinguishes a ban-caused dead end (the item had an allowed producer
    that a ban then removed) from the pre-existing closed-gate case (no
    producer was ever unlocked), so the diagnostic names the specific ban
    responsible instead of pointing at ``allowed_recipes`` generically.
    """
    producer_keys = {
        normalize_class_name(recipe.class_name)
        for recipe in catalog.all_recipes()
        if any(normalize_class_name(product.class_name) == item_key for product in recipe.products)
    }
    if not producer_keys:
        return f"unproducible '{item_key}': no recipe in the catalog produces it (no-recipe)"
    banned_producers = sorted(producer_keys & allowed_recipes & effective_banned)
    if banned_producers:
        return (
            f"unproducible '{item_key}': recipe(s) {banned_producers} would produce it "
            f"but are banned (ban-excluded)"
        )
    return (
        f"unproducible '{item_key}': recipe(s) exist but none are unlocked in "
        f"allowed_recipes (closed-gate)"
    )


def solve_stage(
    catalog: DocsCatalog,
    allowed_recipes: frozenset[str],
    demands: tuple[tuple[str, float], ...],
    *,
    pinned: frozenset[str] = frozenset(),
    banned: frozenset[str] = frozenset(),
    prior_capacity: dict[str, float] | None = None,
) -> SolveResult:
    """Solve one stage's material balance: recipe run rates and raw imports.

    Args:
        catalog: Docs catalog providing items, recipes, and buildings.
        allowed_recipes: Normalized recipe class keys unlocked for this
            stage (the gate); only automatable recipes in this set are
            candidates.
        demands: ``(item_class, required_rate_per_minute)`` pairs; item
            classes are normalized (idempotent if already normalized).
            Repeated items accumulate.
        pinned: Recipe class keys the caller has chosen to force. Each one
            must already be in ``allowed_recipes`` (a pin never smuggles a
            locked recipe in); pinning a recipe bans every other recipe
            that produces its first-listed ("primary") product, so a
            competing recipe for the same item cannot be selected instead.
        banned: Recipe class keys removed from the candidate set before
            reachability is checked, as if they were never unlocked.
        prior_capacity: Recipe class key -> ``machines_exact`` already
            built for that recipe in a previous stage. When given, level
            2's objective minimizes NEW machine-equivalents (the amount by
            which each recipe's run rate exceeds its prior capacity)
            instead of the total run rate, so a stage prefers reusing a
            prior stage's machines over building new ones whenever that
            does not cost any raw-import optimality. ``None`` reproduces
            today's level 2 exactly (no reuse awareness).

    Returns:
        A :class:`SolveResult`. ``status`` is ``"no_candidates"`` when no
        automatable recipe is allowed and there is demand to satisfy,
        ``"infeasible"`` when the demand cannot be reached with the
        allowed recipes (before or after the LP), a pin names a recipe
        outside ``allowed_recipes``, and ``"optimal"`` otherwise
        (including the trivial empty-demand case).
    """
    demand_by_item: dict[str, float] = {}
    for item_class, rate in demands:
        key = normalize_class_name(item_class)
        demand_by_item[key] = demand_by_item.get(key, 0.0) + rate

    if not demand_by_item:
        return SolveResult(
            status="optimal", runs=(), imports=(), satisfied_demands=(), diagnostics=()
        )

    pinned_keys = frozenset(normalize_class_name(key) for key in pinned)
    banned_keys = frozenset(normalize_class_name(key) for key in banned)

    invalid_pins = sorted(key for key in pinned_keys if key not in allowed_recipes)
    if invalid_pins:
        return SolveResult(
            status="infeasible",
            runs=(),
            imports=(),
            satisfied_demands=(),
            diagnostics=tuple(
                f"pinned recipe '{key}' is not in allowed_recipes: a pin can only "
                f"select a recipe the caller has already unlocked"
                for key in invalid_pins
            ),
        )

    # Primary-product convention: pinning recipe R bans every OTHER recipe
    # that lists R's first product among its own products, so a locked
    # alternate for the same item can never smuggle itself in as the sole
    # remaining producer once its competitor is pinned (guardrail: no
    # locked recipe selected by default).
    effective_banned = set(banned_keys)
    for pin_key in pinned_keys:
        pin_recipe = catalog.recipe(pin_key)
        if pin_recipe is None or not pin_recipe.products:
            continue
        primary_product = normalize_class_name(pin_recipe.products[0].class_name)
        for recipe in catalog.all_recipes():
            other_key = normalize_class_name(recipe.class_name)
            if other_key == pin_key:
                continue
            if any(
                normalize_class_name(product.class_name) == primary_product
                for product in recipe.products
            ):
                effective_banned.add(other_key)
    effective_banned = frozenset(effective_banned)

    candidates: dict[str, Recipe] = {
        normalize_class_name(recipe.class_name): recipe
        for recipe in catalog.automatable_recipes()
        if normalize_class_name(recipe.class_name) in allowed_recipes
        and normalize_class_name(recipe.class_name) not in effective_banned
    }
    if not candidates:
        return SolveResult(
            status="no_candidates",
            runs=(),
            imports=(),
            satisfied_demands=(),
            diagnostics=("no candidate recipes: allowed_recipes matched no automatable recipe",),
        )

    raw_classes = catalog.raw_resource_classes()

    # Reachability pre-check: walk backward from demand items through
    # candidate recipes, collecting every touched item and every candidate
    # recipe that can produce one. An item with no candidate producer and
    # not raw is a dead end (its consumers get zero-forced in the LP); if a
    # *demand* item itself is a dead end the stage is infeasible and the
    # LP is never called.
    touched_items: set[str] = set(demand_by_item)
    touched_recipes: dict[str, Recipe] = {}
    unproducible: set[str] = set()
    processed: set[str] = set()
    queue: deque[str] = deque(demand_by_item)

    while queue:
        item_key = queue.popleft()
        if item_key in processed:
            continue
        processed.add(item_key)
        if item_key in raw_classes:
            continue
        producers = [
            recipe
            for recipe in candidates.values()
            if any(
                normalize_class_name(product.class_name) == item_key for product in recipe.products
            )
        ]
        if not producers:
            unproducible.add(item_key)
            continue
        for recipe in producers:
            recipe_key = normalize_class_name(recipe.class_name)
            if recipe_key in touched_recipes:
                continue
            touched_recipes[recipe_key] = recipe
            for product in recipe.products:
                touched_items.add(normalize_class_name(product.class_name))
            for ingredient in recipe.ingredients:
                ingredient_key = normalize_class_name(ingredient.class_name)
                touched_items.add(ingredient_key)
                if ingredient_key not in processed:
                    queue.append(ingredient_key)

    unproducible_demands = sorted(key for key in demand_by_item if key in unproducible)
    if unproducible_demands:
        return SolveResult(
            status="infeasible",
            runs=(),
            imports=(),
            satisfied_demands=(),
            diagnostics=tuple(
                _diagnose_unproducible(catalog, key, allowed_recipes, effective_banned)
                for key in unproducible_demands
            ),
        )

    # Variables: candidate recipes reachable from the demands, plus one
    # raw-import variable per raw resource touched by the graph.
    # Deterministic ordering: sorted by normalized class key.
    recipe_order = sorted(touched_recipes)
    raw_order = sorted(key for key in touched_items if key in raw_classes)
    item_order = sorted(touched_items)

    recipe_buildings: dict[str, Building] = {}
    for recipe_key, recipe in touched_recipes.items():
        building = _resolve_building(catalog, recipe)
        if building is None:
            # automatable_recipes() already guarantees a resolvable
            # building for every candidate; never invent one here.
            return SolveResult(
                status="infeasible",
                runs=(),
                imports=(),
                satisfied_demands=(),
                diagnostics=(f"internal error: '{recipe_key}' has no resolvable building",),
            )
        recipe_buildings[recipe_key] = building

    # Precompute each touched recipe's (produced, consumed) rate per item
    # once, reused for both the LP coefficients and the residual check.
    recipe_item_rates: dict[str, dict[str, tuple[float, float]]] = {}
    for recipe_key, recipe in touched_recipes.items():
        building = recipe_buildings[recipe_key]
        rates: dict[str, list[float]] = {}
        for product in recipe.products:
            key = normalize_class_name(product.class_name)
            rates.setdefault(key, [0.0, 0.0])[0] += _item_rate(catalog, product, recipe, building)
        for ingredient in recipe.ingredients:
            key = normalize_class_name(ingredient.class_name)
            rates.setdefault(key, [0.0, 0.0])[1] += _item_rate(catalog, ingredient, recipe, building)
        recipe_item_rates[recipe_key] = {key: (produced, consumed) for key, (produced, consumed) in rates.items()}

    recipe_index = {key: position for position, key in enumerate(recipe_order)}
    raw_index = {key: len(recipe_order) + position for position, key in enumerate(raw_order)}
    n_vars = len(recipe_order) + len(raw_order)

    # Objective: minimize raw-resource imports (uniform weight) plus a tiny
    # stability term on every recipe run. Without the epsilon, a zero-net
    # cycle (e.g. a recipe whose byproduct feeds right back into one of its
    # own ingredients elsewhere in the graph) has no cost and could float
    # to an arbitrary rate; the epsilon picks the unique minimal-activity
    # solution and keeps results reproducible.
    c = np.zeros(n_vars)
    c[: len(recipe_order)] = _RECIPE_STABILITY_WEIGHT
    c[len(recipe_order) :] = _RAW_IMPORT_WEIGHT

    # Constraints: linprog solves A_ub @ x <= b_ub. The balance requirement
    # is production - consumption + raw_import >= demand; negated to
    # consumption - production - raw_import <= -demand, one row per item
    # touched by the graph.
    a_ub = np.zeros((len(item_order), n_vars))
    b_ub = np.zeros(len(item_order))
    for row, item_key in enumerate(item_order):
        b_ub[row] = -demand_by_item.get(item_key, 0.0)
        for recipe_key in recipe_order:
            produced, consumed = recipe_item_rates[recipe_key].get(item_key, (0.0, 0.0))
            a_ub[row, recipe_index[recipe_key]] = consumed - produced
        if item_key in raw_index:
            a_ub[row, raw_index[item_key]] = -1.0

    try:
        from scipy.optimize import linprog
    except ImportError as error:
        return SolveResult(
            status="infeasible",
            runs=(),
            imports=(),
            satisfied_demands=(),
            diagnostics=(f"scipy is required to solve this stage but is not installed: {error}",),
        )

    level1 = linprog(c=c, A_ub=a_ub, b_ub=b_ub, method="highs")
    if not level1.success:
        return SolveResult(
            status="infeasible",
            runs=(),
            imports=(),
            satisfied_demands=(),
            diagnostics=(
                f"LP infeasible for demand items {sorted(demand_by_item)} involving raw "
                f"resources {raw_order}: {level1.message}",
            ),
        )

    x = np.asarray(level1.x, dtype=float)

    # Two-level lexicographic objective: level 1 above already minimizes raw
    # imports (plus the stability epsilon). This second pass holds that raw
    # total to within a tiny numerical-safety slack and, among the
    # solutions that still meet it, minimizes total machine-equivalents
    # (the sum of recipe run rates) -- so two recipes tied on raw cost no
    # longer depend on the epsilon term, or on which vertex the solver
    # happens to return, to prefer the one that needs fewer machines.
    two_level_diagnostics: list[str] = []
    raw_total = float(sum(x[raw_index[key]] for key in raw_order))
    raw_cap_row = np.zeros(n_vars)
    for key in raw_order:
        raw_cap_row[raw_index[key]] = 1.0
    # The raw cap constraint is identical whether or not prior_capacity is
    # given: it holds level 1's raw total to a tiny numerical-safety slack,
    # so raw optimality is preserved by construction regardless of what
    # level 2's objective below prefers among the raw-optimal solutions.
    a_ub_base = np.vstack([a_ub, raw_cap_row])
    b_ub_base = np.append(
        b_ub, raw_total * (1.0 + _LEVEL2_RAW_TOLERANCE) + _LEVEL2_RAW_TOLERANCE
    )

    if prior_capacity is None:
        a_ub_level2 = a_ub_base
        b_ub_level2 = b_ub_base
        # Raw vars keep the same tiny stability weight as level 1 (not
        # zero): with no cost at all, HiGHS can leave a spurious near-zero
        # raw import as numerical slack (it costs nothing in this
        # objective), which would survive the clamp below and read as a
        # phantom import. The epsilon gives the solver a reason to drive
        # any truly-unneeded raw variable all the way to zero.
        c2 = np.zeros(n_vars)
        c2[: len(recipe_order)] = 1.0
        c2[len(recipe_order) :] = _RECIPE_STABILITY_WEIGHT
    else:
        # Reuse-aware level 2: variables are the level-1 set (recipe runs
        # x_i, raw imports) plus one auxiliary "new machine-equivalents"
        # variable n_i per recipe that has prior capacity p_i. Constraints
        # add n_i >= x_i - p_i per such recipe (n_i >= 0 is already the
        # default variable lower bound scipy applies to every variable
        # here, so no extra row is needed for it); the balance rows and the
        # raw cap row above are reused unchanged, just padded with zero
        # columns for the new n_i variables. Objective: minimize sum of
        # n_i for recipes with prior capacity, plus x_i directly for
        # recipes without any (equivalent to p_i == 0, but without
        # introducing an unnecessary auxiliary variable); every recipe run
        # variable also keeps the same tiny stability epsilon as raw
        # imports, since a recipe within its own prior capacity would
        # otherwise be free to float there without penalty (the same
        # phantom-solution risk the raw epsilon above guards against).
        prior_by_key = {
            normalize_class_name(key): value for key, value in prior_capacity.items()
        }
        reuse_keys = [key for key in recipe_order if key in prior_by_key]
        reuse_index = {key: n_vars + position for position, key in enumerate(reuse_keys)}
        n_vars_reuse = n_vars + len(reuse_keys)

        reuse_rows = np.zeros((len(reuse_keys), n_vars_reuse))
        reuse_rhs = np.zeros(len(reuse_keys))
        for position, key in enumerate(reuse_keys):
            reuse_rows[position, recipe_index[key]] = 1.0
            reuse_rows[position, reuse_index[key]] = -1.0
            reuse_rhs[position] = prior_by_key[key]

        pad = np.zeros((a_ub_base.shape[0], len(reuse_keys)))
        a_ub_level2 = np.vstack([np.hstack([a_ub_base, pad]), reuse_rows])
        b_ub_level2 = np.concatenate([b_ub_base, reuse_rhs])

        c2 = np.zeros(n_vars_reuse)
        c2[: len(recipe_order)] = _RECIPE_STABILITY_WEIGHT
        c2[len(recipe_order) : n_vars] = _RECIPE_STABILITY_WEIGHT
        for key in recipe_order:
            if key not in prior_by_key:
                c2[recipe_index[key]] += 1.0
        c2[n_vars:] = 1.0

    level2 = linprog(c=c2, A_ub=a_ub_level2, b_ub=b_ub_level2, method="highs")
    if level2.success:
        x = np.asarray(level2.x, dtype=float)[:n_vars]
    else:
        two_level_diagnostics.append(
            "two-level machine-minimization re-solve was infeasible; falling "
            "back to the level-1 (raw-minimizing) solution"
        )

    x[x < _CLAMP_EPSILON] = 0.0

    runs = tuple(
        sorted(
            (
                RecipeRun(
                    recipe_class=touched_recipes[key].class_name,
                    display_name=touched_recipes[key].display_name,
                    machines_exact=float(x[recipe_index[key]]),
                    building_class=recipe_buildings[key].class_name,
                )
                for key in recipe_order
                if x[recipe_index[key]] > 0.0
            ),
            key=lambda run: normalize_class_name(run.recipe_class),
        )
    )
    imports = tuple(
        sorted(
            (
                RawImport(
                    item_class=(catalog.item(key).class_name if catalog.item(key) else key),
                    display_name=catalog.item_display_name(key),
                    rate_per_min=float(x[raw_index[key]]),
                )
                for key in raw_order
                if x[raw_index[key]] > 0.0
            ),
            key=lambda imported: normalize_class_name(imported.item_class),
        )
    )

    # Post-solve residual verification: production - consumption + import
    # minus demand must never fall meaningfully short. This is a
    # self-consistency check on the solver's own math, not a re-derivation
    # from scipy's result.
    diagnostics: list[str] = list(two_level_diagnostics)
    for item_key in item_order:
        produced_total = 0.0
        consumed_total = 0.0
        for recipe_key in recipe_order:
            produced, consumed = recipe_item_rates[recipe_key].get(item_key, (0.0, 0.0))
            run_rate = x[recipe_index[recipe_key]]
            produced_total += run_rate * produced
            consumed_total += run_rate * consumed
        raw_value = x[raw_index[item_key]] if item_key in raw_index else 0.0
        residual = produced_total - consumed_total + raw_value - demand_by_item.get(item_key, 0.0)
        if residual < _RESIDUAL_TOLERANCE:
            diagnostics.append(
                f"internal residual error for '{item_key}': {residual:.6f} below tolerance"
            )

    return SolveResult(
        status="optimal",
        runs=runs,
        imports=imports,
        satisfied_demands=tuple(sorted(demand_by_item)),
        diagnostics=tuple(diagnostics),
    )


def schedule_machines(
    catalog: DocsCatalog, result: SolveResult
) -> tuple[tuple[ProcessNode, ...], PowerPlan, tuple[str, ...]]:
    """Turn solved machine-equivalents into an integer schedule and power plan.

    Each :class:`RecipeRun` names a recipe and building already validated
    against ``catalog`` by :func:`solve_stage`, so ``catalog`` here must be
    the same catalog (or an equivalent one) that produced ``result``.

    Args:
        catalog: Docs catalog providing recipe durations and building specs.
        result: A :class:`SolveResult` from :func:`solve_stage`.

    Returns:
        A ``(nodes, power, diagnostics)`` triple: process nodes sorted by
        node id, the aggregate :class:`PowerPlan`, and diagnostic strings
        (buildings with zero or unknown power draw).
    """
    nodes: list[ProcessNode] = []
    raw_power_by_building: dict[str, float] = {}
    unpowered_buildings: set[str] = set()

    for run in result.runs:
        recipe = catalog.recipe(run.recipe_class)
        building = catalog.building(run.building_class)
        if recipe is None or building is None:
            raise ValueError(
                f"schedule_machines: catalog has no recipe/building for "
                f"'{run.recipe_class}'/'{run.building_class}'; pass the same "
                f"catalog used to produce this SolveResult"
            )

        # ceil() with a nudge so floating-point noise (e.g. 3.0000000001
        # from the LP solve) never rounds up to an extra machine; the group
        # clock then absorbs the gap between machines_exact and the integer
        # count so total throughput is preserved exactly. If that clock
        # would fall below the game's 1 percent minimum, back off the
        # machine count (which raises the clock) until it clears the floor
        # or only one machine remains.
        machine_count = max(1, math.ceil(run.machines_exact - _MACHINE_CEIL_NUDGE))
        clock = run.machines_exact / machine_count
        while clock < _CLOCK_FLOOR and machine_count > 1:
            machine_count -= 1
            clock = run.machines_exact / machine_count

        runs_per_min = run.machines_exact * (60.0 / recipe.duration_seconds) * building.manufacturing_speed

        if building.power_consumption <= 0.0:
            unpowered_buildings.add(run.building_class)
            raw_power_mw = 0.0
        else:
            # mPowerConsumptionExponent models the game's nonlinear
            # overclock/underclock power cost: draw scales with clock
            # raised to this exponent, not linearly with clock.
            raw_power_mw = (
                machine_count * building.power_consumption * clock**building.power_consumption_exponent
            )

        node = ProcessNode(
            node_id=f"node_{normalize_class_name(run.recipe_class)}",
            recipe_class=run.recipe_class,
            building_class=run.building_class,
            runs_per_min=runs_per_min,
            machine_count_exact=run.machines_exact,
            machine_count=machine_count,
            clock=clock,
            power_mw=round(raw_power_mw, _POWER_DECIMALS),
        )
        nodes.append(node)
        raw_power_by_building[run.building_class] = (
            raw_power_by_building.get(run.building_class, 0.0) + raw_power_mw
        )

    diagnostics = tuple(
        f"building '{building_class}' has zero or unknown power consumption; "
        f"treated as 0 MW"
        for building_class in sorted(unpowered_buildings)
    )

    nodes_sorted = tuple(sorted(nodes, key=lambda node: node.node_id))
    by_building = tuple(
        sorted(
            (
                (building_class, round(mw, _POWER_DECIMALS))
                for building_class, mw in raw_power_by_building.items()
            ),
            key=lambda entry: (-entry[1], entry[0]),
        )
    )
    total_mw = round(sum(raw_power_by_building.values()), _POWER_DECIMALS)

    power = PowerPlan(total_mw=total_mw, by_building=by_building)
    return nodes_sorted, power, diagnostics

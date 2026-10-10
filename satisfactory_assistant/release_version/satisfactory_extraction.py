"""Extraction modeling for raw imports: extractor selection, count, and power.

Pure module: no Wingman imports, stdlib only besides the sibling docs,
solver, and plan-model modules. A solved stage's raw-resource imports
(:class:`~satisfactory_solver.RawImport`) previously entered a plan for
free; :func:`plan_extraction` turns each one into the extractor machines
that actually supply it, mirroring
:func:`~satisfactory_solver.schedule_machines`'s integer-count, clock, and
power math so the plan's power budget reflects extraction too.

Scope this packet: normal-purity solid nodes (miners) and the two known
fluid pumps (water, crude oil). Resource wells, geothermal, and per-node
purity are out of scope (see the SSP-P5-W01 packet in DEVLOG.md).
"""

from __future__ import annotations

import math

from satisfactory_docs import Building, DocsCatalog, ItemAmount, normalize_class_name
from satisfactory_plan_models import ResourceSource
from satisfactory_solver import RawImport


# Miner tier requested by the caller maps to the building class whose real
# Docs stats (extract_cycle_time, items_per_cycle, power) drive the count/
# clock/power math; "mk2" is the mid-game default so an unconfigured call
# plans with neither the earliest- nor latest-game miner.
_MINER_MARK_BUILDINGS: dict[str, str] = {
    "mk1": "Build_MinerMk1_C",
    "mk2": "Build_MinerMk2_C",
    "mk3": "Build_MinerMk3_C",
}
DEFAULT_MINER_MARK = "mk2"

_WATER_PUMP_CLASS = "Build_WaterPump_C"
_OIL_PUMP_CLASS = "Build_OilPump_C"

# Why this table exists: extractor selection is data-driven first (see
# _resolve_extractor), checking the known extractor buildings' own
# allowed_resources for the item. Some Docs dumps leave mAllowedResources
# empty for the fluid pumps even though the game always pairs them with a
# fixed resource (satisfactory_mirror.py's _extractor_rates has the same
# single-item workaround for this gap). This table reproduces that fixed,
# game-defined pairing by item identity so the plan still resolves an
# extractor instead of degrading to a diagnostic when the data is missing:
# water and crude oil by their known class keys, any other raw item by the
# requested miner_mark (every automatable solid resource is minable).
_WATER_ITEM_KEY = normalize_class_name("Desc_Water_C")
_CRUDE_OIL_ITEM_KEY = normalize_class_name("Desc_LiquidOil_C")
_FALLBACK_EXTRACTOR_BY_ITEM: dict[str, str] = {
    _WATER_ITEM_KEY: _WATER_PUMP_CLASS,
    _CRUDE_OIL_ITEM_KEY: _OIL_PUMP_CLASS,
}

# Purity assumption locked for this packet: every solid extraction node is
# planned at normal purity (multiplier 1.0); fluid pumps have no purity
# concept in the game, so the same no-op multiplier is safe to apply to
# them too. Per-node purity (save-derived) is Phase 8/9 territory.
NORMAL_PURITY_MULTIPLIER = 1.0

# Mirrors satisfactory_solver.schedule_machines's ceil-nudge/clock-floor/
# power-decimals constants exactly (see that function's docstring for the
# derivation of each). Reimplemented here rather than imported since they
# are module-private there; this comment is the pointer to that source of
# truth so the two never drift silently.
_MACHINE_CEIL_NUDGE = 1e-9
_CLOCK_FLOOR = 0.01
_POWER_DECIMALS = 3


def _resolve_extractor(catalog: DocsCatalog, item_key: str, miner_class: str) -> Building | None:
    """Return the extractor building that supplies ``item_key``, or None.

    Data-driven first: check the three known extractor classes (water
    pump, oil pump, the requested miner tier) for real ``allowed_resources``
    data that contains this item. Falls back to the conventional item-
    identity pairing table when none of those buildings' allowed_resources
    lists the item (see that table's why-comment).
    """
    for candidate_class in (_WATER_PUMP_CLASS, _OIL_PUMP_CLASS, miner_class):
        building = catalog.building(candidate_class)
        if building is None:
            continue
        allowed = {normalize_class_name(resource) for resource in building.allowed_resources}
        if item_key in allowed:
            return building

    fallback_class = _FALLBACK_EXTRACTOR_BY_ITEM.get(item_key, miner_class)
    return catalog.building(fallback_class)


def _extractor_rate_per_min(catalog: DocsCatalog, item_class: str, building: Building) -> float:
    """One extractor's throughput per minute at 100 percent clock, normal purity.

    Mirrors ``satisfactory_mirror.py``'s ``_extractor_rates`` rate formula
    so fluid unit conversion (the /1000 handling in
    ``DocsCatalog.rate_amount`` for RF_LIQUID/RF_GAS items) applies here
    identically to how it applies to the live-save mirror.
    """
    amount = ItemAmount(class_name=item_class, amount=building.items_per_cycle)
    return (
        catalog.rate_amount(amount)
        * (60.0 / building.extract_cycle_time)
        * NORMAL_PURITY_MULTIPLIER
    )


def plan_extraction(
    catalog: DocsCatalog,
    imports: tuple[RawImport, ...],
    miner_mark: str = DEFAULT_MINER_MARK,
) -> tuple[tuple[ResourceSource, ...], tuple[tuple[str, float], ...], tuple[str, ...]]:
    """Resolve extractor machines and power for a stage's solved raw imports.

    For each import, selects a candidate extractor building (see
    :func:`_resolve_extractor`), then mirrors
    :func:`~satisfactory_solver.schedule_machines`'s integer-schedule math:
    the exact machine count is ``required_rate / per_extractor_rate``,
    ceil'd with the same floating-point nudge, with the group clock
    absorbing the remainder and backing off the count if the clock would
    fall below the game's 1 percent floor. Power draw uses the same
    nonlinear clock-exponent formula.

    Args:
        catalog: Docs catalog providing extractor building specs.
        imports: Solved raw imports from :func:`~satisfactory_solver.solve_stage`.
        miner_mark: Which miner tier to use for solid resources: "mk1",
            "mk2" (default), or "mk3".

    Returns:
        A ``(sources, power_additions, diagnostics)`` triple:

        - ``sources``: one :class:`~satisfactory_plan_models.ResourceSource`
          per import, sorted by node id. An import whose extractor could
          not be resolved to a usable cycle rate keeps
          ``extractor_class=""``/``extractor_count=0`` (the prior
          unmodeled-extraction shape) rather than crashing.
        - ``power_additions``: ``(building_class, mw)`` pairs, one per
          distinct extractor building used, sorted by descending MW then
          building class.
        - ``diagnostics``: human-readable strings for imports whose
          extractor could not be resolved, sorted for determinism.

    Raises:
        ValueError: If ``miner_mark`` is not "mk1", "mk2", or "mk3".
    """
    if miner_mark not in _MINER_MARK_BUILDINGS:
        raise ValueError(
            f"plan_extraction: invalid miner_mark {miner_mark!r}; expected one "
            f"of {sorted(_MINER_MARK_BUILDINGS)}"
        )
    miner_class = _MINER_MARK_BUILDINGS[miner_mark]

    sources: list[ResourceSource] = []
    power_by_building: dict[str, float] = {}
    diagnostics: list[str] = []

    for imported in imports:
        item_key = normalize_class_name(imported.item_class)
        node_id = f"raw_{item_key}"
        building = _resolve_extractor(catalog, item_key, miner_class)

        if building is None or building.extract_cycle_time <= 0.0 or building.items_per_cycle <= 0.0:
            diagnostics.append(
                f"unknown extractor for item '{imported.item_class}': no candidate "
                f"extractor building resolves a usable cycle rate for it"
            )
            sources.append(
                ResourceSource(
                    node_id=node_id,
                    item_class=imported.item_class,
                    rate_per_min=imported.rate_per_min,
                    extractor_class="",
                    extractor_count=0,
                )
            )
            continue

        per_extractor_rate = _extractor_rate_per_min(catalog, imported.item_class, building)

        machines_exact = imported.rate_per_min / per_extractor_rate
        machine_count = max(1, math.ceil(machines_exact - _MACHINE_CEIL_NUDGE))
        clock = machines_exact / machine_count
        while clock < _CLOCK_FLOOR and machine_count > 1:
            machine_count -= 1
            clock = machines_exact / machine_count

        if building.power_consumption <= 0.0:
            power_mw = 0.0
        else:
            power_mw = (
                machine_count
                * building.power_consumption
                * clock**building.power_consumption_exponent
            )

        sources.append(
            ResourceSource(
                node_id=node_id,
                item_class=imported.item_class,
                rate_per_min=imported.rate_per_min,
                extractor_class=building.class_name,
                extractor_count=machine_count,
            )
        )
        power_by_building[building.class_name] = (
            power_by_building.get(building.class_name, 0.0) + power_mw
        )

    sources_sorted = tuple(sorted(sources, key=lambda source: source.node_id))
    power_pairs = tuple(
        sorted(
            (
                (building_class, round(mw, _POWER_DECIMALS))
                for building_class, mw in power_by_building.items()
            ),
            key=lambda entry: (-entry[1], entry[0]),
        )
    )
    return sources_sorted, power_pairs, tuple(sorted(diagnostics))

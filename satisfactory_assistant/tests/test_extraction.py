"""Tests for extraction modeling: extractor selection, count, clock, power."""

from __future__ import annotations

import math

import pytest

from satisfactory_docs import Building, DocsCatalog, ItemDescriptor
from satisfactory_extraction import DEFAULT_MINER_MARK, plan_extraction
from satisfactory_solver import RawImport


def _building(
    class_name: str,
    *,
    extract_cycle_time: float = 0.0,
    items_per_cycle: float = 0.0,
    allowed_resources: tuple[str, ...] = (),
    power_consumption: float = 0.0,
    power_consumption_exponent: float = 1.6,
) -> Building:
    return Building(
        class_name=class_name,
        display_name=class_name,
        manufacturing_speed=1.0,
        power_consumption=power_consumption,
        extract_cycle_time=extract_cycle_time,
        items_per_cycle=items_per_cycle,
        allowed_resources=allowed_resources,
        power_consumption_exponent=power_consumption_exponent,
    )


def _catalog(buildings: dict[str, Building], items: dict[str, ItemDescriptor] | None = None) -> DocsCatalog:
    return DocsCatalog(items=items or {}, recipes={}, buildings=buildings)


# --- Fixture catalog: miner (all three tiers), water pump, oil pump --------

_IRON_ORE = "Desc_OreIron_C"
_WATER = "Desc_Water_C"
_CRUDE_OIL = "Desc_LiquidOil_C"


def _full_catalog() -> DocsCatalog:
    """One catalog covering every known extractor class this packet models.

    Mk2 miner and the water pump resolve via the data-driven path (their
    ``allowed_resources`` lists the item directly); the oil pump's
    ``allowed_resources`` is left empty on purpose to exercise the fallback
    table's conventional pairing for crude oil.
    """
    items = {
        "desc_oreiron": ItemDescriptor(
            class_name=_IRON_ORE, display_name="Iron Ore", form="RF_SOLID", is_resource=True
        ),
        "desc_water": ItemDescriptor(
            class_name=_WATER, display_name="Water", form="RF_LIQUID", is_resource=True
        ),
        "desc_liquidoil": ItemDescriptor(
            class_name=_CRUDE_OIL, display_name="Crude Oil", form="RF_LIQUID", is_resource=True
        ),
    }
    buildings = {
        "build_minermk1": _building(
            "Build_MinerMk1_C",
            extract_cycle_time=2.0,
            items_per_cycle=1,
            allowed_resources=(_IRON_ORE,),
            power_consumption=5.0,
        ),
        "build_minermk2": _building(
            "Build_MinerMk2_C",
            extract_cycle_time=1.0,
            items_per_cycle=1,
            allowed_resources=(_IRON_ORE,),
            power_consumption=15.0,
        ),
        "build_minermk3": _building(
            "Build_MinerMk3_C",
            extract_cycle_time=1.0,
            items_per_cycle=2,
            allowed_resources=(_IRON_ORE,),
            power_consumption=45.0,
        ),
        "build_waterpump": _building(
            "Build_WaterPump_C",
            extract_cycle_time=1.0,
            items_per_cycle=2000,
            allowed_resources=(_WATER,),
            power_consumption=20.0,
        ),
        "build_oilpump": _building(
            "Build_OilPump_C",
            extract_cycle_time=1.0,
            items_per_cycle=2000,
            allowed_resources=(),
            power_consumption=40.0,
        ),
    }
    return _catalog(buildings, items)


def _import(item_class: str, rate_per_min: float, display_name: str = "") -> RawImport:
    return RawImport(item_class=item_class, display_name=display_name or item_class, rate_per_min=rate_per_min)


# --- Hand-computed counts, clocks, and power --------------------------------


def test_miner_mk2_hand_computed_count_clock_power() -> None:
    catalog = _full_catalog()

    sources, power, diagnostics = plan_extraction(catalog, (_import(_IRON_ORE, 250.0),))

    assert diagnostics == ()
    assert len(sources) == 1
    source = sources[0]
    assert source.extractor_class == "Build_MinerMk2_C"
    # 1 item/cycle at 1.0s -> 60/min per miner; 250/60 == 4.1(6) machines.
    machines_exact = 250.0 / 60.0
    expected_count = math.ceil(machines_exact - 1e-9)
    assert source.extractor_count == expected_count == 5
    clock = machines_exact / expected_count
    expected_power = round(5 * 15.0 * clock**1.6, 3)
    assert power == (("Build_MinerMk2_C", expected_power),)


def test_water_pump_data_driven_selection() -> None:
    catalog = _full_catalog()

    sources, power, diagnostics = plan_extraction(catalog, (_import(_WATER, 180.0),))

    assert diagnostics == ()
    assert len(sources) == 1
    source = sources[0]
    assert source.extractor_class == "Build_WaterPump_C"
    # items_per_cycle 2000 is a fluid amount -> /1000 -> 2.0 m3/cycle; at
    # 1.0s cycle time that's 120 m3/min per pump; 180/120 == 1.5 machines.
    machines_exact = 180.0 / 120.0
    expected_count = math.ceil(machines_exact - 1e-9)
    assert source.extractor_count == expected_count == 2
    clock = machines_exact / expected_count
    expected_power = round(2 * 20.0 * clock**1.6, 3)
    assert power == (("Build_WaterPump_C", expected_power),)


def test_oil_pump_fallback_selection() -> None:
    """Oil pump's allowed_resources is empty, so the fallback table applies."""
    catalog = _full_catalog()

    sources, power, diagnostics = plan_extraction(catalog, (_import(_CRUDE_OIL, 60.0),))

    assert diagnostics == ()
    assert len(sources) == 1
    source = sources[0]
    assert source.extractor_class == "Build_OilPump_C"
    machines_exact = 60.0 / 120.0
    expected_count = math.ceil(machines_exact - 1e-9)
    assert source.extractor_count == expected_count == 1
    clock = machines_exact / expected_count
    expected_power = round(1 * 40.0 * clock**1.6, 3)
    assert power == (("Build_OilPump_C", expected_power),)


def test_multiple_imports_hand_computed_together() -> None:
    catalog = _full_catalog()

    sources, power, diagnostics = plan_extraction(
        catalog,
        (
            _import(_IRON_ORE, 250.0),
            _import(_WATER, 180.0),
            _import(_CRUDE_OIL, 60.0),
        ),
    )

    assert diagnostics == ()
    assert len(sources) == 3
    assert len(power) == 3
    by_item = {source.item_class: source for source in sources}
    assert by_item[_IRON_ORE].extractor_class == "Build_MinerMk2_C"
    assert by_item[_IRON_ORE].extractor_count == 5
    assert by_item[_WATER].extractor_class == "Build_WaterPump_C"
    assert by_item[_WATER].extractor_count == 2
    assert by_item[_CRUDE_OIL].extractor_class == "Build_OilPump_C"
    assert by_item[_CRUDE_OIL].extractor_count == 1
    # Sources are sorted by node id (raw_<item key>) regardless of input order.
    assert [source.node_id for source in sources] == sorted(source.node_id for source in sources)


def test_miner_mark_changes_selection_and_math() -> None:
    """mk1/mk3 use their own real cycle stats, not mk2's."""
    catalog = _full_catalog()

    mk1_sources, mk1_power, _ = plan_extraction(
        catalog, (_import(_IRON_ORE, 30.0),), miner_mark="mk1"
    )
    mk3_sources, mk3_power, _ = plan_extraction(
        catalog, (_import(_IRON_ORE, 240.0),), miner_mark="mk3"
    )

    assert mk1_sources[0].extractor_class == "Build_MinerMk1_C"
    # Mk1: 1 item/cycle at 2.0s -> 30/min per miner; 30/30 == 1.0 machine.
    assert mk1_sources[0].extractor_count == 1
    assert mk1_power == (("Build_MinerMk1_C", round(1 * 5.0 * 1.0**1.6, 3)),)

    assert mk3_sources[0].extractor_class == "Build_MinerMk3_C"
    # Mk3: 2 items/cycle at 1.0s -> 120/min per miner; 240/120 == 2.0 machines.
    assert mk3_sources[0].extractor_count == 2
    assert mk3_power == (("Build_MinerMk3_C", round(2 * 45.0 * 1.0**1.6, 3)),)


def test_default_miner_mark_is_mk2() -> None:
    assert DEFAULT_MINER_MARK == "mk2"


# --- Unknown extractor: diagnostic, never a crash ---------------------------


def test_unknown_extractor_degrades_to_diagnostic() -> None:
    """A solid item with no water/oil/miner match (miner absent) -> diagnostic."""
    catalog = _catalog(
        {
            "build_waterpump": _building(
                "Build_WaterPump_C",
                extract_cycle_time=1.0,
                items_per_cycle=2000,
                allowed_resources=(_WATER,),
                power_consumption=20.0,
            ),
        }
    )
    mystery_item = "Desc_Mystery_C"

    sources, power, diagnostics = plan_extraction(catalog, (_import(mystery_item, 120.0),))

    assert len(diagnostics) == 1
    assert "unknown extractor" in diagnostics[0]
    assert mystery_item in diagnostics[0]
    assert power == ()
    assert len(sources) == 1
    source = sources[0]
    assert source.item_class == mystery_item
    assert source.rate_per_min == 120.0
    assert source.extractor_class == ""
    assert source.extractor_count == 0


# --- Invalid miner_mark ------------------------------------------------------


def test_invalid_miner_mark_raises_value_error() -> None:
    catalog = _full_catalog()

    with pytest.raises(ValueError, match="miner_mark"):
        plan_extraction(catalog, (_import(_IRON_ORE, 60.0),), miner_mark="mk4")


# --- Determinism -------------------------------------------------------------


def test_plan_extraction_is_deterministic() -> None:
    catalog = _full_catalog()
    imports = (
        _import(_CRUDE_OIL, 60.0),
        _import(_IRON_ORE, 250.0),
        _import(_WATER, 180.0),
    )

    first = plan_extraction(catalog, imports)
    second = plan_extraction(catalog, imports)

    assert first == second

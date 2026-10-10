"""Tests for construction bills of materials and commissioning order (SSP-P6-W01)."""

from __future__ import annotations

import pytest

from satisfactory_construction import build_construction_plan
from satisfactory_docs import Building, DocsCatalog, ItemAmount, ItemDescriptor, Recipe
from satisfactory_plan_models import (
    BuildTask,
    DataProvenance,
    PowerPlan,
    ProcessNode,
    RecipePolicy,
    ResourceSource,
    StagePlan,
    build_task_from_payload,
)


# --- Fixture builders (direct-construction style, per test_extraction.py) ---


def _item(class_name: str, form: str = "RF_SOLID") -> ItemDescriptor:
    return ItemDescriptor(class_name=class_name, display_name=class_name, form=form)


def _recipe(
    class_name: str,
    ingredients: list[tuple[str, float]],
    products: list[tuple[str, float]],
    produced_in: tuple[str, ...] = ("BP_BuildGun_C",),
) -> Recipe:
    return Recipe(
        class_name=class_name,
        display_name=class_name,
        duration_seconds=60.0,
        ingredients=tuple(ItemAmount(class_name=c, amount=a) for c, a in ingredients),
        products=tuple(ItemAmount(class_name=c, amount=a) for c, a in products),
        produced_in=produced_in,
    )


def _building(class_name: str) -> Building:
    return Building(
        class_name=class_name,
        display_name=class_name,
        manufacturing_speed=1.0,
        power_consumption=4.0,
        extract_cycle_time=0.0,
        items_per_cycle=0.0,
        allowed_resources=(),
    )


def _stage(
    nodes: tuple[ProcessNode, ...] = (), sources: tuple[ResourceSource, ...] = ()
) -> StagePlan:
    """Minimal StagePlan; only ``nodes``/``sources`` matter to this module."""
    return StagePlan(
        phase=1,
        window_hours=1.0,
        pace_multiplier=1.0,
        demands=(),
        nodes=nodes,
        sources=sources,
        flows=(),
        power=PowerPlan(total_mw=0.0, by_building=()),
        recipe_policy=RecipePolicy(mode="standard", pinned=(), banned=(), allowed_alternates=()),
        diagnostics=(),
        assumptions=(),
        provenance=DataProvenance(source="test", retrieved="2026-07-02T00:00:00", note=""),
        solver_run_id=None,
        revision=0,
        created_at="2026-07-02T00:00:00",
    )


# --- Fixture catalog: a real production chain plus the Smelter mismatch ----

# Desc_FoundryMk1_C mirrors the real Docs anomaly discovered while verifying
# this packet: the "recipe_smeltermk1" key actually builds the Foundry, not
# the Smelter (Recipe_SmelterBasicMk1_C is the Smelter's real build recipe),
# so the naive "build_x -> recipe_x" convention must not be trusted blindly;
# a fallback scan of every recipe's sole product is required to still
# resolve the Smelter correctly. Build_TrulyMissing_C has no recipe
# anywhere producing it, for the genuinely-unresolvable case.


def _catalog() -> DocsCatalog:
    items = {
        key: _item(class_name)
        for key, class_name in {
            "desc_oreiron": "Desc_OreIron_C",
            "desc_ironingot": "Desc_IronIngot_C",
            "desc_ironplate": "Desc_IronPlate_C",
            "desc_constructormk1": "Desc_ConstructorMk1_C",
            "desc_minermk2": "Desc_MinerMk2_C",
            "desc_smeltermk1": "Desc_SmelterMk1_C",
            "desc_foundrymk1": "Desc_FoundryMk1_C",
            "desc_x": "Desc_X_C",
            "desc_y": "Desc_Y_C",
        }.items()
    }
    recipes = {
        # Production recipes (run by a solved ProcessNode).
        "recipe_ironingot": _recipe(
            "Recipe_IronIngot_C", [("Desc_OreIron_C", 1)], [("Desc_IronIngot_C", 1)]
        ),
        "recipe_ironplate": _recipe(
            "Recipe_IronPlate_C", [("Desc_IronIngot_C", 1)], [("Desc_IronPlate_C", 1)]
        ),
        "recipe_alta": _recipe("Recipe_AltA_C", [("Desc_Y_C", 1)], [("Desc_X_C", 1)]),
        "recipe_altb": _recipe("Recipe_AltB_C", [("Desc_X_C", 1)], [("Desc_Y_C", 1)]),
        # Build-gun recipes: the convention holds for these two.
        "recipe_constructormk1": _recipe(
            "Recipe_ConstructorMk1_C", [("Desc_IronPlate_C", 2)], [("Desc_ConstructorMk1_C", 1)]
        ),
        "recipe_minermk2": _recipe(
            "Recipe_MinerMk2_C", [("Desc_IronPlate_C", 3)], [("Desc_MinerMk2_C", 1)]
        ),
        # Build-gun key collision: resolves by key, but its sole product is
        # the Foundry's, not the Smelter's; the keyed lookup must reject it.
        "recipe_smeltermk1": _recipe(
            "Recipe_SmelterMk1_C", [("Desc_IronPlate_C", 5)], [("Desc_FoundryMk1_C", 1)]
        ),
        # The Smelter's real build recipe, at a differently-named class
        # (mirrors the real Docs): only found by the fallback scan.
        "recipe_smelterbasicmk1": _recipe(
            "Recipe_SmelterBasicMk1_C", [("Desc_IronPlate_C", 7)], [("Desc_SmelterMk1_C", 1)]
        ),
        # No ingredients/products at all: guaranteed to contribute zero
        # graph edges, for the tie-break-by-node-id test.
        "recipe_standalonea": _recipe("Recipe_StandaloneA_C", [], []),
        "recipe_standaloneb": _recipe("Recipe_StandaloneB_C", [], []),
    }
    buildings = {
        "build_constructormk1": _building("Build_ConstructorMk1_C"),
        "build_minermk2": _building("Build_MinerMk2_C"),
        "build_smeltermk1": _building("Build_SmelterMk1_C"),
        "build_trulymissing": _building("Build_TrulyMissing_C"),
    }
    return DocsCatalog(items=items, recipes=recipes, buildings=buildings)


def _node(node_id: str, recipe_class: str, building_class: str, machine_count: int) -> ProcessNode:
    return ProcessNode(
        node_id=node_id,
        recipe_class=recipe_class,
        building_class=building_class,
        runs_per_min=float(machine_count),
        machine_count_exact=float(machine_count),
        machine_count=machine_count,
        clock=100.0,
        power_mw=0.0,
    )


# --- Build-recipe resolution: convention holds, and the Smelter mismatch ---


def test_convention_resolves_materials_scaled_by_count() -> None:
    catalog = _catalog()
    node = _node("node_recipe_ironplate", "Recipe_IronPlate_C", "Build_ConstructorMk1_C", 3)
    stage = _stage(nodes=(node,))

    tasks, bom, diagnostics, assumptions = build_construction_plan(catalog, stage)

    assert len(tasks) == 1
    task = tasks[0]
    assert task.building_class == "Build_ConstructorMk1_C"
    assert task.count == 3
    assert task.materials == (("Desc_IronPlate_C", 6.0),)
    assert diagnostics == ()
    assert len(assumptions) == 2
    assert bom == (("Desc_IronPlate_C", 6.0),)


def test_smelter_key_collision_falls_back_to_correct_recipe() -> None:
    """Recipe_SmelterMk1_C resolves by key but produces the Foundry; the keyed
    lookup must reject it, and the fallback scan must find
    Recipe_SmelterBasicMk1_C (the Smelter's real build recipe) instead."""
    catalog = _catalog()
    node = _node("node_recipe_ironingot", "Recipe_IronIngot_C", "Build_SmelterMk1_C", 2)
    stage = _stage(nodes=(node,))

    tasks, bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert len(tasks) == 1
    # 7 (per-unit cost) * 2 (count) = 14.0, from Recipe_SmelterBasicMk1_C,
    # never the mismatched Recipe_SmelterMk1_C's cost of 5.
    assert tasks[0].materials == (("Desc_IronPlate_C", 14.0),)
    assert bom == (("Desc_IronPlate_C", 14.0),)
    assert diagnostics == ()


def test_no_build_recipe_anywhere_gets_diagnostic_and_empty_materials() -> None:
    """No recipe in the catalog produces Build_TrulyMissing_C: both the keyed
    lookup and the fallback scan must fail, leaving materials empty."""
    catalog = _catalog()
    node = _node("node_recipe_ironingot", "Recipe_IronIngot_C", "Build_TrulyMissing_C", 2)
    stage = _stage(nodes=(node,))

    tasks, bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert len(tasks) == 1
    assert tasks[0].materials == ()
    assert bom == ()
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "missing_build_recipe"
    assert diagnostics[0].severity == "warning"
    assert "Build_TrulyMissing_C" in diagnostics[0].message


def test_building_not_matching_build_prefix_yields_no_recipe() -> None:
    catalog = _catalog()
    node = _node("node_recipe_ironingot", "Recipe_IronIngot_C", "SomeBuilding_C", 1)
    stage = _stage(nodes=(node,))

    tasks, bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert tasks[0].materials == ()
    assert bom == ()
    assert diagnostics[0].code == "missing_build_recipe"


# --- Ordering: extractors first, then topological production order --------


def test_extractors_first_then_topological_iron_chain() -> None:
    catalog = _catalog()
    source = ResourceSource(
        node_id="raw_oreiron",
        item_class="Desc_OreIron_C",
        rate_per_min=120.0,
        extractor_class="Build_MinerMk2_C",
        extractor_count=2,
    )
    ironingot = _node("node_recipe_ironingot", "Recipe_IronIngot_C", "Build_ConstructorMk1_C", 3)
    ironplate = _node("node_recipe_ironplate", "Recipe_IronPlate_C", "Build_ConstructorMk1_C", 2)
    # Nodes deliberately out of eventual order, to prove sorting is by the
    # graph/rule, not by input order.
    stage = _stage(nodes=(ironplate, ironingot), sources=(source,))

    tasks, bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert diagnostics == ()
    assert [task.node_id for task in tasks] == [
        "raw_oreiron",
        "node_recipe_ironingot",
        "node_recipe_ironplate",
    ]
    assert [task.order_index for task in tasks] == [0, 1, 2]
    assert [task.task_id for task in tasks] == [
        "task_0_raw_oreiron",
        "task_1_node_recipe_ironingot",
        "task_2_node_recipe_ironplate",
    ]

    extractor_task, ironingot_task, ironplate_task = tasks
    assert extractor_task.depends_on == ()
    assert ironingot_task.depends_on == ()
    assert ironplate_task.depends_on == ("node_recipe_ironingot",)

    # Hand-computed: 3*2 (ironingot) + 2*2 (ironplate) + 2*3 (miner) = 16.
    assert bom == (("Desc_IronPlate_C", 16.0),)


def test_cycle_broken_deterministically_with_diagnostic() -> None:
    catalog = _catalog()
    node_a = _node("node_recipe_alta", "Recipe_AltA_C", "Build_ConstructorMk1_C", 1)
    node_b = _node("node_recipe_altb", "Recipe_AltB_C", "Build_ConstructorMk1_C", 1)
    stage = _stage(nodes=(node_a, node_b))

    tasks, _bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    # node_recipe_alta -> node_recipe_altb sorts first among the two
    # possible back-edges, so it is the one broken; node_recipe_altb (now
    # freed of its predecessor) is scheduled first.
    assert [task.node_id for task in tasks] == ["node_recipe_altb", "node_recipe_alta"]
    cycle_diagnostics = [d for d in diagnostics if d.code == "construction_order_cycle"]
    assert len(cycle_diagnostics) == 1
    assert "node_recipe_alta -> node_recipe_altb" in cycle_diagnostics[0].message

    # depends_on still reports the true (cyclic) graph, independent of how
    # the cycle was broken for sequencing purposes.
    by_node = {task.node_id: task for task in tasks}
    assert by_node["node_recipe_alta"].depends_on == ("node_recipe_altb",)
    assert by_node["node_recipe_altb"].depends_on == ("node_recipe_alta",)


def test_ties_broken_by_node_id_when_no_dependency() -> None:
    """Two independent nodes (no shared product/ingredient) order by node_id."""
    catalog = _catalog()
    # recipe_standalonea/b have no ingredients or products at all, so
    # neither contributes an edge in either direction: a genuine tie.
    node_z = _node("node_recipe_z", "Recipe_StandaloneA_C", "Build_ConstructorMk1_C", 1)
    node_a = _node("node_recipe_a", "Recipe_StandaloneB_C", "Build_ConstructorMk1_C", 1)
    stage = _stage(nodes=(node_z, node_a))

    tasks, _bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert diagnostics == ()
    assert [task.node_id for task in tasks] == ["node_recipe_a", "node_recipe_z"]


# --- Determinism -------------------------------------------------------------


def test_determinism_double_run() -> None:
    catalog = _catalog()
    source = ResourceSource(
        node_id="raw_oreiron",
        item_class="Desc_OreIron_C",
        rate_per_min=120.0,
        extractor_class="Build_MinerMk2_C",
        extractor_count=2,
    )
    ironingot = _node("node_recipe_ironingot", "Recipe_IronIngot_C", "Build_ConstructorMk1_C", 3)
    ironplate = _node("node_recipe_ironplate", "Recipe_IronPlate_C", "Build_ConstructorMk1_C", 2)
    stage = _stage(nodes=(ironingot, ironplate), sources=(source,))

    first = build_construction_plan(catalog, stage)
    second = build_construction_plan(catalog, stage)

    assert first == second


# --- Unresolved extractor sources contribute no build task ------------------


def test_unresolved_extractor_source_contributes_no_task() -> None:
    catalog = _catalog()
    source = ResourceSource(
        node_id="raw_oreiron",
        item_class="Desc_OreIron_C",
        rate_per_min=60.0,
        extractor_class="",
        extractor_count=0,
    )
    stage = _stage(sources=(source,))

    tasks, bom, diagnostics, _assumptions = build_construction_plan(catalog, stage)

    assert tasks == ()
    assert bom == ()
    assert diagnostics == ()


# --- BuildTask payload round-trip -------------------------------------------


def test_build_task_payload_round_trip() -> None:
    task = BuildTask(
        task_id="task_1_node_recipe_ironplate",
        order_index=1,
        node_id="node_recipe_ironplate",
        building_class="Build_ConstructorMk1_C",
        count=2,
        materials=(("Desc_IronPlate_C", 6.0),),
        depends_on=("node_recipe_ironingot",),
    )

    rebuilt = build_task_from_payload(task.to_payload())

    assert rebuilt == task


def test_build_task_payload_round_trip_empty_collections() -> None:
    task = BuildTask(
        task_id="task_0_raw_oreiron",
        order_index=0,
        node_id="raw_oreiron",
        building_class="Build_MinerMk2_C",
        count=2,
        materials=(),
        depends_on=(),
    )

    rebuilt = build_task_from_payload(task.to_payload())

    assert rebuilt == task


# --- Real-install gated test (P6-W01 acceptance criterion 3) ---------------


def test_real_install_phase1_construction_plan_is_coherent() -> None:
    from satisfactory_dataset import get_docs_catalog
    from satisfactory_extraction import plan_extraction
    from satisfactory_install import discover_docs
    from satisfactory_progression import (
        build_capability_snapshot,
        derive_phase_demand,
        load_project_assembly_phases,
    )
    from satisfactory_solver import schedule_machines, solve_stage

    discovery = discover_docs()
    if discovery.docs_path is None:
        pytest.skip("No Satisfactory install found on this machine")

    catalog, _dataset_info = get_docs_catalog(discovery.docs_path)
    phase_data = load_project_assembly_phases()

    demand_set = derive_phase_demand(phase_data, 1, 1.0)
    snapshot = build_capability_snapshot(catalog, phase_data, 1, include_alternates=())
    demands = tuple(
        (demand.item_class, demand.required_rate_per_minute) for demand in demand_set.demands
    )
    solve_result = solve_stage(catalog, snapshot.allowed_recipes, demands)
    assert solve_result.status == "optimal"

    nodes, _power, _schedule_diagnostics = schedule_machines(catalog, solve_result)
    sources, _power_additions, _extraction_diagnostics = plan_extraction(
        catalog, solve_result.imports
    )
    stage = _stage(nodes=nodes, sources=sources)

    tasks, bom, diagnostics, assumptions = build_construction_plan(catalog, stage)

    assert len(assumptions) == 2
    assert tasks, "expected at least one build task for phase 1"
    assert bom, "expected a non-empty stage bill of materials"

    # The fallback scan (F-P6W01-1) must resolve every phase 1 building's
    # real build recipe, including the Smelter's key-collision case,
    # so no build recipe should be left unresolved on a real install.
    missing_recipe_diagnostics = [d for d in diagnostics if d.code == "missing_build_recipe"]
    assert missing_recipe_diagnostics == []

    smelter_tasks = [task for task in tasks if task.building_class == "Build_SmelterMk1_C"]
    for smelter_task in smelter_tasks:
        assert smelter_task.materials, "Smelter build task must resolve real materials"

    extractor_node_ids = {source.node_id for source in sources if source.extractor_class}
    extractor_task_count = sum(1 for task in tasks if task.node_id in extractor_node_ids)
    # Every extractor task must precede every production-node task.
    if extractor_task_count:
        assert [task.node_id in extractor_node_ids for task in tasks] == sorted(
            (task.node_id in extractor_node_ids for task in tasks), reverse=True
        )

    for item_class, quantity in bom:
        # Not every real build-cost ingredient resolves via catalog.item():
        # e.g. Build_MinerMk2_C's real build recipe lists the "Portable
        # Miner" equipment (BP_ItemDescriptorPortableMiner_C) as an
        # ingredient, which is neither an FGItemDescriptor nor an
        # FGResourceDescriptor entry, so the Docs item catalog never
        # parses it (catalog.rate_amount already degrades gracefully for
        # this: unresolved items are treated as non-fluid). "Coherent"
        # here means every material is a well-formed, positive quantity,
        # not that every class resolves to a parsed item descriptor.
        assert item_class, "BOM entry with an empty item class"
        assert quantity > 0.0, f"non-positive BOM quantity for {item_class}: {quantity}"

    # Iron chain sanity: if both an ingot and a plate production node
    # exist, the ingot's task must be commissioned before the plate's.
    node_ids_by_recipe = {
        node.recipe_class: node.node_id
        for node in nodes
        if "ironingot" in node.recipe_class.lower() or "ironplate" in node.recipe_class.lower()
    }
    order_by_node_id = {task.node_id: task.order_index for task in tasks}
    ingot_ids = [nid for recipe, nid in node_ids_by_recipe.items() if "ironingot" in recipe.lower()]
    plate_ids = [nid for recipe, nid in node_ids_by_recipe.items() if "ironplate" in recipe.lower()]
    for ingot_id in ingot_ids:
        for plate_id in plate_ids:
            assert order_by_node_id[ingot_id] < order_by_node_id[plate_id]

    print(f"phase1 tasks={len(tasks)} bom_lines={len(bom)}")
    print("first three:", [task.node_id for task in tasks[:3]])
    print("last:", tasks[-1].node_id)
    print("sample bom:", bom[:3])
    print("diagnostics:", [d.code for d in diagnostics])


# --- SSP-P6-W02: commissioning checks in the construction markdown ----------


def test_construction_plan_to_markdown_includes_commissioning_checks() -> None:
    """Production and extractor tasks each carry a deterministic check line."""
    from satisfactory_reports import construction_plan_to_markdown

    catalog = _catalog()
    node = ProcessNode(
        node_id="node_recipe_ironingot",
        recipe_class="Recipe_IronIngot_C",
        building_class="Build_ConstructorMk1_C",
        runs_per_min=3.0,
        machine_count_exact=3.0,
        machine_count=3,
        clock=100.0,
        power_mw=12.0,
    )
    source = ResourceSource(
        node_id="raw_oreiron",
        item_class="Desc_OreIron_C",
        rate_per_min=120.0,
        extractor_class="Build_MinerMk2_C",
        extractor_count=2,
    )
    stage = _stage(nodes=(node,), sources=(source,))

    tasks, bom, diagnostics, assumptions = build_construction_plan(catalog, stage)
    markdown = construction_plan_to_markdown(catalog, stage, tasks, bom, diagnostics, assumptions)

    assert "## Commissioning Checks" in markdown
    # Extractor task: resource target and belt routing (Desc_OreIron_C is RF_SOLID).
    assert "resource target Desc_OreIron_C" in markdown
    assert "output routed via belt" in markdown
    # Production task: recipe inputs/outputs, clock, and power.
    assert "inputs connected Desc_OreIron_C" in markdown
    assert "output routed Desc_IronIngot_C" in markdown
    assert "clock set to 100.0000%" in markdown
    assert "power available 12.000 MW" in markdown


def test_commissioning_check_line_routes_fluid_extractor_to_pipe() -> None:
    """An RF_LIQUID/RF_GAS resource source reports pipe routing, not belt."""
    from satisfactory_reports import construction_plan_to_markdown

    items = {
        "desc_water": ItemDescriptor(
            class_name="Desc_Water_C", display_name="Water", form="RF_LIQUID"
        ),
    }
    catalog = DocsCatalog(items=items, recipes={}, buildings={})
    source = ResourceSource(
        node_id="raw_water",
        item_class="Desc_Water_C",
        rate_per_min=120.0,
        extractor_class="Build_WaterPump_C",
        extractor_count=1,
    )
    stage = _stage(sources=(source,))

    tasks, bom, diagnostics, assumptions = build_construction_plan(catalog, stage)
    markdown = construction_plan_to_markdown(catalog, stage, tasks, bom, diagnostics, assumptions)

    assert "resource target Water" in markdown
    assert "output routed via pipe" in markdown


def test_commissioning_check_line_falls_back_when_recipe_unresolved() -> None:
    """A node whose recipe_class isn't in the catalog still renders a check line."""
    from satisfactory_reports import construction_plan_to_markdown

    catalog = _catalog()
    node = _node("node_missing_recipe", "Recipe_DoesNotExist_C", "Build_ConstructorMk1_C", 1)
    stage = _stage(nodes=(node,))

    tasks, bom, diagnostics, assumptions = build_construction_plan(catalog, stage)
    markdown = construction_plan_to_markdown(catalog, stage, tasks, bom, diagnostics, assumptions)

    assert "(unresolved recipe)" in markdown


def test_commissioning_checks_section_renders_none_when_no_tasks() -> None:
    from satisfactory_reports import construction_plan_to_markdown

    catalog = _catalog()
    stage = _stage()

    markdown = construction_plan_to_markdown(catalog, stage, (), (), (), ())

    assert "## Commissioning Checks" in markdown
    assert "(none)" in markdown

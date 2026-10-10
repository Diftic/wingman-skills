"""Satisfactory Docs catalog loading and expected-rate helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


_AMOUNT_RE = re.compile(
    r"ItemClass=\"(?P<path>[^\"]+)\"\s*,\s*Amount=(?P<amount>-?\d+(?:\.\d+)?)"
)
_PRODUCED_IN_RE = re.compile(r"\"(?P<path>[^\"]+)\"")


def normalize_class_name(raw: object) -> str:
    """Normalize Unreal class/path text to a stable lookup key."""
    text = str(raw or "").strip().strip("'\"")
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    if text.endswith("_C"):
        text = text[:-2]
    return text.lower()


def display_amount(amount: float, form: str) -> float:
    """Convert docs amount units into player-facing item or m3 units."""
    if form in {"RF_LIQUID", "RF_GAS"}:
        return amount / 1000.0
    return amount


def _float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class ItemAmount:
    class_name: str
    amount: float


@dataclass(frozen=True)
class ItemDescriptor:
    class_name: str
    display_name: str
    form: str
    is_resource: bool = False


@dataclass(frozen=True)
class Recipe:
    class_name: str
    display_name: str
    duration_seconds: float
    ingredients: tuple[ItemAmount, ...]
    products: tuple[ItemAmount, ...]
    produced_in: tuple[str, ...]


@dataclass(frozen=True)
class Building:
    class_name: str
    display_name: str
    manufacturing_speed: float
    power_consumption: float
    extract_cycle_time: float
    items_per_cycle: float
    allowed_resources: tuple[str, ...]
    power_consumption_exponent: float = 1.6


@dataclass(frozen=True)
class Logistics:
    """One belt or pipe tier's throughput capacity.

    ``capacity`` is items/min for a belt (``is_pipe`` False) or m3/min for a
    pipe (``is_pipe`` True); both units already match the player-facing
    numbers shown in the buildable's in-game description.
    """

    class_name: str
    display_name: str
    capacity: float
    is_pipe: bool


@dataclass(frozen=True)
class Schematic:
    class_name: str
    display_name: str
    schematic_type: str
    tech_tier: int
    time_to_complete: float
    cost: tuple[ItemAmount, ...]
    unlocked_recipes: tuple[str, ...]
    dependency_schematics: tuple[str, ...]


_UNLOCK_RECIPE_CLASS = "BP_UnlockRecipe_C"
_SCHEMATIC_DEPENDENCY_CLASS = "BP_SchematicPurchasedDependency_C"
_ALTERNATE_SCHEMATIC_TYPES = frozenset({"EST_Alternate", "EST_HardDrive"})

# "NoIndicator" belt/pipe classes ("Clean Pipeline Mk.1", etc.) are cosmetic
# duplicates of a canonical tier at the same capacity (verified against the
# real Docs: e.g. Build_PipelineMK2_NoIndicator_C shares Build_PipelineMK2_C's
# mFlowLimit); excluded so belts()/pipes() report one entry per tier.
_NON_CANONICAL_LOGISTICS_MARKER = "noindicator"


def _parse_unlocked_recipes(unlocks: object) -> tuple[str, ...]:
    """Parse ``mUnlocks`` entries into normalized unlocked recipe keys."""
    if not isinstance(unlocks, list):
        return ()
    keys: list[str] = []
    for entry in unlocks:
        if not isinstance(entry, dict) or entry.get("Class") != _UNLOCK_RECIPE_CLASS:
            continue
        for path in parse_produced_in(str(entry.get("mRecipes", "") or "")):
            keys.append(normalize_class_name(path))
    return tuple(keys)


def _parse_dependency_schematics(dependencies: object) -> tuple[str, ...]:
    """Parse ``mSchematicDependencies`` entries into normalized schematic keys."""
    if not isinstance(dependencies, list):
        return ()
    keys: list[str] = []
    for entry in dependencies:
        if not isinstance(entry, dict) or entry.get("Class") != _SCHEMATIC_DEPENDENCY_CLASS:
            continue
        for path in parse_produced_in(str(entry.get("mSchematics", "") or "")):
            keys.append(normalize_class_name(path))
    return tuple(keys)


def _build_recipe_schematic_index(
    schematics: dict[str, Schematic],
) -> dict[str, tuple[str, ...]]:
    """Build a recipe key to sorted schematic keys index, once per catalog."""
    index: dict[str, list[str]] = {}
    for schematic_key, schematic in schematics.items():
        for recipe_key in schematic.unlocked_recipes:
            index.setdefault(recipe_key, []).append(schematic_key)
    return {recipe_key: tuple(sorted(keys)) for recipe_key, keys in index.items()}


_NON_AUTOMATABLE_BUILDING_MARKERS = ("workbench", "workshop")


def _is_automatable_recipe(recipe: Recipe, buildings: dict[str, Building]) -> bool:
    """True when a recipe's produced_in resolves to at least one automated building.

    Build-gun and manual-workbench crafting are excluded: the normalized
    building key must start with ``build_`` and must not reference a
    workbench or workshop, and it must resolve to a catalog building.
    """
    for path in recipe.produced_in:
        key = normalize_class_name(path)
        if not key.startswith("build_"):
            continue
        if any(marker in key for marker in _NON_AUTOMATABLE_BUILDING_MARKERS):
            continue
        if key in buildings:
            return True
    return False


class DocsCatalog:
    """Resolved subset of Satisfactory Docs needed for factory mirrors."""

    def __init__(
        self,
        *,
        items: dict[str, ItemDescriptor],
        recipes: dict[str, Recipe],
        buildings: dict[str, Building],
        schematics: dict[str, Schematic] | None = None,
        logistics: dict[str, Logistics] | None = None,
    ) -> None:
        self._items = items
        self._recipes = recipes
        self._buildings = buildings
        self._schematics = schematics or {}
        self._logistics = logistics or {}
        self._recipe_schematics = _build_recipe_schematic_index(self._schematics)
        self._automatable_recipes = tuple(
            sorted(
                (
                    recipe
                    for recipe in self._recipes.values()
                    if _is_automatable_recipe(recipe, self._buildings)
                ),
                key=lambda recipe: recipe.class_name,
            )
        )

    @property
    def item_count(self) -> int:
        return len(self._items)

    @property
    def recipe_count(self) -> int:
        return len(self._recipes)

    @property
    def building_count(self) -> int:
        return len(self._buildings)

    @property
    def schematic_count(self) -> int:
        return len(self._schematics)

    def item(self, class_name: object) -> ItemDescriptor | None:
        return self._items.get(normalize_class_name(class_name))

    def all_items(self) -> tuple[ItemDescriptor, ...]:
        """Return every item descriptor in the catalog, unordered."""
        return tuple(self._items.values())

    def recipe(self, class_name: object) -> Recipe | None:
        return self._recipes.get(normalize_class_name(class_name))

    def all_recipes(self) -> tuple[Recipe, ...]:
        """Return every recipe in the catalog, unordered."""
        return tuple(self._recipes.values())

    def building(self, class_name: object) -> Building | None:
        return self._buildings.get(normalize_class_name(class_name))

    def schematic(self, class_name: object) -> Schematic | None:
        return self._schematics.get(normalize_class_name(class_name))

    def milestones_by_tier(self, tier: int) -> tuple[Schematic, ...]:
        """Return EST_Milestone schematics at the given tech tier, sorted by class name."""
        matches = [
            schematic
            for schematic in self._schematics.values()
            if schematic.schematic_type == "EST_Milestone" and schematic.tech_tier == tier
        ]
        matches.sort(key=lambda schematic: schematic.class_name)
        return tuple(matches)

    def schematics_of_type(self, est_type: str) -> tuple[Schematic, ...]:
        """Return schematics whose raw ``mType`` matches exactly, sorted by class name."""
        matches = [
            schematic
            for schematic in self._schematics.values()
            if schematic.schematic_type == est_type
        ]
        matches.sort(key=lambda schematic: schematic.class_name)
        return tuple(matches)

    def recipe_unlocked_by(self, recipe_class: object) -> tuple[str, ...]:
        """Return the normalized schematic keys that unlock a recipe, sorted."""
        return self._recipe_schematics.get(normalize_class_name(recipe_class), ())

    def is_alternate_recipe(self, recipe_class: object) -> bool:
        """True when the recipe is unlocked by an alternate/hard-drive schematic.

        Also true for recipes named with the ``recipe_alternate_`` prefix, so
        alternates with no unlocking schematic (or missing unlock data) still
        classify correctly.
        """
        key = normalize_class_name(recipe_class)
        if key.startswith("recipe_alternate_"):
            return True
        for schematic_key in self._recipe_schematics.get(key, ()):
            schematic = self._schematics.get(schematic_key)
            if schematic is not None and schematic.schematic_type in _ALTERNATE_SCHEMATIC_TYPES:
                return True
        return False

    def item_display_name(self, class_name: object) -> str:
        item = self.item(class_name)
        if item is not None and item.display_name:
            return item.display_name
        text = str(class_name or "")
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        if "/" in text:
            text = text.rsplit("/", 1)[-1]
        return text.removesuffix("_C")

    def rate_amount(self, amount: ItemAmount) -> float:
        item = self.item(amount.class_name)
        form = item.form if item is not None else ""
        return display_amount(amount.amount, form)

    def raw_resource_classes(self) -> frozenset[str]:
        """Return normalized class keys of every raw-resource item.

        Raw resources are items parsed from the ``FGResourceDescriptor``
        docs group (ores, water, and similar extractables).
        """
        return frozenset(key for key, item in self._items.items() if item.is_resource)

    def belts(self) -> tuple[Logistics, ...]:
        """Return every parsed conveyor-belt tier, sorted by ascending capacity."""
        return tuple(
            sorted(
                (entry for entry in self._logistics.values() if not entry.is_pipe),
                key=lambda entry: entry.capacity,
            )
        )

    def pipes(self) -> tuple[Logistics, ...]:
        """Return every parsed pipeline tier, sorted by ascending capacity."""
        return tuple(
            sorted(
                (entry for entry in self._logistics.values() if entry.is_pipe),
                key=lambda entry: entry.capacity,
            )
        )

    def automatable_recipes(self) -> tuple[Recipe, ...]:
        """Return recipes producible in an automated building, sorted by class name.

        A recipe qualifies when at least one of its ``produced_in`` entries
        resolves to a catalog building whose normalized key starts with
        ``build_`` and does not reference a workbench or workshop (manual
        and build-gun crafting are excluded). Computed once in the
        constructor.
        """
        return self._automatable_recipes


def _decode_docs(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") or b"\x00" in raw[:100]:
        return raw.decode("utf-16")
    return raw.decode("utf-8")


def _path_class(path_text: str) -> str:
    text = path_text.strip().strip("'\"")
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 2 and parts[1]:
            text = parts[1]
    text = text.strip("'\"")
    if "." in text:
        return text.rsplit(".", 1)[-1]
    return text.rsplit("/", 1)[-1]


def parse_item_amounts(raw: str) -> tuple[ItemAmount, ...]:
    """Parse docs ``mIngredients`` / ``mProduct`` strings."""
    amounts: list[ItemAmount] = []
    for match in _AMOUNT_RE.finditer(raw or ""):
        amounts.append(
            ItemAmount(
                class_name=_path_class(match.group("path")),
                amount=_float(match.group("amount")),
            )
        )
    return tuple(amounts)


def parse_produced_in(raw: str) -> tuple[str, ...]:
    """Parse docs ``mProducedIn`` machine path strings."""
    result: list[str] = []
    for match in _PRODUCED_IN_RE.finditer(raw or ""):
        result.append(_path_class(match.group("path")))
    return tuple(result)


def load_docs_catalog(path: Path) -> DocsCatalog:
    """Load the Satisfactory ``CommunityResources/Docs/en-US.json`` catalog."""
    docs_path = path.resolve()
    data = json.loads(_decode_docs(docs_path))
    if not isinstance(data, list):
        raise ValueError(f"Unexpected docs JSON root in {path}")

    items: dict[str, ItemDescriptor] = {}
    recipes: dict[str, Recipe] = {}
    buildings: dict[str, Building] = {}
    schematics: dict[str, Schematic] = {}
    logistics: dict[str, Logistics] = {}

    for group in data:
        if not isinstance(group, dict):
            continue
        native = str(group.get("NativeClass", ""))
        classes = group.get("Classes", [])
        if not isinstance(classes, list):
            continue

        if "FGItemDescriptor" in native or "FGResourceDescriptor" in native:
            is_resource = "FGResourceDescriptor" in native
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                key = normalize_class_name(class_name)
                items[key] = ItemDescriptor(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    form=str(row.get("mForm", "") or ""),
                    is_resource=is_resource,
                )
            continue

        if "FGRecipe" in native:
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                recipe = Recipe(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    duration_seconds=max(_float(row.get("mManufactoringDuration")), 0.001),
                    ingredients=parse_item_amounts(str(row.get("mIngredients", ""))),
                    products=parse_item_amounts(str(row.get("mProduct", ""))),
                    produced_in=parse_produced_in(str(row.get("mProducedIn", ""))),
                )
                recipes[normalize_class_name(class_name)] = recipe
            continue

        # Exact suffix match (not substring containment): the Docs also
        # define FGBuildablePipelineJunction and FGBuildablePipelinePump,
        # which contain "FGBuildablePipeline" as a substring but are not
        # pipe segments and carry no mFlowLimit (verified against the real
        # Docs, where a loose substring check pulled in zero-capacity
        # "pipe" entries for those buildables).
        if native.endswith(".FGBuildableConveyorBelt'"):
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                key = normalize_class_name(class_name)
                if _NON_CANONICAL_LOGISTICS_MARKER in key:
                    continue
                # mSpeed is in belt items/min * 2 (verified against every real
                # Mk1-Mk6 belt's in-game description, e.g. Mk1 mSpeed=120 ->
                # "Transports up to 60 resources per minute").
                logistics[key] = Logistics(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    capacity=_float(row.get("mSpeed")) / 2.0,
                    is_pipe=False,
                )
            continue

        if native.endswith(".FGBuildablePipeline'"):
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                key = normalize_class_name(class_name)
                if _NON_CANONICAL_LOGISTICS_MARKER in key:
                    continue
                # mFlowLimit is in m3/sec (verified against both real pipe
                # tiers' in-game description, e.g. Mk1 mFlowLimit=5.0 ->
                # "Capacity: 300/m3 of fluid per minute").
                logistics[key] = Logistics(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    capacity=_float(row.get("mFlowLimit")) * 60.0,
                    is_pipe=True,
                )
            continue

        if "FGBuildable" in native:
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                building = Building(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    manufacturing_speed=_float(row.get("mManufacturingSpeed"), 1.0) or 1.0,
                    power_consumption=_float(row.get("mPowerConsumption")),
                    extract_cycle_time=_float(row.get("mExtractCycleTime")),
                    items_per_cycle=float(_int(row.get("mItemsPerCycle"))),
                    allowed_resources=parse_produced_in(str(row.get("mAllowedResources", ""))),
                    power_consumption_exponent=_float(row.get("mPowerConsumptionExponent"), 1.6),
                )
                buildings[normalize_class_name(class_name)] = building
            continue

        if "FGSchematic" in native:
            for row in classes:
                class_name = str(row.get("ClassName", ""))
                if not class_name:
                    continue
                schematic = Schematic(
                    class_name=class_name,
                    display_name=str(row.get("mDisplayName", "") or class_name),
                    schematic_type=str(row.get("mType", "") or ""),
                    tech_tier=_int(row.get("mTechTier")),
                    time_to_complete=_float(row.get("mTimeToComplete")),
                    cost=parse_item_amounts(str(row.get("mCost", "") or "")),
                    unlocked_recipes=_parse_unlocked_recipes(row.get("mUnlocks")),
                    dependency_schematics=_parse_dependency_schematics(
                        row.get("mSchematicDependencies")
                    ),
                )
                schematics[normalize_class_name(class_name)] = schematic

    return DocsCatalog(
        items=items,
        recipes=recipes,
        buildings=buildings,
        schematics=schematics,
        logistics=logistics,
    )



"""Project Assembly phase progression data and capability snapshots.

Pure module: no Wingman imports, stdlib only, except for reusing the
Docs catalog types and the shared class-name normalizer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from satisfactory_docs import DocsCatalog, normalize_class_name


_DATA_FILE = Path(__file__).resolve().parent / "data" / "project_assembly_phases.json"
_SUPPORTED_SCHEMA_VERSIONS = frozenset({1})
_MIN_PACE_MULTIPLIER = 1.0
_MAX_PACE_MULTIPLIER = 3.0
_EXPECTED_PHASE_NUMBERS = frozenset({1, 2, 3, 4, 5})
_MILESTONE_SCHEMATIC_TYPE = "EST_Milestone"


@dataclass(frozen=True)
class PhasePart:
    item_class: str
    display_name: str
    quantity: float


@dataclass(frozen=True)
class PhaseDefinition:
    phase: int
    name: str
    window_hours_baseline: float
    unlocks_tiers: tuple[int, ...]
    parts: tuple[PhasePart, ...]


@dataclass(frozen=True)
class ProjectAssemblyData:
    base_tiers: tuple[int, ...]
    phases: tuple[PhaseDefinition, ...]


@dataclass(frozen=True)
class PhaseDemand:
    item_class: str
    display_name: str
    quantity: float
    required_rate_per_minute: float


@dataclass(frozen=True)
class PhaseDemandSet:
    phase: int
    name: str
    pace_multiplier: float
    window_hours: float
    demands: tuple[PhaseDemand, ...]


@dataclass(frozen=True)
class CapabilitySnapshot:
    upcoming_phase: int
    max_tier: int
    purchased_schematics: frozenset[str]
    allowed_recipes: frozenset[str]


def _read_json(path: Path) -> object:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(
            f"Could not read Project Assembly phase data at {path}: {error}"
        ) from error
    try:
        return json.loads(raw)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Malformed Project Assembly phase data at {path}: {error}"
        ) from error


def _parse_part(phase_number: int, entry: object, path: Path) -> PhasePart:
    if not isinstance(entry, dict):
        raise ValueError(f"Phase {phase_number} has a malformed part entry in {path}")
    quantity = entry.get("quantity")
    if not isinstance(quantity, (int, float)) or isinstance(quantity, bool) or quantity <= 0:
        raise ValueError(
            f"Phase {phase_number} part {entry.get('item_class')!r} has a "
            f"non-positive quantity in {path}"
        )
    return PhasePart(
        item_class=str(entry.get("item_class", "")),
        display_name=str(entry.get("display_name", "")),
        quantity=float(quantity),
    )


def _parse_phase(entry: object, path: Path) -> PhaseDefinition:
    if not isinstance(entry, dict):
        raise ValueError(f"Phase entry must be an object in {path}")

    phase_number = entry.get("phase")
    if not isinstance(phase_number, int) or isinstance(phase_number, bool):
        raise ValueError(f"Phase entry missing integer 'phase' in {path}")

    parts_raw = entry.get("parts")
    if not isinstance(parts_raw, list) or not parts_raw:
        raise ValueError(f"Phase {phase_number} has no parts in {path}")
    parts = tuple(_parse_part(phase_number, part_entry, path) for part_entry in parts_raw)

    unlocks_tiers_raw = entry.get("unlocks_tiers", [])
    if not isinstance(unlocks_tiers_raw, list):
        raise ValueError(f"Phase {phase_number} has an invalid 'unlocks_tiers' in {path}")

    return PhaseDefinition(
        phase=phase_number,
        name=str(entry.get("name", "")),
        window_hours_baseline=float(entry.get("window_hours_baseline", 0.0)),
        unlocks_tiers=tuple(int(tier) for tier in unlocks_tiers_raw),
        parts=parts,
    )


def load_project_assembly_phases(path: Path | None = None) -> ProjectAssemblyData:
    """Load and structurally validate the bundled Project Assembly phase data.

    Args:
        path: Optional override path to a phase data JSON file. Defaults to
            the bundled file next to this module.

    Returns:
        The base tiers and phase definitions (ordered by phase number,
        1 through 5) as a single ``ProjectAssemblyData`` value.

    Raises:
        ValueError: The file cannot be read, is not valid JSON, has an
            unsupported schema_version, has a missing or invalid
            base_tiers list, does not define exactly phases 1-5 once
            each, or any phase has an empty parts list or a non-positive
            part quantity.
    """
    docs_path = path if path is not None else _DATA_FILE
    data = _read_json(docs_path)

    if not isinstance(data, dict):
        raise ValueError(f"Unexpected Project Assembly phase data root in {docs_path}")

    schema_version = data.get("schema_version")
    if schema_version not in _SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(f"Unsupported schema_version {schema_version!r} in {docs_path}")

    base_tiers_raw = data.get("base_tiers")
    if not isinstance(base_tiers_raw, list):
        raise ValueError(f"Missing or invalid 'base_tiers' in {docs_path}")
    base_tiers = tuple(int(tier) for tier in base_tiers_raw)

    phases_raw = data.get("phases")
    if not isinstance(phases_raw, list):
        raise ValueError(f"Missing or invalid 'phases' list in {docs_path}")

    phases = [_parse_phase(entry, docs_path) for entry in phases_raw]

    phase_numbers = [phase.phase for phase in phases]
    if set(phase_numbers) != _EXPECTED_PHASE_NUMBERS or len(phase_numbers) != len(
        _EXPECTED_PHASE_NUMBERS
    ):
        raise ValueError(
            f"Project Assembly phase data must define exactly phases 1-5 "
            f"once each, found {sorted(phase_numbers)} in {docs_path}"
        )

    phases.sort(key=lambda phase: phase.phase)
    return ProjectAssemblyData(base_tiers=base_tiers, phases=tuple(phases))


def validate_phases_against_docs(
    data: ProjectAssemblyData, catalog: DocsCatalog
) -> tuple[str, ...]:
    """Cross-check bundled phase data against the installed Docs catalog.

    Returns diagnostics instead of raising: a game-patch item rename must
    degrade gracefully, not crash the skill.

    Args:
        data: Project Assembly data to validate.
        catalog: Docs catalog to resolve each part's item class against.

    Returns:
        Human-readable diagnostic strings, one per unresolved item class;
        empty when every item class resolves.
    """
    diagnostics: list[str] = []
    for phase in data.phases:
        for part in phase.parts:
            if catalog.item(part.item_class) is None:
                diagnostics.append(
                    f"Phase {phase.phase} ({phase.name}): item class "
                    f"'{part.item_class}' not found in Docs catalog"
                )
    return tuple(diagnostics)


def derive_phase_demand(
    data: ProjectAssemblyData,
    phase: int,
    pace_multiplier: float = 1.0,
) -> PhaseDemandSet:
    """Derive per-minute production demand for a phase at a given pace.

    Args:
        data: Project Assembly data to look up the phase in.
        phase: The 1-5 phase number to derive demand for.
        pace_multiplier: Multiplier applied to the baseline window hours.
            Must be between 1.0 and 3.0 inclusive.

    Returns:
        The demand set for the requested phase, with each part's required
        rate in items per minute.

    Raises:
        ValueError: If phase is unknown, or pace_multiplier is outside
            [1.0, 3.0]. The pace is never silently clamped.
    """
    if not (_MIN_PACE_MULTIPLIER <= pace_multiplier <= _MAX_PACE_MULTIPLIER):
        raise ValueError(
            f"pace_multiplier {pace_multiplier} out of range "
            f"[{_MIN_PACE_MULTIPLIER}, {_MAX_PACE_MULTIPLIER}]"
        )

    definition = next((candidate for candidate in data.phases if candidate.phase == phase), None)
    if definition is None:
        raise ValueError(f"Unknown phase {phase}")

    window_hours = definition.window_hours_baseline * pace_multiplier
    window_minutes = window_hours * 60.0
    demands = tuple(
        PhaseDemand(
            item_class=part.item_class,
            display_name=part.display_name,
            quantity=part.quantity,
            required_rate_per_minute=part.quantity / window_minutes,
        )
        for part in definition.parts
    )
    return PhaseDemandSet(
        phase=definition.phase,
        name=definition.name,
        pace_multiplier=pace_multiplier,
        window_hours=window_hours,
        demands=demands,
    )


def available_tiers_for_phase(
    data: ProjectAssemblyData,
    upcoming_phase: int,
) -> frozenset[int]:
    """Return the tech tiers available while planning for an upcoming phase.

    Implements the "do not use technology unlocked by completing the
    upcoming phase" rule: base tiers plus every tier unlocked by phases
    strictly before ``upcoming_phase``.

    Args:
        data: Project Assembly data providing base tiers and phase unlocks.
        upcoming_phase: The phase currently being planned for; its own
            unlocks are excluded.

    Returns:
        The set of tech tiers available for planning.
    """
    tiers = set(data.base_tiers)
    for definition in data.phases:
        if definition.phase < upcoming_phase:
            tiers.update(definition.unlocks_tiers)
    return frozenset(tiers)


def build_capability_snapshot(
    catalog: DocsCatalog,
    data: ProjectAssemblyData,
    upcoming_phase: int,
    extra_schematics: tuple[str, ...] = (),
    include_alternates: tuple[str, ...] = (),
) -> CapabilitySnapshot:
    """Build the purchased-schematic and allowed-recipe gate for a phase.

    Purchased schematics are EST_Milestone, EST_Tutorial, and EST_Custom
    schematics at an available tech tier from the Docs catalog, plus
    extra_schematics regardless of tier. EST_MAM and EST_HardDrive unlocks
    remain excluded by default. Allowed recipes are every recipe unlocked
    by a purchased schematic, plus every catalog automatable recipe with
    no unlocking schematic at all (base recipes with no schematic gate,
    such as Iron Screw, are always craftable). Alternate recipes (per
    catalog.is_alternate_recipe) are excluded from both sources unless
    explicitly opted into via include_alternates.

    Args:
        catalog: Docs catalog providing schematic and recipe data.
        data: Project Assembly data used to derive available tiers.
        upcoming_phase: The phase currently being planned for.
        extra_schematics: Additional schematic class names to treat as
            purchased regardless of tier (normalized before use).
        include_alternates: Alternate recipe class names to allow despite
            the default alternate exclusion (normalized before use).

    Returns:
        The capability snapshot for the requested phase.
    """
    available_tiers = available_tiers_for_phase(data, upcoming_phase)
    max_tier = max(available_tiers) if available_tiers else 0

    normalized_extra = frozenset(normalize_class_name(key) for key in extra_schematics)
    normalized_alternates = frozenset(normalize_class_name(key) for key in include_alternates)

    purchased: set[str] = set(normalized_extra)
    for tier in available_tiers:
        for schematic in catalog.milestones_by_tier(tier):
            purchased.add(normalize_class_name(schematic.class_name))
    for est_type in ("EST_Tutorial", "EST_Custom"):
        for schematic in catalog.schematics_of_type(est_type):
            if schematic.tech_tier in available_tiers:
                purchased.add(normalize_class_name(schematic.class_name))

    allowed_recipes: set[str] = set(normalized_alternates)
    for schematic_key in purchased:
        schematic = catalog.schematic(schematic_key)
        if schematic is None:
            continue
        for recipe_key in schematic.unlocked_recipes:
            if catalog.is_alternate_recipe(recipe_key) and recipe_key not in normalized_alternates:
                continue
            allowed_recipes.add(recipe_key)

    for recipe in catalog.automatable_recipes():
        recipe_key = normalize_class_name(recipe.class_name)
        if catalog.recipe_unlocked_by(recipe_key):
            continue
        if catalog.is_alternate_recipe(recipe_key):
            continue
        allowed_recipes.add(recipe_key)

    return CapabilitySnapshot(
        upcoming_phase=upcoming_phase,
        max_tier=max_tier,
        purchased_schematics=frozenset(purchased),
        allowed_recipes=frozenset(allowed_recipes),
    )

"""Locate factory lines/machines in a save mirror and render location maps.

Pure module: no Wingman runtime imports and no catalog dependency. Operates
only on an already-built mirror payload (``satisfactory_mirror.py``), whose
lines carry a ``primaryOutput`` display name and whose machines carry the raw
``recipe``/``resource``/``type`` class-ish strings straight from the save
snapshot. Pillow is imported lazily inside ``render_map`` (mirroring the
lazy-scipy precedent in ``satisfactory_solver.py``) so an install missing
Pillow degrades to text-only coordinates instead of failing at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

_MAX_LOCATE_LIMIT = 5
_MAX_MAP_HITS = 100

_CANVAS_SIZE = 1024
_PLOT_MARGIN_PX = 80
_BOUNDING_BOX_MARGIN_FRACTION = 0.05
_HIGHLIGHT_RADIUS_PX = 12
_HIT_MARKER_RADIUS_PX = 5
_BACKGROUND_RGB = (250, 250, 245)
_BORDER_RGB = (0, 0, 0)
_FAINT_POINT_RGB = (180, 180, 180)
_HIT_MARKER_RGB = (30, 90, 200)
_HIGHLIGHT_RGB = (200, 30, 30)
_LABEL_RGB = (0, 0, 0)
_TERRAIN_LABEL_RGB = (255, 255, 255)
_TERRAIN_LABEL_SHADOW_RGB = (0, 0, 0)
_TERRAIN_MIN_VIEWPORT_CM = 125_000.0
_TERRAIN_CROP_MARGIN_FRACTION = 0.18

# The canonical cropped Satisfactory world-map bounds in Unreal centimetres.
# Image Y and world Y both grow south/down; unlike the schematic renderer, the
# terrain transform therefore must not invert Y.
_WORLD_MIN_X_CM = -324_698.832031
_WORLD_MAX_X_CM = 425_301.832031
_WORLD_MIN_Y_CM = -375_000.0
_WORLD_MAX_Y_CM = 375_000.0

# Save class names are implementation names, not the terms players use. The
# first alias is the map label; the rest are accepted search vocabulary. The
# generic humanizer below remains the fallback for future machine classes.
_MACHINE_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "Build_MinerMk1": ("Miner Mk.1", "miner", "mining extractor"),
    "Build_MinerMk2": ("Miner Mk.2", "miner", "mining extractor"),
    "Build_MinerMk3": ("Miner Mk.3", "miner", "mining extractor"),
    "Build_SmelterMk1": ("Smelter",),
    "Build_FoundryMk1": ("Foundry",),
    "Build_ConstructorMk1": ("Constructor",),
    "Build_AssemblerMk1": ("Assembler",),
    "Build_ManufacturerMk1": ("Manufacturer",),
    "Build_OilRefinery": ("Refinery", "oil refinery"),
    "Build_Packager": ("Packager", "packaging machine"),
    "Build_Blender": ("Blender",),
    "Build_HadronCollider": ("Particle Accelerator", "hadron collider"),
    "Build_Converter": ("Converter",),
    "Build_QuantumEncoder": ("Quantum Encoder",),
    "Build_OilPump": ("Oil Extractor", "oil pump", "oil field", "oil node"),
    "Build_WaterPump": ("Water Extractor", "water pump", "water node"),
    "Build_FrackingSmasher": (
        "Resource Well Pressurizer",
        "fracking smasher",
        "resource well",
    ),
    "Build_FrackingExtractor": (
        "Resource Well Extractor",
        "fracking extractor",
        "resource well",
    ),
    "Build_GeneratorGeoThermal": ("Geothermal Generator", "geothermal"),
    "Build_GeneratorCoal": ("Coal-Powered Generator", "coal generator"),
    "Build_GeneratorFuel": ("Fuel-Powered Generator", "fuel generator"),
    "Build_GeneratorNuclear": ("Nuclear Power Plant", "nuclear generator"),
    "Build_GeneratorBiomass": ("Biomass Burner", "biomass generator"),
}


@dataclass(frozen=True)
class LocationHit:
    """One matched location: an inferred production line or a single machine.

    ``machine_count`` is set (non-``None``) for ``kind == "line"``;
    ``clock`` is set for ``kind == "machine"``. Coordinates are world-cm,
    matching the mirror's own units (see ``satisfactory_mirror._location``).
    """

    label: str
    kind: str
    x: float
    y: float
    z: float
    machine_count: int | None = None
    clock: float | None = None


def _rank(candidates: list[str], query: str) -> int | None:
    """Rank a location candidate against a lowercased query.

    Mirrors ``satisfactory_dataset._match_rank``'s exact/prefix/substring
    scheme (0/1/2, else ``None``) but checks several raw fields per
    location (recipe, resource, type for machines; primary-output item for
    lines) and keeps the best (lowest) rank found.
    """
    best: int | None = None
    query_forms = {query.lower(), _normalize_search_text(query)}
    for candidate in candidates:
        if not candidate:
            continue
        candidate_forms = {candidate.lower(), _normalize_search_text(candidate)}
        for candidate_form in candidate_forms:
            for query_form in query_forms:
                if not query_form:
                    continue
                if candidate_form == query_form:
                    rank = 0
                elif candidate_form.startswith(query_form):
                    rank = 1
                elif query_form in candidate_form:
                    rank = 2
                else:
                    continue
                if best is None or rank < best:
                    best = rank
    return best


def _singularize_word(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _normalize_search_text(value: str) -> str:
    human = _humanize_class_name(value).lower().replace(".", "")
    words = re.findall(r"[a-z0-9]+", human)
    return " ".join(_singularize_word(word) for word in words)


def _query_variants(query: str) -> tuple[str, ...]:
    """Expand common player language into the save's class/display terms.

    Satisfactory serializes an Oil Extractor as ``Build_OilPump``. Players
    naturally say oil field, oil node, or oil extractor, none of which is a
    literal substring of that class. Variants are ordered by intent so an
    extractor request ranks individual pumps before the broader Crude Oil
    production lines.
    """
    normalized = " ".join(query.strip().lower().replace("_", " ").split())
    # Faster Whisper commonly joins spoken "oil extractors" into "oilless
    # extractors". Treat that factory-domain homophone as oil rather than
    # silently falling back to broad oil-production lines.
    normalized = re.sub(r"\boil[ -]?less\b", "oil", normalized)
    compact = normalized.replace(" ", "")
    variants = [normalized]
    if "oil" in normalized:
        extractor_intent = any(
            token in compact
            for token in ("oilfield", "oilnode", "oilextractor", "oilpump")
        )
        additions = ("oilpump", "oil extractor") if extractor_intent else (
            "crude oil",
            "oilpump",
            "oil",
        )
        variants.extend(additions)
    if "nitrogen" in normalized:
        variants.extend(("nitrogen gas", "nitrogen"))
    return tuple(dict.fromkeys(variant for variant in variants if variant))


def query_targets_machine_type(query: str) -> bool:
    normalized = " ".join(query.strip().lower().replace("_", " ").split())
    normalized = re.sub(r"\boil[ -]?less\b", "oil", normalized)
    query_form = _normalize_search_text(normalized)
    query_compact = query_form.replace(" ", "")
    if re.search(r"\bextract(?:or|ion)s?\b", query_form):
        return True
    for aliases in _MACHINE_TYPE_ALIASES.values():
        for alias in aliases:
            alias_form = _normalize_search_text(alias)
            alias_compact = alias_form.replace(" ", "")
            if (
                alias_form in query_form
                or alias_compact in query_compact
            ):
                return True
    return False


def _query_requires_extractor(query: str) -> bool:
    query_form = _normalize_search_text(query)
    return re.search(r"\bextract(?:or|ion)s?\b", query_form) is not None


def _humanize_class_name(value: str) -> str:
    text = value.strip()
    for prefix in ("Build_", "Recipe_", "Desc_"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.endswith("_C"):
        text = text[:-2]
    text = text.replace("_", " ")
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).strip()


def _machine_type_aliases(machine_type: str) -> tuple[str, ...]:
    key = machine_type[:-2] if machine_type.endswith("_C") else machine_type
    aliases = _MACHINE_TYPE_ALIASES.get(key)
    if aliases is not None:
        return aliases
    # Future Mk variants still get a useful base alias without code changes.
    without_mark = re.sub(r"Mk\d+$", "", key)
    human = _humanize_class_name(key)
    base = _humanize_class_name(without_mark)
    return tuple(dict.fromkeys(alias for alias in (human, base) if alias))


def _line_hit(line: dict[str, Any]) -> tuple[str, LocationHit] | None:
    centroid = line.get("centroid") or {}
    x, y, z = centroid.get("x"), centroid.get("y"), centroid.get("z")
    if x is None or y is None or z is None:
        return None
    primary = line.get("primaryOutput") or {}
    item_name = str(primary.get("item") or "").strip()
    label = f"{item_name} line" if item_name else str(line.get("id") or "line")
    return item_name, LocationHit(
        label=label,
        kind="line",
        x=float(x),
        y=float(y),
        z=float(z),
        machine_count=int(line.get("machineCount") or 0),
    )


def _machine_hit(
    machine: dict[str, Any],
) -> tuple[list[str], list[str], LocationHit] | None:
    location = machine.get("location") or None
    if location is None:
        return None
    x, y, z = location.get("x"), location.get("y"), location.get("z")
    if x is None or y is None or z is None:
        return None
    recipe = str(machine.get("recipe") or "").strip()
    resource = str(machine.get("resource") or "").strip()
    machine_type = str(machine.get("type") or "").strip()
    unresolved_resource = resource.lower().startswith("persistent_level:")
    type_aliases = _machine_type_aliases(machine_type)
    type_label = type_aliases[0] if type_aliases else ""
    if machine_type.rstrip("_C") == "Build_FrackingExtractor" and resource:
        label = f"{_humanize_class_name(resource)} Resource Well Extractor"
    else:
        label = (
            recipe
            or (resource if resource and not unresolved_resource else "")
            or type_label
            or str(machine.get("id") or "machine")
        )
    type_candidates = [machine_type, *type_aliases]
    candidates = [recipe, resource, *type_candidates, label]
    return candidates, type_candidates, LocationHit(
        label=label,
        kind="machine",
        x=float(x),
        y=float(y),
        z=float(z),
        clock=float(machine.get("clock") or 0.0),
    )


def _ranked_locations(mirror: dict[str, Any], query: str) -> list[LocationHit]:
    """Return every matching hit in deterministic relevance order."""
    query_variants = _query_variants(query)
    if not query_variants:
        return []

    ranked: list[tuple[int, str, LocationHit]] = []
    extractor_only = _query_requires_extractor(query)

    if not query_targets_machine_type(query):
        for line in mirror.get("lines", []) or []:
            result = _line_hit(line)
            if result is None:
                continue
            item_name, hit = result
            ranks = [
                variant_index * 3 + rank
                for variant_index, variant in enumerate(query_variants)
                if (rank := _rank([item_name], variant)) is not None
            ]
            if not ranks:
                continue
            ranked.append((min(ranks), hit.label.lower(), hit))

    for machine in mirror.get("machines", []) or []:
        result = _machine_hit(machine)
        if result is None:
            continue
        candidates, type_candidates, hit = result
        if extractor_only and not any(
            "extractor" in _normalize_search_text(candidate)
            for candidate in type_candidates
        ):
            continue
        ranks = [
            variant_index * 3 + rank
            for variant_index, variant in enumerate(query_variants)
            if (rank := _rank(candidates, variant)) is not None
        ]
        if not ranks:
            continue
        rank = min(ranks)
        type_ranks = [
            variant_index * 3 + type_rank
            for variant_index, variant in enumerate(query_variants)
            if (type_rank := _rank(type_candidates, variant)) is not None
        ]
        if type_ranks and min(type_ranks) == rank and type_candidates[1:]:
            hit = replace(hit, label=type_candidates[1])
        ranked.append((rank, hit.label.lower(), hit))

    ranked.sort(key=lambda entry: (entry[0], entry[1], entry[2].x, entry[2].y))
    return [hit for _, _, hit in ranked]


def find_locations(
    mirror: dict[str, Any], query: str, limit: int = 5
) -> tuple[LocationHit, ...]:
    """Search a mirror and return the five response-sized best matches.

    Case-insensitive; lines are matched on their primary output's display
    name, machines on recipe/resource/type and player-facing aliases. An
    empty query returns no hits. ``limit`` is clamped to 1..5 so spoken tool
    responses remain bounded.
    """
    capped_limit = max(1, min(limit, _MAX_LOCATE_LIMIT))
    return tuple(_ranked_locations(mirror, query)[:capped_limit])


def find_map_locations(
    mirror: dict[str, Any], query: str, limit: int = _MAX_MAP_HITS
) -> tuple[LocationHit, ...]:
    """Return enough matches to draw the complete requested building set."""
    capped_limit = max(1, min(limit, _MAX_MAP_HITS))
    return tuple(_ranked_locations(mirror, query)[:capped_limit])


def _world_to_terrain_px(
    x: float,
    y: float,
    width: int,
    height: int,
) -> tuple[float, float]:
    """Map world centimetres to the canonical full-world terrain image."""
    px = (x - _WORLD_MIN_X_CM) / (_WORLD_MAX_X_CM - _WORLD_MIN_X_CM)
    py = (y - _WORLD_MIN_Y_CM) / (_WORLD_MAX_Y_CM - _WORLD_MIN_Y_CM)
    return px * max(width - 1, 0), py * max(height - 1, 0)


def _terrain_crop_box(
    hits: tuple[LocationHit, ...],
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    """Return a clamped square crop around hits with useful geographic context."""
    if not hits:
        return 0, 0, width, height

    pixels = [_world_to_terrain_px(hit.x, hit.y, width, height) for hit in hits]
    xs = [point[0] for point in pixels]
    ys = [point[1] for point in pixels]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    min_viewport = (
        _TERRAIN_MIN_VIEWPORT_CM
        / (_WORLD_MAX_X_CM - _WORLD_MIN_X_CM)
        * min(width, height)
    )
    side = max(span * (1.0 + 2.0 * _TERRAIN_CROP_MARGIN_FRACTION), min_viewport)
    side = min(side, float(min(width, height)))
    centre_x = (min(xs) + max(xs)) / 2.0
    centre_y = (min(ys) + max(ys)) / 2.0
    left = min(max(centre_x - side / 2.0, 0.0), width - side)
    top = min(max(centre_y - side / 2.0, 0.0), height - side)
    return (
        int(round(left)),
        int(round(top)),
        int(round(left + side)),
        int(round(top + side)),
    )


def _render_terrain_map(
    hits: tuple[LocationHit, ...],
    out_path: Path,
    terrain_path: Path,
    highlight_index: int,
    fit_to_hits: bool,
    compact_labels: bool,
) -> bool:
    """Render numbered location pins over a calibrated geographic base image."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    try:
        with Image.open(terrain_path) as source:
            terrain = source.convert("RGB")
    except (OSError, ValueError):
        return False

    width, height = terrain.size
    if width < 2 or height < 2:
        return False
    crop = _terrain_crop_box(hits, width, height) if fit_to_hits else (0, 0, width, height)
    left, top, right, bottom = crop
    resampling = getattr(Image, "Resampling", Image)
    cropped = terrain.crop(crop).resize(
        (_CANVAS_SIZE, _CANVAS_SIZE),
        resample=resampling.LANCZOS,
    )
    draw = ImageDraw.Draw(cropped)
    crop_width = max(right - left, 1)
    crop_height = max(bottom - top, 1)

    def to_px(x: float, y: float) -> tuple[int, int]:
        source_x, source_y = _world_to_terrain_px(x, y, width, height)
        px = (source_x - left) / crop_width * _CANVAS_SIZE
        py = (source_y - top) / crop_height * _CANVAS_SIZE
        return int(round(px)), int(round(py))

    for index, hit in enumerate(hits):
        px, py = to_px(hit.x, hit.y)
        if not (0 <= px < _CANVAS_SIZE and 0 <= py < _CANVAS_SIZE):
            continue
        highlighted = index == highlight_index
        radius = 14 if highlighted else 11
        fill = _HIGHLIGHT_RGB if highlighted else _HIT_MARKER_RGB
        draw.ellipse(
            (px - radius, py - radius, px + radius, py + radius),
            fill=fill,
            outline=(255, 255, 255),
            width=3,
        )
        marker_label = str(index + 1) if compact_labels else hit.label
        text_x = px - 3 if compact_labels and index < 9 else px + radius + 4
        text_y = py - 6
        draw.text(
            (text_x + 1, text_y + 1),
            marker_label,
            fill=_TERRAIN_LABEL_SHADOW_RGB,
        )
        draw.text((text_x, text_y), marker_label, fill=_TERRAIN_LABEL_RGB)

    if compact_labels and hits:
        summary = f"{len(hits)} match{'es' if len(hits) != 1 else ''}: {hits[0].label}"
        draw.rounded_rectangle((8, 8, 290, 32), radius=5, fill=(0, 0, 0))
        draw.text((14, 14), summary, fill=_TERRAIN_LABEL_RGB)
    draw.rectangle((0, 0, _CANVAS_SIZE - 1, _CANVAS_SIZE - 1), outline=_BORDER_RGB, width=2)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cropped.save(out_path, format="PNG")
    return True


def render_map(
    hits: tuple[LocationHit, ...],
    all_points: tuple[tuple[float, float], ...],
    out_path: Path,
    highlight_index: int = 0,
    fit_to_hits: bool = False,
    compact_labels: bool = False,
    terrain_path: Path | None = None,
) -> bool:
    """Render a 1024x1024 PNG pinning ``hits`` on terrain or a coordinate grid.

    ``all_points`` (world-cm x/y for every machine in the mirror, regardless
    of match) sets the bounding box so the grid reflects the whole factory,
    not just the hits. Faint dots mark every point in ``all_points``, small
    labeled markers mark each hit, and the hit at ``highlight_index`` also
    gets a ring plus crosshair. Axis labels are in meters; a north-up note
    is included; all text is ASCII-only.

    Deterministic for identical inputs: nothing time-seeded or random is
    drawn, and Pillow's PNG encoder is deterministic for identical pixel
    data, so two renders of the same inputs are byte-identical.

    When ``terrain_path`` names a readable image, its canonical Satisfactory
    world coordinates are used and the view is cropped around the matches.
    Missing or invalid terrain gracefully falls back to the schematic.

    Returns:
        ``True`` if the PNG was written, ``False`` (no file written) when
        Pillow is unavailable in this environment.
    """
    if terrain_path is not None and terrain_path.is_file():
        rendered = _render_terrain_map(
            hits,
            out_path,
            terrain_path,
            highlight_index,
            fit_to_hits,
            compact_labels,
        )
        if rendered:
            return True

    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    plot_size = _CANVAS_SIZE - 2 * _PLOT_MARGIN_PX

    fit_points = (
        [(hit.x, hit.y) for hit in hits] if fit_to_hits and hits else list(all_points)
    )
    xs = [point[0] for point in fit_points]
    ys = [point[1] for point in fit_points]
    if not xs or not ys:
        xs = [hit.x for hit in hits]
        ys = [hit.y for hit in hits]
    if not xs or not ys:
        xs, ys = [0.0], [0.0]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1.0)
    span_y = max(max_y - min_y, 1.0)
    # A flat factory (all points on one axis) would otherwise collapse the
    # margin/scale math to zero on that axis; a 1.0 cm floor keeps both
    # spans positive without visibly distorting real, non-degenerate data.
    margin_x = span_x * _BOUNDING_BOX_MARGIN_FRACTION
    margin_y = span_y * _BOUNDING_BOX_MARGIN_FRACTION
    min_x -= margin_x
    max_x += margin_x
    min_y -= margin_y
    max_y += margin_y
    span_x = max_x - min_x
    span_y = max_y - min_y

    # Fixed aspect ratio: one shared cm-per-pixel scale for both axes (driven
    # by whichever span is larger) so the schematic is never stretched.
    scale = plot_size / max(span_x, span_y)

    def to_px(x: float, y: float) -> tuple[int, int]:
        px = _PLOT_MARGIN_PX + (x - min_x) * scale
        # World y grows "north"; image y grows downward, so flip it.
        py = _PLOT_MARGIN_PX + (plot_size - (y - min_y) * scale)
        return int(round(px)), int(round(py))

    image = Image.new("RGB", (_CANVAS_SIZE, _CANVAS_SIZE), color=_BACKGROUND_RGB)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, _CANVAS_SIZE - 1, _CANVAS_SIZE - 1), outline=_BORDER_RGB)

    for x, y in all_points:
        px, py = to_px(x, y)
        if _PLOT_MARGIN_PX <= px <= _CANVAS_SIZE - _PLOT_MARGIN_PX and (
            _PLOT_MARGIN_PX <= py <= _CANVAS_SIZE - _PLOT_MARGIN_PX
        ):
            draw.ellipse((px - 1, py - 1, px + 1, py + 1), fill=_FAINT_POINT_RGB)

    for index, hit in enumerate(hits):
        px, py = to_px(hit.x, hit.y)
        if index == highlight_index:
            radius = _HIGHLIGHT_RADIUS_PX
            draw.ellipse(
                (px - radius, py - radius, px + radius, py + radius),
                outline=_HIGHLIGHT_RGB,
                width=3,
            )
            draw.line(
                (px - radius - 6, py, px + radius + 6, py), fill=_HIGHLIGHT_RGB, width=2
            )
            draw.line(
                (px, py - radius - 6, px, py + radius + 6), fill=_HIGHLIGHT_RGB, width=2
            )
        else:
            radius = _HIT_MARKER_RADIUS_PX
            draw.ellipse(
                (px - radius, py - radius, px + radius, py + radius), fill=_HIT_MARKER_RGB
            )
        marker_label = str(index + 1) if compact_labels else hit.label
        draw.text((px + 8, py - 6), marker_label, fill=_LABEL_RGB)

    draw.text((10, 10), "North: +Y (up)", fill=_LABEL_RGB)
    if compact_labels and hits:
        draw.text(
            (10, 26),
            f"Matches: {len(hits)}  Type: {hits[0].label}",
            fill=_LABEL_RGB,
        )
    draw.text(
        (10, _CANVAS_SIZE - 40),
        f"X: {min_x / 100.0:.0f}m to {max_x / 100.0:.0f}m",
        fill=_LABEL_RGB,
    )
    draw.text(
        (10, _CANVAS_SIZE - 24),
        f"Y: {min_y / 100.0:.0f}m to {max_y / 100.0:.0f}m",
        fill=_LABEL_RGB,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path, format="PNG")
    return True

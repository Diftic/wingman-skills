"""Locate factory lines/machines in a save mirror and render a schematic map.

Pure module: no Wingman runtime imports and no catalog dependency. Operates
only on an already-built mirror payload (``satisfactory_mirror.py``), whose
lines carry a ``primaryOutput`` display name and whose machines carry the raw
``recipe``/``resource``/``type`` class-ish strings straight from the save
snapshot. Pillow is imported lazily inside ``render_map`` (mirroring the
lazy-scipy precedent in ``satisfactory_solver.py``) so an install missing
Pillow degrades to text-only coordinates instead of failing at import time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


_MAX_LOCATE_LIMIT = 5

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
    for candidate in candidates:
        if not candidate:
            continue
        lower = candidate.lower()
        if lower == query:
            rank = 0
        elif lower.startswith(query):
            rank = 1
        elif query in lower:
            rank = 2
        else:
            continue
        if best is None or rank < best:
            best = rank
    return best


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


def _machine_hit(machine: dict[str, Any]) -> tuple[list[str], LocationHit] | None:
    location = machine.get("location") or None
    if location is None:
        return None
    x, y, z = location.get("x"), location.get("y"), location.get("z")
    if x is None or y is None or z is None:
        return None
    recipe = str(machine.get("recipe") or "").strip()
    resource = str(machine.get("resource") or "").strip()
    machine_type = str(machine.get("type") or "").strip()
    label = recipe or resource or machine_type or str(machine.get("id") or "machine")
    return [recipe, resource, machine_type], LocationHit(
        label=label,
        kind="machine",
        x=float(x),
        y=float(y),
        z=float(z),
        clock=float(machine.get("clock") or 0.0),
    )


def find_locations(
    mirror: dict[str, Any], query: str, limit: int = 5
) -> tuple[LocationHit, ...]:
    """Search a mirror's inferred lines and machines for ``query``.

    Case-insensitive; lines are matched on their primary output's display
    name, machines on their recipe/resource/type raw fields. Ranked exact
    match first, then prefix, then substring (see ``_rank``), alphabetical
    by label within a rank. An empty or whitespace-only query returns an
    empty tuple. ``limit`` is clamped to 1..5.
    """
    query_lower = query.strip().lower()
    if not query_lower:
        return ()
    capped_limit = max(1, min(limit, _MAX_LOCATE_LIMIT))

    ranked: list[tuple[int, str, LocationHit]] = []

    for line in mirror.get("lines", []) or []:
        result = _line_hit(line)
        if result is None:
            continue
        item_name, hit = result
        rank = _rank([item_name], query_lower)
        if rank is None:
            continue
        ranked.append((rank, hit.label.lower(), hit))

    for machine in mirror.get("machines", []) or []:
        result = _machine_hit(machine)
        if result is None:
            continue
        candidates, hit = result
        rank = _rank(candidates, query_lower)
        if rank is None:
            continue
        ranked.append((rank, hit.label.lower(), hit))

    ranked.sort(key=lambda entry: (entry[0], entry[1]))
    return tuple(hit for _, _, hit in ranked[:capped_limit])


def render_map(
    hits: tuple[LocationHit, ...],
    all_points: tuple[tuple[float, float], ...],
    out_path: Path,
    highlight_index: int = 0,
) -> bool:
    """Render a 1024x1024 schematic PNG pinning ``hits`` on a coordinate grid.

    ``all_points`` (world-cm x/y for every machine in the mirror, regardless
    of match) sets the bounding box so the grid reflects the whole factory,
    not just the hits. Faint dots mark every point in ``all_points``, small
    labeled markers mark each hit, and the hit at ``highlight_index`` also
    gets a ring plus crosshair. Axis labels are in meters; a north-up note
    is included; all text is ASCII-only.

    Deterministic for identical inputs: nothing time-seeded or random is
    drawn, and Pillow's PNG encoder is deterministic for identical pixel
    data, so two renders of the same inputs are byte-identical.

    Returns:
        ``True`` if the PNG was written, ``False`` (no file written) when
        Pillow is unavailable in this environment.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    plot_size = _CANVAS_SIZE - 2 * _PLOT_MARGIN_PX

    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]
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
        draw.text((px + 8, py - 6), hit.label, fill=_LABEL_RGB)

    draw.text((10, 10), "North: +Y (up)", fill=_LABEL_RGB)
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

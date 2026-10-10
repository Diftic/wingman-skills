"""Memoized Satisfactory Docs catalog loading and bounded dataset lookup.

Wingman skills run on a single event loop; tool calls are never dispatched
concurrently for the same skill instance. The module-level memo below
therefore uses no locking: there is no runtime path where two callers race
to parse the same Docs path at once.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from satisfactory_docs import (
    DocsCatalog,
    ItemAmount,
    ItemDescriptor,
    Recipe,
    load_docs_catalog,
    normalize_class_name,
)


_MEMO_CAP = 4
_MAX_LOOKUP_LIMIT = 5

# Keyed by resolved Docs path string; insertion order doubles as FIFO
# eviction order since existing keys are overwritten in place, never moved.
_memo: dict[str, tuple[DocsCatalog, "DatasetInfo"]] = {}


@dataclass(frozen=True)
class DatasetInfo:
    """Provenance and signature metadata for a memoized Docs catalog load.

    ``parse_ms`` is ``None`` unless this specific call to
    ``get_docs_catalog`` performed a real parse (first load, or a reparse
    after the file content changed). It stays ``None`` on a plain memo hit
    or a touch-only signature refresh, so callers can emit a diagnostic
    only when real parsing work actually happened.
    """

    docs_path: str
    size_bytes: int
    mtime_ns: int
    sha256: str
    parse_ms: float | None
    loaded_at: str
    item_count: int
    recipe_count: int
    building_count: int
    schematic_count: int


def clear_dataset_memo() -> None:
    """Clear the in-process dataset memo. Test-only reset hook."""
    _memo.clear()


def _sha256_of(path: Path) -> str:
    """Hash a file's full contents; the metadata-mismatch tiebreaker.

    ``mtime_ns`` alone is not reliable on every filesystem (Windows
    FAT/exFAT mtime granularity can mask a real edit, and a save-tool
    touch can bump mtime without changing content), so a signature
    mismatch always falls back to content hashing before deciding to
    reparse.
    """
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_docs_catalog(docs_path: Path) -> tuple[DocsCatalog, DatasetInfo]:
    """Load a Docs catalog, memoized by file signature.

    Args:
        docs_path: Path to the Satisfactory Docs JSON export.

    Returns:
        A tuple of the resolved ``DocsCatalog`` and its ``DatasetInfo``.
        On a memo hit or a touch-only signature refresh,
        ``DatasetInfo.parse_ms`` is ``None``; it is set only on a call
        that performed a real parse.

    Raises:
        OSError: If the file cannot be stat'd, hashed, or read.
        ValueError: If the loader rejects the file content; see
            ``satisfactory_docs.load_docs_catalog``.

    A failed load never updates the memo, so the next valid call for the
    same path parses cleanly instead of reusing a partial or stale entry.
    """
    resolved = str(docs_path.resolve())
    stat = docs_path.stat()
    size_bytes = stat.st_size
    mtime_ns = stat.st_mtime_ns

    cached = _memo.get(resolved)
    if cached is not None:
        catalog, info = cached
        if info.size_bytes == size_bytes and info.mtime_ns == mtime_ns:
            return catalog, replace(info, parse_ms=None)

    sha256 = _sha256_of(docs_path)
    if cached is not None:
        catalog, info = cached
        if sha256 == info.sha256:
            # File was touched (mtime changed) but content is identical:
            # reuse the parsed catalog and only refresh the signature.
            refreshed = replace(info, size_bytes=size_bytes, mtime_ns=mtime_ns)
            _memo[resolved] = (catalog, refreshed)
            return catalog, replace(refreshed, parse_ms=None)

    start = time.perf_counter()
    catalog = load_docs_catalog(docs_path)
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    info = DatasetInfo(
        docs_path=resolved,
        size_bytes=size_bytes,
        mtime_ns=mtime_ns,
        sha256=sha256,
        parse_ms=elapsed_ms,
        loaded_at=datetime.now().isoformat(),
        item_count=catalog.item_count,
        recipe_count=catalog.recipe_count,
        building_count=catalog.building_count,
        schematic_count=catalog.schematic_count,
    )
    if cached is None and len(_memo) >= _MEMO_CAP:
        oldest_key = next(iter(_memo))
        del _memo[oldest_key]
    _memo[resolved] = (catalog, info)
    return catalog, info


def _match_rank(display_name: str, class_key: str, query: str) -> int | None:
    """Rank a catalog entry against a lowercased query.

    Returns 0 for an exact match, 1 for a prefix match, 2 for a substring
    match (against either the display name or the normalized class key),
    or ``None`` when neither field matches at all.
    """
    display_lower = display_name.lower()
    if display_lower == query or class_key == query:
        return 0
    if display_lower.startswith(query) or class_key.startswith(query):
        return 1
    if query in display_lower or query in class_key:
        return 2
    return None


def _rates_per_min(
    catalog: DocsCatalog, amounts: tuple[ItemAmount, ...], duration_seconds: float
) -> dict[str, float]:
    """Convert recipe ingredient/product amounts to per-minute rates.

    Rates are at 100 percent clock (no building speed or clock factor
    applied); fluids are already in m3 via ``catalog.rate_amount``.
    """
    multiplier = 60.0 / duration_seconds
    return {
        catalog.item_display_name(amount.class_name): round(
            catalog.rate_amount(amount) * multiplier, 3
        )
        for amount in amounts
    }


def lookup_items(
    catalog: DocsCatalog, query: str, limit: int = 5
) -> tuple[dict[str, Any], ...]:
    """Look up items by display name or class key, ranked and capped.

    Args:
        catalog: The parsed Docs catalog to search.
        query: Free-text search term matched case-insensitively against
            each item's display name and normalized class key.
        limit: Maximum number of results, clamped to 1..5.

    Returns:
        A tuple of ``{"item", "class", "form"}`` dicts, ranked exact match
        first, then prefix, then substring, alphabetical within a rank.
        An empty or whitespace-only query returns an empty tuple.
    """
    query_lower = query.strip().lower()
    if not query_lower:
        return ()
    capped_limit = max(1, min(limit, _MAX_LOOKUP_LIMIT))

    ranked: list[tuple[int, str, ItemDescriptor]] = []
    for item in catalog.all_items():
        class_key = normalize_class_name(item.class_name)
        rank = _match_rank(item.display_name, class_key, query_lower)
        if rank is None:
            continue
        ranked.append((rank, item.display_name.lower(), item))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))

    return tuple(
        {"item": item.display_name, "class": item.class_name, "form": item.form}
        for _, _, item in ranked[:capped_limit]
    )


def lookup_recipes(
    catalog: DocsCatalog, query: str, limit: int = 5
) -> tuple[dict[str, Any], ...]:
    """Look up recipes by display name or class key, ranked and capped.

    Args:
        catalog: The parsed Docs catalog to search.
        query: Free-text search term matched case-insensitively against
            each recipe's display name and normalized class key.
        limit: Maximum number of results, clamped to 1..5.

    Returns:
        A tuple of recipe result dicts (``recipe``, ``class``,
        ``duration_seconds``, ``inputs_per_min``, ``outputs_per_min``,
        ``produced_in``, ``alternate``), ranked exact match first, then
        prefix, then substring, alphabetical within a rank. An empty or
        whitespace-only query returns an empty tuple.
    """
    query_lower = query.strip().lower()
    if not query_lower:
        return ()
    capped_limit = max(1, min(limit, _MAX_LOOKUP_LIMIT))

    ranked: list[tuple[int, str, Recipe]] = []
    for recipe in catalog.all_recipes():
        class_key = normalize_class_name(recipe.class_name)
        rank = _match_rank(recipe.display_name, class_key, query_lower)
        if rank is None:
            continue
        ranked.append((rank, recipe.display_name.lower(), recipe))
    ranked.sort(key=lambda entry: (entry[0], entry[1]))

    results = []
    for _, _, recipe in ranked[:capped_limit]:
        results.append(
            {
                "recipe": recipe.display_name,
                "class": recipe.class_name,
                "duration_seconds": recipe.duration_seconds,
                "inputs_per_min": _rates_per_min(
                    catalog, recipe.ingredients, recipe.duration_seconds
                ),
                "outputs_per_min": _rates_per_min(
                    catalog, recipe.products, recipe.duration_seconds
                ),
                "produced_in": recipe.produced_in,
                "alternate": catalog.is_alternate_recipe(recipe.class_name),
            }
        )
    return tuple(results)

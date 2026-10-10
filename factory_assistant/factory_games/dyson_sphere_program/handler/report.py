"""Dyson Sphere Program Handler logic: turn save statistics into short answers.

All rates come from the game's own production statistics in the save (the same
numbers as the in-game Statistics panel), so they are measured, not estimated.
"""

from __future__ import annotations

from dataclasses import dataclass

from factory_games.dyson_sphere_program.reader.catalog import Catalog, Recipe
from factory_games.dyson_sphere_program.reader.save_file import (
    ALL_TIME,
    PERIOD_MINUTES,
    TICKS_PER_SECOND,
    DspSaveSummary,
)

DEFAULT_WINDOW_MINUTES = 10
_DEFICIT_RATIO = 0.95  # consumption above production by more than 5 %
_MIN_RATE = 0.5  # per minute; ignore noise below this


@dataclass(frozen=True)
class ItemRate:
    item_id: int
    name: str
    produced: float  # per minute
    consumed: float  # per minute

    @property
    def net(self) -> float:
        return self.produced - self.consumed


def window_level(minutes: int) -> int:
    """Statistic period index for a window (1, 10, 60, 600 or 6000 minutes)."""
    for level, period in PERIOD_MINUTES.items():
        if period == minutes:
            return level
    return 2  # 10 minutes


def _effective_minutes(summary: DspSaveSummary, level: int) -> float:
    played = summary.game_tick / TICKS_PER_SECOND / 60.0
    window = float(PERIOD_MINUTES[level])
    return max(min(window, played), 1.0 / 60.0)


def cluster_rates(
    summary: DspSaveSummary,
    catalog: Catalog,
    window_minutes: int = DEFAULT_WINDOW_MINUTES,
    factory_index: int | None = None,
) -> list[ItemRate]:
    """Per-minute production and consumption, summed over all planets (or one)."""
    level = window_level(window_minutes)
    minutes = _effective_minutes(summary, level)
    produced: dict[int, int] = {}
    consumed: dict[int, int] = {}
    for factory in summary.factories:
        if factory_index is not None and factory.index != factory_index:
            continue
        for item_id, totals in factory.items.items():
            produced[item_id] = produced.get(item_id, 0) + totals.produced[level]
            consumed[item_id] = consumed.get(item_id, 0) + totals.consumed[level]
    return [
        ItemRate(item_id, catalog.item_name(item_id), produced[item_id] / minutes, consumed[item_id] / minutes)
        for item_id in produced
        if produced[item_id] or consumed[item_id]
    ]


def power_mw(summary: DspSaveSummary, window_minutes: int = DEFAULT_WINDOW_MINUTES) -> dict[str, float]:
    """Average power per pool in MW (research hash pool: hashes per second)."""
    level = window_level(window_minutes)
    seconds = _effective_minutes(summary, level) * 60.0
    out: dict[str, float] = {}
    for factory in summary.factories:
        for pool, totals in factory.power.items():
            out[pool] = out.get(pool, 0.0) + totals[level]
    result = {}
    for pool, total in out.items():
        per_second = total / seconds
        # Energy pools hold per-tick energy (W / 60); hash pool holds hashes.
        result[pool] = per_second if pool == "research_hash" else per_second * TICKS_PER_SECOND / 1e6 / 60.0
    return result


def deficits(rates: list[ItemRate], limit: int) -> list[ItemRate]:
    short = [
        r for r in rates
        if r.consumed >= _MIN_RATE and r.produced < r.consumed * _DEFICIT_RATIO
    ]
    return sorted(short, key=lambda r: r.net)[:limit]


def surpluses(rates: list[ItemRate], limit: int) -> list[ItemRate]:
    extra = [r for r in rates if r.net >= _MIN_RATE and r.consumed > 0]
    return sorted(extra, key=lambda r: -r.net)[:limit]


def _rate(value: float) -> str:
    if value >= 100:
        return f"{value:,.0f}"
    if value >= 10:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _mw(value: float) -> str:
    return f"{value / 1000:.2f} GW" if value >= 1000 else f"{value:.1f} MW"


def header_lines(summary: DspSaveSummary) -> list[str]:
    hours, rest = divmod(int(summary.play_time.total_seconds()), 3600)
    stem = summary.path.stem
    if summary.game_name and stem.startswith("_"):
        title = f"{summary.game_name} (from {_auto_label(stem)})"
    else:
        title = stem
    lines = [
        f"Active save: {title} (galaxy seed {summary.galaxy_seed}, {summary.star_count} stars)",
        f"Game version {summary.version_text}; play time {hours} h {rest // 60} min",
    ]
    if summary.saved_at:
        lines.append(f"Saved {summary.saved_at:%Y-%m-%d %H:%M}")
    return lines


def _auto_label(stem: str) -> str:
    if stem.startswith("_autosave"):
        return "autosave"
    if stem.startswith("_lastexit"):
        return "last-exit save"
    return stem


def all_time_lines(summary: DspSaveSummary, catalog: Catalog, limit: int) -> list[str]:
    """Totals since the game started (hand crafting and mecha mining count only here)."""
    totals: dict[int, int] = {}
    for factory in summary.factories:
        for item_id, item in factory.items.items():
            totals[item_id] = totals.get(item_id, 0) + item.produced[ALL_TIME]
    top = sorted((v, k) for k, v in totals.items() if v > 0)[::-1][:limit]
    if not top:
        return []
    return ["Made or gathered since the game started: " + "; ".join(
        f"{catalog.item_name(item_id)} {count:,}" for count, item_id in top
    )]


def production_lines(
    summary: DspSaveSummary,
    catalog: Catalog,
    window_minutes: int,
    max_items: int,
    focus: str = "",
) -> list[str]:
    if not summary.stats_found:
        return [
            "No production numbers in this save yet. Build something, let the game "
            "autosave, then ask again.",
        ]
    rates = cluster_rates(summary, catalog, window_minutes)
    if not rates:
        lines = [
            f"No machines produced anything in the last {window_minutes} min "
            "(hand crafting and mecha mining are not in the per-minute numbers)."
        ]
        return lines + all_time_lines(summary, catalog, max(3, max_items // 2))
    lines = [f"Production, average of the last {window_minutes} min, per minute, all planets:"]
    focus_lc = focus.strip().lower()
    if focus_lc:
        hits = [r for r in rates if focus_lc in r.name.lower()]
        if not hits:
            lines.append(f"  - Nothing named '{focus}' was made or used.")
        for r in sorted(hits, key=lambda r: -max(r.produced, r.consumed))[:max_items]:
            lines.append(f"  - {r.name}: make {_rate(r.produced)}, use {_rate(r.consumed)}, net {r.net:+.1f}")
        return lines

    short = deficits(rates, max(3, max_items // 2))
    if short:
        lines.append("Using more than you make (drawing from storage):")
        lines.extend(
            f"  - {r.name}: make {_rate(r.produced)}, use {_rate(r.consumed)} ({r.net:+.1f}/min)"
            for r in short
        )
    else:
        lines.append("No item is used faster than it is made.")
    top = sorted(rates, key=lambda r: -r.produced)[: max(3, max_items // 2)]
    if top:
        lines.append("Biggest outputs: " + "; ".join(f"{r.name} {_rate(r.produced)}" for r in top))
    return lines


_NEAR_LIMIT = 0.95


def power_lines(summary: DspSaveSummary, window_minutes: int) -> list[str]:
    """Power capacity and use. Verified against the Power tab (0.10.35).

    Pool "generated" is the generation CAPACITY (the panel's Generation /
    Generation Capacity), not the energy actually used; pool "consumed" is the
    energy used (its all-time total equals "Total Energy Consumption").
    The last minute is used for the shortage check, the window for the average.
    """
    if not summary.stats_found:
        return []
    now = power_mw(summary, 1)
    avg = power_mw(summary, window_minutes)
    capacity = now.get("generated", 0.0) + now.get("discharged", 0.0)
    use = now.get("consumed", 0.0)
    share = f" ({use / capacity:.0%} of capacity)" if capacity > 0 else ""
    lines = [
        f"Power, last minute: capacity {_mw(capacity)}, use {_mw(use)}{share}; "
        f"{window_minutes}-min average use {_mw(avg.get('consumed', 0.0))}"
    ]
    if capacity > 0 and use >= capacity * _NEAR_LIMIT:
        lines.append("  Warning: power use is at the limit of the generation capacity. Build more power.")
    elif capacity == 0 and use > 0:
        lines.append("  Warning: machines use power but there is no generation capacity.")
    if now.get("discharged", 0.0) > now.get("charged", 0.0) and now.get("discharged", 0.0) > 0.1:
        lines.append("  Accumulators are draining.")
    hashes = avg.get("research_hash", 0.0)
    if hashes > 0:
        lines.append(f"Research speed: {hashes:,.0f} hashes per second ({window_minutes}-min average)")
    return lines


def planet_lines(summary: DspSaveSummary, window_minutes: int, limit: int) -> list[str]:
    """Per planet: use and capacity in the last minute (capacity includes accumulators/exchangers)."""
    if not summary.stats_found or len(summary.factories) < 2:
        return []
    level = window_level(1)
    seconds = _effective_minutes(summary, level) * 60.0
    rows = []
    for factory in summary.factories:
        capacity = factory.power.get("generated", (0,) * 7)[level] + factory.power.get("discharged", (0,) * 7)[level]
        cap = capacity / seconds / 1e6
        use = factory.power.get("consumed", (0,) * 7)[level] / seconds / 1e6
        rows.append((use, cap, factory.index))
    rows.sort(reverse=True)
    lines = [f"Planets with buildings: {len(summary.factories)} (names are not in the short read)"]
    for use, cap, index in rows[:limit]:
        flag = "  <- at power limit" if use > 0.05 and use >= cap * _NEAR_LIMIT else ""
        lines.append(f"  - Planet {index + 1}: use {_mw(use)} of {_mw(cap)} capacity{flag}")
    return lines


def _recipe_line(recipe: Recipe, catalog: Catalog) -> str:
    def part(entries) -> str:
        return " + ".join(f"{count} {catalog.item_name(item)}" for item, count in entries)

    return f"  - Recipe {recipe.name} ({recipe.type}, {recipe.seconds:g} s): {part(recipe.inputs)} -> {part(recipe.outputs)}"


def lookup_lines(catalog: Catalog, query: str) -> list[str]:
    items = catalog.find_items(query)
    recipes = catalog.find_recipes(query)
    for item in items[:2]:
        for recipe in catalog.recipes_making(item["id"]):
            if recipe not in recipes:
                recipes.append(recipe)
    if not items and not recipes:
        return [f"I couldn't find '{query}' in the Dyson Sphere Program data."]
    lines = [f"Lookup '{query}':"]
    for item in items:
        source = f", mined from {item['mining_from']}" if item.get("mining_from") else ""
        lines.append(f"  - Item {item['name']} ({item['type']}, stack {item['stack']}{source})")
    lines.extend(_recipe_line(recipe, catalog) for recipe in recipes[:5])
    return lines


def audit_report(
    summary: DspSaveSummary, catalog: Catalog, window_minutes: int, max_items: int
) -> str:
    lines = header_lines(summary)
    lines.extend(power_lines(summary, window_minutes))
    lines.extend(production_lines(summary, catalog, window_minutes, max_items * 2))
    rates = cluster_rates(summary, catalog, window_minutes) if summary.stats_found else []
    extra = surpluses(rates, max(3, max_items // 2))
    if extra:
        lines.append("Most extra (made but not used): " + "; ".join(f"{r.name} +{_rate(r.net)}" for r in extra))
    lines.extend(planet_lines(summary, window_minutes, 5))
    lines.extend(summary.notes)
    return "\n".join(lines)

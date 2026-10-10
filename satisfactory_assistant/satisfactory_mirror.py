"""Build a save-derived Satisfactory factory mirror.

The mirror is deterministic expected-state data derived from a save snapshot and
the game's Docs catalog. Autosave history is used only as a lightweight health
estimate, never as the source of production truth.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from satisfactory_docs import DocsCatalog, ItemAmount


@dataclass(frozen=True)
class TrendConfig:
    window_saves: int = 5
    zero_streak_saves: int = 3
    deviation_threshold: float = 0.25
    minimum_expected_rate: float = 1.0


def _num(value: object, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        result = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return 0.0 if result == -0.0 else result


def _round(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(value, digits)


def _machine_clock(machine: dict[str, Any]) -> float:
    clock = _num((machine.get("clock") or {}).get("currentPotential"), 1.0)
    if clock is None or clock <= 0:
        return 1.0
    return clock


def _production_boost(machine: dict[str, Any]) -> float:
    boost = _num((machine.get("clock") or {}).get("productionBoost"), 1.0)
    if boost is None or boost <= 0:
        return 1.0
    return boost


def _location(machine: dict[str, Any]) -> dict[str, float] | None:
    translation = ((machine.get("transform") or {}).get("translation") or {})
    x = _num(translation.get("x"))
    y = _num(translation.get("y"))
    z = _num(translation.get("z"))
    if x is None or y is None or z is None:
        return None
    return {"x": x, "y": y, "z": z}


def _rate_entry(catalog: DocsCatalog, amount: ItemAmount, rate: float) -> dict[str, Any]:
    return {
        "itemClass": amount.class_name,
        "item": catalog.item_display_name(amount.class_name),
        "ratePerMin": _round(rate),
    }


def _recipe_rates(
    catalog: DocsCatalog,
    recipe_name: str,
    machine_type: str,
    clock: float,
    production_boost: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], str]:
    recipe = catalog.recipe(recipe_name)
    building = catalog.building(machine_type)
    notes: list[str] = []
    if recipe is None:
        return [], [], [f"Unknown recipe {recipe_name}."], "unknown"

    speed = building.manufacturing_speed if building is not None else 1.0
    if building is None:
        notes.append(f"Unknown building {machine_type}; assumed manufacturing speed 1.0.")
    multiplier = (60.0 / recipe.duration_seconds) * speed * clock

    inputs = [
        _rate_entry(catalog, amount, catalog.rate_amount(amount) * multiplier)
        for amount in recipe.ingredients
    ]
    outputs = [
        _rate_entry(catalog, amount, catalog.rate_amount(amount) * multiplier * production_boost)
        for amount in recipe.products
    ]
    if production_boost != 1.0:
        notes.append("Production boost applied to outputs only.")
    return inputs, outputs, notes, "high" if not notes else "medium"


def _extractor_rates(
    catalog: DocsCatalog,
    resource_name: str,
    machine_type: str,
    clock: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], str]:
    building = catalog.building(machine_type)
    item = catalog.item(resource_name)
    notes: list[str] = []
    if building is None or building.extract_cycle_time <= 0 or building.items_per_cycle <= 0:
        return [], [], [f"Unknown extractor rate for {machine_type}."], "unknown"
    if item is None and len(building.allowed_resources) == 1:
        item = catalog.item(building.allowed_resources[0])
        if item is not None:
            notes.append("Resource inferred from extractor type allowed resources.")
    if item is None:
        return [], [], [f"Unknown extractable resource {resource_name}."], "unknown"

    amount = ItemAmount(class_name=item.class_name, amount=building.items_per_cycle)
    rate = catalog.rate_amount(amount) * (60.0 / building.extract_cycle_time) * clock
    if "Miner" in machine_type or "OilPump" in machine_type or "Fracking" in machine_type:
        notes.append("Resource purity/pressure not decoded yet; rate assumes normal/base extraction.")
    return [], [_rate_entry(catalog, amount, rate)], notes, "medium" if notes else "high"


def _productivity_ratio(machine: dict[str, Any]) -> float | None:
    state = machine.get("state") or {}
    for prefix in ("current", "last"):
        duration = _num(state.get(f"{prefix}ProductivityMeasurementDuration"))
        produce = _num(state.get(f"{prefix}ProductivityMeasurementProduceDuration"))
        if duration and duration > 0 and produce is not None:
            return max(0.0, min(1.0, produce / duration))
    producing = state.get("isProducing")
    if producing is True:
        return 1.0
    if producing is False:
        return 0.0
    return None


def _sum_rates(target: dict[str, float], rates: list[dict[str, Any]], multiplier: float = 1.0) -> None:
    for rate in rates:
        item = str(rate.get("item") or rate.get("itemClass") or "?")
        value = _num(rate.get("ratePerMin"), 0.0) or 0.0
        target[item] += value * multiplier


def _sorted_rates(
    rates: dict[str, float], *, include_zero: bool = False
) -> list[dict[str, Any]]:
    return [
        {"item": item, "ratePerMin": _round(rate)}
        for item, rate in sorted(rates.items(), key=lambda pair: (-pair[1], pair[0]))
        if rate > 0 or include_zero
    ]


def machine_expected_state(
    machine: dict[str, Any],
    catalog: DocsCatalog,
) -> dict[str, Any]:
    """Build one machine's expected input/output state."""
    machine_type = str(machine.get("type") or "")
    clock = _machine_clock(machine)
    boost = _production_boost(machine)
    recipe = machine.get("recipe") or {}
    resource = machine.get("extractableResource") or {}
    notes: list[str] = []

    if recipe.get("name"):
        inputs, outputs, rate_notes, confidence = _recipe_rates(
            catalog,
            str(recipe["name"]),
            machine_type,
            clock,
            boost,
        )
        notes.extend(rate_notes)
    elif resource.get("name"):
        inputs, outputs, rate_notes, confidence = _extractor_rates(
            catalog,
            str(resource["name"]),
            machine_type,
            clock,
        )
        notes.extend(rate_notes)
    else:
        inputs, outputs, confidence = [], [], "unknown"
        notes.append("No current recipe or extractable resource in save snapshot.")

    productivity = _productivity_ratio(machine)
    estimated_outputs = None
    if productivity is not None:
        estimated_outputs = [
            {
                **rate,
                "ratePerMin": _round((_num(rate.get("ratePerMin"), 0.0) or 0.0) * productivity),
            }
            for rate in outputs
        ]

    return {
        "id": machine.get("id"),
        "type": machine_type,
        "kind": machine.get("kind"),
        "location": _location(machine),
        "recipe": recipe.get("name"),
        "resource": resource.get("name"),
        "clock": _round(clock),
        "productionBoost": _round(boost),
        "expected": {"inputs": inputs, "outputs": outputs},
        "observedEstimate": {
            "productivityRatio": _round(productivity),
            "outputs": estimated_outputs,
        },
        "confidence": confidence,
        "notes": notes,
    }


def _distance_xy(a: dict[str, float] | None, b: dict[str, float] | None) -> float | None:
    if a is None or b is None:
        return None
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _item_set(machine: dict[str, Any], direction: str) -> set[str]:
    return {
        str(rate.get("item"))
        for rate in machine.get("expected", {}).get(direction, [])
        if rate.get("item")
    }


def _compatible(a: dict[str, Any], b: dict[str, Any]) -> bool:
    a_out = _item_set(a, "outputs")
    a_in = _item_set(a, "inputs")
    b_out = _item_set(b, "outputs")
    b_in = _item_set(b, "inputs")
    if a_out & b_in or b_out & a_in:
        return True
    if a.get("recipe") and a.get("recipe") == b.get("recipe"):
        return True
    return bool(a_out and a_out == b_out)


def infer_lines(machines: list[dict[str, Any]], proximity_cm: float = 10000.0) -> list[dict[str, Any]]:
    """Infer probable production lines from proximity and item compatibility."""
    candidates = [
        machine
        for machine in machines
        if machine.get("location") is not None
        and (machine.get("expected", {}).get("inputs") or machine.get("expected", {}).get("outputs"))
    ]
    parent = list(range(len(candidates)))
    edge_counts = [0 for _ in candidates]

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        edge_counts[a] += 1
        edge_counts[b] += 1

    for i, left in enumerate(candidates):
        for j in range(i + 1, len(candidates)):
            right = candidates[j]
            distance = _distance_xy(left.get("location"), right.get("location"))
            if distance is None or distance > proximity_cm:
                continue
            if _compatible(left, right):
                union(i, j)

    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    group_edges: dict[int, int] = defaultdict(int)
    for idx, machine in enumerate(candidates):
        root = find(idx)
        groups[root].append(machine)
        group_edges[root] += edge_counts[idx]

    lines = []
    for root, members in groups.items():
        if len(members) < 2:
            continue
        inputs: dict[str, float] = defaultdict(float)
        outputs: dict[str, float] = defaultdict(float)
        xs = [m["location"]["x"] for m in members]
        ys = [m["location"]["y"] for m in members]
        zs = [m["location"]["z"] for m in members]
        for member in members:
            _sum_rates(inputs, member.get("expected", {}).get("inputs", []))
            _sum_rates(outputs, member.get("expected", {}).get("outputs", []))
        primary = _sorted_rates(outputs)[:1]
        lines.append(
            {
                "id": f"line_{len(lines) + 1:04d}",
                "machineCount": len(members),
                "confidence": "probable" if group_edges[root] else "inferred",
                "primaryOutput": primary[0] if primary else None,
                "centroid": {
                    "x": _round(sum(xs) / len(xs), 1),
                    "y": _round(sum(ys) / len(ys), 1),
                    "z": _round(sum(zs) / len(zs), 1),
                },
                "grossInputs": _sorted_rates(inputs),
                "grossOutputs": _sorted_rates(outputs),
                "machineIds": [m.get("id") for m in members if m.get("id")],
            }
        )

    lines.sort(
        key=lambda line: (
            -line["machineCount"],
            -(line.get("primaryOutput") or {}).get("ratePerMin", 0),
            line["id"],
        )
    )
    for idx, line in enumerate(lines, start=1):
        line["id"] = f"line_{idx:04d}"
    return lines


def build_factory_mirror(
    snapshot: dict[str, Any],
    catalog: DocsCatalog,
    *,
    proximity_cm: float = 10000.0,
) -> dict[str, Any]:
    """Build a deterministic factory mirror from snapshot plus Docs data."""
    machines = [
        machine_expected_state(machine, catalog)
        for machine in snapshot.get("machines", [])
        if isinstance(machine, dict)
    ]
    expected_inputs: dict[str, float] = defaultdict(float)
    expected_outputs: dict[str, float] = defaultdict(float)
    estimated_outputs: dict[str, float] = defaultdict(float)
    unknown = 0

    for machine in machines:
        _sum_rates(expected_inputs, machine.get("expected", {}).get("inputs", []))
        _sum_rates(expected_outputs, machine.get("expected", {}).get("outputs", []))
        observed = machine.get("observedEstimate") or {}
        if observed.get("outputs") is not None:
            _sum_rates(estimated_outputs, observed.get("outputs", []))
        if machine.get("confidence") == "unknown":
            unknown += 1

    lines = infer_lines(machines, proximity_cm=proximity_cm)
    return {
        "schemaVersion": 1,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": snapshot.get("source", {}),
        "header": snapshot.get("header", {}),
        "counts": {
            **(snapshot.get("counts") or {}),
            "mirrorMachines": len(machines),
            "unknownRateMachines": unknown,
            "inferredLines": len(lines),
        },
        "expectedTotals": {
            "inputs": _sorted_rates(expected_inputs),
            "outputs": _sorted_rates(expected_outputs),
        },
        "observedEstimateTotals": {
            "outputs": _sorted_rates(estimated_outputs, include_zero=True),
        },
        "machines": machines,
        "lines": lines,
    }


def _mirror_dir(workspace_dir: Path) -> Path:
    return workspace_dir / "mirror"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _observation(mirror: dict[str, Any]) -> dict[str, Any]:
    zero_ids = []
    for machine in mirror.get("machines", []):
        expected_outputs = machine.get("expected", {}).get("outputs", [])
        ratio = (machine.get("observedEstimate") or {}).get("productivityRatio")
        if expected_outputs and ratio == 0:
            zero_ids.append(machine.get("id"))
    return {
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "source": mirror.get("source", {}),
        "expectedOutputs": mirror.get("expectedTotals", {}).get("outputs", []),
        "estimatedOutputs": mirror.get("observedEstimateTotals", {}).get("outputs", []),
        "zeroMachineIds": [item for item in zero_ids if item],
    }


def _rates_to_map(rows: list[dict[str, Any]]) -> dict[str, float]:
    return {str(row.get("item")): _num(row.get("ratePerMin"), 0.0) or 0.0 for row in rows}


def calculate_health(
    observations: list[dict[str, Any]],
    config: TrendConfig,
) -> dict[str, Any]:
    """Calculate rolling estimated health from recent snapshot observations."""
    window = observations[-max(1, config.window_saves) :]
    if not window:
        return {"status": "no_observations", "deviations": [], "zeroStreakMachines": []}

    current_expected = _rates_to_map(window[-1].get("expectedOutputs", []))
    estimated_sums: dict[str, float] = defaultdict(float)
    estimated_counts: dict[str, int] = defaultdict(int)
    for row in window:
        estimated = _rates_to_map(row.get("estimatedOutputs", []))
        for item, expected in current_expected.items():
            if expected < config.minimum_expected_rate:
                continue
            if item in estimated:
                estimated_sums[item] += estimated[item]
                estimated_counts[item] += 1

    deviations = []
    if len(window) >= config.window_saves:
        for item, expected in current_expected.items():
            count = estimated_counts.get(item, 0)
            if count < config.window_saves or expected < config.minimum_expected_rate:
                continue
            avg = estimated_sums[item] / count
            if avg < expected * (1.0 - config.deviation_threshold):
                deviations.append(
                    {
                        "item": item,
                        "expectedPerMin": _round(expected),
                        "estimatedAveragePerMin": _round(avg),
                        "sampleCount": count,
                        "belowExpectedPercent": _round((expected - avg) / expected * 100.0, 1),
                    }
                )

    recent_for_zero = observations[-max(1, config.zero_streak_saves) :]
    zero_sets = [set(row.get("zeroMachineIds", [])) for row in recent_for_zero]
    zero_streak = sorted(set.intersection(*zero_sets)) if len(zero_sets) == config.zero_streak_saves else []

    return {
        "status": "ok",
        "windowSampleCount": len(window),
        "deviations": deviations[:20],
        "zeroStreakMachines": zero_streak[:20],
        "zeroStreakCount": len(zero_streak),
    }


def store_mirror_artifacts(
    workspace_dir: Path,
    snapshot: dict[str, Any],
    mirror: dict[str, Any],
    trend_config: TrendConfig,
) -> dict[str, Any]:
    """Persist latest snapshot/mirror and append one observation row."""
    out_dir = _mirror_dir(workspace_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "latest_snapshot.json", snapshot)
    _write_json(out_dir / "latest_mirror.json", mirror)

    observations_path = out_dir / "observations.jsonl"
    observation = _observation(mirror)
    with observations_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(observation, ensure_ascii=False) + "\n")

    history = _read_jsonl(observations_path)
    # Keep the file bounded while preserving enough data for larger future windows.
    # Rewrite only when the append pushed the file past the cap; while it stays
    # within the cap the append above is the only write.
    cap = max(50, trend_config.window_saves * 4)
    if len(history) > cap:
        history = list(deque(history, maxlen=cap))
        observations_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in history),
            encoding="utf-8",
        )
    health = calculate_health(history, trend_config)
    _write_json(out_dir / "latest_health.json", health)
    return {
        "mirrorDir": str(out_dir),
        "snapshotPath": str(out_dir / "latest_snapshot.json"),
        "mirrorPath": str(out_dir / "latest_mirror.json"),
        "healthPath": str(out_dir / "latest_health.json"),
        "health": health,
    }


def _format_rates(label: str, rows: list[dict[str, Any]], limit: int) -> list[str]:
    if not rows:
        return [f"{label}: none resolved"]
    shown = rows[:limit]
    values = ", ".join(f"{row['item']} {_round(row['ratePerMin'], 1)}/min" for row in shown)
    extra = f" (+{len(rows) - len(shown)} more)" if len(rows) > len(shown) else ""
    return [f"{label}: {values}{extra}"]


def format_factory_audit(
    mirror: dict[str, Any],
    artifact_info: dict[str, Any],
    *,
    max_lines: int = 8,
) -> str:
    """Render a compact, user-facing factory audit summary."""
    source = mirror.get("source", {})
    counts = mirror.get("counts", {})
    health = artifact_info.get("health", {})
    kind_counts = ", ".join(
        f"{row.get('count', 0)} {row.get('name', 'unknown')}"
        for row in counts.get("machineCandidatesByKind", [])
    )
    lines = [
        f"Factory mirror for {source.get('saveName', 'active save')}:",
        (
            f"  Machines: {counts.get('mirrorMachines', 0)} "
            f"({counts.get('objectsWithCurrentRecipe', 0)} recipe"
            f"{'; ' + kind_counts if kind_counts else ''})"
        ),
        f"  Inferred production lines: {counts.get('inferredLines', 0)}",
        f"  Unknown-rate machines: {counts.get('unknownRateMachines', 0)}",
    ]
    lines.extend(
        _format_rates(
            "  Expected gross outputs",
            mirror.get("expectedTotals", {}).get("outputs", []),
            max_lines,
        )
    )
    lines.extend(
        _format_rates(
            "  Expected gross inputs",
            mirror.get("expectedTotals", {}).get("inputs", []),
            max_lines,
        )
    )

    top_lines = mirror.get("lines", [])[: min(5, max_lines)]
    if top_lines:
        lines.append("  Largest inferred lines:")
        for line in top_lines:
            primary = line.get("primaryOutput") or {}
            output = (
                f"{primary.get('item')} {_round(primary.get('ratePerMin'), 1)}/min"
                if primary
                else "unknown output"
            )
            lines.append(
                f"    - {line['id']}: {line['machineCount']} machines, {output}, {line['confidence']}"
            )

    deviations = health.get("deviations") or []
    zero_streak = health.get("zeroStreakMachines") or []
    if deviations or zero_streak:
        lines.append("  Estimated health deviations:")
        for deviation in deviations[:5]:
            lines.append(
                "    - "
                f"{deviation['item']}: estimated avg {deviation['estimatedAveragePerMin']}/min "
                f"vs expected {deviation['expectedPerMin']}/min"
            )
        if zero_streak:
            lines.append(
                f"    - {len(zero_streak)} machine(s) have zero-output streaks "
                f"for the configured threshold."
            )
    else:
        lines.append(
            f"  Estimated health: no rolling deviations yet "
            f"({health.get('windowSampleCount', 0)} sample(s))."
        )

    lines.append(f"  Artifacts: {artifact_info.get('mirrorDir')}")
    return "\n".join(lines)




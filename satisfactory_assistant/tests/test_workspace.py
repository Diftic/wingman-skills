"""Tests for the per-save planning workspace and its isolation guarantees."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

import json
import os
import re

from satisfactory_workspace import (
    CLEARABLE_FIELDS,
    SaveWorkspace,
    _is_within,
    adopt_legacy_workspace,
    clip,
    format_context,
    kind_for_id,
    parse_clear_fields,
    safe_save_key,
    slugify,
    stable_workspace_key,
)


NOW = datetime(2026, 6, 17, 15, 30, 12)


def _ws(tmp_path: Path, key: str = "megatime-abcd1234") -> SaveWorkspace:
    ws = SaveWorkspace(tmp_path, key)
    ws.ensure()
    return ws


def test_save_key_is_stable_and_disambiguated() -> None:
    a = safe_save_key("megatime", "/path/one")
    b = safe_save_key("megatime", "/path/two")
    assert a != b
    assert safe_save_key("megatime", "/path/one") == a
    assert a.startswith("megatime-")


def test_slugify_handles_messy_names() -> None:
    assert slugify("Shit is sinking") == "shit-is-sinking"
    assert slugify("!!!") == "save"


def test_separate_saves_get_separate_workspaces(tmp_path: Path) -> None:
    a = _ws(tmp_path, "save-a-0001")
    b = _ws(tmp_path, "save-b-0002")
    assert a.dir != b.dir
    a.add_item("todos", "A only", "", NOW)
    assert a.summary(10)["counts"]["todos"] == 1
    assert b.summary(10)["counts"]["todos"] == 0


def test_add_and_complete_todo(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    item_id = ws.add_item("todos", "Upgrade steel line to 240/min", "", NOW)
    assert item_id.startswith("todo_")
    summary = ws.summary(10)
    assert any(t["id"] == item_id for t in summary["open_todos"])

    assert ws.set_status(item_id, "done", NOW) is True
    summary = ws.summary(10)
    assert all(t["id"] != item_id for t in summary["open_todos"])


def test_set_status_unknown_id_returns_false(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    assert ws.set_status("todo_does_not_exist", "done", NOW) is False


def test_summary_caps_items(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    for i in range(5):
        ws.add_item("todos", f"todo {i}", "", NOW)
    summary = ws.summary(2)
    assert len(summary["open_todos"]) == 2
    assert summary["counts"]["todos"] == 5


def test_workspace_refuses_traversal_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SaveWorkspace(tmp_path, "../../escape")


def test_malicious_title_stays_in_workspace(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    # A title with traversal characters must not affect where data is written;
    # the title is a value the store carries, never a path component.
    ws.add_item("notes", "../../../etc/passwd", "details", NOW)

    assert not (tmp_path / "etc").exists()
    written = [p for p in ws.dir.rglob("*") if p.is_file()]
    assert written, "record should be written inside the workspace"
    for path in written:
        assert ws.dir.resolve() in path.resolve().parents

    titles = {n["title"] for n in ws.summary(10)["notes"]}
    assert any("etc/passwd" in title for title in titles)


def test_add_flow_stores_inputs_and_outputs_as_lists(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item(
        "flows",
        "Steel beam expansion",
        "build 360/min",
        NOW,
        extra={"inputs": ["Iron Ore 240/min", "Coal 240/min"], "outputs": ["Steel Ingot 360/min"]},
        status="planned",
    )
    assert flow_id.startswith("flow_")
    flows = ws.summary(10)["flows"]
    flow = next(f for f in flows if f["id"] == flow_id)
    assert flow["inputs"] == ["Iron Ore 240/min", "Coal 240/min"]
    assert flow["outputs"] == ["Steel Ingot 360/min"]
    assert flow["status"] == "planned"


def test_summary_surfaces_blocked_and_missing_input_flows(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    # Explicitly blocked.
    ws.add_item("flows", "Aluminum", "", NOW, extra={"inputs": ["Bauxite 120/min"], "outputs": ["Alclad 60/min"]}, status="blocked")
    # Has an output target but no known inputs -> treated as missing inputs.
    ws.add_item("flows", "Plastic", "", NOW, extra={"inputs": [], "outputs": ["Plastic 120/min"]}, status="planned")
    # Healthy flow should not be flagged.
    ws.add_item("flows", "Iron", "", NOW, extra={"inputs": ["Iron Ore 60/min"], "outputs": ["Iron Ingot 60/min"]}, status="balanced")

    blocked = ws.summary(10)["blocked_flows"]
    titles = {f["title"] for f in blocked}
    assert titles == {"Aluminum", "Plastic"}


def test_update_flow_changes_only_given_fields(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item("flows", "Steel", "orig", NOW, extra={"inputs": ["a"], "outputs": ["b"]}, status="planned")
    assert ws.update_flow(flow_id, NOW, status="building", outputs=["Steel Ingot 360/min"]) is True
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["status"] == "building"
    assert flow["outputs"] == ["Steel Ingot 360/min"]
    assert flow["inputs"] == ["a"]  # unchanged


def test_update_flow_unknown_id_returns_false(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    assert ws.update_flow("flow_nope", NOW, status="done") is False


def test_archived_flow_excluded_from_summary(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item("flows", "Old line", "", NOW, extra={"outputs": ["x"]}, status="planned")
    ws.set_status(flow_id, "archived", NOW)
    assert ws.summary(10)["flows"] == []


def test_flows_isolated_between_saves(tmp_path: Path) -> None:
    a = _ws(tmp_path, "save-a-0001")
    b = _ws(tmp_path, "save-b-0002")
    a.add_item("flows", "A flow", "", NOW, extra={"outputs": ["x"]}, status="planned")
    assert len(a.summary(10)["flows"]) == 1
    assert b.summary(10)["flows"] == []


def test_focus_filters_before_truncation(tmp_path: Path) -> None:
    """A matching older item must survive even behind many newer records."""
    ws = _ws(tmp_path)
    early = datetime(2026, 6, 17, 10, 0, 0)
    later = datetime(2026, 6, 17, 12, 0, 0)
    target = ws.add_item("todos", "Steel plant rebuild", "", early)
    for i in range(20):
        ws.add_item("todos", f"unrelated chore {i}", "", later)

    # Without focus, the older target is pushed out of a small cap.
    unfocused = ws.summary(2)["open_todos"]
    assert all(t["id"] != target for t in unfocused)

    # With focus, it surfaces despite the small cap.
    focused = ws.summary(2, focus="steel")["open_todos"]
    assert any(t["id"] == target for t in focused)


def test_focus_matches_flow_inputs_and_outputs(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    fid = ws.add_item("flows", "Line A", "", NOW, extra={"inputs": ["Iron Ore 240/min"], "outputs": ["Steel Ingot 360/min"]}, status="planned")
    for i in range(10):
        ws.add_item("flows", f"other {i}", "", NOW, extra={"outputs": ["x"]}, status="planned")
    focused = ws.summary(2, focus="iron ore")["flows"]
    assert any(f["id"] == fid for f in focused)


def test_focus_blocked_returns_blocked_flows(tmp_path: Path) -> None:
    """A status query like focus='blocked' must return blocked flows."""
    ws = _ws(tmp_path)
    ws.add_item("flows", "Aluminum line", "", NOW, extra={"inputs": ["Bauxite 120/min"], "outputs": ["Alclad 60/min"]}, status="blocked")
    ws.add_item("flows", "Iron line", "", NOW, extra={"inputs": ["Ore 60/min"], "outputs": ["Ingot 60/min"]}, status="balanced")

    s = ws.summary(10, focus="blocked")
    titles = {f["title"] for f in s["flows"]}
    assert "Aluminum line" in titles
    assert "Iron line" not in titles
    assert any(f["title"] == "Aluminum line" for f in s["blocked_flows"])


def test_focus_balanced_returns_balanced_flow(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    ws.add_item("flows", "Iron line", "", NOW, extra={"inputs": ["Ore 60/min"], "outputs": ["Ingot 60/min"]}, status="balanced")
    ws.add_item("flows", "Steel line", "", NOW, extra={"inputs": ["x"], "outputs": ["y"]}, status="planned")

    titles = {f["title"] for f in ws.summary(10, focus="balanced")["flows"]}
    assert titles == {"Iron line"}


def test_focus_missing_alias_surfaces_inputless_flows(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    ws.add_item("flows", "Plastic", "", NOW, extra={"inputs": [], "outputs": ["Plastic 120/min"]}, status="planned")
    ws.add_item("flows", "Iron", "", NOW, extra={"inputs": ["Ore"], "outputs": ["Ingot"]}, status="balanced")

    titles = {f["title"] for f in ws.summary(10, focus="missing")["flows"]}
    assert titles == {"Plastic"}


def test_summary_caps_field_lengths(tmp_path: Path) -> None:
    """A single oversized title/material must be clipped at the summary boundary."""
    ws = _ws(tmp_path)
    many = [f"Item{i} 60/min" for i in range(20)]
    flow_id = ws.add_item(
        "flows",
        "X" * 200,
        "",
        NOW,
        extra={"inputs": many, "outputs": ["Y" * 200]},
        status="planned",
    )
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert len(flow["title"]) <= 80
    assert all(len(x) <= 48 for x in flow["outputs"])
    assert len(flow["inputs"]) <= 7  # 6 materials + a "(+N more)" marker
    assert flow["inputs"][-1].startswith("(+")

    todo_id = ws.add_item("todos", "Z" * 200, "", NOW)
    todo = next(t for t in ws.summary(10)["open_todos"] if t["id"] == todo_id)
    assert len(todo["title"]) <= 80


def test_clip_uses_ascii_marker_and_limit() -> None:
    assert clip("short", 80) == "short"
    clipped = clip("Z" * 200, 60)
    assert len(clipped) == 60
    assert clipped.endswith("...")
    assert "…" not in clipped  # no Unicode ellipsis


def test_format_context_stays_within_budget_and_dedupes(tmp_path: Path) -> None:
    """Many blocked flows at default caps must not blow the token budget."""
    ws = _ws(tmp_path)
    for i in range(12):
        ws.add_item(
            "flows",
            f"Production line {i} " + "x" * 70,
            "",
            NOW,
            extra={
                "inputs": [f"Input {j} 240/min" for j in range(8)],
                "outputs": [f"Output {j} 360/min" for j in range(8)],
            },
            status="blocked",
        )
    summary = ws.summary(12)
    text = format_context(["Active save: Test"], summary)

    assert len(text) <= 3000
    # Each flow id appears at most once (blocked flows are not duplicated).
    ids = re.findall(r"flow_\d{8}_\d{6}_[0-9a-f]{4}", text)
    assert len(ids) == len(set(ids))


def test_format_context_empty_workspace(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    text = format_context(["Active save: Test"], ws.summary(12))
    assert "No planning records yet" in text


@pytest.mark.skipif(os.name == "nt", reason="case-sensitivity test is POSIX-only")
def test_containment_rejects_case_only_sibling_on_posix() -> None:
    # On POSIX, ".../Saves/x" must NOT be considered inside ".../saves".
    base = Path("/tmp/sat-test/saves")
    sibling = Path("/tmp/sat-test/Saves/x")
    assert _is_within(base, sibling) is False
    assert _is_within(base, base / "ok") is True


# --- SSP-P0-W01: flow metadata round-trip and explicit clearing ---


def _full_flow(ws: SaveWorkspace) -> str:
    """Add a flow carrying every documented metadata field."""
    return ws.add_item(
        "flows",
        "Steel beam line",
        "player wording preserved",
        NOW,
        extra={
            "area": "Northern Forest",
            "recipe": "Steel Beam (Foundry)",
            "machines": "Foundry x8; Constructor x4",
            "constraints": "power<=200MW",
            "inputs": ["Iron Ore 240/min", "Coal 240/min"],
            "outputs": ["Steel Beam 360/min"],
        },
        status="planned",
    )


def test_add_flow_persists_all_metadata_fields(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = _full_flow(ws)
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["area"] == "Northern Forest"
    assert flow["recipe"] == "Steel Beam (Foundry)"
    assert flow["machines"] == "Foundry x8; Constructor x4"
    assert flow["constraints"] == "power<=200MW"
    assert flow["inputs"] == ["Iron Ore 240/min", "Coal 240/min"]
    assert flow["outputs"] == ["Steel Beam 360/min"]


def test_metadata_round_trips_through_format_context(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    _full_flow(ws)
    text = format_context(["Active save: Test"], ws.summary(10))
    assert "Northern Forest" in text
    assert "Steel Beam (Foundry)" in text
    assert "Foundry x8" in text
    assert "power<=200MW" in text


def test_flow_details_round_trip_through_summary_and_context(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item(
        "flows",
        "Steel line",
        "use the alternate Solid Steel recipe",
        NOW,
        extra={"outputs": ["Steel Ingot 360/min"]},
        status="planned",
    )
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["details"] == "use the alternate Solid Steel recipe"
    text = format_context(["Active save: Test"], ws.summary(10))
    assert "use the alternate Solid Steel recipe" in text


def test_flow_details_are_bounded_in_summary(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item(
        "flows", "Line", "D" * 400, NOW, extra={"outputs": ["x"]}, status="planned"
    )
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert len(flow["details"]) <= 160


def test_update_flow_sets_each_metadata_field(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item("flows", "Line", "", NOW, extra={"outputs": ["x"]}, status="planned")
    assert ws.update_flow(
        flow_id,
        NOW,
        area="Blue Crater",
        recipe="Cast Screw",
        machines="Assembler x2",
        constraints="belt<=780",
    )
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["area"] == "Blue Crater"
    assert flow["recipe"] == "Cast Screw"
    assert flow["machines"] == "Assembler x2"
    assert flow["constraints"] == "belt<=780"


def test_update_flow_empty_metadata_leaves_unchanged(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = ws.add_item(
        "flows", "Line", "", NOW, extra={"area": "Keep", "outputs": ["x"]}, status="planned"
    )
    # Empty strings mean "leave unchanged", never "clear".
    assert ws.update_flow(flow_id, NOW, area="", recipe="")
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["area"] == "Keep"


def test_update_flow_clears_string_metadata(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = _full_flow(ws)
    assert ws.update_flow(
        flow_id, NOW, clear_fields={"area", "recipe", "machines", "constraints", "details"}
    )
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["area"] == ""
    assert flow["recipe"] == ""
    assert flow["machines"] == ""
    assert flow["constraints"] == ""
    assert flow["details"] == ""  # details cleared and visible as empty in summary


def test_update_flow_clears_inputs_and_outputs_to_empty_list(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    flow_id = _full_flow(ws)
    assert ws.update_flow(flow_id, NOW, clear_fields={"inputs", "outputs"})
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["inputs"] == []
    assert flow["outputs"] == []


def test_parse_clear_fields_accepts_comma_and_semicolon() -> None:
    assert parse_clear_fields("inputs, outputs; details") == {"inputs", "outputs", "details"}
    assert parse_clear_fields("AREA") == {"area"}
    assert parse_clear_fields("") == set()
    assert parse_clear_fields("  ") == set()


def test_parse_clear_fields_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        parse_clear_fields("inputs, title")
    with pytest.raises(ValueError):
        parse_clear_fields("status")  # status is not in the clear allowlist
    assert "title" not in CLEARABLE_FIELDS
    assert "status" not in CLEARABLE_FIELDS


def test_malformed_legacy_record_does_not_crash(tmp_path: Path) -> None:
    """Non-list inputs/outputs and non-string metadata must not crash rendering."""
    ws = _ws(tmp_path)
    path = ws.dir / "flows.jsonl"
    path.write_text(
        json.dumps(
            {
                "id": "flow_legacy_0001",
                "title": "Legacy",
                "status": "planned",
                "inputs": "Iron Ore 240/min",  # string, not a list
                "outputs": None,  # explicit null
                "area": 123,  # non-string metadata
                "updated_at": "2026-06-17T10:00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary = ws.summary(10)  # must not raise
    text = format_context(["Active save: Test"], summary)  # must not raise
    assert "Legacy" in text


def test_non_object_json_lines_are_ignored(tmp_path: Path) -> None:
    """Valid JSON that is not an object (list, string, number, null) is skipped."""
    ws = _ws(tmp_path)
    path = ws.dir / "todos.jsonl"
    path.write_text(
        "[]\n"
        '"just a string"\n'
        "42\n"
        "null\n"
        '{"id": "todo_real_0001", "title": "Real todo", "status": "open"}\n',
        encoding="utf-8",
    )
    summary = ws.summary(10)  # must not raise on the non-object lines
    titles = {t["title"] for t in summary["open_todos"]}
    assert titles == {"Real todo"}
    # Counts reflect only the surviving dict record, not the junk lines.
    assert summary["counts"]["todos"] == 1
    # Status updates resolve via _read too and must not crash.
    assert ws.set_status("todo_real_0001", "done", NOW) is True
    text = format_context(["Active save: Test"], ws.summary(10))  # must not raise
    assert "Real todo" not in text  # now done, so not in open todos


# --- SSP-P0-W02: record-type safe status actions ---


def test_kind_for_id_maps_known_prefixes() -> None:
    assert kind_for_id("note_20260617_120000_ab12") == "notes"
    assert kind_for_id("todo_20260617_120000_ab12") == "todos"
    assert kind_for_id("goal_20260617_120000_ab12") == "goals"
    assert kind_for_id("flow_20260617_120000_ab12") == "flows"
    assert kind_for_id("chg_20260617_120000_ab12") == "changes"


def test_kind_for_id_rejects_unknown_and_malformed() -> None:
    assert kind_for_id("bogus_1") is None
    assert kind_for_id("") is None
    assert kind_for_id("../../etc/passwd") is None


def test_set_status_for_kind_updates_only_that_kind(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    todo_id = ws.add_item("todos", "Build steel", "", NOW)
    goal_id = ws.add_item("goals", "Reach phase 3", "", NOW)

    # Positive: updating the right kind works.
    assert ws.set_status_for_kind("todos", todo_id, "done", NOW) is True
    assert all(t["id"] != todo_id for t in ws.summary(10)["open_todos"])

    # Negative: pointing a todo id at the goals file must not mutate anything.
    assert ws.set_status_for_kind("goals", todo_id, "archived", NOW) is False
    # The goal is untouched and still open.
    assert any(g["id"] == goal_id for g in ws.summary(10)["goals"])


def test_set_status_for_kind_cannot_cross_into_another_file(tmp_path: Path) -> None:
    """A flow id handed to the todos file must not change the flow's status."""
    ws = _ws(tmp_path)
    flow_id = ws.add_item("flows", "Steel line", "", NOW, extra={"outputs": ["x"]}, status="planned")
    assert ws.set_status_for_kind("todos", flow_id, "archived", NOW) is False
    flow = next(f for f in ws.summary(10)["flows"] if f["id"] == flow_id)
    assert flow["status"] == "planned"  # unchanged


def test_set_status_for_kind_rejects_unknown_kind(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    with pytest.raises(ValueError):
        ws.set_status_for_kind("widgets", "todo_x", "done", NOW)


def test_set_status_infers_kind_from_prefix(tmp_path: Path) -> None:
    """The generic set_status now infers kind, so a mismatched id is a no-op."""
    ws = _ws(tmp_path)
    goal_id = ws.add_item("goals", "Reach phase 3", "", NOW)
    # A fabricated todo id must not touch the goals file.
    assert ws.set_status("todo_does_not_exist", "done", NOW) is False
    assert any(g["id"] == goal_id for g in ws.summary(10)["goals"])


# --- SSP-P0-W03: stable workspace identity ---


def test_stable_key_ignores_save_file_state() -> None:
    """Same root and save name -> same key regardless of .sav presence."""
    root = "/games/FactoryGame/Saved"
    # The key is derived only from root + save name, so a found vs missing
    # save file cannot change it.
    key = stable_workspace_key(root, "Megatime")
    assert stable_workspace_key(root, "Megatime") == key
    # The historical missing-save identity form is preserved, so pre-fix
    # workspaces resolve to the same key without migration.
    assert key == safe_save_key("Megatime", f"{root}|Megatime")


def test_stable_key_disambiguates_roots_and_names() -> None:
    a = stable_workspace_key("/games/A/Saved", "Megatime")
    b = stable_workspace_key("/games/B/Saved", "Megatime")
    c = stable_workspace_key("/games/A/Saved", "Other Save")
    assert len({a, b, c}) == 3


def test_stable_key_handles_missing_save_name() -> None:
    # A None save name must not crash and must stay stable.
    key = stable_workspace_key("/games/A/Saved", None)
    assert key.startswith("save-")
    assert stable_workspace_key("/games/A/Saved", None) == key


def _seed_legacy(tmp_path: Path, legacy_key: str) -> Path:
    legacy_dir = tmp_path / "saves" / legacy_key
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "todos.jsonl").write_text(
        '{"id": "todo_legacy_0001", "title": "Old plan", "status": "open"}\n',
        encoding="utf-8",
    )
    return legacy_dir


def test_adopt_legacy_copies_when_stable_absent(tmp_path: Path) -> None:
    legacy_key = "megatime-deadbeef"
    stable_key = "megatime-cafebabe"
    legacy_dir = _seed_legacy(tmp_path, legacy_key)

    assert adopt_legacy_workspace(tmp_path, stable_key, legacy_key) is True

    stable_dir = tmp_path / "saves" / stable_key
    adopted = (stable_dir / "todos.jsonl").read_text(encoding="utf-8")
    assert "Old plan" in adopted
    # Legacy directory is preserved, never deleted.
    assert legacy_dir.is_dir()
    assert (legacy_dir / "todos.jsonl").is_file()


def test_adopt_legacy_noops_when_stable_has_data(tmp_path: Path) -> None:
    legacy_key = "megatime-deadbeef"
    stable_key = "megatime-cafebabe"
    _seed_legacy(tmp_path, legacy_key)
    stable_dir = tmp_path / "saves" / stable_key
    stable_dir.mkdir(parents=True)
    (stable_dir / "todos.jsonl").write_text(
        '{"id": "todo_new_0001", "title": "Current plan", "status": "open"}\n',
        encoding="utf-8",
    )

    # Both workspaces hold data: no merge, no overwrite.
    assert adopt_legacy_workspace(tmp_path, stable_key, legacy_key) is False
    kept = (stable_dir / "todos.jsonl").read_text(encoding="utf-8")
    assert "Current plan" in kept
    assert "Old plan" not in kept


def test_adopt_legacy_noops_when_no_legacy(tmp_path: Path) -> None:
    assert adopt_legacy_workspace(tmp_path, "stable-1", "legacy-1") is False


def test_context_within_budget_with_metadata_heavy_flows(tmp_path: Path) -> None:
    ws = _ws(tmp_path)
    for i in range(12):
        ws.add_item(
            "flows",
            f"Line {i} " + "x" * 60,
            "",
            NOW,
            extra={
                "area": "Area " + "a" * 60,
                "recipe": "Recipe " + "r" * 60,
                "machines": "Machines " + "m" * 60,
                "constraints": "Constraints " + "c" * 60,
                "inputs": [f"In {j} 240/min" for j in range(8)],
                "outputs": [f"Out {j} 360/min" for j in range(8)],
            },
            status="blocked",
        )
    text = format_context(["Active save: Test"], ws.summary(12))
    assert len(text) <= 3000

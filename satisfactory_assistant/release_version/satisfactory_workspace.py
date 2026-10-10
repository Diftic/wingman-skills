"""Per-save planning workspace for the Satisfactory Assistant skill.

Each active save gets an isolated workspace directory under the skill's
generated-files directory. All reads and writes are confined to that directory
via resolved-path containment checks, so a malicious id or title cannot escape
it. Records are persisted in a per-save SQLite store (``satisfactory_store``);
the five legacy ``<kind>.jsonl`` files that predate the store are imported
into it (never modified, appended to, or deleted) so plans recorded before
this change keep showing up.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from satisfactory_store import SaveStore
from satisfactory_store import import_jsonl as _import_legacy_jsonl


_KINDS = ("notes", "todos", "goals", "flows", "changes")
_ID_PREFIX = {
    "notes": "note",
    "todos": "todo",
    "goals": "goal",
    "flows": "flow",
    "changes": "chg",
}
# Reverse of _ID_PREFIX: the id prefix is the stable record-kind signal, so a
# status action can resolve exactly one JSONL file from an id instead of
# searching every kind blindly.
_KIND_BY_PREFIX = {prefix: kind for kind, prefix in _ID_PREFIX.items()}

STATUS_OPEN = "open"
STATUS_DONE = "done"
STATUS_ARCHIVED = "archived"

# Status values valid for a production flow. "planned" is the default.
FLOW_STATUSES = ("planned", "building", "blocked", "balanced", "done", "archived")

# Flow fields a caller may explicitly clear via update_flow's clear_fields.
# Deliberately excludes "title" (a flow must keep an identifier) and "status"
# (which has its own validated vocabulary and default).
CLEARABLE_FIELDS = ("details", "area", "recipe", "machines", "constraints", "inputs", "outputs")

# Compact string metadata carried on a production flow alongside inputs/outputs.
_FLOW_META_FIELDS = ("area", "recipe", "machines", "constraints")

# Hard per-field caps applied at the summary boundary so a single verbose
# title/material cannot blow the low-token return budget even when the item
# count cap is generous.
_TITLE_MAX = 80
_RATE_MAX = 48
_META_MAX = 80
_DETAILS_MAX = 160
_MAX_FLOW_MATERIALS = 6

# Bound on id-collision retries in add_item (see there for why collisions
# are now possible at all).
_MAX_ID_ATTEMPTS = 5

# Hard ceiling on the rendered context string (~700 tokens), well under the
# 800-token plan target after headers. Sections are added until the budget is
# reached, then a truncation note is appended.
_CONTEXT_CHAR_BUDGET = 2800

_ELLIPSIS = "..."


def clip(text: str, limit: int) -> str:
    """Clip text to ``limit`` chars, appending an ASCII ellipsis if truncated."""
    text = str(text)
    if len(text) <= limit:
        return text
    keep = max(0, limit - len(_ELLIPSIS))
    return text[:keep].rstrip() + _ELLIPSIS


def _clip_rates(items: list, limit_items: int, limit_len: int) -> list[str]:
    clipped = [clip(item, limit_len) for item in items[:limit_items]]
    if len(items) > limit_items:
        clipped.append(f"(+{len(items) - limit_items} more)")
    return clipped


def _as_list(value: object) -> list[str]:
    """Coerce a stored value to a list of strings, tolerating legacy junk.

    Old or hand-edited records may store ``inputs``/``outputs`` as a bare
    string or ``null``; those must degrade to an empty list rather than crash
    summary or context rendering.
    """
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _as_str(value: object) -> str:
    """Coerce stored metadata to a string, tolerating non-string legacy values."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def parse_clear_fields(raw: str) -> set[str]:
    """Parse an explicit clear-fields request into a validated set.

    Accepts comma or semicolon separators and is case-insensitive. Returns an
    empty set for empty input. Raises ``ValueError`` naming any field that is
    not in ``CLEARABLE_FIELDS`` so an unknown request never silently mutates a
    flow.
    """
    tokens = [token.strip().lower() for token in re.split(r"[,;]", raw) if token.strip()]
    fields = set(tokens)
    unknown = fields - set(CLEARABLE_FIELDS)
    if unknown:
        allowed = ", ".join(CLEARABLE_FIELDS)
        raise ValueError(
            f"Cannot clear unknown field(s): {', '.join(sorted(unknown))}. "
            f"Allowed: {allowed}."
        )
    return fields


def slugify(name: str) -> str:
    """Produce a filesystem-safe, lowercase slug from a save name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "save"


def short_hash(identity: str) -> str:
    """Stable 8-char hash used to disambiguate workspaces."""
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]


def safe_save_key(save_name: str, identity: str) -> str:
    """Build a stable, collision-resistant workspace key for a save."""
    return f"{slugify(save_name)}-{short_hash(identity)}"


def stable_workspace_key(root: object, save_name: str | None) -> str:
    """Build a workspace key from stable logical save evidence.

    The key depends only on the active ``Saved`` root and the save name, never
    on whether the ``.sav`` file is currently found on disk. This keeps the same
    logical save mapped to the same workspace even when the active-save result
    flips ``save_file`` between ``None`` and a concrete path, or a transient
    filesystem error hides the file during lookup.

    The identity string matches the historical missing-save form
    (``"<root>|<save_name>"``), so workspaces created before this change resolve
    to the same key without migration.
    """
    identity = f"{root}|{save_name}"
    return safe_save_key(save_name or "save", identity)


def kind_for_id(item_id: str) -> str | None:
    """Resolve the JSONL record kind from an item id's prefix.

    Ids are minted as ``<prefix>_<stamp>_<rand>`` (e.g. ``todo_2026...``), so the
    leading token before the first underscore identifies the kind. Returns the
    kind name (e.g. ``"todos"``) or ``None`` for an unknown/malformed id, letting
    callers reject mismatched ids without touching any file.
    """
    if not item_id:
        return None
    prefix = item_id.split("_", 1)[0]
    return _KIND_BY_PREFIX.get(prefix)


def _is_within(base: Path, target: Path) -> bool:
    """True if ``target`` resolves to a path inside (or equal to) ``base``.

    Uses case-sensitive ``relative_to`` containment. A lowercased string
    fallback is applied ONLY on Windows, whose filesystem is case-insensitive;
    on case-sensitive POSIX filesystems that fallback would wrongly treat a
    case-different sibling (``.../Saves`` vs ``.../saves``) as contained.
    """
    base_resolved = base.resolve()
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(base_resolved)
        return True
    except ValueError:
        if os.name != "nt":
            return False
        base_str = str(base_resolved).lower().rstrip("\\/")
        target_str = str(target_resolved).lower()
        return (
            target_str == base_str
            or target_str.startswith(base_str + "\\")
            or target_str.startswith(base_str + "/")
        )


def adopt_legacy_workspace(base_dir: Path, stable_key: str, legacy_key: str) -> bool:
    """Adopt a legacy path-hash workspace's JSONL files under the stable key.

    Older workspaces were keyed on the volatile ``.sav`` file path. When the
    stable workspace holds no data yet, copy the legacy workspace's ``*.jsonl``
    files under the stable key so plans created before the stable-identity fix
    do not appear to vanish. Conservative by design:

    - never deletes or rewrites the legacy directory;
    - never overwrites a stable workspace that already holds data, so no
      automatic merge can clobber records;
    - never copies over a file that already exists under the stable key;
    - stays within the skill's ``saves`` root via containment checks.

    Returns True if at least one file was adopted.
    """
    saves_root = (base_dir / "saves").resolve()
    legacy_dir = (saves_root / legacy_key).resolve()
    stable_dir = (saves_root / stable_key).resolve()
    if not (_is_within(saves_root, legacy_dir) and _is_within(saves_root, stable_dir)):
        return False
    if not legacy_dir.is_dir():
        return False
    legacy_files = sorted(p for p in legacy_dir.glob("*.jsonl") if p.is_file())
    if not legacy_files:
        return False
    # Prefer an existing stable workspace: if it already holds data, leave both
    # directories untouched rather than merging.
    if stable_dir.is_dir() and any(stable_dir.glob("*.jsonl")):
        return False
    stable_dir.mkdir(parents=True, exist_ok=True)
    adopted = False
    for src in legacy_files:
        dest = (stable_dir / src.name).resolve()
        if not _is_within(stable_dir, dest) or dest.exists():
            continue
        dest.write_bytes(src.read_bytes())
        adopted = True
    return adopted


class SaveWorkspace:
    """SQLite-backed planning workspace scoped to a single active save.

    Records live in ``planning.sqlite3`` inside the workspace directory (see
    ``satisfactory_store.SaveStore``). Workspace instances are short-lived,
    constructed fresh per tool call (see ``main.py``'s ``_workspace_for``), so
    the store is opened and closed around each operation rather than held
    open on the instance: this keeps the SQLite file handle from outliving a
    call (important for test ``tmp_path`` teardown on Windows) and means a
    legacy ``<kind>.jsonl`` file edited or created between calls is picked up
    on the very next operation, since the legacy import re-checks each
    source's content hash on every open and is a no-op once it is caught up.
    """

    def __init__(self, base_dir: Path, save_key: str) -> None:
        self._saves_root = (base_dir / "saves").resolve()
        self.dir = (self._saves_root / save_key).resolve()
        if not _is_within(self._saves_root, self.dir):
            raise ValueError(f"Refusing workspace outside saves root: {save_key}")

    def ensure(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, kind: str) -> Path:
        if kind not in _KINDS:
            raise ValueError(f"Unknown record kind: {kind}")
        path = (self.dir / f"{kind}.jsonl").resolve()
        if not _is_within(self.dir, path):
            raise ValueError("Path escapes workspace")
        return path

    def _new_id(self, kind: str, now: datetime) -> str:
        stamp = now.strftime("%Y%m%d_%H%M%S")
        return f"{_ID_PREFIX[kind]}_{stamp}_{uuid.uuid4().hex[:8]}"

    def _open_store(self) -> SaveStore:
        """Open this workspace's SQLite store, importing legacy JSONL first.

        The import is keyed on each legacy file's content hash (see
        ``satisfactory_store.import_jsonl``), so running it on every open is
        cheap once caught up: an unchanged file is skipped entirely, and a
        file created or edited directly (as some tests do, and as a hand
        edit in the wild would) is picked up without a separate "first use"
        step. Callers own the returned store and must close it.
        """
        self.ensure()
        store = SaveStore.open(self.dir / "planning.sqlite3")
        legacy_sources = {kind: self._path(kind) for kind in _KINDS}
        _import_legacy_jsonl(store, legacy_sources)
        return store

    def _read(self, kind: str) -> list[dict]:
        if kind not in _KINDS:
            raise ValueError(f"Unknown record kind: {kind}")
        store = self._open_store()
        try:
            return store.list_records(kind, newest_first=False)
        finally:
            store.close()

    def add_item(
        self,
        kind: str,
        title: str,
        details: str,
        now: datetime,
        extra: dict | None = None,
        status: str = STATUS_OPEN,
    ) -> str:
        """Add a new record and return its id."""
        store = self._open_store()
        try:
            item_id = self._new_id(kind, now)
            for attempt in range(_MAX_ID_ATTEMPTS):
                try:
                    store.add_record(
                        kind,
                        item_id,
                        title.strip(),
                        details.strip(),
                        status,
                        now,
                        extra=extra or {},
                    )
                    break
                except sqlite3.IntegrityError:
                    # id is a per-second timestamp plus a short random suffix;
                    # same-second inserts can collide, and id is now a SQLite
                    # primary key (post the SaveStore swap), so a collision
                    # raises instead of silently overwriting.
                    if attempt == _MAX_ID_ATTEMPTS - 1:
                        raise
                    item_id = self._new_id(kind, now)
        finally:
            store.close()
        return item_id

    def update_flow(
        self,
        item_id: str,
        now: datetime,
        title: str | None = None,
        details: str | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
        status: str | None = None,
        area: str | None = None,
        recipe: str | None = None,
        machines: str | None = None,
        constraints: str | None = None,
        clear_fields: set[str] | None = None,
    ) -> bool:
        """Update fields of an existing flow. Returns True if the flow was found.

        Only provided, non-empty fields are changed; an empty string means
        "leave unchanged". Clearing a field to its empty value is opt-in via
        ``clear_fields`` (a set restricted to ``CLEARABLE_FIELDS``) and is
        applied last, so an explicit clear wins over a set in the same call.
        """
        clear = {f for f in (clear_fields or set()) if f in CLEARABLE_FIELDS}
        store = self._open_store()
        try:
            return store.update_flow(
                item_id,
                now,
                title=title,
                details=details,
                inputs=inputs,
                outputs=outputs,
                status=status,
                area=area,
                recipe=recipe,
                machines=machines,
                constraints=constraints,
                clear_fields=clear,
            )
        finally:
            store.close()

    def set_status_for_kind(
        self, kind: str, item_id: str, status: str, now: datetime
    ) -> bool:
        """Update an item's status within a single record kind only.

        Scoped to ``kind`` in the store, so an id that belongs to another
        kind (or to no record) cannot mutate a different kind's record.
        Returns True if a matching record was found and updated.
        """
        if kind not in _KINDS:
            raise ValueError(f"Unknown record kind: {kind}")
        store = self._open_store()
        try:
            return store.set_status(kind, item_id, status, now)
        finally:
            store.close()

    def set_status(self, item_id: str, status: str, now: datetime) -> bool:
        """Update an item's status, resolving its kind from the id prefix.

        Type-safe by construction: the id prefix selects exactly one JSONL file,
        so a mismatched or unknown id is a no-op rather than a blind cross-kind
        search. Returns True if a matching record was found.
        """
        kind = kind_for_id(item_id)
        if kind is None:
            return False
        return self.set_status_for_kind(kind, item_id, status, now)

    def summary(self, max_items: int, focus: str = "") -> dict:
        """Compact, capped view of the workspace for the AI.

        When ``focus`` is given, records are filtered across title, details,
        inputs, and outputs BEFORE capping, so a matching older item is not
        hidden behind newer unrelated records.
        """
        focus_lc = focus.strip().lower()

        def matches(record: dict) -> bool:
            if not focus_lc:
                return True
            parts = [
                _as_str(record.get("title", "")),
                _as_str(record.get("details", "")),
                _as_str(record.get("status", "")),
            ]
            parts.extend(_as_str(record.get(field, "")) for field in _FLOW_META_FIELDS)
            parts.extend(_as_list(record.get("inputs")))
            parts.extend(_as_list(record.get("outputs")))
            if focus_lc in " ".join(parts).lower():
                return True
            # Alias: "missing" surfaces flows with an output target but no inputs.
            if focus_lc in ("missing", "missing inputs", "missing materials"):
                return bool(_as_list(record.get("outputs"))) and not _as_list(
                    record.get("inputs")
                )
            return False

        def latest_open(kind: str) -> list[dict]:
            items = [
                r
                for r in self._read(kind)
                if r.get("status") == STATUS_OPEN and matches(r)
            ]
            items.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
            return items[:max_items]

        notes = [r for r in self._read("notes") if matches(r)]
        notes.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        recent_changes = [r for r in self._read("changes") if matches(r)]
        recent_changes.sort(key=lambda r: r.get("updated_at", ""), reverse=True)

        def shape(record: dict) -> dict:
            return {
                "id": record.get("id", ""),
                "title": clip(record.get("title", ""), _TITLE_MAX),
                "status": record.get("status", ""),
            }

        def shape_flow(record: dict) -> dict:
            shaped = {
                "id": _as_str(record.get("id", "")),
                "title": clip(_as_str(record.get("title", "")), _TITLE_MAX),
                "status": _as_str(record.get("status", "")),
                "details": clip(_as_str(record.get("details", "")), _DETAILS_MAX),
                "inputs": _clip_rates(_as_list(record.get("inputs")), _MAX_FLOW_MATERIALS, _RATE_MAX),
                "outputs": _clip_rates(_as_list(record.get("outputs")), _MAX_FLOW_MATERIALS, _RATE_MAX),
            }
            for field in _FLOW_META_FIELDS:
                shaped[field] = clip(_as_str(record.get(field, "")), _META_MAX)
            return shaped

        all_flows = [
            r
            for r in self._read("flows")
            if r.get("status") != STATUS_ARCHIVED and matches(r)
        ]
        all_flows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)

        def is_blocked(record: dict) -> bool:
            # Explicitly blocked, or has a target output but no known inputs.
            if record.get("status") == "blocked":
                return True
            return bool(_as_list(record.get("outputs"))) and not _as_list(record.get("inputs"))

        blocked_flows = [r for r in all_flows if is_blocked(r)]

        return {
            "open_todos": [shape(r) for r in latest_open("todos")],
            "goals": [shape(r) for r in latest_open("goals")],
            "notes": [shape(r) for r in notes[:max_items]],
            "flows": [shape_flow(r) for r in all_flows[:max_items]],
            "blocked_flows": [shape_flow(r) for r in blocked_flows[:max_items]],
            "recent_changes": [shape(r) for r in recent_changes[:max_items]],
            "counts": {kind: len(self._read(kind)) for kind in _KINDS},
        }


def _item_line(item: dict) -> str:
    return f"  - [{item['id']}] {item['title']}"


def _flow_line(item: dict) -> str:
    outs = ", ".join(item.get("outputs", [])) or "?"
    ins = ", ".join(item.get("inputs", []))
    tail = f" (in: {ins})" if ins else ""
    area = item.get("area", "")
    where = f" @{area}" if area else ""
    # Compact, only-if-present metadata block keeps quiet flows terse while
    # surfacing recipe/machines/constraints/details when the player recorded them.
    meta = [
        f"{label}: {item[field]}"
        for label, field in (
            ("recipe", "recipe"),
            ("machines", "machines"),
            ("constraints", "constraints"),
            ("details", "details"),
        )
        if item.get(field)
    ]
    extra = f" {{{'; '.join(meta)}}}" if meta else ""
    return (
        f"  - [{item['id']}] {item['title']}{where}: {outs}{tail} "
        f"[{item['status']}]{extra}"
    )


def format_context(
    header_lines: list[str],
    summary: dict,
    char_budget: int = _CONTEXT_CHAR_BUDGET,
) -> str:
    """Render a compact, hard-bounded context string from a summary.

    Blocked flows are shown only once (in their own section, not also under
    "Production flows"), and sections are appended only while they fit within
    ``char_budget`` so the total return stays under the low-token target
    regardless of how many records match.
    """
    blocked_ids = {f["id"] for f in summary.get("blocked_flows", [])}
    non_blocked = [f for f in summary.get("flows", []) if f["id"] not in blocked_ids]

    out = list(header_lines)
    used = sum(len(line) + 1 for line in out)
    truncated = False

    def emit(label: str, items: list[dict], fmt) -> None:
        nonlocal used, truncated
        if truncated or not items:
            return
        pending = [f"\n{label}:"]
        added = 0
        for item in items:
            line = fmt(item)
            extra = sum(len(s) + 1 for s in pending) + len(line) + 1
            if used + extra > char_budget:
                truncated = True
                break
            pending.append(line)
            added += 1
        if added:
            out.extend(pending)
            used += sum(len(s) + 1 for s in pending)

    emit("Production flows", non_blocked, _flow_line)
    emit("Blocked / missing inputs", summary.get("blocked_flows", []), _flow_line)
    emit("Open todos", summary.get("open_todos", []), _item_line)
    emit("Production goals", summary.get("goals", []), _item_line)
    emit("Notes", summary.get("notes", []), _item_line)
    emit("Recent changes", summary.get("recent_changes", []), _item_line)

    if truncated:
        out.append("\n(more items not shown; narrow with a focus keyword)")
    if len(out) <= len(header_lines):
        out.append("\nNo planning records yet for this save.")
    return "\n".join(out)

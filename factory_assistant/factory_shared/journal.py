"""Per-save player journal: notes, jobs (todos), goals and production setups (flows).

Every factory game has the same journal, so this logic is shared. A game
Handler resolves the active save and its workspace, then calls
:func:`apply_journal_update`. Nothing here imports a game or Wingman.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from factory_shared.workspace import (
    FLOW_STATUSES,
    STATUS_ARCHIVED,
    STATUS_DONE,
    SaveWorkspace,
    clip,
    kind_for_id,
    parse_clear_fields,
)

# Clip titles echoed in write-tool acknowledgements (stored titles are kept in
# full); keeps tool responses short even for long natural-language titles.
ACK_TITLE_MAX = 60

JOURNAL_ACTIONS = (
    "add_note",
    "add_todo",
    "complete_todo",
    "add_goal",
    "add_flow",
    "update_flow",
    "archive_item",
)


def parse_rates(raw: str) -> list[str]:
    """Split a semicolon-separated material-rate string into a clean list."""
    return [part.strip() for part in raw.split(";") if part.strip()]


def _append_rate_alias(materials: str, rate: Any) -> str:
    """Fold common LLM-invented rate aliases into the existing material field."""
    rate_text = str(rate).strip() if rate is not None else ""
    materials = materials.strip()
    if not rate_text:
        return materials
    if not materials:
        return rate_text
    if rate_text.lower() in materials.lower():
        return materials
    return f"{materials} {rate_text}"


def normalize_rate_aliases(
    inputs: str, outputs: str, kwargs: dict[str, Any]
) -> tuple[str, str]:
    for key in ("input_rate", "input_rates"):
        inputs = _append_rate_alias(inputs, kwargs.get(key))
    for key in ("output_rate", "output_rates"):
        outputs = _append_rate_alias(outputs, kwargs.get(key))
    return inputs, outputs


def resolve_status_target(action: str, item_id: str) -> tuple[str | None, str | None]:
    """Resolve which record kind a status action may touch, enforcing type safety.

    Returns ``(kind, None)`` when the action is allowed for ``item_id``'s kind, or
    ``(None, error_message)`` when it is not (so the caller mutates nothing):

    - ``complete_todo`` only accepts a ``todo_`` id and only touches ``todos``.
    - ``archive_item`` accepts note/todo/goal/flow ids; it rejects ``chg_``
      change-log ids (append-only audit history) and unknown prefixes.
    """
    kind = kind_for_id(item_id)
    if action == "complete_todo":
        if kind != "todos":
            return None, f"complete_todo needs a todo id (todo_...), not '{item_id}'."
        return "todos", None
    if kind is None or kind == "changes":
        return None, (
            f"archive_item needs a note, todo, goal, or flow id, not '{item_id}'."
        )
    return kind, None


def apply_journal_update(
    ws: SaveWorkspace,
    save_name: str | None,
    action: str,
    *,
    title: str = "",
    details: str = "",
    item_id: str = "",
    inputs: str = "",
    outputs: str = "",
    status: str = "",
    area: str = "",
    recipe: str = "",
    machines: str = "",
    constraints: str = "",
    clear_fields: str = "",
    extra: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> str:
    """Apply one journal action to ``ws`` and return a short player-facing reply."""
    now = now or datetime.now()
    inputs, outputs = normalize_rate_aliases(inputs, outputs, extra or {})

    if action in ("complete_todo", "archive_item"):
        if not item_id:
            return "I couldn't tell which saved item you wanted to change."
        kind, target_error = resolve_status_target(action, item_id)
        if target_error:
            return target_error
        new_status = STATUS_DONE if action == "complete_todo" else STATUS_ARCHIVED
        if not ws.set_status_for_kind(kind, item_id, new_status, now):
            return "I couldn't find that saved item."
        ws.add_item("changes", f"{action}: {item_id}", "", now)
        return "Done — I updated that saved item."

    flow_status = status.strip().lower() if status.strip() else None
    if flow_status and flow_status not in FLOW_STATUSES:
        return f"I don't recognize that progress status. Try: {', '.join(FLOW_STATUSES)}."

    if action == "update_flow":
        if not item_id:
            return "I couldn't tell which production setup you wanted to change."
        try:
            to_clear = parse_clear_fields(clear_fields)
        except ValueError as exc:
            return str(exc)
        found = ws.update_flow(
            item_id,
            now,
            title=title or None,
            details=details or None,
            inputs=parse_rates(inputs) if inputs.strip() else None,
            outputs=parse_rates(outputs) if outputs.strip() else None,
            status=flow_status,
            area=area or None,
            recipe=recipe or None,
            machines=machines or None,
            constraints=constraints or None,
            clear_fields=to_clear,
        )
        if not found:
            return "I couldn't find that production setup."
        ws.add_item("changes", f"update_flow: {item_id}", "", now)
        return "Done — I updated that production setup."

    if not title.strip():
        return "Tell me what you want to call it."

    # Full title is stored; only the echoed acknowledgement is clipped.
    title_disp = clip(title.strip(), ACK_TITLE_MAX)

    if action == "add_flow":
        ws.add_item(
            "flows",
            title,
            details,
            now,
            extra={
                "inputs": parse_rates(inputs),
                "outputs": parse_rates(outputs),
                "area": area.strip(),
                "recipe": recipe.strip(),
                "machines": machines.strip(),
                "constraints": constraints.strip(),
            },
            status=flow_status or "planned",
        )
        ws.add_item("changes", f"add_flow: {title.strip()}", "", now)
        return f"Saved the production setup '{title_disp}' for {save_name}."

    kind = {"add_note": "notes", "add_todo": "todos", "add_goal": "goals"}[action]
    ws.add_item(kind, title, details, now)
    ws.add_item("changes", f"{action}: {title.strip()}", "", now)
    friendly_kind = {"notes": "note", "todos": "job", "goals": "goal"}[kind]
    return f"Saved the {friendly_kind} '{title_disp}' for {save_name}."

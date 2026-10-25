"""Let a Wingman use its own tools on a board task. Pure Python, no Wingman imports.

The skill facade's model calls (`ai.generate`) return text only and send no tools. So the model
is told to reply with one JSON object naming a tool, the answer, or a member to pass the task
to, and this loop runs the tools itself through callables the skill hands in.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Awaitable, Callable

MAX_TOOL_RESULT_CHARS = 4000
MAX_DESCRIPTION_CHARS = 200
MAX_PARAMETERS_CHARS = 300
GAVE_UP = "I couldn't finish this task."

Generate = Callable[[list[dict]], Awaitable[str]]
Invoke = Callable[[str, dict], Awaitable[str]]
ListTools = Callable[[], list[dict]]


@dataclass(frozen=True)
class Step:
    kind: str  # "answer", "tool", "forward" or "invalid"
    text: str = ""
    tool: str = ""
    arguments: dict = field(default_factory=dict)
    forward_to: str = ""


@dataclass(frozen=True)
class Outcome:
    kind: str  # "answer" or "forward"
    text: str
    forward_to: str = ""
    tool_steps: int = 0


_MARKUP = re.compile(r"<(invoke|function_calls|parameter)\b")
_INVOKE = re.compile(r'<invoke\s+name="([^"]+)"\s*>(.*?)</invoke>', re.DOTALL)
_PARAMETER = re.compile(r'<parameter\s+name="([^"]+)"\s*>(.*?)</parameter>', re.DOTALL)


def _parse_markup(text: str) -> Step:
    """Claude's own tool-call format, which it sometimes falls back to mid-task:
    <invoke name="tool"><parameter name="key">value</parameter></invoke>. First call only."""
    match = _INVOKE.search(text)
    if match is None:
        return Step("invalid")
    arguments = {}
    for key, raw in _PARAMETER.findall(match.group(2)):
        value = raw.strip()
        try:
            arguments[key] = json.loads(value)
        except ValueError:
            arguments[key] = value
    return Step("tool", tool=match.group(1).strip(), arguments=arguments)


def _find_json_object(text: str) -> dict | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    decoder = json.JSONDecoder()
    for candidate in candidates:
        for start in (i for i, ch in enumerate(candidate) if ch == "{"):
            try:
                value, _ = decoder.raw_decode(candidate, start)
            except ValueError:
                continue
            if isinstance(value, dict):
                return value
    return None


def parse_reply(text: str) -> Step:
    """Read the model's reply. Plain text without any JSON counts as the answer."""
    text = (text or "").strip()
    if not text:
        return Step("invalid")
    if _MARKUP.search(text):  # a tool call in markup is never the answer, even a broken one
        return _parse_markup(text)
    data = _find_json_object(text)
    if data is None:
        return Step("answer", text=text)
    if isinstance(data.get("answer"), str) and data["answer"].strip():
        return Step("answer", text=data["answer"].strip())
    if isinstance(data.get("tool"), str) and data["tool"].strip():
        arguments = data.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except ValueError:
                arguments = {}
        return Step("tool", tool=data["tool"].strip(),
                    arguments=arguments if isinstance(arguments, dict) else {})
    if isinstance(data.get("forward_to"), str) and data["forward_to"].strip():
        return Step("forward", forward_to=data["forward_to"].strip(),
                    text=str(data.get("note") or "").strip())
    return Step("invalid")


def catalog_text(tools: list[dict], max_chars: int) -> str:
    """The tool list for the prompt: name, short description, parameters. Cut to max_chars."""
    if not tools:
        return "You have no tools for this task."
    lines = []
    used = 0
    reserve = 60
    for index, tool in enumerate(tools):
        properties = (tool.get("parameters") or {}).get("properties") or {}
        params = json.dumps(properties, separators=(",", ":"))[:MAX_PARAMETERS_CHARS]
        description = " ".join(str(tool.get("description") or "").split())[:MAX_DESCRIPTION_CHARS]
        line = f"- {tool.get('name')}: {description} Parameters: {params}"
        if used + len(line) + 1 > max_chars - reserve:
            lines.append(f"({len(tools) - index} more tools not listed)")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)[:max_chars]


def _protocol(tools: list[dict], allow_forward: bool, max_catalog_chars: int) -> str:
    options = [
        '{"tool": "<tool name>", "arguments": {...}} to use one of your tools,',
        '{"answer": "<your answer>"} when you have the answer,',
    ]
    if allow_forward:
        options.append('{"forward_to": "<member name>", "note": "<why>"} to pass the task to '
                       "a board member who fits it better.")
    return ("BOARD TASK RULES\nReply with exactly one JSON object and nothing else, every "
            "time, also after a tool result. Never use XML or any other tool-call format:\n"
            + "\n".join(options)
            + "\n\nYour tools:\n" + catalog_text(tools, max_catalog_chars))


async def run_task(*, system: str, history: list[dict], task: str, list_tools: ListTools,
                   generate: Generate, invoke: Invoke, max_steps: int,
                   allow_forward: bool = True, max_catalog_chars: int = 12000) -> Outcome:
    """Run the task until the model answers or forwards, with at most max_steps tool calls."""
    messages = [
        {"role": "system",
         "content": f"{system}\n\n{_protocol(list_tools(), allow_forward, max_catalog_chars)}"},
        *history,
        {"role": "user", "content": task},
    ]
    tool_steps = 0
    corrections = 0
    over_limit = 0
    for _ in range(max_steps + 4):
        reply = await generate(messages)
        step = parse_reply(reply)
        if step.kind == "answer":
            return Outcome("answer", step.text, tool_steps=tool_steps)
        if step.kind == "forward" and allow_forward:
            return Outcome("forward", step.text, forward_to=step.forward_to, tool_steps=tool_steps)
        messages.append({"role": "assistant", "content": reply})

        if step.kind == "tool" and tool_steps >= max_steps:
            over_limit += 1
            if over_limit > 1:
                break
            messages.append({"role": "user", "content":
                             'No more tools. Answer now with {"answer": "..."} using what you have.'})
            continue

        if step.kind == "tool":
            tool_steps += 1
            known = {t.get("name") for t in list_tools()}
            if step.tool not in known:
                messages.append({"role": "user", "content":
                                 f"There is no tool named {step.tool}. Use one from your list, "
                                 'or answer with {"answer": "..."}.'})
                continue
            try:
                result = await invoke(step.tool, step.arguments)
            except Exception as error:  # a tool's failure is information for the model
                result = f"The tool failed: {error}"
            messages.append({"role": "user", "content":
                             f"Result of {step.tool}:\n{str(result)[:MAX_TOOL_RESULT_CHARS]}"})
            continue

        corrections += 1
        if corrections > 1:
            break
        messages.append({"role": "user", "content":
                         "Reply with exactly one JSON object as described in BOARD TASK RULES."})
    return Outcome("answer", GAVE_UP, tool_steps=tool_steps)

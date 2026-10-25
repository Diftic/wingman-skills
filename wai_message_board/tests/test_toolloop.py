"""The tool loop a Wingman runs for a board task: JSON replies, tools, limits."""

from __future__ import annotations

import asyncio
import json

from wai_toolloop import Outcome, catalog_text, parse_reply, run_task


TOOLS = [
    {"name": "uex_get_item_prices", "description": "Live item prices from UEX.",
     "parameters": {"type": "object", "properties": {"item": {"type": "string"}}}},
]


class FakeModel:
    """Answers with the scripted replies in order and records what it was sent."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []

    async def __call__(self, messages: list[dict]) -> str:
        self.calls.append([dict(m) for m in messages])
        return self.replies.pop(0) if self.replies else '{"answer": "fallback"}'


class FakeTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def __call__(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"{name} says 85000 aUEC"


def run(model, tools=None, max_steps=4, task="Price of an S4 repeater?") -> Outcome:
    return asyncio.run(run_task(
        system="You are Professor Martin.",
        history=[{"role": "user", "content": "earlier question"},
                 {"role": "assistant", "content": "earlier answer"}],
        task=task,
        list_tools=lambda: TOOLS,
        generate=model,
        invoke=tools or FakeTools(),
        max_steps=max_steps,
    ))


def test_parse_reply_reads_each_kind():
    assert parse_reply('{"answer": "340k"}').kind == "answer"
    tool = parse_reply('{"tool": "uex_get_item_prices", "arguments": {"item": "S4"}}')
    assert (tool.kind, tool.tool, tool.arguments) == ("tool", "uex_get_item_prices", {"item": "S4"})
    forward = parse_reply('{"forward_to": "Quartermaster", "note": "yours"}')
    assert (forward.kind, forward.forward_to, forward.text) == ("forward", "Quartermaster", "yours")


def test_parse_reply_finds_json_inside_a_code_fence_or_prose():
    step = parse_reply('Sure.\n```json\n{"answer": "340k aUEC"}\n```')

    assert (step.kind, step.text) == ("answer", "340k aUEC")


def test_parse_reply_takes_plain_text_as_the_answer():
    step = parse_reply("The total is 340k aUEC, Captain.")

    assert (step.kind, step.text) == ("answer", "The total is 340k aUEC, Captain.")


def test_parse_reply_reads_claudes_own_tool_call_markup():
    # Seen live on 2026-10-25: Claude Sonnet 5.5 dropped the JSON format after two tool steps.
    text = ('<invoke name="mcp_wingman_websearch_fetch_url">\n'
            '<parameter name="url">https://starcitizen.tools/Nyx_system</parameter>\n'
            '</invoke>\n</invoke>\n\n\n'
            '<invoke name="mcp_wingman_websearch_fetch_url">\n'
            '<parameter name="url">https://starcitizen.tools/Nyx_system</parameter>\n</invoke>')

    step = parse_reply(text)

    assert (step.kind, step.tool) == ("tool", "mcp_wingman_websearch_fetch_url")
    assert step.arguments == {"url": "https://starcitizen.tools/Nyx_system"}


def test_markup_parameters_holding_json_are_decoded():
    text = ('<function_calls><invoke name="uex_get_item_prices">'
            '<parameter name="limit">5</parameter>'
            '<parameter name="filters">{"item": "S4"}</parameter>'
            '</invoke></function_calls>')

    step = parse_reply(text)

    assert step.arguments == {"limit": 5, "filters": {"item": "S4"}}


def test_broken_tool_markup_is_not_taken_as_the_answer():
    assert parse_reply('<invoke name="search_web"><parameter name="q">Nyx').kind == "invalid"
    assert parse_reply("<function_calls>\n</function_calls>").kind == "invalid"


def test_a_markup_tool_call_is_run_like_a_json_one():
    model = FakeModel('<invoke name="uex_get_item_prices"><parameter name="item">S4'
                      '</parameter></invoke>', '{"answer": "85k"}')
    tools = FakeTools()

    outcome = run(model, tools)

    assert tools.calls == [("uex_get_item_prices", {"item": "S4"})]
    assert outcome.text == "85k"


def test_parse_reply_flags_json_of_the_wrong_shape():
    assert parse_reply('{"tool": ""}').kind == "invalid"
    assert parse_reply('{"something": 1}').kind == "invalid"
    assert parse_reply("").kind == "invalid"


def test_a_direct_answer_needs_one_call():
    model = FakeModel('{"answer": "340k aUEC"}')

    outcome = run(model)

    assert (outcome.kind, outcome.text, outcome.tool_steps) == ("answer", "340k aUEC", 0)
    sent = model.calls[0]
    assert sent[0]["role"] == "system"
    assert "You are Professor Martin." in sent[0]["content"]
    assert "uex_get_item_prices" in sent[0]["content"]
    assert sent[-1] == {"role": "user", "content": "Price of an S4 repeater?"}
    assert {"role": "assistant", "content": "earlier answer"} in sent


def test_a_tool_step_runs_the_tool_and_feeds_the_result_back():
    model = FakeModel('{"tool": "uex_get_item_prices", "arguments": {"item": "S4"}}',
                      '{"answer": "85k each"}')
    tools = FakeTools()

    outcome = run(model, tools)

    assert tools.calls == [("uex_get_item_prices", {"item": "S4"})]
    assert (outcome.text, outcome.tool_steps) == ("85k each", 1)
    assert "85000 aUEC" in model.calls[1][-1]["content"]


def test_an_unknown_tool_is_not_run_and_the_model_is_told():
    model = FakeModel('{"tool": "launch_missiles", "arguments": {}}', '{"answer": "ok"}')
    tools = FakeTools()

    outcome = run(model, tools)

    assert tools.calls == []
    assert outcome.text == "ok"
    assert "launch_missiles" in model.calls[1][-1]["content"]


def test_the_step_limit_forces_an_answer():
    tool_call = '{"tool": "uex_get_item_prices", "arguments": {}}'
    model = FakeModel(tool_call, tool_call, tool_call, '{"answer": "best I have"}')
    tools = FakeTools()

    outcome = run(model, tools, max_steps=2)

    assert len(tools.calls) == 2
    assert outcome.text == "best I have"
    assert "no more tools" in model.calls[-1][-1]["content"].lower()


def test_a_model_that_never_answers_still_ends():
    tool_call = '{"tool": "uex_get_item_prices", "arguments": {}}'
    model = FakeModel(*([tool_call] * 10))

    outcome = run(model, max_steps=1)

    assert outcome.kind == "answer"
    assert outcome.text
    assert len(model.calls) <= 4


def test_bad_json_gets_one_correction():
    model = FakeModel('{"something": 1}', '{"answer": "fixed"}')

    outcome = run(model)

    assert outcome.text == "fixed"
    assert "json" in model.calls[1][-1]["content"].lower()


def test_forward_ends_the_loop():
    model = FakeModel('{"forward_to": "Quartermaster", "note": "prices are yours"}')

    outcome = run(model)

    assert (outcome.kind, outcome.forward_to, outcome.text) == ("forward", "Quartermaster",
                                                                  "prices are yours")


def test_a_failing_tool_is_reported_to_the_model_not_raised():
    async def broken(name, arguments):
        raise RuntimeError("UEX is down")

    model = FakeModel('{"tool": "uex_get_item_prices", "arguments": {}}', '{"answer": "no data"}')

    outcome = run(model, broken)

    assert outcome.text == "no data"
    assert "UEX is down" in model.calls[1][-1]["content"]


def test_catalog_text_lists_tools_and_stays_under_the_limit():
    many = [{"name": f"tool_{i}", "description": "x" * 500,
             "parameters": {"type": "object", "properties": {"a": {"type": "string"}}}}
            for i in range(100)]

    text = catalog_text(many, max_chars=3000)

    assert len(text) <= 3000
    assert "tool_0" in text
    assert "more tools not listed" in text


def test_catalog_text_with_no_tools_says_so():
    assert "no tools" in catalog_text([], max_chars=1000).lower()


def test_tool_arguments_that_are_a_json_string_are_decoded():
    model = FakeModel(json.dumps({"tool": "uex_get_item_prices", "arguments": '{"item": "S4"}'}),
                      '{"answer": "ok"}')
    tools = FakeTools()

    run(model, tools)

    assert tools.calls == [("uex_get_item_prices", {"item": "S4"})]

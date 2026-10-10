"""Navigation acknowledgements cannot acquire a generated trip narrative."""
import asyncio
import ast
import inspect
import json
import textwrap

from _stubs import install_runtime_stubs
install_runtime_stubs()
import main
from test_arrival import _bare_skill, _Target


def test_navigation_tool_disables_summary_and_waiting_chatter():
    function = ast.parse(textwrap.dedent(inspect.getsource(main.SC_NavPoint.navigate_to))).body[0]
    options = {kw.arg: ast.literal_eval(kw.value) for kw in function.decorator_list[0].keywords}
    assert options['summarize'] is False
    assert options['wait_response'] is False


def test_navigation_dispatch_speaks_only_the_confirmed_target(monkeypatch):
    skill = _bare_skill()
    payload = dict(success=True, target=dict(name='Mining location 47'),
                   guidance='4 point 2 kilometers | Direction unavailable')
    async def execute(self, name, parameters, benchmark):
        return json.dumps(payload), ''
    monkeypatch.setattr(main.Skill, 'execute_tool', execute, raising=False)
    raw, speech = asyncio.run(skill.execute_tool('navigate_to', {'name': '47'}, None))
    assert json.loads(raw) == payload
    assert speech == 'Navigating to Mining location 47.'


def test_navigation_failure_keeps_actual_error_and_action(monkeypatch):
    skill = _bare_skill()
    payload = dict(error='Position overlay is not visible.', hint='Open the console and type: r_displayinfo 2.', target_not_set=True)
    async def execute(self, name, parameters, benchmark):
        return json.dumps(payload), ''
    monkeypatch.setattr(main.Skill, 'execute_tool', execute, raising=False)
    raw, speech = asyncio.run(skill.execute_tool('navigate_to', {'name': '47'}, None))
    assert json.loads(raw) == payload
    assert speech == payload['error'] + ' ' + payload['hint']
    raw, speech = asyncio.run(skill.execute_tool('mark_location', {}, None))
    assert speech == ''


def test_automatic_alerts_are_short_and_never_added_to_reply_history():
    skill = _bare_skill()
    target = _Target(1, 'Mining location 47', 'Hurston', 0, 0, 0)
    asyncio.run(skill._announce_arrival(target, 999, 1000, 250))
    asyncio.run(skill._announce_arrival(target, 200, 1000, 250))
    asyncio.run(skill._announce_arrival(target, 200, 1000, 250))
    for callback, args in skill._audio_calls:
        asyncio.run(callback(*args))
    assert skill.wingman.speech_calls == [('Approaching: 999 meters.', False), ('Arrived.', False)]
    assert skill.wingman.assistant_messages == []

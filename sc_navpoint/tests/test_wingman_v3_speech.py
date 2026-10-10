"""The supported Wingman v3 speech interface keeps navigation speech queued."""
import asyncio
from types import SimpleNamespace
from test_arrival import _bare_skill


def test_v3_arrival_uses_run_in_thread_and_noninterrupting_speech():
    skill = _bare_skill()
    queued, spoken = [], []
    async def speak(text, *, interrupt=True):
        spoken.append((text, interrupt))
    skill.wingman = SimpleNamespace(
        run_in_thread=lambda fn, *args: queued.append((fn, args)),
        tts=SimpleNamespace(speak=speak),
    )
    skill._active_target = SimpleNamespace(name='Crash')
    async def arrive():
        await skill._announce_arrival(skill._active_target, 200., 1000., 250.)
        await skill._announce_arrival(skill._active_target, 200., 1000., 250.)
    asyncio.run(arrive())
    assert len(queued) == 1
    fn, args = queued[0]
    asyncio.run(fn(*args))
    assert spoken == [('Arrived.', False)]

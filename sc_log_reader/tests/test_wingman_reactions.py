import asyncio
import unittest
from unittest.mock import AsyncMock

from test_v3_integration import v3_host

from sc_log_reader.host_notifications import WingmanReactionSink, present_poll
from sc_log_reader.notifications import NotificationPolicy
from sc_log_reader.reader import Event, Instructions, Reader, bundled_bytes
from sc_log_reader.state import State


def event(kind="mission_accepted", name="Delivery"):
    return dict(
        environment="LIVE",
        generation="one",
        event_type=kind,
        data=dict(mission_name=name, mission_id=name),
        status="confirmed",
    )


class ReactionTests(unittest.IsolatedAsyncioTestCase):
    async def test_ship_channel_events_identify_player_boarding_and_leaving(self):
        instructions = Instructions.load(bundled_bytes())
        reader = Reader(instructions)
        # The named owner is not necessarily the player boarding the ship.
        for owner in ("Mallachi", "OtherPilot"):
            state = State(instructions.data["lookups"])
            state.apply(Event("user_login", {"player_name": "Mallachi"}), "login", "g")
            host = v3_host()
            sink = WingmanReactionSink(host)
            policy = NotificationPolicy({"ship"})
            for index, (action, expected) in enumerate(
                [("joined", "Player boarded ship"), ("left", "Player left ship")]
            ):
                with self.subTest(owner=owner, action=action):
                    parsed = reader.parse(
                        '<SHUDEvent> Added notification "You '
                        f"{action} channel 'Anvil C8R Pisces Rescue : {owner}'.: "
                        '" [2] to queue.'
                    )
                    rows = state.apply(parsed, f"channel-{index}", "g")
                    self.assertEqual(len(rows), 1)
                    for row in rows:
                        row.update(environment="LIVE", generation="g")
                    await present_poll(policy, sink, rows, {}, {}, now=index * 5)
                    await sink.task
                    self.assertEqual(
                        host.ai.generate.call_args.args[0],
                        f"[Game Event] {expected}: Anvil C8R Pisces Rescue",
                    )
            await sink.close()

    async def test_selected_events_enter_host_conversation_as_one_batch(self):
        host = v3_host()
        sink = WingmanReactionSink(host)
        await present_poll(
            NotificationPolicy({"mission"}),
            sink,
            [event(), event("mission_complete"), event("ship_entered")],
            {},
            {},
            now=1,
        )
        await sink.task
        host.ai.generate.assert_awaited_once()
        text = host.ai.generate.call_args.args[0]
        self.assertTrue(text.startswith("[Game Events]"))
        self.assertIn("Delivery", text)
        self.assertNotIn("Player boarded ship", text)
        self.assertNotIn("untrusted", text)
        self.assertNotIn("<observations>", text)
        self.assertNotIn("React briefly", text)

    async def test_single_event_is_only_a_short_event_message(self):
        host = v3_host()
        sink = WingmanReactionSink(host)
        await sink.send("Player location reported: Kaboos")
        await sink.task
        self.assertEqual(
            host.ai.generate.call_args.args,
            ("[Game Event] Player location reported: Kaboos",),
        )

    async def test_catchup_final_drain_and_disabled_categories_never_react(self):
        host = v3_host()
        sink = WingmanReactionSink(host)
        for before, after in [
            ({}, {"LIVE": {"catching_up": True}}),
            ({"LIVE": {"unread_bytes": 1}}, {}),
        ]:
            await present_poll(
                NotificationPolicy(), sink, [event()], before, after, now=1
            )
        await present_poll(NotificationPolicy(set()), sink, [event()], {}, {}, now=2)
        self.assertIsNone(sink.task)
        host.ai.generate.assert_not_called()

    async def test_slow_response_does_not_block_reader_or_queue_more_responses(self):
        started, release = asyncio.Event(), asyncio.Event()

        async def process(*args, **kwargs):
            started.set()
            await release.wait()

        sink = WingmanReactionSink(v3_host(process))
        self.assertEqual(await asyncio.wait_for(sink.send("first"), 0.1), 1)
        await started.wait()
        for _ in range(100):
            self.assertEqual(await sink.send("while busy"), 0)
        self.assertEqual(sink.stats["busy_drops"], 100)
        await sink.close()
        self.assertTrue(sink.task.done())
        self.assertEqual(await sink.send("after unload"), 0)

    async def test_ten_reaction_budget_requires_real_user_reset(self):
        host = v3_host()
        sink = WingmanReactionSink(host)
        for _ in range(10):
            self.assertEqual(await sink.send("event"), 1)
            await sink.task
        self.assertEqual(await sink.send("eleven"), 0)
        sink.reset_budget()
        self.assertEqual(await sink.send("after user"), 1)
        await sink.task
        self.assertEqual(host.ai.generate.await_count, 11)

    async def test_failure_and_timeout_are_observable_without_retry(self):
        host = v3_host(AsyncMock(side_effect=RuntimeError("provider")))
        sink = WingmanReactionSink(host)
        await sink.send("event")
        await sink.task
        self.assertEqual(sink.stats["failures"], 1)
        self.assertEqual(sink.stats["last_error"], "RuntimeError")

        async def blocked(*args, **kwargs):
            await asyncio.Event().wait()

        sink = WingmanReactionSink(v3_host(blocked), timeout=0.01)
        await sink.send("event")
        await sink.task
        self.assertEqual(sink.stats["timeouts"], 1)


if __name__ == "__main__":
    unittest.main()

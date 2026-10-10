import asyncio
import tempfile
import types
import unittest
from pathlib import Path

from sc_log_reader.notifications import NotificationPolicy


def event():
    return {
        "environment": "LIVE",
        "generation": "g",
        "event_type": "user_login",
        "data": {"player_name": "literal <tool>"},
    }


class NotificationTargetTests(unittest.IsolatedAsyncioTestCase):
    def test_public_no_event_purge(self):
        policy = NotificationPolicy()
        policy.offer(event(), now=0, catching_up=False)
        policy.discard_environment("LIVE")
        self.assertEqual(policy.flush(now=1), [])

    async def test_only_public_send_to_used_without_disconnected_queue(self):
        from sc_log_reader.host_notifications import LiteralGuiSink

        sent = []

        async def send_to(command, websocket):
            sent.append((command, websocket))

        manager = types.SimpleNamespace(active_connections=[], send_to=send_to)
        sink = LiteralGuiSink(manager, lambda **kw: kw, "info")
        self.assertEqual(await sink.send("literal"), 0)
        manager.active_connections = list(range(20))
        self.assertEqual(await sink.send("literal"), 8)
        self.assertEqual(len(sent), 8)
        self.assertEqual(sent[0][0]["text"], "literal")
        self.assertEqual(sink.stats["transport_successes"], 8)

    async def test_swallowed_disconnect_is_failure_and_hung_socket_bounded(self):
        from sc_log_reader.host_notifications import LiteralGuiSink

        manager = types.SimpleNamespace(active_connections=[1, 2])

        async def send_to(command, websocket):
            if websocket == 1:
                manager.active_connections.remove(1)
            else:
                await asyncio.sleep(10)

        manager.send_to = send_to
        sink = LiteralGuiSink(manager, lambda **kw: kw, "info", timeout=0.02)
        self.assertEqual(await asyncio.wait_for(sink.send("literal"), 0.2), 0)
        self.assertEqual(sink.stats["transport_failures"], 2)

    async def test_final_backlog_poll_and_empty_poll_purge(self):
        from sc_log_reader.host_notifications import present_poll

        policy = NotificationPolicy()
        policy.offer(event(), now=0, catching_up=False)
        sent = []

        async def send(text):
            sent.append(text)
            return 1

        sink = types.SimpleNamespace(send=send)
        await present_poll(
            policy,
            sink,
            [],
            {"LIVE": {"bytes_behind": 50}},
            {"LIVE": {"bytes_behind": 0}},
            now=1,
        )
        self.assertEqual(policy.flush(now=1), [])
        await present_poll(
            policy,
            sink,
            [event()],
            {"LIVE": {"bytes_behind": 50}},
            {"LIVE": {"bytes_behind": 0}},
            now=2,
        )
        self.assertEqual(sent, [])
        await present_poll(policy, sink, [event()], {"LIVE": {}}, {"LIVE": {}}, now=3)
        self.assertEqual(len(sent), 1)

    async def test_real_tailer_partial_next_line_does_not_suppress_fresh_event(self):
        from sc_log_reader.host_notifications import present_poll
        from sc_log_reader.service import Service, Tailer

        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "Game.log"
            log.write_text("")
            service = Service(Path(tmp) / "runtime")
            try:
                tailer = Tailer(service, {"LIVE": log})
                tailer.poll()
                policy = NotificationPolicy()
                sent = []

                async def send(text):
                    sent.append(text)
                    return 1

                sink = types.SimpleNamespace(send=send)
                for i in range(2):
                    with log.open("a") as stream:
                        stream.write(
                            ("\n" if i else "")
                            + f"User Login Success Handle[Player{i}]\npartial next line"
                        )
                    before = {env: dict(h) for env, h in service.live_health.items()}
                    events = tailer.poll()
                    self.assertTrue(events)
                    self.assertGreater(service.live_health["LIVE"]["bytes_behind"], 0)
                    self.assertEqual(service.live_health["LIVE"]["unread_bytes"], 0)
                    self.assertEqual(service.live_health["LIVE"]["pending_records"], 0)
                    await present_poll(
                        policy, sink, events, before, service.live_health, now=i * 5
                    )
                self.assertEqual(len(sent), 2)
            finally:
                service.close()

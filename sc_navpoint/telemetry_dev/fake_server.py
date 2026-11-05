"""Serve synthetic TelemetryStream frames on loopback, to test probe.py without the game.

Usage:
    python fake_server.py                       # 127.0.0.1:2942, 20 Hz, no auth
    python fake_server.py --port 29420 --token x  # demand "authorization: Bearer x"
"""
import argparse
import math
import time
from concurrent import futures

import grpc
from probe import load_stubs

FRAME_INTERVAL = 0.05  # 20 Hz, the game's documented default
SPEED_MPS = 120.0
TURN_DEG_PER_S = 6.0


def make_servicer(pb2, pb2_grpc, token: str | None, frames: int):
    class FakeTelemetry(pb2_grpc.GameTelemetryServiceServicer):
        def TelemetryStream(self, request, context):
            if token:
                sent = dict(context.invocation_metadata()).get("authorization")
                if sent != f"Bearer {token}":
                    context.abort(grpc.StatusCode.UNAUTHENTICATED, "missing or wrong bearer token")
            start = time.monotonic()
            for index in range(frames):
                elapsed = time.monotonic() - start
                frame = pb2.TelemetryStreamResponse()
                state = frame.vehicle.state
                state.name = "Fake Cutlass"
                state.class_name = "DRAK_Cutlass_Black"
                state.type = pb2.VEHICLE_TYPE_SPACESHIP
                inst = state.flight.instruments
                inst.speed = SPEED_MPS
                inst.heading = (TURN_DEG_PER_S * elapsed) % 360.0
                inst.altitude = 1500.0 + 50.0 * math.sin(elapsed)
                inst.vertical_speed_indicator = 50.0 * math.cos(elapsed)
                inst.g_meter.current = 1.0
                frame.actor.state.locomotion = pb2.ACTOR_LOCOMOTION_STATE_SEATED
                frame.actor.state.seat_name = "pilot_seat"
                if index == 0:
                    frame.events.events.add(type=pb2.GameEvent.GAME_EVENT_TYPE_ACTOR_ENTER_SEAT)
                yield frame
                time.sleep(FRAME_INTERVAL)

    return FakeTelemetry()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=2942)
    parser.add_argument("--token")
    parser.add_argument("--frames", type=int, default=200, help="frames per stream before it ends")
    args = parser.parse_args()

    pb2, pb2_grpc = load_stubs()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb2_grpc.add_GameTelemetryServiceServicer_to_server(make_servicer(pb2, pb2_grpc, args.token, args.frames), server)
    server.add_insecure_port(f"127.0.0.1:{args.port}")
    server.start()
    print(f"fake telemetry on 127.0.0.1:{args.port}", flush=True)
    server.wait_for_termination()


if __name__ == "__main__":
    main()

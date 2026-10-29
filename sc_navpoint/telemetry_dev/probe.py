"""Connect to Star Citizen's local gRPC telemetry stream and print what arrives.

Dev probe only, not shipped with the skill. It only reads: one TelemetryStream call to a loopback
address, nothing is sent to the game besides that request.

Usage:
    python probe.py                      # 127.0.0.1:2942, one summary line per second
    python probe.py --wait               # keep retrying until the game opens the port
    python probe.py --raw                # every frame as JSON
    python probe.py --token <bearer>     # if the server answers UNAUTHENTICATED
    python probe.py --log frames.jsonl   # also write every frame to a JSON-lines file
"""
import argparse
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, TextIO

import grpc
from google.protobuf.json_format import MessageToDict
from google.protobuf.message import Message

HERE = Path(__file__).resolve().parent
GEN_DIR = HERE / "_gen"
PROTO = HERE / "sc_telemetry.proto"
DEFAULT_ADDRESS = "127.0.0.1:2942"
RETRY_SECONDS = 2.0

# What each status code most likely means for this probe.
STATUS_HINTS = {
    grpc.StatusCode.UNAVAILABLE: "nothing is listening: the game is not running, or the gRPC client server is off",
    grpc.StatusCode.UNIMPLEMENTED: "a gRPC server answers, but GameTelemetryService is not registered on it",
    grpc.StatusCode.UNAUTHENTICATED: "the server wants a token: retry with --token",
    grpc.StatusCode.PERMISSION_DENIED: "the token was refused",
}


def load_stubs() -> tuple[ModuleType, ModuleType]:
    """Compile sc_telemetry.proto into _gen/ when it is missing or older than the proto, then import it."""
    generated = GEN_DIR / "sc_telemetry_pb2.py"
    if not generated.exists() or generated.stat().st_mtime < PROTO.stat().st_mtime:
        from grpc_tools import protoc

        GEN_DIR.mkdir(exist_ok=True)
        status = protoc.main([
            "protoc", f"-I{HERE}", f"--python_out={GEN_DIR}", f"--grpc_python_out={GEN_DIR}", str(PROTO),
        ])
        if status != 0:
            sys.exit(f"protoc failed with exit code {status}")
    sys.path.insert(0, str(GEN_DIR))
    import sc_telemetry_pb2
    import sc_telemetry_pb2_grpc

    return sc_telemetry_pb2, sc_telemetry_pb2_grpc


def enum_name(message: Message, field: str) -> str:
    """The enum value's name without its type prefix, e.g. SEATED instead of 3."""
    value = getattr(message, field)
    enum = message.DESCRIPTOR.fields_by_name[field].enum_type
    name = enum.values_by_number[value].name if value in enum.values_by_number else str(value)
    prefix = enum.values[0].name.removesuffix("UNSPECIFIED")
    return name.removeprefix(prefix)


def summary(frame: Message) -> str:
    """One line with the fields NavPoint cares about, plus which top-level frames were present."""
    parts = [",".join(f.name for f, _ in frame.ListFields()) or "(empty)"]
    if frame.HasField("vehicle"):
        state = frame.vehicle.state
        inst = state.flight.instruments
        parts.append(
            f"{state.name or state.class_name or '?'} spd={inst.speed:.1f} hdg={inst.heading:.2f} "
            f"alt={inst.altitude:.0f} ralt={inst.radar_altitude:.0f} vsi={inst.vertical_speed_indicator:.1f}"
        )
        if inst.HasField("g_meter"):
            parts.append(f"g={inst.g_meter.current:.2f}")
    if frame.HasField("actor"):
        parts.append(f"loco={enum_name(frame.actor.state, 'locomotion')} seat={frame.actor.state.seat_name!r}")
    if frame.HasField("events") and frame.events.events:
        parts.append("events=" + ",".join(enum_name(e, "type") for e in frame.events.events))
    return " | ".join(parts)


def stream_once(stub: Any, pb2: ModuleType, args: argparse.Namespace, log_file: TextIO | None) -> int:
    """Run one TelemetryStream call until it ends. Returns the number of frames received."""
    metadata = [("authorization", f"Bearer {args.token}")] if args.token else None
    frames, last_print = 0, 0.0
    for frame in stub.TelemetryStream(pb2.TelemetryStreamRequest(), metadata=metadata):
        frames += 1
        now = time.monotonic()
        as_dict = MessageToDict(frame, preserving_proto_field_name=True) if (args.raw or log_file) else None
        if log_file:
            log_file.write(json.dumps({"t": time.time(), "frame": as_dict}) + "\n")
        if args.raw:
            print(json.dumps(as_dict))
        elif now - last_print >= args.every:
            print(f"{time.strftime('%H:%M:%S')} #{frames} {summary(frame)}", flush=True)
            last_print = now
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--address", default=DEFAULT_ADDRESS)
    parser.add_argument("--token", help="Bearer token, sent as the authorization header")
    parser.add_argument("--every", type=float, default=1.0, help="seconds between summary lines")
    parser.add_argument("--raw", action="store_true", help="print every frame as JSON")
    parser.add_argument("--log", type=Path, help="append every frame to this JSON-lines file")
    parser.add_argument("--wait", action="store_true", help="retry until the server is up")
    args = parser.parse_args()

    pb2, pb2_grpc = load_stubs()
    log_file = args.log.open("a", encoding="utf-8") if args.log else None
    print(f"connecting to {args.address} (plain-text gRPC, loopback only)", flush=True)
    try:
        with grpc.insecure_channel(args.address) as channel:
            stub = pb2_grpc.GameTelemetryServiceStub(channel)
            while True:
                try:
                    frames = stream_once(stub, pb2, args, log_file)
                    print(f"stream ended by the server after {frames} frames", flush=True)
                    if not args.wait:
                        return 0
                except grpc.RpcError as error:
                    hint = STATUS_HINTS.get(error.code(), "")
                    print(f"{error.code().name}: {error.details()} {('-> ' + hint) if hint else ''}", flush=True)
                    if error.code() != grpc.StatusCode.UNAVAILABLE:
                        return 1
                if not args.wait:
                    return 1
                time.sleep(RETRY_SECONDS)
    except KeyboardInterrupt:
        return 0
    finally:
        if log_file:
            log_file.close()


if __name__ == "__main__":
    sys.exit(main())

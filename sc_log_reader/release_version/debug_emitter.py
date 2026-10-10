"""
SC_LogReader - Debug Emitter

UDP fire-and-forget emitter for the DevKit dashboard.
Sends JSON packets to localhost:7865 (devkit) and localhost:7867
(nodeview). If nothing is listening, packets are silently dropped
— zero impact on the skill.

Author: Mallachi
"""

import json
import socket
from datetime import datetime
from typing import Any


_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_ADDRS = [("127.0.0.1", 7865), ("127.0.0.1", 7867)]


def emit(layer: str, event_type: str, data: dict[str, Any]) -> None:
    """Send a debug event via UDP. Silent no-op if nothing is listening."""
    try:
        payload = json.dumps(
            {
                "layer": layer,
                "type": event_type,
                "data": _make_serializable(data),
                "ts": datetime.now().isoformat(timespec="milliseconds"),
            },
        ).encode()
        for addr in _ADDRS:
            _sock.sendto(payload, addr)
    except OSError:
        pass


def _make_serializable(obj: Any) -> Any:
    """Convert non-serializable types for JSON encoding."""
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_serializable(i) for i in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, set):
        return list(obj)
    return obj

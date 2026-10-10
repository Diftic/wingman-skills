"""
SC_LogReader DevKit NodeView - UDP Bridge

Listens for UDP debug packets from the SC_LogReader skill and
broadcasts them to connected SSE clients.

Author: Mallachi
"""

import asyncio
import json
import logging
import socket
import threading
from typing import Any


logger = logging.getLogger(__name__)

UDP_PORT = 7867
MAX_PACKET_SIZE = 65535


class DebugBridge:
    """Receives UDP debug packets and fans out to async queues."""

    def __init__(self) -> None:
        self._clients: list[asyncio.Queue[dict[str, Any]]] = []
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        # Snapshot of latest states for new client catchup
        self._current_states: dict[str, Any] = {}
        self._states_lock = threading.Lock()

    def start(self) -> None:
        """Start the UDP listener thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        logger.info("Debug bridge listening on UDP port %d", UDP_PORT)

    def stop(self) -> None:
        """Stop the UDP listener."""
        self._running = False
        if self._sock:
            self._sock.close()

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        """Create a new SSE client queue."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
        with self._lock:
            self._clients.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove an SSE client queue."""
        with self._lock:
            if queue in self._clients:
                self._clients.remove(queue)

    def get_current_states(self) -> dict[str, Any]:
        """Get snapshot of all current states for initial client load."""
        with self._states_lock:
            return self._current_states.copy()

    def _listen(self) -> None:
        """UDP listener loop."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", UDP_PORT))
        self._sock.settimeout(1.0)

        while self._running:
            try:
                data, _ = self._sock.recvfrom(MAX_PACKET_SIZE)
                packet = json.loads(data.decode())
                self._process_packet(packet)
            except socket.timeout:
                continue
            except json.JSONDecodeError:
                logger.warning("Bridge: malformed JSON packet")
            except OSError:
                if self._running:
                    logger.exception("Bridge: socket error")
                break

        self._sock.close()

    def _process_packet(self, packet: dict[str, Any]) -> None:
        """Process a received packet and broadcast to clients."""
        # Track state snapshot for new client catchup
        if packet.get("type") == "state_change":
            data = packet.get("data", {})
            key = data.get("key")
            if key:
                with self._states_lock:
                    self._current_states[key] = data.get("new")

        # Broadcast to all connected SSE clients
        with self._lock:
            dead_clients = []
            for queue in self._clients:
                try:
                    queue.put_nowait(packet)
                except asyncio.QueueFull:
                    dead_clients.append(queue)
            for q in dead_clients:
                self._clients.remove(q)

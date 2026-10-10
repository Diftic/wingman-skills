"""
SC_LogReader DevKit - Entry Point

Standalone debug dashboard for SC_LogReader.
Run this separately from Wingman AI to visualize the parsing pipeline.

Usage:
    python devkit.py

Then open http://localhost:7864 in a browser or tablet.

Author: Mallachi
"""

import logging
import webbrowser

import uvicorn

from bridge import DebugBridge
from server import create_app


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

PORT = 7864


def main() -> None:
    """Start the DevKit dashboard."""
    bridge = DebugBridge()
    bridge.start()

    app = create_app(bridge)

    print("\n  SC_LogReader DevKit")
    print(f"  Dashboard: http://localhost:{PORT}")
    print(f"  UDP listener: port {bridge._sock and 7865}")
    print("  Waiting for SC_LogReader debug packets...\n")

    webbrowser.open(f"http://localhost:{PORT}")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

"""
SC_LogReader DevKit NodeView - Entry Point

Node-based diagram view of the SC_LogReader parsing pipeline.
Run this separately from Wingman AI to visualize data flow.

Usage:
    python Devkit_node.py

Then open http://localhost:7866 in a browser or tablet.

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

PORT = 7866


def main() -> None:
    """Start the DevKit NodeView dashboard."""
    bridge = DebugBridge()
    bridge.start()

    app = create_app(bridge)

    print("\n  SC_LogReader DevKit — NodeView")
    print(f"  Dashboard: http://localhost:{PORT}")
    print(f"  UDP listener: port {bridge._sock and 7867}")
    print("  Waiting for SC_LogReader debug packets...\n")

    webbrowser.open(f"http://localhost:{PORT}")

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

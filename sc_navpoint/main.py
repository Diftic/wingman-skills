"""
main.py — SC NavPoint skill for Wingman AI
Author: Mallachi
Version: 4.8.0.0 (qualified against Star Citizen 4.8.0)

Mark and navigate to custom waypoints in Star Citizen using r_displayinfo 4 OCR.
Voice commands to drop, list, and navigate to named positions in space.
"""

import asyncio
import json
import logging
import os
import sys
from typing import TYPE_CHECKING

from api.enums import LogType
from api.interface import WingmanInitializationError
from skills.skill_base import Skill, tool

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import pydirectinput  # noqa: E402

from database import NavPoint, NavPointDatabase  # noqa: E402
from navigation import calculate_bearing, format_distance  # noqa: E402
from scanner import NavPointScanner  # noqa: E402

if TYPE_CHECKING:
    from wingmen.open_ai_wingman import OpenAiWingman


logger = logging.getLogger(__name__)


class SC_NavPoint(Skill):
    # Versions mirror the Star Citizen patch this skill is qualified against.
    # Within-patch updates append a dotted suffix (4.8.0.1, 4.8.0.2, …).
    # See skills/Versioning.md.
    VERSION = "4.8.0.0"
    SC_TARGET_VERSION = "4.8.0"

    def __init__(self, config, settings, wingman) -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)
        self._db: NavPointDatabase | None = None
        self._scanner: NavPointScanner | None = None
        self._ui_server = None
        self._ui_window = None
        self._active_target: NavPoint | None = None
        self._nav_task: asyncio.Task | None = None

    async def validate(self) -> list[WingmanInitializationError]:
        errors = await super().validate()
        self.retrieve_custom_property_value("display", errors)
        return errors

    def _get_display(self) -> int:
        errors: list[WingmanInitializationError] = []
        val = self.retrieve_custom_property_value("display", errors)
        return int(val) if val else 1

    async def prepare(self) -> None:
        await super().prepare()

        db_dir = self.get_generated_files_dir()
        self._db = NavPointDatabase(db_dir)
        self._scanner = NavPointScanner()

        try:
            from navpoint_ui.app import NavPointServer  # noqa: E402
            from navpoint_ui.window import NavPointWindow  # noqa: E402

            self._ui_server = NavPointServer(db=self._db, port=7869)
            self._ui_server.start()
            self._ui_window = NavPointWindow(url=self._ui_server.url)
            self.printr.print(
                f"NavPoint HUD available at {self._ui_server.url}",
                color=LogType.POSITIVE,
                server_only=True,
            )
        except ImportError as e:
            logger.warning("NavPoint HUD unavailable: %s", e)

    async def unload(self) -> None:
        self._stop_nav_polling()
        if self._ui_window:
            try:
                self._ui_window.close()
            except OSError:
                pass
            self._ui_window = None
        if self._ui_server:
            try:
                self._ui_server.stop()
            except OSError:
                pass
            self._ui_server = None
        await super().unload()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    async def _capture_position(self) -> dict | None:
        """Capture current screen and extract position data via Vision AI.

        Uses two images per call: full screenshot (context) + top-right crop (detail).
        This dual-image approach significantly improves accuracy on small overlay text.
        """
        if not self._scanner:
            return None
        context_b64, detail_b64 = self._scanner.capture_screen_b64(self._get_display())
        messages = self._scanner.build_extraction_messages(context_b64, detail_b64)
        completion = await self.llm_call(messages)
        return self._scanner.parse_completion(completion)

    # ------------------------------------------------------------------ #
    # Auto-polling
    # ------------------------------------------------------------------ #

    _POLL_INTERVAL_DEFAULT = 5  # fallback if custom property not set

    def _get_poll_interval(self) -> int:
        """Read poll_interval custom property (clamped to 1–10s)."""
        errors: list[WingmanInitializationError] = []
        val = self.retrieve_custom_property_value("poll_interval", errors)
        if val is None:
            return self._POLL_INTERVAL_DEFAULT
        try:
            return max(1, min(10, int(val)))
        except (TypeError, ValueError):
            return self._POLL_INTERVAL_DEFAULT

    def _start_nav_polling(self) -> None:
        """Start the 5-second background position polling loop."""
        self._stop_nav_polling()
        interval = self._get_poll_interval()
        self._nav_task = asyncio.create_task(self._nav_polling_loop(interval))
        logger.info("NavPoint auto-polling started (every %ds)", interval)
        self.printr.print(
            f"[NavPoint] Auto-position tracking started — updating every {interval}s",
            color=LogType.INFO,
            server_only=True,
        )

    def _stop_nav_polling(self) -> None:
        """Cancel the background polling task if running."""
        if self._nav_task and not self._nav_task.done():
            self._nav_task.cancel()
            logger.info("NavPoint auto-polling stopped")
        self._nav_task = None

    async def _nav_polling_loop(self, interval: int) -> None:
        """Background loop: capture position every 5s while a nav target is active."""
        try:
            while self._active_target is not None:
                await asyncio.sleep(interval)

                if self._active_target is None:
                    break

                try:
                    pos_data = await self._capture_position()
                except Exception as e:
                    logger.debug("Nav poll: capture failed: %s", e)
                    continue

                if not pos_data or not all(k in pos_data for k in ("x", "y", "z")):
                    logger.debug("Nav poll: no position extracted")
                    continue

                if self._ui_server:
                    self._ui_server.set_position(pos_data)

                target = self._active_target
                bearing = calculate_bearing(
                    from_pos=(pos_data["x"], pos_data["y"], pos_data["z"]),
                    to_pos=(target.x, target.y, target.z),
                    current_heading=pos_data.get("heading", 0.0),
                )
                logger.debug(
                    "Nav poll update: %s — %s, %s",
                    target.name,
                    bearing["turn_instruction"],
                    format_distance(bearing["distance_km"]),
                )
        except asyncio.CancelledError:
            pass  # Normal shutdown

    def _navpoint_to_result_dict(self, np: NavPoint) -> dict:
        return {
            "id": np.id,
            "name": np.name,
            "server_id": np.server_id,
            "x": np.x,
            "y": np.y,
            "z": np.z,
            "planet": np.planet,
            "moon": np.moon,
            "system": np.system,
            "zone": np.zone,
            "timestamp": np.timestamp,
        }

    def _build_guidance(self, target: NavPoint, bearing: dict) -> str:
        """Build a concise navigation guidance string."""
        dist_str = format_distance(bearing["distance_km"])
        turn = bearing["turn_instruction"]
        elev = bearing["elevation_instruction"]
        parts = [dist_str, turn]
        if elev != "Level":
            parts.append(elev)
        return " | ".join(parts)

    def _build_approach_guidance(self, target: NavPoint) -> str:
        """High-level guidance when current position is unknown."""
        steps = []
        if target.system:
            steps.append(f"System: {target.system}")
        if target.planet:
            steps.append(f"Go to {target.planet}")
        if target.moon:
            steps.append(f"Moon: {target.moon}")
        if target.zone and target.zone not in (target.planet, target.moon):
            steps.append(f"Zone: {target.zone}")
        steps.append(f"Coords: {target.x:.0f}, {target.y:.0f}, {target.z:.0f}")
        return " → ".join(steps)

    async def _send_console_command(self, command: str) -> None:
        """Open the SC console, type a command, press enter, close the console.

        Sequence: tilde → wait 0.5s → typewrite → enter → wait 0.2s → tilde.
        All pydirectinput calls run in a thread so the event loop stays unblocked.
        Star Citizen must be the focused window when this is called.
        """
        await asyncio.to_thread(pydirectinput.press, "`")   # open console
        await asyncio.sleep(0.5)
        await asyncio.to_thread(pydirectinput.unicode_typewrite, command)
        await asyncio.to_thread(pydirectinput.press, "enter")
        await asyncio.sleep(0.2)
        await asyncio.to_thread(pydirectinput.press, "`")   # close console

    # ------------------------------------------------------------------ #
    # Tools
    # ------------------------------------------------------------------ #

    @tool(
        description=(
            "Enable the r_displayinfo 4 position overlay in Star Citizen. "
            "Types the console command directly into the game. "
            "Star Citizen must be the active window. "
            "Call when player says 'enable position overlay', 'activate r_displayinfo', "
            "'turn on position tracking', 'enable debug overlay', or similar."
        ),
        wait_response=True,
    )
    async def enable_displayinfo(self) -> str:
        """Open the SC console and run: r_displayinfo 4"""
        try:
            await self._send_console_command("r_displayinfo 4")
        except Exception as e:
            return json.dumps({"error": f"Failed to send console command: {e}"})
        return json.dumps({
            "success": True,
            "message": "r_displayinfo 4 activated. Position overlay is now visible.",
        })

    @tool(
        description=(
            "Disable the r_displayinfo overlay in Star Citizen. "
            "Types the console command directly into the game. "
            "Star Citizen must be the active window. "
            "Call when player says 'disable position overlay', 'deactivate r_displayinfo', "
            "'hide debug overlay', 'turn off position tracking', or similar."
        ),
        wait_response=True,
    )
    async def disable_displayinfo(self) -> str:
        """Open the SC console and run: r_displayinfo 0"""
        try:
            await self._send_console_command("r_displayinfo 0")
        except Exception as e:
            return json.dumps({"error": f"Failed to send console command: {e}"})
        return json.dumps({
            "success": True,
            "message": "r_displayinfo 0 — position overlay hidden.",
        })

    @tool(
        description=(
            "Mark the current in-game location as a named waypoint. "
            "Captures and analyzes the screen to extract coordinates from the r_displayinfo overlay. "
            "Call when player says 'mark location', 'drop waypoint', 'save position', "
            "'place nav marker', 'drop a pin', or similar phrases. "
            "After saving, report the location info and ask for a name if not provided."
        ),
        wait_response=True,
    )
    async def mark_location(self, name: str = "") -> str:
        """
        Mark current position as a named waypoint.

        Args:
            name: Name for the waypoint. Leave empty to use a default name like 'Location 1'.
        """
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        pos_data = await self._capture_position()
        if not pos_data:
            return json.dumps({
                "error": "Could not extract position from screen.",
                "hint": (
                    "Make sure r_displayinfo 4 is active. "
                    "Open the Star Citizen console with F1 and type: r_displayinfo 4"
                ),
            })

        if not name:
            count = self._db.count_navpoints()
            name = f"Location {count + 1}"

        navpoint = self._db.add_navpoint(
            name=name,
            server_id=pos_data.get("server_id", ""),
            x=pos_data["x"],
            y=pos_data["y"],
            z=pos_data["z"],
            planet=pos_data.get("planet", ""),
            moon=pos_data.get("moon", ""),
            system=pos_data.get("system", ""),
            zone=pos_data.get("zone", ""),
            heading=pos_data.get("heading", 0.0),
        )

        location_label = (
            pos_data.get("zone")
            or pos_data.get("moon")
            or pos_data.get("planet")
            or pos_data.get("system")
            or "unknown location"
        )

        # Notify the HUD
        if self._ui_server:
            self._ui_server.notify_update()

        return json.dumps({
            "success": True,
            "navpoint": self._navpoint_to_result_dict(navpoint),
            "location_label": location_label,
            "message": f"Waypoint '{name}' saved at {location_label}.",
            "coordinates": f"X={navpoint.x:.0f}  Y={navpoint.y:.0f}  Z={navpoint.z:.0f}",
            "ask_for_name": name.startswith("Location "),
        })

    @tool(
        description=(
            "Open the NavPoint HUD in the browser. Shows all saved waypoints and the navigation compass. "
            "Call when player says 'show navigation HUD', 'open waypoints', 'show nav HUD', "
            "'open navpoint', or similar."
        )
    )
    def show_navpoint_hud(self) -> str:
        """Open the NavPoint HUD in the default browser."""
        if not self._ui_window:
            return json.dumps({"error": "NavPoint HUD not available — missing dependencies"})
        self._ui_window.open()
        url = self._ui_server.url if self._ui_server else ""
        return json.dumps({"success": True, "url": url, "message": "NavPoint HUD opened."})

    @tool(
        description=(
            "List all stored navigation waypoints. Can filter by server ID. "
            "Call when player says 'list my waypoints', 'show saved locations', "
            "'what waypoints do I have', or similar."
        )
    )
    def list_navpoints(self, server_id: str = "") -> str:
        """
        List stored waypoints.

        Args:
            server_id: Filter by server ID. Leave empty to list all servers.
        """
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        navpoints = self._db.get_navpoints(server_id=server_id or None)
        if not navpoints:
            msg = "No waypoints saved"
            if server_id:
                msg += f" for server {server_id}"
            return json.dumps({"navpoints": [], "message": msg})

        return json.dumps({
            "navpoints": [self._navpoint_to_result_dict(n) for n in navpoints],
            "count": len(navpoints),
            "servers": self._db.get_distinct_servers(),
        })

    @tool(
        description=(
            "Set a stored waypoint as the active navigation target and show direction guidance. "
            "Also captures current position to calculate bearing if possible. "
            "Call when player says 'navigate to [name]', 'guide me to [name]', "
            "'how do I get to [name]', 'set destination to [name]', or similar."
        ),
        wait_response=True,
    )
    async def navigate_to(self, name: str) -> str:
        """
        Set a stored waypoint as the active navigation target.

        Args:
            name: Name (or partial name) of the waypoint to navigate to.
        """
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        navpoint = self._db.find_navpoint_by_name(name)
        if not navpoint:
            matches = self._db.search_navpoints(name)
            if not matches:
                return json.dumps({
                    "error": f"Waypoint '{name}' not found.",
                    "hint": "Use 'list waypoints' to see all saved locations.",
                })
            navpoint = matches[0]

        self._active_target = navpoint

        if self._ui_server:
            self._ui_server.set_active_target(navpoint)

        # Try to capture current position for immediate bearing
        pos_data = await self._capture_position()

        result: dict = {
            "success": True,
            "target": self._navpoint_to_result_dict(navpoint),
        }

        if pos_data and all(k in pos_data for k in ("x", "y", "z")):
            bearing = calculate_bearing(
                from_pos=(pos_data["x"], pos_data["y"], pos_data["z"]),
                to_pos=(navpoint.x, navpoint.y, navpoint.z),
                current_heading=pos_data.get("heading", 0.0),
            )
            result["bearing"] = bearing
            result["guidance"] = self._build_guidance(navpoint, bearing)
            if self._ui_server:
                self._ui_server.set_position(pos_data)
        else:
            result["guidance"] = self._build_approach_guidance(navpoint)

        # Start continuous 5s position tracking
        self._start_nav_polling()
        result["tracking"] = "Auto-tracking active — position updates every 5s."

        return json.dumps(result)

    @tool(
        description=(
            "Refresh current position and update bearing to the active navigation target. "
            "Call when player says 'update position', 'refresh bearing', 'where am I', "
            "'how far', or 'how far to target'."
        ),
        wait_response=True,
    )
    async def update_position(self) -> str:
        """Capture current position and refresh navigation bearing."""
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        pos_data = await self._capture_position()
        if not pos_data:
            return json.dumps({
                "error": "Could not read position. Ensure r_displayinfo 4 is active in-game.",
            })

        result: dict = {
            "position": {
                "x": pos_data.get("x"),
                "y": pos_data.get("y"),
                "z": pos_data.get("z"),
                "zone": pos_data.get("zone", ""),
                "planet": pos_data.get("planet", ""),
                "heading": pos_data.get("heading"),
            }
        }

        if self._active_target and all(k in pos_data for k in ("x", "y", "z")):
            np = self._active_target
            bearing = calculate_bearing(
                from_pos=(pos_data["x"], pos_data["y"], pos_data["z"]),
                to_pos=(np.x, np.y, np.z),
                current_heading=pos_data.get("heading", 0.0),
            )
            result["active_target"] = np.name
            result["bearing"] = bearing
            result["guidance"] = self._build_guidance(np, bearing)

            if self._ui_server:
                self._ui_server.set_position(pos_data)

        return json.dumps(result)

    @tool(
        description=(
            "Stop active navigation and cancel auto-tracking. "
            "Call when player says 'stop navigation', 'cancel navigation', 'stop tracking', "
            "'stop following me', or 'clear destination'."
        )
    )
    def stop_navigation(self) -> str:
        """Stop the active navigation target and cancel auto-tracking."""
        if not self._active_target:
            return json.dumps({"message": "No active navigation target."})

        name = self._active_target.name
        self._active_target = None
        self._stop_nav_polling()

        if self._ui_server:
            self._ui_server.set_active_target(None)

        return json.dumps({
            "success": True,
            "message": f"Navigation to '{name}' stopped. Auto-tracking cancelled.",
        })

    @tool(
        description=(
            "Delete a saved waypoint by name. "
            "Call when player says 'delete waypoint [name]', 'remove [name]', "
            "'delete location [name]', or similar."
        )
    )
    def delete_navpoint(self, name: str) -> str:
        """
        Delete a stored waypoint.

        Args:
            name: Exact or partial name of the waypoint to delete.
        """
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        navpoint = self._db.find_navpoint_by_name(name)
        if not navpoint:
            matches = self._db.search_navpoints(name)
            if not matches:
                return json.dumps({"error": f"Waypoint '{name}' not found."})
            navpoint = matches[0]

        self._db.delete_navpoint(navpoint.id)
        if self._active_target and self._active_target.id == navpoint.id:
            self._active_target = None
            self._stop_nav_polling()
            if self._ui_server:
                self._ui_server.set_active_target(None)

        if self._ui_server:
            self._ui_server.notify_update()

        return json.dumps({"success": True, "message": f"Waypoint '{navpoint.name}' deleted."})

    @tool(
        description=(
            "Rename a stored waypoint. "
            "Call when player says 'rename [old] to [new]', 'name this waypoint [name]', "
            "'call it [name]', or 'label this location [name]'."
        )
    )
    def rename_navpoint(self, old_name: str, new_name: str) -> str:
        """
        Rename a stored waypoint.

        Args:
            old_name: Current name of the waypoint.
            new_name: New name to assign.
        """
        if not self._db:
            return json.dumps({"error": "NavPoint skill not initialized"})

        navpoint = self._db.find_navpoint_by_name(old_name)
        if not navpoint:
            matches = self._db.search_navpoints(old_name)
            if not matches:
                return json.dumps({"error": f"Waypoint '{old_name}' not found."})
            navpoint = matches[0]

        self._db.rename_navpoint(navpoint.id, new_name)
        if self._active_target and self._active_target.id == navpoint.id:
            self._active_target = self._db.find_navpoint_by_id(navpoint.id)

        if self._ui_server:
            self._ui_server.notify_update()

        return json.dumps({
            "success": True,
            "message": f"Waypoint renamed from '{navpoint.name}' to '{new_name}'.",
        })

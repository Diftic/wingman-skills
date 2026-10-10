"""
SC_LogReader - Layer 3: Log Parser

Reads Star Citizen Game.log and translates log lines into atomic states.
Can run standalone or be imported by Layer 2.

Author: Mallachi
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from atomic_io import atomic_write_text
from debug_emitter import emit as _debug_emit
from location_names import get_location_name, get_location_system


logger = logging.getLogger(__name__)

# Ship manufacturer prefixes used to detect and clean ship channel names
SHIP_MANUFACTURER_PREFIXES = (
    "AEGS_",
    "ANVL_",
    "ORIG_",
    "CRUS_",
    "DRAK_",
    "MISC_",
    "RSI_",
    "ARGO_",
    "BANU_",
    "CNOU_",
    "ESPR_",
    "GAMA_",
    "KRIG_",
    "TMBL_",
    "VNCL_",
    "XIAN_",
    "XNAA_",
)

# Human-readable manufacturer names for ship channel detection.
# SC sometimes uses "Aegis Avenger Titan : Player" instead of
# "@vehicle_NameAEGS_Avenger_Titan : Player".
SHIP_MANUFACTURER_NAMES = (
    "Aegis",
    "Anvil",
    "Origin",
    "Crusader",
    "Drake",
    "MISC",
    "RSI",
    "Argo",
    "Banu",
    "Consolidated",
    "Esperia",
    "Gatac",
    "Kruger",
    "Tumbril",
    "Vanduul",
    "Aopoa",
)

# Lowercased manufacturer identifiers, log prefix codes (without the trailing
# underscore) plus human-readable names, used to strip manufacturer tokens when
# comparing a log entity class (e.g. "DRAK_Clipper") against a channel-derived
# ship name (e.g. "Drake Clipper" or "Clipper") so both reduce to the same model
# token set.
_MANUFACTURER_TOKENS: frozenset[str] = frozenset(
    {prefix.rstrip("_").lower() for prefix in SHIP_MANUFACTURER_PREFIXES}
    | {name.lower() for name in SHIP_MANUFACTURER_NAMES}
)


# Ports that carry no gameplay or economy significance — purely cosmetic/identity.
# AttachmentReceived events on these ports are silently discarded.
_COSMETIC_PORTS: frozenset[str] = frozenset({
    "Teeth_ItemPort",
    "Eyes_ItemPort",
    "Hair_ItemPort",
    "Eyebrow_ItemPort",
    "Eyelashes_ItemPort",
    "Lens_ItemPort",
    "Eyedetail_ItemPort",
    "Head_ItemPort",
    "Universal_Scalp_ItemPort",
    "universal_necksock",
    "universal_necksock_undersuit",
    "legacy_mobiglas_screen_attach",
    "mobiglas_screen_attach",
    "mobiglas_attach",
    "Body_ItemPort",         # Base body model slot
    "Beard_ItemPort",
    "Piercings_Eyebrows_ItemPort",
    "Piercings_R_Ear_ItemPort",
    "Piercings_L_Ear_ItemPort",
    "Piercings_Nose_ItemPort",
    "Piercings_L_Eye_ItemPort",
    "Piercings_R_Eye_ItemPort",
    "Tattoo_ItemPort",
    "Scar_ItemPort",
})


@dataclass
class LogEvent:
    """Represents a parsed log event with type, timestamp, and extracted data."""

    event_type: str
    timestamp: datetime
    raw_line: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "raw_line": self.raw_line,
            "data": self.data,
        }


class StateStore:
    """Thread-safe key-value store for atomic states with change notifications."""

    def __init__(self) -> None:
        self._state: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[str, Any, Any], None]] = []

    def set(self, key: str, value: Any) -> bool:
        """Set a state value. Returns True if value changed."""
        with self._lock:
            old_value = self._state.get(key)
            if old_value == value:
                return False
            self._state[key] = value

        _debug_emit(
            "parser",
            "state_change",
            {
                "key": key,
                "old": old_value,
                "new": value,
            },
        )

        # Snapshot outside lock to prevent deadlocks while iterating
        with self._lock:
            callbacks = list(self._subscribers)
        for callback in callbacks:
            try:
                callback(key, old_value, value)
            except Exception:
                logger.exception("Error in state change callback")

        return True

    def get(self, key: str, default: Any = None) -> Any:
        """Get a state value."""
        with self._lock:
            return self._state.get(key, default)

    def get_all(self) -> dict[str, Any]:
        """Get a copy of all states."""
        with self._lock:
            return self._state.copy()

    def subscribe(self, callback: Callable[[str, Any, Any], None]) -> None:
        """Subscribe to state changes. Callback receives (key, old_value, new_value)."""
        with self._lock:
            self._subscribers.append(callback)

    def emit_full_state(self) -> None:
        """Broadcast all current states via debug emitter.

        Allows DevKit dashboards started after the parser to receive
        the full current state without waiting for changes.
        """
        with self._lock:
            snapshot = self._state.copy()
        for key, value in snapshot.items():
            _debug_emit(
                "parser",
                "state_change",
                {"key": key, "old": None, "new": value},
            )

    def clear(self) -> None:
        """Clear all states."""
        with self._lock:
            self._state.clear()

    def load_dict(self, data: dict[str, Any]) -> None:
        """Bulk-load state without triggering change notifications.

        Used for restoring persisted state on startup.
        """
        with self._lock:
            self._state.update(data)


class LogParser:
    """
    Reads Star Citizen Game.log and produces atomic states.

    Can run standalone for debugging or be controlled by Layer 2.
    """

    def __init__(self, log_path: str | Path) -> None:
        self._log_path = Path(log_path)
        self._state_store = StateStore()
        self._event_subscribers: list[Callable[[LogEvent], None]] = []
        self._event_subscribers_lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._file_position = 0

        # File output (optional)
        self._file_output_enabled = False
        self._file_output_path: Path | None = None
        self._event_history: list[dict[str, Any]] = []

        # Deduplication: suppress repeated session_start during loading screens
        self._last_session_geid: str | None = None

        # Multi-line notification accumulation: "You sent PlayerName:" spans two lines
        self._pending_money_sent: str | None = None

        # Cached from _scan_log_startup: last session_start timestamp in the log
        self._last_session_ts: datetime | None = None

        # Whether _scan_log_startup() has been run (may leave _last_session_ts None)
        self._startup_scanned: bool = False

        # Catch-up: replay from last login trigger to current EOF
        self._catching_up = False
        self._on_catchup_complete: Callable[[], None] | None = None

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def prepare(self) -> None:
        """Pre-scan the log file to find the replay start position and last session.

        Call this before ``start()`` when the results are needed before the
        monitor thread launches (e.g. to detect a new session and clear stale
        state).  ``start()`` will use the cached results and skip a second scan.

        Safe to call multiple times — only scans once.
        """
        if self._startup_scanned:
            return
        self._startup_scanned = True
        login_pos, self._last_session_ts = self._scan_log_startup()
        if login_pos is not None:
            self._file_position = login_pos
            self._catching_up = True
            logger.info(
                "Prepared: found session login at byte %d", login_pos
            )
        elif self._log_path.exists():
            self._file_position = self._log_path.stat().st_size
            logger.info("Prepared: no login trigger — will tail from EOF")

    def start(self) -> None:
        """Start monitoring the log file in a background thread.

        Scans for the last ``User Login Success`` line and replays from
        that point so the parser catches up on the current session even
        if the game has been running for a while.  When no login trigger
        is found the parser falls back to tailing from EOF.

        If ``prepare()`` was already called the scan is skipped.
        """
        if self._running:
            logger.warning("LogParser already running")
            return

        if not self._log_path.exists():
            raise FileNotFoundError(f"Log file not found: {self._log_path}")

        self._running = True

        # Use cached scan result if prepare() was called; otherwise scan now
        if not self._startup_scanned:
            self._startup_scanned = True
            login_pos, self._last_session_ts = self._scan_log_startup()
        else:
            login_pos = self._file_position if self._catching_up else None

        if login_pos is not None:
            self._file_position = login_pos
            self._catching_up = True
            logger.info(
                "Found session login at byte %d — replaying from there",
                login_pos,
            )
        else:
            self._file_position = self._log_path.stat().st_size
            logger.info("No login trigger found — tailing from EOF")

        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("LogParser started monitoring: %s", self._log_path)

    def stop(self) -> None:
        """Stop monitoring the log file."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._flush_file_output()
        logger.info("LogParser stopped")

    def subscribe(self, callback: Callable[[LogEvent], None]) -> None:
        """Subscribe to new log events."""
        with self._event_subscribers_lock:
            self._event_subscribers.append(callback)

    def subscribe_state(self, callback: Callable[[str, Any, Any], None]) -> None:
        """Subscribe to state changes. Callback receives (key, old_value, new_value)."""
        self._state_store.subscribe(callback)

    def get_state(self, key: str | None = None) -> dict[str, Any] | Any:
        """Get current state. If key provided, returns that value; else returns all."""
        if key is None:
            return self._state_store.get_all()
        return self._state_store.get(key)

    def save_state(self) -> dict[str, Any]:
        """Return current state as a serializable dict for persistence."""
        state = self._state_store.get_all()
        state["_last_session_geid"] = self._last_session_geid
        return state

    def load_state(self, state: dict[str, Any]) -> None:
        """Restore state silently without triggering change notifications."""
        self._last_session_geid = state.pop("_last_session_geid", None)
        self._state_store.load_dict(state)

    def clear_state(self, key: str) -> None:
        """Clear a specific state key (sets to None, fires notification)."""
        self._state_store.set(key, None)

    def is_running(self) -> bool:
        """Check if the parser is currently monitoring."""
        return self._running

    def enable_file_output(self, path: str | Path) -> None:
        """Enable JSON file output for debugging."""
        self._file_output_path = Path(path)
        self._file_output_enabled = True
        logger.info("File output enabled: %s", self._file_output_path)

    def disable_file_output(self) -> None:
        """Disable JSON file output."""
        self._flush_file_output()
        self._file_output_enabled = False
        self._file_output_path = None

    # -------------------------------------------------------------------------
    # Background Monitoring
    # -------------------------------------------------------------------------

    _STATE_BROADCAST_INTERVAL = 30.0  # seconds between full state broadcasts

    def _monitor_loop(self) -> None:
        """Main loop that tails the log file."""
        last_broadcast = 0.0
        while self._running:
            try:
                self._check_for_new_lines()
            except Exception:
                logger.exception("Error reading log file")

            # Periodic state broadcast for DevKit dashboards started later
            now = time.monotonic()
            if now - last_broadcast >= self._STATE_BROADCAST_INTERVAL:
                self._state_store.emit_full_state()
                last_broadcast = now

            time.sleep(0.1)  # 100ms polling interval

    def _scan_log_startup(self) -> tuple[int | None, datetime | None]:
        """Single-pass scan for the last login position and last session timestamp.

        Returns ``(login_byte_pos, last_session_timestamp)``.  Both may be None
        if the log does not exist or contains no relevant lines.

        Called once before the monitor thread starts so the results can be
        shared with the skill layer (avoids a second full-file scan there).
        """
        if not self._log_path.exists():
            return None, None

        last_pos: int | None = None
        last_session_ts: datetime | None = None
        ts_re = re.compile(r"<(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)>")

        with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
            while True:
                line_start = f.tell()
                line = f.readline()
                if not line:
                    break
                if "User Login Success" in line:
                    last_pos = line_start
                if "AccountLoginCharacterStatus_Character" in line:
                    m = ts_re.search(line)
                    if m:
                        try:
                            last_session_ts = datetime.fromisoformat(
                                m.group(1).rstrip("Z")
                            )
                        except ValueError:
                            pass

        return last_pos, last_session_ts

    @property
    def last_session_timestamp(self) -> datetime | None:
        """Return the last session timestamp found during startup scan, if any."""
        return self._last_session_ts

    def _check_for_new_lines(self) -> None:
        """Read new lines from log file since last position."""
        if not self._log_path.exists():
            return

        current_size = self._log_path.stat().st_size

        # File was truncated/rotated
        if current_size < self._file_position:
            self._file_position = 0

        if current_size == self._file_position:
            return

        with open(self._log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(self._file_position)
            while True:
                line = f.readline()
                if not line:
                    break
                self._file_position = f.tell()
                if line.strip():
                    self._process_line(line)

        # After processing all available lines, transition from catch-up to live
        if self._catching_up:
            self._catching_up = False
            logger.info("Catch-up complete — now tailing live")
            # Broadcast full state so any listening DevKit gets current snapshot
            self._state_store.emit_full_state()
            if self._on_catchup_complete:
                try:
                    self._on_catchup_complete()
                except Exception:
                    logger.exception("Error in catch-up complete callback")

    def _process_line(self, line: str) -> None:
        """Process a single log line."""
        # Handle money_sent two-line notification (amount appears on the next log line)
        if self._pending_money_sent is not None:
            amount_match = re.search(r"([\d,]+)\s+aUEC", line)
            if amount_match:
                event = LogEvent(
                    event_type="money_sent",
                    timestamp=self._extract_timestamp(line),
                    raw_line=line,
                    data={
                        "recipient": self._pending_money_sent,
                        "amount": amount_match.group(1).replace(",", ""),
                    },
                )
                self._pending_money_sent = None
            else:
                # Not the continuation line — discard pending, parse normally
                self._pending_money_sent = None
                event = self._parse_line(line)
        else:
            event = self._parse_line(line)

        if event is None:
            return

        # Intercept partial money_sent — store recipient and wait for amount line
        if event.event_type == "_money_sent_partial":
            self._pending_money_sent = event.data.get("recipient", "")
            return

        # Suppress repeated session_start during loading screens
        if event.event_type == "session_start":
            geid = event.data.get("player_geid")
            if geid and geid == self._last_session_geid:
                return
            self._last_session_geid = geid

        _debug_emit(
            "parser",
            "raw_event",
            {
                "event_type": event.event_type,
                "timestamp": event.timestamp.isoformat(),
                "data": event.data,
                "raw_line": event.raw_line[:200],
            },
        )

        # Update atomic states based on event
        self._update_state(event)

        # Record for file output
        if self._file_output_enabled:
            self._event_history.append(event.to_dict())
            if len(self._event_history) % 10 == 0:  # Flush every 10 events
                self._flush_file_output()

        # Snapshot subscriber list to avoid mutation-during-iteration
        with self._event_subscribers_lock:
            callbacks = list(self._event_subscribers)
        for callback in callbacks:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in event callback")

    # -------------------------------------------------------------------------
    # Parsing
    # -------------------------------------------------------------------------

    def _parse_line(self, line: str) -> LogEvent | None:
        """Parse a log line into a LogEvent, or None if not relevant."""
        event_type = self._classify_event(line)
        if event_type is None:
            return None

        timestamp = self._extract_timestamp(line)
        data = self._extract_event_data(line, event_type)

        return LogEvent(
            event_type=event_type,
            timestamp=timestamp,
            raw_line=line,
            data=data,
        )

    def _extract_timestamp(self, line: str) -> datetime:
        """Extract timestamp from log line, or return current time."""
        match = re.search(r"<(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+)Z?>", line)
        if match:
            try:
                ts_str = match.group(1)
                # Handle variable decimal places
                if "." in ts_str:
                    base, frac = ts_str.split(".")
                    frac = frac[:6].ljust(6, "0")  # Normalize to 6 digits
                    ts_str = f"{base}.{frac}"
                return datetime.fromisoformat(ts_str)
            except ValueError:
                pass
        return datetime.now()

    def _classify_event(self, line: str) -> str | None:
        """Determine the event type from a log line. Returns None for irrelevant lines."""
        line_lower = line.lower()

        # Skip duplicate notification lines (only process SHUDEvent_OnNotification)
        if "UpdateNotificationItem" in line:
            return None

        # Session events
        if "User Login Success" in line:
            return "user_login"
        if "AccountLoginCharacterStatus_Character" in line:
            return "session_start"
        # Prefer the <Join PU> address line — contains real shard name.
        # The earlier {Join PU} index line is ignored to avoid duplicate events.
        if "<Join PU>" in line and "shard[" in line:
            return "join_pu"

        # Health events
        if "<MED BED HEAL>" in line and "Perform surgery event Success" in line:
            return "med_bed_heal"
        if "Injury Detected" in line and "SHUDEvent" in line:
            return "injury"

        # Quantum travel arrival (internal log, not SHUDEvent).
        # SC logs OnQuantumDriveArrived for every ship in replication range,
        # not just the player's, and the AUTH marker does not discriminate
        # (own and foreign arrivals both read NOT AUTH). Only classify when the
        # player is aboard their own ship.
        if "Quantum Drive has arrived at final destination" in line:
            if self._event_belongs_to_player_ship(
                self._extract_qt_arrival_class(line)
            ):
                return "qt_arrived"
            return None

        # Fatal collision (internal log, not SHUDEvent). Same replication-range
        # blindness as qt_arrived; additionally require the player to be piloting.
        if "<FatalCollision>" in line:
            if not re.search(r"PlayerPilot:\s*1\b", line):
                return None
            if self._event_belongs_to_player_ship(
                self._extract_collision_vehicle_class(line)
            ):
                return "fatal_collision"
            return None

        # Insurance (internal wallet logs, not SHUDEvent)
        if "CWallet::ProcessClaimToNextStep" in line and "New Insurance Claim Request" in line:
            return "insurance_claim"
        if "CWallet::RmMulticastOnProcessClaimCallback" in line:
            return "insurance_claim_complete"

        # Contract/Mission events (SHUDEvent notifications)
        if "SHUDEvent" in line:
            # Contracts
            if "Contract Accepted:" in line:
                return "contract_accepted"
            if "Contract Complete:" in line:
                return "contract_complete"
            if "Contract Failed:" in line:
                return "contract_failed"
            if "Contract Shared:" in line:
                return "contract_shared"
            if "Contract Available:" in line:
                return "contract_available"

            # Objectives
            if "New Objective:" in line:
                return "objective_new"
            if "Objective Complete:" in line:
                return "objective_complete"
            if "Objective Withdrawn:" in line:
                return "objective_withdrawn"

            # Monitored space
            if "Entered Monitored Space" in line:
                return "entered_monitored_space"
            if "Exited Monitored Space" in line:
                return "exited_monitored_space"
            if "Monitored Space Down" in line:
                return "monitored_space_down"
            if "Monitored Space Restored" in line:
                return "monitored_space_restored"

            # Journal entries must be checked before jurisdiction
            # ("Journal Entry Added: Jurisdiction:" contains "Jurisdiction")
            if "Journal Entry Added:" in line:
                return "journal_entry"

            # Zones and jurisdiction
            if "Jurisdiction" in line:
                return "jurisdiction_change"
            if "Armistice Zone" in line:
                return "armistice_zone"
            if "Restricted Area" in line:
                return "restricted_area"

            # Ships and hangars
            if "Hangar Request Completed" in line:
                return "hangar_ready"
            if "Joined hangar queue" in line:
                return "hangar_queue"

            # Quantum travel
            if "Quantum Travel Calibration Started" in line:
                return "quantum_calibration_started"
            if "Quantum Travel Calibration Complete By" in line:
                return "qt_calibration_complete_group"
            if "Quantum Travel Calibration Complete" in line:
                return "quantum_calibration_complete"

            # Social
            if "Party Invite Received" in line:
                return "party_invite"
            if "Incoming call:" in line:
                return "incoming_call"

            # Economy
            if "You've earned:" in line:
                return "reward_earned"
            if "Awarded" in line and "aUEC" in line:
                return "reward_earned"
            if "Received Blueprint:" in line:
                return "blueprint_received"
            if "Refinery Work Order" in line:
                return "refinery_complete"

            # Medical
            if "Emergency Services Are En Route" in line:
                return "emergency_services"

            # Health status
            if "Bleeding:" in line:
                return "bleeding"
            if "Low Fuel:" in line:
                return "fuel_low"

            # Law status
            if "CrimeStat Rating Increased:" in line:
                return "crimestat_increased"
            if "Vehicle Impounded:" in line:
                return "vehicle_impounded"

            # Social (party)
            if "You have left the party." in line:
                return "party_left"
            if "has joined the party." in line:
                return "party_member_joined"

            # Economy
            if "Fined" in line:
                return "fined"
            if "Transaction Complete:" in line:
                return "transaction_complete"

            # Health (incapacitation — distinct from injury)
            if "Incapacitated:" in line:
                return "incapacitated"

            # Economy — player-to-player transfer (two-line notification)
            if "You sent" in line:
                return "_money_sent_partial"

        # Location/ship events
        if "RequestLocationInventory" in line:
            return "location_change"
        if "Player Selected Quantum Target" in line:
            return "quantum_route_set"
        # Channel changes - only from SHUDEvent to avoid duplicates
        if "SHUDEvent" in line and (
            "joined channel" in line_lower
            or "left channel" in line_lower
            or "left the channel" in line_lower
        ):
            return "channel_change"

        # Cargo transfer via freight elevator kiosk
        if "FreightElevatorUIProvider::FillUnstowRequest" in line:
            return "cargo_transfer"

        # Ore submitted to refinery
        if "MiningShopUIProvider::OnRefineryRequest" in line:
            return "refinery_submitted"

        # Item attached to player character (equipment, weapons, consumables).
        # Cosmetic/identity ports (face parts, hair, MobiGlas UI) are excluded —
        # they carry no gameplay or economy significance.
        if "AttachmentReceived" in line and "Status[persistent]" in line:
            port_match = re.search(r"Port\[([^\]]+)\]", line)
            if port_match and port_match.group(1) not in _COSMETIC_PORTS:
                return "attachment_received"

        # Shop transactions (item shops). June 2026 logs use both
        # CEntityComponentShopUIProvider and CEntityComponentShoppingProvider.
        if "ShopUIProvider" in line or "ShoppingProvider" in line:
            if "SendShopBuyRequest" in line or "SendStandardItemBuyRequest" in line:
                return "shop_buy"
            if "SendShopSellRequest" in line or "SendStandardItemSellRequest" in line:
                return "shop_sell"
            if "RmShopFlowResponse" in line:
                return "shop_transaction_result"
        # Commodity transactions (cargo trading)
        if "CommodityUIProvider" in line:
            if "SendCommodityBuyRequest" in line:
                return "commodity_buy"
            if "SendCommoditySellRequest" in line:
                return "commodity_sell"

        # ATC departure detection — disabled pending reliable log signal.
        # AImodule_ATC was removed in PTU; replacement tag <Connection Flow>
        # also fires on terminal use, making it unusable as a departure filter.
        # if "AImodule_ATC" in line:
        #     if "DoEstablishCommunicationCommon" in line:
        #         return "station_departed"

        return None

    def _extract_event_data(self, line: str, event_type: str) -> dict[str, Any]:
        """Extract structured data from a log line based on event type."""
        data: dict[str, Any] = {}

        if event_type == "user_login":
            # Pattern: "User Login Success - Handle[Mallachi] - Time[...]"
            handle_match = re.search(r"Handle\[([^\]]+)\]", line)
            if handle_match:
                data["player_name"] = handle_match.group(1)

        elif event_type == "session_start":
            match = re.search(r"name\s+(\S+)", line)
            if match:
                data["player_name"] = match.group(1)
            match = re.search(r"geid\s+(\S+)", line)
            if match:
                data["player_geid"] = match.group(1)

        elif event_type == "join_pu":
            # Pattern: <Join PU> address[...] shard[pub_euw1b_11135423_170] ...
            match = re.search(r"shard\[([^\]]+)\]", line)
            if match:
                data["shard"] = match.group(1)
            addr_match = re.search(r"address\[([^\]]+)\]", line)
            if addr_match:
                data["server_address"] = addr_match.group(1)

        elif event_type in (
            "contract_accepted",
            "contract_complete",
            "contract_failed",
        ):
            # Full mission name captured between quotes
            type_map = {
                "contract_accepted": "Contract Accepted",
                "contract_complete": "Contract Complete",
                "contract_failed": "Contract Failed",
            }
            pattern = rf'"{type_map[event_type]}:\s*(.+?):\s*"'
            name_match = re.search(pattern, line)
            if name_match:
                data["mission_name"] = name_match.group(1).strip()
            mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
            if mission_id_match:
                data["mission_id"] = mission_id_match.group(1)

        elif event_type in ("contract_shared", "contract_available"):
            type_map = {
                "contract_shared": "Contract Shared",
                "contract_available": "Contract Available",
            }
            pattern = rf'"{type_map[event_type]}:\s*(.+?):\s*"'
            name_match = re.search(pattern, line)
            if name_match:
                data["mission_name"] = name_match.group(1).strip()
            mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
            if mission_id_match:
                data["mission_id"] = mission_id_match.group(1)

        elif event_type == "objective_new":
            obj_match = re.search(r'"New Objective:\s*(.+?):\s*"', line)
            if obj_match:
                data["objective"] = obj_match.group(1).strip()
            mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
            if mission_id_match:
                data["mission_id"] = mission_id_match.group(1)

        elif event_type == "objective_complete":
            obj_match = re.search(r'"Objective Complete:\s*(.+?)(?::\s*"|\s*")', line)
            if obj_match:
                data["objective"] = obj_match.group(1).strip()
            mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
            if mission_id_match:
                data["mission_id"] = mission_id_match.group(1)

        elif event_type == "objective_withdrawn":
            obj_match = re.search(r'"Objective Withdrawn:\s*(.+?):\s*"', line)
            if obj_match:
                data["objective"] = obj_match.group(1).strip()
            mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
            if mission_id_match:
                data["mission_id"] = mission_id_match.group(1)

        elif event_type == "injury":
            # Pattern: "Minor Injury Detected - Left arm - Tier 3 Treatment Required"
            severity_match = re.search(r"(\w+)\s+Injury Detected", line)
            if severity_match:
                data["severity"] = severity_match.group(1)
            # Body part is between first and second dash
            part_match = re.search(r"Injury Detected\s*-\s*([^-]+)\s*-", line)
            if part_match:
                data["body_part"] = part_match.group(1).strip()
            tier_match = re.search(r"Tier\s*(\d+)", line)
            if tier_match:
                data["tier"] = int(tier_match.group(1))

        elif event_type == "med_bed_heal":
            # Pattern: "head: true torso: false leftArm: true ..."
            healed = {}
            for part in ["head", "torso", "leftArm", "rightArm", "leftLeg", "rightLeg"]:
                if f"{part}: true" in line:
                    healed[part] = True
            data["healed_parts"] = healed

        elif event_type == "location_change":
            # Pattern: "Location[RR_CRU_LEO]" or "Location[Stanton1_Lorville]"
            loc_match = re.search(r"Location\[([^\]]+)\]", line)
            if loc_match:
                data["location"] = loc_match.group(1)
            # Fallback player name from "Player[name]" — session_start fires
            # before parser attaches (starts at EOF), so this is often the
            # first opportunity to capture the player name.
            player_match = re.search(r"Player\[([^\]]+)\]", line)
            if player_match:
                data["player_name"] = player_match.group(1)

        elif event_type == "quantum_route_set":
            # Destination names in logs are unreliable (LOCRRS codes, asset IDs)
            # so we no longer extract them. Event detection is sufficient.
            pass

        elif event_type == "channel_change":
            # Detect ship entry/exit via channel changes
            line_lower = line.lower()
            if "joined channel" in line_lower:
                data["action"] = "joined"
            elif "left channel" in line_lower or "left the channel" in line_lower:
                data["action"] = "left"
            # Extract channel name
            channel_match = re.search(
                r"(?:joined|left(?:\s+the)?)\s+channel\s+'([^']+)'",
                line,
                re.IGNORECASE,
            )
            if channel_match:
                raw_channel = channel_match.group(1)
                data["channel_raw"] = raw_channel
                # Extract owner name before cleaning
                # (e.g., "Aegis Avenger Titan : Mallachi" → owner = "Mallachi")
                if " : " in raw_channel:
                    data["channel_owner"] = raw_channel.split(" : ", 1)[1].strip()
                # Clean up ship name: "@vehicle_NameAEGS_Avenger_Titan : Player" -> "Avenger Titan"
                data["channel"] = self._clean_ship_name(raw_channel)

        elif event_type == "jurisdiction_change":
            # Pattern: "Entered Hurston Dynamics Jurisdiction: "
            jur_match = re.search(r'"Entered\s+(.+?)\s+Jurisdiction', line)
            if jur_match:
                data["jurisdiction"] = jur_match.group(1).strip()

        elif event_type in (
            "entered_monitored_space",
            "exited_monitored_space",
            "monitored_space_down",
            "monitored_space_restored",
        ):
            # Derive the monitored state from event type
            data["monitored"] = event_type in (
                "entered_monitored_space",
                "monitored_space_restored",
            )

        elif event_type == "armistice_zone":
            if "Entering" in line or "entered" in line.lower():
                data["action"] = "entered"
            elif "Leaving" in line or "exited" in line.lower():
                data["action"] = "exited"

        elif event_type == "restricted_area":
            if "Leaving" in line:
                data["action"] = "exited"
            else:
                data["action"] = "entered"

        elif event_type == "hangar_ready":
            data["action"] = "ready"

        elif event_type == "hangar_queue":
            data["action"] = "queued"

        elif event_type == "quantum_calibration_started":
            # Pattern: "Quantum Travel Calibration Started By PlayerName: "
            cal_match = re.search(
                r"Quantum Travel Calibration Started By\s+([^:]+)", line
            )
            if cal_match:
                data["player"] = cal_match.group(1).strip()

        elif event_type == "quantum_calibration_complete":
            # Own player's calibration — no "By" suffix, no player data to extract
            pass

        elif event_type == "party_invite":
            # Pattern: "PlayerName\nParty Invite Received: Accept Invitation?"
            invite_match = re.search(r'"([^"\\]+?)\\nParty Invite Received', line)
            if invite_match:
                data["from_player"] = invite_match.group(1).strip()

        elif event_type == "journal_entry":
            # Pattern: "Journal Entry Added: Jurisdiction: Crusader Industries : "
            journal_match = re.search(r'"Journal Entry Added:\s*(.+?):\s*"', line)
            if journal_match:
                data["subject"] = journal_match.group(1).strip()

        elif event_type == "incoming_call":
            # Pattern: "Incoming call: " with possible caller info
            call_match = re.search(r'"Incoming call:\s*([^"]*)"', line)
            if call_match:
                caller = call_match.group(1).strip()
                if caller:
                    data["caller"] = caller

        elif event_type == "refinery_complete":
            # Pattern: "Refinery Work Order(s) Completed at CRU-L1"
            ref_match = re.search(r"Refinery Work Order.*?at\s+([^:\"]+)", line)
            if ref_match:
                data["location"] = ref_match.group(1).strip()

        elif event_type == "reward_earned":
            # Current format: "Awarded 79250 aUEC: " (SHUDEvent_OnNotification)
            # Legacy format: "You've earned: 15,000" or "You've earned: Item Name"
            self._extract_notification_context(line, data)
            amount_match = re.search(r"Awarded\s*([\d,]+)\s*aUEC", line)
            if not amount_match:
                amount_match = re.search(r"You've earned:\s*([\d,]+)", line)
            if amount_match:
                data["amount"] = amount_match.group(1).replace(",", "")
            else:
                item_match = re.search(r'"You\'ve earned:\s*(.+?)(?::\s*"|\s*")', line)
                if item_match:
                    data["item_name"] = item_match.group(1).strip()

        elif event_type == "transaction_complete":
            self._extract_notification_context(line, data)

        elif event_type == "blueprint_received":
            # Format: "Received Blueprint: Citadel Core Base: "
            self._extract_notification_context(line, data)
            bp_match = re.search(r'Received Blueprint:\s*([^":]+)', line)
            if bp_match:
                data["blueprint_name"] = bp_match.group(1).strip()

        # emergency_services has no additional data to extract

        elif event_type in ("shop_buy", "shop_sell"):
            data["source_provider"] = (
                "shopping" if "ShoppingProvider" in line else "shop_ui"
            )
            self._extract_bracketed(
                line,
                data,
                ("player_id", "playerId"),
                ("shop_id", "shopId"),
                ("shop_name", "shopName"),
                ("kiosk_id", "kioskId"),
                ("item_guid", "itemClassGUID"),
                ("item_name", "itemName"),
                ("currency_type", "currencyType"),
            )
            price_match = re.search(r"client_price\[([^\]]+)\]", line)
            if price_match:
                data["price"] = float(price_match.group(1))
            qty_match = re.search(r"quantity\[([^\]]+)\]", line)
            if qty_match:
                data["quantity"] = int(qty_match.group(1))

        elif event_type == "commodity_buy":
            self._extract_bracketed(
                line,
                data,
                ("player_id", "playerId"),
                ("shop_id", "shopId"),
                ("shop_name", "shopName"),
                ("kiosk_id", "kioskId"),
                ("resource_guid", "resourceGUID"),
            )
            price_match = re.search(r"price\[([^\]]+)\]", line)
            if price_match:
                data["price"] = float(price_match.group(1))
            qty_match = re.search(r"quantity\[([^\]]+)\]", line)
            if qty_match:
                raw_qty = qty_match.group(1)
                # Commodity buy quantity is "12800.000000 cSCU"
                num_match = re.search(r"([\d.]+)", raw_qty)
                if num_match:
                    data["quantity_cscu"] = float(num_match.group(1))

        elif event_type == "commodity_sell":
            self._extract_bracketed(
                line,
                data,
                ("player_id", "playerId"),
                ("shop_id", "shopId"),
                ("shop_name", "shopName"),
                ("kiosk_id", "kioskId"),
                ("resource_guid", "resourceGUID"),
            )
            amount_match = re.search(r"amount\[([^\]]+)\]", line)
            if amount_match:
                data["price"] = float(amount_match.group(1))
            qty_match = re.search(r"quantity\[(\d+)\]", line)
            if qty_match:
                data["quantity"] = int(qty_match.group(1))

        elif event_type == "vehicle_impounded":
            # Pattern: "Vehicle Impounded: Parking Violation: "
            reason_match = re.search(r'"Vehicle Impounded:\s*(.+?):\s*"', line)
            if reason_match:
                data["reason"] = reason_match.group(1).strip()

        elif event_type == "party_member_joined":
            # Pattern: "{username} has joined the party.: "
            player_match = re.search(r'"(.+?) has joined the party\.', line)
            if player_match:
                data["player_name"] = player_match.group(1).strip()

        elif event_type == "qt_calibration_complete_group":
            # Pattern: "Quantum Travel Calibration Complete By {player}: "
            cal_match = re.search(
                r'"Quantum Travel Calibration Complete By\s+(.+?):\s*"', line
            )
            if cal_match:
                data["player"] = cal_match.group(1).strip()

        # fuel_low, bleeding, crimestat_increased, party_left: no extractable data

        elif event_type == "shop_transaction_result":
            data["source_provider"] = (
                "shopping" if "ShoppingProvider" in line else "shop_ui"
            )
            self._extract_bracketed(
                line,
                data,
                ("player_id", "playerId"),
                ("shop_id", "shopId"),
                ("shop_name", "shopName"),
                ("kiosk_id", "kioskId"),
                ("kiosk_state", "kioskState"),
            )
            result_match = re.search(r"result\[([^\]]+)\]", line)
            if result_match:
                data["result"] = result_match.group(1)
            type_match = re.search(r"type\[([^\]]+)\]", line)
            if type_match:
                data["transaction_type"] = type_match.group(1)

        elif event_type == "fined":
            # Pattern: "Fined 5,000 UEC" or "Fined 5000 UEC"
            amount_match = re.search(r'"Fined\s+([\d,]+)\s+UEC', line)
            if amount_match:
                data["amount"] = amount_match.group(1).replace(",", "")

        elif event_type == "_money_sent_partial":
            # First line of two-line money_sent notification: "You sent PlayerName:"
            recipient_match = re.search(r'"You sent\s+(.+?):', line)
            if recipient_match:
                data["recipient"] = recipient_match.group(1).strip()

        elif event_type == "fatal_collision":
            # Pattern: <FatalCollision> Fatal Collision occured for vehicle AEGS_Avenger Zone: Lorville, ...
            vehicle_match = re.search(
                r"<FatalCollision>\s+Fatal Collision occured for vehicle\s+(\S+)", line
            )
            if vehicle_match:
                data["vehicle"] = vehicle_match.group(1)
            zone_match = re.search(r"Zone:\s*([^,\]]+)", line)
            if zone_match:
                data["zone"] = zone_match.group(1).strip()

        elif event_type == "insurance_claim":
            # Pattern: New Insurance Claim Request - entitlementURN: urn:..., requestId : 1
            urn_match = re.search(r"entitlementURN:\s*([^,]+)", line)
            if urn_match:
                data["urn"] = urn_match.group(1).strip()
            req_match = re.search(r"requestId\s*:\s*(\d+)", line)
            if req_match:
                data["request_id"] = int(req_match.group(1))

        elif event_type == "insurance_claim_complete":
            # Pattern: Claim Complete - entitlementURN: urn:..., result: 7,  requestId: 1
            urn_match = re.search(r"entitlementURN:\s*([^,]+)", line)
            if urn_match:
                data["urn"] = urn_match.group(1).strip()
            result_match = re.search(r"result:\s*(\d+)", line)
            if result_match:
                data["result"] = int(result_match.group(1))

        # qt_arrived, transaction_complete, incapacitated: no additional data to extract

        elif event_type == "cargo_transfer":
            # Pattern: FreightElevatorKiosk_{type}[{kiosk_id}] - Processed bindings
            # into transfer request - Entities: {count}, Location: {loc_id}
            # - RequestId: {req_id}, ItemBank: {bank}
            kiosk_match = re.search(
                r"FreightElevatorKiosk_(\w+)\[(\d+)\]", line
            )
            if kiosk_match:
                data["kiosk_type"] = kiosk_match.group(1)
                data["kiosk_id"] = kiosk_match.group(2)
            entities_match = re.search(r"Entities:\s*(\d+)", line)
            if entities_match:
                data["entity_count"] = int(entities_match.group(1))
            location_match = re.search(r"Location:\s*(\d+)", line)
            if location_match:
                data["location_id"] = location_match.group(1)
            req_match = re.search(r"RequestId:\s*(\d+)", line)
            if req_match:
                data["request_id"] = int(req_match.group(1))

        elif event_type == "refinery_submitted":
            # Pattern: Sending SShopRefineryRequest - playerId[{id}] shopId[{id}]
            # shopName[{name}] kioskId[{id}] request[] currencyType[UEC]
            self._extract_bracketed(
                line,
                data,
                ("player_id", "playerId"),
                ("shop_id", "shopId"),
                ("shop_name", "shopName"),
                ("kiosk_id", "kioskId"),
                ("currency_type", "currencyType"),
            )

        elif event_type == "attachment_received":
            # Pattern: Player[{name}] Attachment[{full_name}_{entity_id},
            # {short_name}, {entity_id}] Status[persistent] Port[{port}]
            # Elapsed[{seconds}]
            #
            # Only log gameplay-relevant ports — cosmetic face/hair/body-model
            # ports are skipped at classification time in _classify_event via
            # the port filter below; extraction runs only when we reach here.
            player_match = re.search(r"Player\[([^\]]+)\]", line)
            if player_match:
                data["player_name"] = player_match.group(1)
            attach_match = re.search(
                r"Attachment\[([^\]]+),\s*([^\]]+),\s*(\d+)\]", line
            )
            if attach_match:
                data["item_full_name"] = attach_match.group(1).strip()
                data["item_short_name"] = attach_match.group(2).strip()
                data["entity_id"] = attach_match.group(3).strip()
            port_match = re.search(r"Port\[([^\]]+)\]", line)
            if port_match:
                data["port"] = port_match.group(1)
            elapsed_match = re.search(r"Elapsed\[([^\]]+)\]", line)
            if elapsed_match:
                try:
                    data["elapsed"] = float(elapsed_match.group(1))
                except ValueError:
                    pass

        return data

    # -------------------------------------------------------------------------
    # State Updates
    # -------------------------------------------------------------------------

    def _update_state(self, event: LogEvent) -> None:
        """Update atomic states based on a parsed event."""
        data = event.data
        event_type = event.event_type

        if event_type == "user_login":
            if "player_name" in data:
                self._state_store.set("player_name", data["player_name"])

        elif event_type == "session_start":
            if "player_name" in data:
                self._state_store.set("player_name", data["player_name"])
            if "player_geid" in data:
                self._state_store.set("player_geid", data["player_geid"])

        elif event_type == "join_pu":
            if "shard" in data:
                self._state_store.set("server", data["shard"])

        elif event_type == "contract_accepted":
            self._state_store.set("last_contract_accepted", data.get("mission_name"))
            self._state_store.set("last_contract_accepted_id", data.get("mission_id"))

        elif event_type == "contract_complete":
            self._state_store.set("last_contract_completed", data.get("mission_name"))
            self._state_store.set("last_contract_completed_id", data.get("mission_id"))

        elif event_type == "contract_failed":
            self._state_store.set("last_contract_failed", data.get("mission_name"))
            self._state_store.set("last_contract_failed_id", data.get("mission_id"))

        elif event_type == "objective_new":
            self._state_store.set("current_objective", data.get("objective"))

        elif event_type == "injury":
            raw_part = data.get("body_part", "")
            # Normalize body part to camelCase to match med_bed_heal keys
            _part_map = {
                "head": "head",
                "torso": "torso",
                "left arm": "leftArm",
                "right arm": "rightArm",
                "left leg": "leftLeg",
                "right leg": "rightLeg",
            }
            part = _part_map.get(raw_part.lower(), raw_part.lower().replace(" ", ""))
            severity = data.get("severity")
            if part and severity:
                self._state_store.set(f"injury_{part}", severity)

        elif event_type == "med_bed_heal":
            for part in data.get("healed_parts", {}):
                self._state_store.set(f"injury_{part}", None)

        elif event_type == "location_change":
            raw_location = data.get("location")
            self._state_store.set("location", raw_location)
            self._state_store.set("location_name", get_location_name(raw_location))
            self._state_store.set("star_system", get_location_system(raw_location))
            # Fallback: set player name if not yet known from session_start
            if "player_name" in data and not self._state_store.get("player_name"):
                self._state_store.set("player_name", data["player_name"])

        elif event_type == "quantum_route_set":
            # No state update — destination names are unreliable
            pass

        elif event_type == "channel_change":
            channel_raw = data.get("channel_raw", "")
            channel_clean = data.get("channel", "")
            action = data.get("action")
            # Ship detection heuristic: channel names that look like ships
            if self._is_ship_channel(channel_raw):
                if action == "joined":
                    self._state_store.set("ship", channel_clean)
                    owner = data.get("channel_owner")
                    self._state_store.set("ship_owner", owner)
                    player = self._state_store.get("player_name")
                    if owner and player:
                        self._state_store.set("own_ship", owner == player)
                    else:
                        self._state_store.set("own_ship", None)
                elif action == "left":
                    self._state_store.set("ship", None)
                    self._state_store.set("ship_owner", None)
                    self._state_store.set("own_ship", None)

        elif event_type == "jurisdiction_change":
            if "jurisdiction" in data:
                self._state_store.set("jurisdiction", data["jurisdiction"])

        elif event_type in (
            "entered_monitored_space",
            "exited_monitored_space",
            "monitored_space_down",
            "monitored_space_restored",
        ):
            self._state_store.set("in_monitored_space", data.get("monitored", False))

        elif event_type == "armistice_zone":
            action = data.get("action")
            self._state_store.set("in_armistice", action == "entered")

        elif event_type == "restricted_area":
            action = data.get("action")
            self._state_store.set("in_restricted_area", action == "entered")

        elif event_type == "objective_complete":
            self._state_store.set("current_objective", None)

        elif event_type == "objective_withdrawn":
            self._state_store.set("current_objective", None)

        # elif event_type == "station_departed":
        #     pass  # Disabled — see _classify_event

        # hangar_ready, hangar_queue are events - handled in logic layer

    def _is_ship_channel(self, channel: str) -> bool:
        """Heuristic to detect if a channel name is a ship."""
        channel_upper = channel.upper()
        # Coded format: @vehicle_NameAEGS_Avenger_Titan : Player
        if any(prefix in channel_upper for prefix in SHIP_MANUFACTURER_PREFIXES):
            return True
        # Human-readable format: "Aegis Avenger Titan : Player"
        # Use word-boundary matching to avoid false positives from substrings
        # (e.g. "MISC" inside "Miscellaneous" or "misc" in a player name)
        channel_lower = channel.lower()
        return any(
            re.search(r"(?<!\w)" + re.escape(name.lower()) + r"(?!\w)", channel_lower)
            for name in SHIP_MANUFACTURER_NAMES
        )

    @staticmethod
    def _extract_notification_context(line: str, data: dict[str, Any]) -> None:
        """Extract common SHUDEvent notification fields when present."""
        notification_match = re.search(r'Added notification ".*" \[(\d+)\]', line)
        if notification_match:
            data["notification_id"] = notification_match.group(1)
        mission_id_match = re.search(r"MissionId:\s*\[([^\]]+)\]", line)
        if mission_id_match:
            data["mission_id"] = mission_id_match.group(1)
        objective_id_match = re.search(r"ObjectiveId:\s*\[([^\]]*)\]", line)
        if objective_id_match:
            data["objective_id"] = objective_id_match.group(1)

    @staticmethod
    def _extract_bracketed(
        line: str,
        data: dict[str, Any],
        *fields: tuple[str, str],
    ) -> None:
        """Extract multiple ``key[value]`` fields from a log line.

        Each *fields* entry is ``(data_key, log_key)`` where *log_key*
        is the name that appears in the log (e.g. ``playerId``) and
        *data_key* is the name stored in the event data dict.
        """
        for data_key, log_key in fields:
            # (?<!\w) prevents matching log_key as a suffix of a longer field name
            match = re.search(rf"(?<!\w){log_key}\[([^\]]*)\]", line)
            if match:
                data[data_key] = match.group(1)

    def _clean_ship_name(self, raw_channel: str) -> str:
        """
        Clean up raw channel name to readable ship name.

        Example: "@vehicle_NameAEGS_Avenger_Titan : Mallachi" -> "Avenger Titan"
        """
        # Remove player name suffix (after " : ")
        if " : " in raw_channel:
            raw_channel = raw_channel.split(" : ")[0]

        # Remove @vehicle_Name prefix
        if raw_channel.startswith("@vehicle_Name"):
            raw_channel = raw_channel[13:]  # len("@vehicle_Name") = 13

        # Remove manufacturer prefix (AEGS_, ANVL_, etc.)
        # Prefixes are always uppercase in the log; no case-folding needed
        for prefix in SHIP_MANUFACTURER_PREFIXES:
            if raw_channel.startswith(prefix):
                raw_channel = raw_channel[len(prefix):]
                break

        # Replace underscores with spaces
        raw_channel = raw_channel.replace("_", " ")

        return raw_channel.strip()

    def _event_belongs_to_player_ship(self, entity_class: str | None) -> bool:
        """Decide if a ship-scoped log line refers to the player's own ship.

        Star Citizen logs ``OnQuantumDriveArrived`` and ``<FatalCollision>`` for
        every ship in replication range, not just the player's, and the AUTH
        marker does not distinguish them. The player is only aboard a ship when
        the parser has seen a ship voice-channel join (state key ``ship``); when
        on foot these lines always describe someone else.

        When aboard, the arriving/colliding entity's model tokens are compared
        against the current ``ship`` state.

        Args:
            entity_class: Ship class parsed from the log line (e.g.
                ``DRAK_Clipper``), or None when it could not be derived.

        Returns:
            False when the player is not aboard any ship, or on a confident
            model mismatch (both sides derivable and their model tokens are
            disjoint). True otherwise, including when either side cannot be
            derived, so a genuine own-ship event is never lost to a parse gap.
        """
        ship = self._state_store.get("ship")
        if not ship:
            return False
        ship_tokens = self._ship_model_tokens(ship)
        entity_tokens = self._ship_model_tokens(entity_class or "")
        if not ship_tokens or not entity_tokens:
            return True  # cannot compare confidently, fail open while aboard
        return bool(ship_tokens & entity_tokens)

    @staticmethod
    def _ship_model_tokens(name: str) -> set[str]:
        """Reduce a ship class or channel name to its lowercase model tokens.

        Drops the ``@vehicle_Name`` wrapper, manufacturer identifiers (both log
        prefix codes like ``DRAK`` and human-readable names like ``Drake``) and
        numeric entity ids, so a log entity class (``DRAK_Clipper``) and a
        channel-derived ship name (``Drake Clipper`` or ``Clipper``) reduce to
        the same token set.
        """
        cleaned = re.sub(r"@vehicle_Name", " ", name, flags=re.IGNORECASE)
        cleaned = cleaned.replace("_", " ").lower()
        tokens = {token for token in re.split(r"\s+", cleaned) if token}
        return {
            token
            for token in tokens
            if token not in _MANUFACTURER_TOKENS and not token.isdigit()
        }

    @staticmethod
    def _extract_qt_arrival_class(line: str) -> str | None:
        """Extract the arriving ship's class from an OnQuantumDriveArrived line.

        Example: ``AEGS_Avenger_Titan_587638492213[...]|CSCItemNavigation::
        OnQuantumDriveArrived`` yields ``AEGS_Avenger_Titan`` (trailing numeric
        entity id stripped). Returns None when no entity class is present.
        """
        match = re.search(
            r"([A-Za-z0-9_]+)\[\d+\]\|CSCItemNavigation::OnQuantumDriveArrived",
            line,
        )
        if not match:
            return None
        return re.sub(r"_\d+$", "", match.group(1))

    @staticmethod
    def _extract_collision_vehicle_class(line: str) -> str | None:
        """Extract the colliding vehicle's class from a <FatalCollision> line.

        Example: ``vehicle DRAK_Clipper_663913295369 [Part: ...`` yields
        ``DRAK_Clipper`` (trailing numeric entity id stripped). Returns None
        when no vehicle token is present.
        """
        match = re.search(
            r"Fatal Collision occured for vehicle\s+(\S+)", line
        )
        if not match:
            return None
        return re.sub(r"_\d+$", "", match.group(1))

    # -------------------------------------------------------------------------
    # File Output
    # -------------------------------------------------------------------------

    def _flush_file_output(self) -> None:
        """Write current state and event history to JSON file."""
        if not self._file_output_enabled or not self._file_output_path:
            return

        output = {
            "timestamp": datetime.now().isoformat(),
            "state_snapshot": self._state_store.get_all(),
            "recent_events": self._event_history[-100:],  # Keep last 100
        }

        try:
            atomic_write_text(
                self._file_output_path, json.dumps(output, indent=2, default=str)
            )
        except Exception:
            logger.exception("Failed to write file output")


# -----------------------------------------------------------------------------
# Standalone Entry Point
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    argparser = argparse.ArgumentParser(description="SC Log Parser - Layer 3")
    argparser.add_argument(
        "log_path",
        help="Path to Star Citizen Game.log",
    )
    argparser.add_argument(
        "--output",
        "-o",
        help="Path for JSON output file (optional)",
    )
    args = argparser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Create parser
    parser = LogParser(args.log_path)

    # Enable file output if specified
    if args.output:
        parser.enable_file_output(args.output)

    # Print events and state changes to console
    def on_event(event: LogEvent) -> None:
        print(f"\n[EVENT] {event.event_type}")
        print(f"  Time: {event.timestamp}")
        print(f"  Data: {event.data}")

    def on_state_change(key: str, old: Any, new: Any) -> None:
        print(f"[STATE] {key}: {old} -> {new}")

    parser.subscribe(on_event)
    parser.subscribe_state(on_state_change)

    # Run
    print(f"Monitoring: {args.log_path}")
    print("Press Ctrl+C to stop\n")

    parser.start()

    try:
        while parser.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        parser.stop()

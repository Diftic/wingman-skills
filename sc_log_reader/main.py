"""
SC_LogReader - Layer 1: WingmanAI Skill

AI interface for Star Citizen log monitoring.
Receives events from Layer 2 and provides tools for AI interaction.

Author: Mallachi
"""

import asyncio
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, Thread, Timer
from typing import Any

from api.enums import LogSource, LogType
from skills.skill_base import Skill

# Add the current directory (SC_LogReader) to the sys path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from atomic_io import atomic_write_text  # noqa: E402
from event_log import EventLog, EventLogEntry  # noqa: E402
from logic import DerivedEvent, StateLogic  # noqa: E402
from parser import LogEvent, LogParser  # noqa: E402


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event Category Mappings
# ---------------------------------------------------------------------------

# Maps raw event types to their config toggle key
# Maps every event type (raw-forwarded and derived) to its per-event toggle key.
# Derived event types use specific names set in logic.py.
# Raw event types use the event_type string from the parser.
_EVENT_TOGGLE_MAP: dict[str, str] = {
    # --- Derived events (from logic.py) ---
    # Contracts / missions
    "mission_accepted": "notify_mission_accepted",
    "mission_complete": "notify_mission_complete",
    "mission_failed": "notify_mission_failed",
    # Objectives
    "mission_objective_new": "notify_mission_objective_new",
    # Travel
    "location_arrived": "notify_location_arrived",
    # Zones
    "zone_entered_armistice": "notify_zone_entered_armistice",
    "zone_left_armistice": "notify_zone_left_armistice",
    "hangar_access": "notify_hangar_access",
    # Ships
    "ship_entered": "notify_ship_entered",
    "ship_exited": "notify_ship_exited",
    # Health
    "health_injury_reminder": "notify_health_injury_reminder",
    # --- Raw events forwarded directly (not in _HAS_DERIVED_EVENT) ---
    # Contracts
    "contract_shared": "notify_contract_shared",
    "contract_available": "notify_contract_available",
    # Objectives
    "objective_complete": "notify_objective_complete",
    "objective_withdrawn": "notify_objective_withdrawn",
    # Zones
    "entered_monitored_space": "notify_entered_monitored_space",
    "exited_monitored_space": "notify_exited_monitored_space",
    "monitored_space_down": "notify_monitored_space_down",
    "monitored_space_restored": "notify_monitored_space_restored",
    "jurisdiction_change": "notify_jurisdiction_change",
    "restricted_area": "notify_restricted_area",
    # Ships
    "hangar_queue": "notify_hangar_queue",
    # Travel
    "quantum_route_set": "notify_quantum_route_set",
    "quantum_calibration_started": "notify_quantum_calibration_started",
    "quantum_calibration_complete": "notify_quantum_calibration_complete",
    "qt_calibration_complete_group": "notify_qt_calibration_complete_group",
    # Health
    "injury": "notify_injury",
    "med_bed_heal": "notify_med_bed_heal",
    "emergency_services": "notify_emergency_services",
    "bleeding": "notify_bleeding",
    "fuel_low": "notify_fuel_low",
    # Law
    "crimestat_increased": "notify_crimestat_increased",
    "vehicle_impounded": "notify_vehicle_impounded",
    # Social
    "party_invite": "notify_party_invite",
    "incoming_call": "notify_incoming_call",
    "party_member_joined": "notify_party_member_joined",
    "party_left": "notify_party_left",
    # Economy
    "reward_earned": "notify_reward_earned",
    "refinery_complete": "notify_refinery_complete",
    "fined": "notify_fined",
    "transaction_complete": "notify_transaction_complete",
    "money_sent": "notify_money_sent",
    # Health
    "incapacitated": "notify_incapacitated",
    # Session
    "user_login": "notify_user_login",
    "session_start": "notify_session_start",
    "join_pu": "notify_join_pu",
    # Travel
    "qt_arrived": "notify_qt_arrived",
    # Game items
    "blueprint_received": "notify_blueprint_received",
    # Incidents
    "fatal_collision": "notify_fatal_collision",
    # Insurance
    "insurance_claim": "notify_insurance_claim",
    "insurance_claim_complete": "notify_insurance_claim_complete",
    # Journal
    "journal_entry": "notify_journal_entry",
}

# Events that produce derived events via logic.py — not forwarded as raw
# to avoid double-notifications
_HAS_DERIVED_EVENT: set[str] = {
    "contract_accepted",
    "contract_complete",
    "contract_failed",
    "objective_new",
    "hangar_ready",
    "channel_change",
    "armistice_zone",
    # "station_departed",  # Disabled — unreliable log signal
    "location_change",
    # Trade events: logic layer handles pending/confirmation and ledger writes
    "shop_buy",
    "shop_sell",
    "shop_transaction_result",
    "commodity_buy",
    "commodity_sell",
}

# Environments monitored within the StarCitizen base folder
_SC_ENVIRONMENTS = ("LIVE", "PTU", "EPTU", "HOTFIX", "TECH-PREVIEW")

# Pre-4.8.3 donor state DB location. Superseded by a path under this skill's
# own generated_files dir; kept only to migrate existing installs forward.
_LEGACY_DONOR_STATE_DB_PATH = "${APPDATA}/Wingman/sc_log_reader/donor_state.sqlite"


@dataclass
class _GameStack:
    """One monitoring stack for a single SC environment (LIVE / PTU / HOTFIX)."""

    env: str                          # "LIVE", "PTU", or "HOTFIX"
    game_path: Path                   # .../StarCitizen/LIVE
    log_path: Path                    # game_path / "Game.log"
    parser: LogParser
    logic: StateLogic
    event_log: EventLog
    state_saved_at: datetime | None = field(default=None)
    last_event_at: datetime | None = field(default=None)


class SC_LogReader(Skill):
    """
    Star Citizen Log Reader Skill

    3-Layer Architecture:
    - Layer 3 (parser.py): Reads Game.log, produces atomic states
    - Layer 2 (logic.py): Combines states into derived events
    - Layer 1 (this file): AI interface, tools, notifications
    """

    VERSION = "4.8.3.4"
    SC_TARGET_VERSION = "4.8.3"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Multi-environment monitoring stacks (one per found SC environment)
        self._stacks: list[_GameStack] = []
        self._active_stack: _GameStack | None = None  # Most recently active (for tools)
        self._sc_base_path: Path | None = None        # .../StarCitizen folder

        # Event collection for AI queries
        self._recent_events: list[LogEvent] = []
        self._recent_events_lock = Lock()
        self._max_recent_events = 50

        # Notification batching
        self._notification_batch: list[DerivedEvent] = []
        self._batch_timer: Timer | None = None
        self._batch_delay_seconds = 4.0
        self._batch_lock = Lock()

        # Duplicate detection
        self._last_notification: str | None = None
        self._last_notification_time: datetime | None = None
        self._duplicate_cooldown_seconds = 10.0

        # Event loop reference for cross-thread async calls
        self._event_loop: asyncio.AbstractEventLoop | None = None

        # Throttling: pause notifications if user is not engaged
        self._auto_messages_since_user_input = 0
        self._notifications_paused = False
        self._max_auto_messages = 10  # Pause after 10 auto-messages without user input

        # Retry: periodically check for Game.log if not found at startup
        self._retry_timer: Timer | None = None
        self._retry_interval_seconds = 30.0

        # Donor UI (optional - requires fastapi/uvicorn)
        self._donor_server = None
        self._donor_window = None
        self._donor_dedup_store = None

    # -------------------------------------------------------------------------
    # Skill Lifecycle
    # -------------------------------------------------------------------------

    async def validate(self) -> list:
        """Validate skill configuration."""
        errors = await super().validate()

        self._discover_sc_path()

        if not self._sc_base_path or not any(
            (self._sc_base_path / env / "Game.log").exists()
            for env in _SC_ENVIRONMENTS
        ):
            if self.printr:
                self.printr.print(
                    "SC_LogReader: No Game.log found. Will retry after startup.",
                    color=LogType.WARNING,
                )

        return errors

    async def prepare(self) -> None:
        """Initialize the 3-layer stack."""
        await super().prepare()

        # Capture event loop for cross-thread async calls
        self._event_loop = asyncio.get_running_loop()

        if self.printr:
            self.printr.print(
                f"SC_LogReader v{self.VERSION} initializing...",
                color=LogType.INFO,
            )
            # Forward the skill hint to chat as a toast so users see the donation
            # call-to-action on startup. The hint also lives in default_config.yaml;
            # this just surfaces it once at load time since the settings panel
            # renders it at the bottom.
            hint_meta = getattr(self.config, "hint", None)
            hint_en = getattr(hint_meta, "en", None) if hint_meta else None
            if hint_en:
                hint_text = re.sub(r"<[^>]+>", "", hint_en)
                hint_text = re.sub(r"\s+", " ", hint_text).strip()
                if hint_text:
                    self.printr.toast_info(hint_text)

        # Standalone donation UI (optional - requires fastapi)
        try:
            from log_donor._build_config import DONOR_WORKER_TOKEN, DONOR_WORKER_URL
            from log_donor.dedup import DedupStore
            from log_donor.donor_ui.app import DonorServer
            from log_donor.donor_ui.window import DonorWindow
            from services.system_manager import LOCAL_VERSION as WINGMAN_VERSION

            state_db_path = self._migrate_donor_state_db()
            self._donor_dedup_store = DedupStore(db_path=state_db_path)

            self._donor_server = DonorServer(
                sc_root_provider=self._donor_sc_root,
                store=self._donor_dedup_store,
                worker_url_provider=lambda: DONOR_WORKER_URL,
                worker_token_provider=lambda: DONOR_WORKER_TOKEN,
                client_version=self.VERSION,
                wingman_version=WINGMAN_VERSION,
            )
            self._donor_server.start()
            self._donor_window = DonorWindow(url=self._donor_server.url)
            logger.info("Donor UI started at %s", self._donor_server.url)
            self.threaded_execution(self._announce_donor_ui_startup)
        except ImportError as e:
            logger.warning("Donor UI unavailable (missing fastapi/uvicorn?): %s", e)
            if self.printr:
                self.printr.print(
                    "SC_LogReader: Donation UI unavailable (missing dependency). "
                    "Log monitoring is unaffected.",
                    color=LogType.WARNING,
                )
        except Exception as e:
            # Broad on purpose: a corrupt/locked donor_state.sqlite (sqlite3
            # errors), a port bind failure, or any other donor-only startup
            # problem must degrade to "no donor UI", never abort prepare()
            # and take the whole skill down with it.
            logger.warning("Donor UI failed to start: %s", e)
            if self.printr:
                self.printr.print(
                    "SC_LogReader: Donation UI failed to start. "
                    "Log monitoring is unaffected.",
                    color=LogType.WARNING,
                )

        found = self._sc_base_path and any(
            (self._sc_base_path / env / "Game.log").exists()
            for env in _SC_ENVIRONMENTS
        )
        if not found:
            if self.printr:
                self.printr.print(
                    "SC_LogReader: No Game.log found - will retry every "
                    f"{int(self._retry_interval_seconds)}s",
                    color=LogType.WARNING,
                )
            self._start_retry_timer()
            return

        self._initialize_stacks()

    async def _announce_donor_ui_startup(self) -> None:
        """Post a clickable link to the donor UI in the wingman chat."""
        # Give the WebSocket a moment to attach so the chat catches the toast.
        await asyncio.sleep(3)

        if not self._donor_server:
            return

        url = self._donor_server.url
        if not url:
            return

        display_url = url.replace("127.0.0.1", "localhost")
        msg = f"SC Log Reader donation dashboard is ready. Open:\n{display_url}"

        await self.printr.print_async(
            msg,
            color=LogType.POSITIVE,
            source=LogSource.WINGMAN,
            source_name=self.wingman.name if self.wingman else "SC_LogReader",
            skill_name=self.name,
        )

    def _initialize_stacks(self) -> None:
        """Initialize monitoring stacks for all found SC environments.

        Idempotent: stops existing stacks before creating new ones.
        Creates one (parser, logic, ledger) stack per environment whose
        Game.log exists under self._sc_base_path.
        """
        for stack in self._stacks:
            stack.parser.stop()
            stack.logic.stop()
        self._stacks.clear()
        self._active_stack = None

        if not self._sc_base_path:
            return

        ledger_dir = Path(self.get_generated_files_dir())

        for env in _SC_ENVIRONMENTS:
            game_path = self._sc_base_path / env
            log_path = game_path / "Game.log"
            if not log_path.exists():
                continue

            stack = self._create_stack(env, game_path, log_path, ledger_dir)
            self._stacks.append(stack)

            if self.printr:
                self.printr.print(
                    f"SC_LogReader: Monitoring {env}: {log_path}",
                    color=LogType.INFO,
                )

        # Set active stack to the most recently modified log
        if self._stacks:
            self._active_stack = max(
                self._stacks,
                key=lambda s: s.log_path.stat().st_mtime,
            )

    def _create_stack(
        self,
        env: str,
        game_path: Path,
        log_path: Path,
        ledger_dir: Path,
    ) -> _GameStack:
        """Create, wire, and start one monitoring stack for a single environment."""
        parser = LogParser(log_path)
        event_log = EventLog(ledger_dir / f"sc_logreader_eventlog_{env}.jsonl")
        logic = StateLogic(parser)
        logic.set_event_log(event_log)

        # Trim event log entries older than 30 days on startup
        trimmed = event_log.trim(days=30)
        if trimmed and self.printr:
            self.printr.print(
                f"SC_LogReader: trimmed {trimmed} old event log entries for {env}",
                color=LogType.INFO,
            )

        # Set write watermark so catch-up doesn't re-append already-written entries
        # when Wingman restarts mid-session.
        event_log.set_write_watermark()

        stack = _GameStack(
            env=env,
            game_path=game_path,
            log_path=log_path,
            parser=parser,
            logic=logic,
            event_log=event_log,
        )

        # Restore state and detect session change before subscribing
        self._load_stack_state(stack)
        parser.prepare()  # Single-pass scan: caches login position + last session ts
        self._check_stack_session_change(stack)

        # Per-stack closures: catch-up check and active stack tracking
        def on_raw(event: LogEvent, s: _GameStack = stack) -> None:
            # Always collect for AI tools regardless of catch-up state
            with self._recent_events_lock:
                self._recent_events.append(event)
                if len(self._recent_events) > self._max_recent_events:
                    self._recent_events.pop(0)
            if s.parser._catching_up:
                return
            s.last_event_at = datetime.now()
            self._active_stack = s
            self._on_raw_event(event)

        def on_derived(event: DerivedEvent, s: _GameStack = stack) -> None:
            if s.parser._catching_up:
                return
            s.last_event_at = datetime.now()
            self._active_stack = s
            self._on_derived_event(event)

        logic.subscribe_raw(on_raw)
        logic.subscribe(on_derived)

        # Wire catch-up completion callback
        if parser._catching_up:
            def on_catchup_done(s: _GameStack = stack) -> None:
                if self.printr:
                    self.printr.print(
                        f"SC_LogReader: {s.env} catch-up complete — now live",
                        color=LogType.INFO,
                    )
            parser._on_catchup_complete = on_catchup_done

        logic.start()
        parser.start()

        return stack

    def _start_retry_timer(self) -> None:
        """Schedule a timer to re-check for Game.log."""
        self._retry_timer = Timer(
            self._retry_interval_seconds,
            self._retry_find_log,
        )
        self._retry_timer.daemon = True
        self._retry_timer.start()

    def _retry_find_log(self) -> None:
        """Periodic callback: check if any Game.log has appeared and start monitoring."""
        self._retry_timer = None

        self._discover_sc_path()

        found = self._sc_base_path and any(
            (self._sc_base_path / env / "Game.log").exists()
            for env in _SC_ENVIRONMENTS
        )
        if found:
            if self.printr:
                self.printr.print(
                    f"SC_LogReader: Game.log found under {self._sc_base_path}",
                    color=LogType.INFO,
                )
            self._initialize_stacks()
        else:
            self._start_retry_timer()

    def _discover_sc_path(self) -> None:
        """Discover the StarCitizen base folder from config or common locations.

        Updates self._sc_base_path if found.
        Backwards compatible: if the configured path points to a LIVE/PTU/HOTFIX
        folder directly (old format), the parent is used as the base.
        """
        configured = self._get_config_value("sc_game_path", "")
        if configured:
            base = Path(configured)
            # Old config pointed to LIVE subfolder — step up to StarCitizen root
            if (base / "Game.log").exists():
                base = base.parent
            if base.exists():
                self._sc_base_path = base
                return

        common_bases = [
            Path("C:/Roberts Space Industries/StarCitizen"),
            Path("D:/Roberts Space Industries/StarCitizen"),
            Path("C:/Program Files/Roberts Space Industries/StarCitizen"),
            Path("D:/Program Files/Roberts Space Industries/StarCitizen"),
            Path("C:/Games/Roberts Space Industries/StarCitizen"),
            Path("D:/Games/Roberts Space Industries/StarCitizen"),
        ]
        for base in common_bases:
            if any((base / env / "Game.log").exists() for env in _SC_ENVIRONMENTS):
                self._sc_base_path = base
                return

    # -------------------------------------------------------------------------
    # State Persistence (per stack / per environment)
    # -------------------------------------------------------------------------

    def _save_stack_state(self, stack: _GameStack) -> None:
        """Persist a single stack's parser and logic state to disk."""
        # Write alongside the ledger in generated_files_dir, not into the SC install
        state_file = stack.event_log.path.parent / f"sc_logreader_state_{stack.env}.json"
        state = {
            "version": self.VERSION,
            "saved_at": datetime.now().isoformat(),
            "parser_state": stack.parser.save_state(),
            "logic_state": stack.logic.save_state(),
        }
        try:
            atomic_write_text(state_file, json.dumps(state, indent=2, default=str))
            if self.printr:
                self.printr.print(
                    f"SC_LogReader: {stack.env} state saved to {state_file}",
                    color=LogType.INFO,
                    server_only=True,
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to save state for %s", stack.env
            )

    def _load_stack_state(self, stack: _GameStack) -> None:
        """Restore a single stack's parser and logic state from disk."""
        state_file = stack.event_log.path.parent / f"sc_logreader_state_{stack.env}.json"
        if not state_file.exists():
            return
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)

            parser_state = state.get("parser_state", {})
            logic_state = state.get("logic_state", {})

            if parser_state:
                stack.parser.load_state(parser_state)
            if logic_state:
                stack.logic.load_state(logic_state)

            saved_at_str = state.get("saved_at")
            if saved_at_str:
                try:
                    stack.state_saved_at = datetime.fromisoformat(saved_at_str)
                except ValueError:
                    stack.state_saved_at = None

            if self.printr:
                self.printr.print(
                    f"SC_LogReader: {stack.env} state restored from {state_file}",
                    color=LogType.INFO,
                    server_only=True,
                )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to load state for %s", stack.env
            )

    def _check_stack_session_change(self, stack: _GameStack) -> None:
        """Detect if a stack's Game.log has a newer session than the persisted state.

        The parser starts at EOF and misses session_start lines written before
        it attached. Scans the log for the latest session_start timestamp and
        clears mission state if a new session is detected.
        """
        if not stack.state_saved_at:
            return
        try:
            last_session_ts = stack.parser.last_session_timestamp
            if not last_session_ts:
                return
            if last_session_ts > stack.state_saved_at:
                stack.logic.on_new_session()
                if self.printr:
                    self.printr.print(
                        f"SC_LogReader: New session detected ({stack.env}) "
                        "— mission state cleared",
                        color=LogType.INFO,
                    )
        except Exception:
            logging.getLogger(__name__).exception(
                "Session change check failed for %s", stack.env
            )

    async def unload(self) -> None:
        """Stop all monitoring stacks."""
        if self._retry_timer is not None:
            self._retry_timer.cancel()
            self._retry_timer = None

        with self._batch_lock:
            if self._batch_timer is not None:
                self._batch_timer.cancel()
                self._batch_timer = None
            self._notification_batch.clear()

        for stack in self._stacks:
            self._save_stack_state(stack)
            stack.parser.stop()
            stack.logic.stop()
        self._stacks.clear()
        self._active_stack = None

        # Best-effort on purpose: any donor teardown failure must not prevent
        # super().unload() from running, so each step catches broadly rather
        # than just the narrow error its happy path is expected to raise.
        if self._donor_window is not None:
            try:
                self._donor_window.close()
            except Exception:
                logger.debug("Failed to close donor window", exc_info=True)
            self._donor_window = None
        if self._donor_server is not None:
            try:
                self._donor_server.stop()
            except Exception:
                logger.debug("Failed to stop donor server", exc_info=True)
            self._donor_server = None
        if self._donor_dedup_store is not None:
            try:
                self._donor_dedup_store.close()
            except Exception:
                logger.debug("Failed to close donor dedup store", exc_info=True)
            self._donor_dedup_store = None

        await super().unload()

    async def on_add_user_message(self, message: str) -> None:
        """Called when a user message is added to the system.

        Resets the auto-message counter and resumes notifications if paused.
        This ensures the skill stays responsive when the user is engaged.
        """
        was_paused = self._notifications_paused

        # Reset counter and resume notifications
        self._auto_messages_since_user_input = 0
        if self._notifications_paused:
            self._notifications_paused = False

        if was_paused and self.printr:
            self.printr.print(
                "SC_LogReader: User engaged - resuming notifications",
                color=LogType.INFO,
                server_only=True,
            )

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def _on_raw_event(self, event: LogEvent) -> None:
        """Forward a raw event for notification (called only outside catch-up).

        Event collection into _recent_events is handled by the per-stack closure
        so it captures events during catch-up too (for AI tool queries).
        """
        # Debug logging
        if self.printr:
            self.printr.print(
                f"SC_LogReader: {event.event_type} - {event.data}",
                color=LogType.INFO,
                server_only=True,
            )

        # Forward raw events that don't have derived counterparts in logic.py
        if event.event_type not in _HAS_DERIVED_EVENT:
            self._forward_raw_event(event)

    def _on_derived_event(self, event: DerivedEvent) -> None:
        """Handle derived events from Layer 2 (called only outside catch-up)."""
        if not self._should_notify(event.event_type):
            return

        if self._is_duplicate(event.message):
            return

        self._add_to_batch(event)

    def _should_notify(self, event_type: str) -> bool:
        """Check if notifications are enabled for a specific event type."""
        if not self._get_config_value("proactive_notifications", False):
            return False
        toggle = _EVENT_TOGGLE_MAP.get(event_type)
        if not toggle:
            return False
        return self._get_config_value(toggle, False)

    def _get_config_value(self, property_id: str, default: Any) -> Any:
        """Get a config property value with a default fallback."""
        if not self.config.custom_properties:
            return default
        prop = next(
            (p for p in self.config.custom_properties if p.id == property_id),
            None,
        )
        if prop is None:
            return default
        return prop.value if prop.value is not None else default

    def _migrate_donor_state_db(self) -> Path:
        """Return the donor dedup DB path, migrating it from the legacy location if needed.

        Pre-4.8.3 builds wrote donor_state.sqlite to a stray AppData/Wingman
        path outside this skill's own generated_files dir. If that file still
        exists and nothing has been written to the new location yet, move it
        so existing dedup state survives the upgrade.

        Returns:
            The donor dedup DB path under this skill's generated_files dir.
        """
        new_path = Path(self.get_generated_files_dir()) / "donor_state.sqlite"
        legacy_path = Path(os.path.expandvars(_LEGACY_DONOR_STATE_DB_PATH))

        if legacy_path.exists() and not new_path.exists():
            try:
                new_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(legacy_path), str(new_path))
                logger.info(
                    "Migrated donor state DB from %s to %s", legacy_path, new_path
                )
            except OSError as e:
                logger.warning(
                    "Failed to migrate donor state DB from %s to %s: %s",
                    legacy_path, new_path, e,
                )

        return new_path

    def _donor_sc_root(self) -> "Path | None":
        """Return the skill's resolved SC root for the donor scanner.

        Uses self._sc_base_path which is populated by _discover_sc_path() from
        either the configured sc_game_path or the autodetected install location.
        """
        return self._sc_base_path if self._sc_base_path and self._sc_base_path.is_dir() else None

    def _is_duplicate(self, message: str) -> bool:
        """Check if this message is a duplicate of a recent notification.

        Called from background parser threads (potentially multiple stacks),
        so the check-and-set must be atomic under _batch_lock.
        """
        with self._batch_lock:
            now = datetime.now()
            if self._last_notification == message and self._last_notification_time:
                elapsed = (now - self._last_notification_time).total_seconds()
                if elapsed < self._duplicate_cooldown_seconds:
                    return True
            self._last_notification = message
            self._last_notification_time = now
        return False

    def _forward_raw_event(self, event: LogEvent) -> None:
        """Forward a raw event as notification (for events without derived counterparts)."""
        if not self._should_notify(event.event_type):
            return

        message = self._format_raw_event(event)
        if not message:
            return

        if self._is_duplicate(message):
            return

        # Wrap as DerivedEvent for the batching system
        derived = DerivedEvent(
            event_type=event.event_type,
            timestamp=event.timestamp,
            message=message,
            source_states=event.data,
        )
        self._add_to_batch(derived)

    def _format_raw_event(self, event: LogEvent) -> str | None:
        """Format a raw event into a human-readable notification message."""
        d = event.data
        et = event.event_type

        # Contracts
        if et == "contract_shared":
            return f"Contract shared: {d.get('mission_name', 'Unknown')}"
        if et == "contract_available":
            return f"Contract available: {d.get('mission_name', 'Unknown')}"

        # Objectives — suppress when data is missing (CIG logging bug)
        if et == "objective_complete":
            obj = d.get("objective")
            return f"Objective complete: {obj}" if obj else None
        if et == "objective_withdrawn":
            obj = d.get("objective")
            return f"Objective withdrawn: {obj}" if obj else None

        # Zones
        if et == "entered_monitored_space":
            return "Entered monitored space"
        if et == "exited_monitored_space":
            return "Exited monitored space"
        if et == "monitored_space_down":
            return "Monitored space systems down"
        if et == "monitored_space_restored":
            return "Monitored space systems restored"
        if et == "jurisdiction_change":
            jurisdiction = d.get("jurisdiction", "Unknown")
            if jurisdiction == "UEE":
                return None  # UEE is generic/noisy — suppress
            return f"Entered {jurisdiction} jurisdiction"
        if et == "restricted_area":
            if d.get("action") == "entered":
                return "Entered restricted area"
            return "Left restricted area"

        # Ships
        if et == "hangar_queue":
            return "Joined hangar queue"

        # Travel
        if et == "quantum_route_set":
            return "Quantum travel destination set"
        if et == "quantum_calibration_started":
            return "Quantum calibration started"
        if et == "quantum_calibration_complete":
            return "Quantum calibration complete"
        if et == "qt_calibration_complete_group":
            return f"Quantum calibration completed by {d.get('player', 'Party member')}"
        # Health
        if et == "injury":
            sev = d.get("severity", "")
            part = d.get("body_part", "Unknown")
            tier = d.get("tier", "?")
            return f"{sev} injury: {part} (Tier {tier})"
        if et == "med_bed_heal":
            parts = ", ".join(d.get("healed_parts", {}).keys())
            return f"Med bed healed: {parts}" if parts else "Med bed heal"
        if et == "emergency_services":
            return "Emergency services en route"
        if et == "bleeding":
            return "You are bleeding"
        if et == "fuel_low":
            return "Low fuel warning"

        # Law
        if et == "crimestat_increased":
            return "CrimeStat rating increased"
        if et == "vehicle_impounded":
            reason = d.get("reason", "Unknown violation")
            return f"Vehicle impounded: {reason}"

        # Social
        if et == "party_invite":
            return f"Party invite from {d.get('from_player', 'Unknown')}"
        if et == "incoming_call":
            caller = d.get("caller")
            return f"Incoming call: {caller}" if caller else "Incoming call"
        if et == "party_member_joined":
            return f"{d.get('player_name', 'Someone')} joined the party"
        if et == "party_left":
            return "You left the party"

        # Economy
        if et == "reward_earned":
            return f"Earned: {d.get('amount', '?')} aUEC"
        if et == "refinery_complete":
            loc = d.get("location")
            return f"Refinery complete at {loc}" if loc else "Refinery complete"
        if et == "fined":
            return f"Fined {d.get('amount', '?')} UEC"
        if et == "transaction_complete":
            return "Transaction complete"
        if et == "money_sent":
            recipient = d.get("recipient", "Unknown")
            amount = d.get("amount", "?")
            return f"Sent {amount} aUEC to {recipient}"

        # Health
        if et == "incapacitated":
            return "You are incapacitated"

        # Session
        if et == "user_login":
            return f"Logged in: {d.get('player_name', 'Unknown')}"
        if et == "session_start":
            return f"Session started: {d.get('player_name', 'Unknown')}"
        if et == "join_pu":
            return f"Joined PU: {d.get('shard', 'Unknown')}"

        # Travel
        if et == "qt_arrived":
            return "Arrived at quantum destination"

        # Game items
        if et == "blueprint_received":
            return f"Blueprint received: {d.get('name', 'Unknown')}"

        # Incidents
        if et == "fatal_collision":
            vehicle = d.get("vehicle", "Unknown")
            zone = d.get("zone")
            return f"Fatal collision: {vehicle}" + (f" in {zone}" if zone else "")

        # Insurance
        if et == "insurance_claim":
            return "Insurance claim filed"
        if et == "insurance_claim_complete":
            return "Insurance claim complete"

        # Journal
        if et == "journal_entry":
            return f"Journal: {d.get('subject', 'Unknown')}"

        return None

    def _add_to_batch(self, event: DerivedEvent) -> None:
        """Add event to notification batch."""
        with self._batch_lock:
            self._notification_batch.append(event)

            # Start/reset batch timer
            if self._batch_timer is not None:
                self._batch_timer.cancel()

            self._batch_timer = Timer(
                self._batch_delay_seconds,
                self._flush_batch,
            )
            self._batch_timer.start()

    def _flush_batch(self) -> None:
        """Send batched notifications to AI.

        Runs on a Timer thread — any unhandled exception here would
        silently kill delivery for all future events, so the entire
        body is wrapped in try/except.
        """
        try:
            self._flush_batch_inner()
        except Exception:
            if self.printr:
                self.printr.print(
                    "SC_LogReader: _flush_batch failed — see log for details",
                    color=LogType.ERROR,
                    server_only=True,
                )
            logging.getLogger(__name__).exception("SC_LogReader: _flush_batch crashed")

    def _flush_batch_inner(self) -> None:
        """Inner flush logic, separated so _flush_batch can catch errors."""
        # Check if notifications are paused due to no user engagement
        if self._notifications_paused:
            with self._batch_lock:
                self._notification_batch.clear()
                self._batch_timer = None
            if self.printr:
                self.printr.print(
                    "SC_LogReader: Notifications paused (no user input). Events queued but not sent.",
                    color=LogType.INFO,
                    server_only=True,
                )
            return

        with self._batch_lock:
            if not self._notification_batch:
                return

            events = self._notification_batch.copy()
            self._notification_batch.clear()
            self._batch_timer = None

        # Increment auto-message counter and check threshold before formatting/sending
        self._auto_messages_since_user_input += 1
        if self._auto_messages_since_user_input > self._max_auto_messages:
            self._notifications_paused = True
            if self.printr:
                self.printr.print(
                    f"SC_LogReader: Pausing notifications (sent {self._max_auto_messages} without user input)",
                    color=LogType.WARNING,
                    server_only=True,
                )
            return

        # Format message for AI
        message = self._format_batch_message(events)

        # Send to AI in a dedicated thread with its own event loop.
        # Previous approach used run_coroutine_threadsafe on the main
        # event loop, but notifications silently stopped when the main
        # loop was busy or stale.  PTT uses throwaway event loops per
        # thread and works reliably, so we adopt the same pattern.
        if self.wingman:
            thread = Thread(
                target=self._run_notification,
                args=(message,),
                daemon=True,
            )
            thread.start()

    def _format_batch_message(self, events: list[DerivedEvent]) -> str:
        """Format batch of events for AI notification."""
        if len(events) == 1:
            return (
                "[Game Event | log record, already happened; acknowledge "
                f"briefly, no inference, no actions] {events[0].message}"
            )

        lines = [
            "[Game Events | log records, already happened; acknowledge "
            "briefly, no inference, no actions]"
        ]
        for event in events:
            lines.append(f"- {event.message}")
        return "\n".join(lines)

    def _run_notification(self, message: str) -> None:
        """Send notification in a dedicated thread with its own event loop.

        Mirrors the PTT pattern in wingman_core.py: each notification
        gets a throwaway event loop so it doesn't depend on the main
        loop being responsive.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._send_notification(message))
        except Exception:
            if self.printr:
                self.printr.print(
                    "SC_LogReader: Notification delivery failed — see log",
                    color=LogType.ERROR,
                    server_only=True,
                )
            logging.getLogger(__name__).exception(
                "SC_LogReader: _run_notification failed"
            )
        finally:
            loop.close()

    async def _send_notification(self, message: str) -> None:
        """Send a proactive notification via the wingman's full personality pipeline."""
        if not self.wingman:
            return

        # Process through the wingman's full pipeline (display, personality, TTS)
        await self.wingman.process(transcript=message)

    # -------------------------------------------------------------------------
    # AI Tools
    # -------------------------------------------------------------------------

    def get_tools(self) -> list[tuple[str, dict]]:
        """Return available tools for AI."""
        tools = [
            (
                "get_recent_game_events",
                {
                    "type": "function",
                    "function": {
                        "name": "get_recent_game_events",
                        "description": "Get recent events from the Star Citizen game log",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "count": {
                                    "type": "integer",
                                    "description": "Number of events to retrieve (default 10)",
                                    "default": 10,
                                },
                                "event_type": {
                                    "type": "string",
                                    "description": "Filter by event type",
                                    "enum": [
                                        "contract_accepted",
                                        "contract_complete",
                                        "contract_failed",
                                        "objective_new",
                                        "location_change",
                                        "injury",
                                        "all",
                                    ],
                                },
                            },
                            "required": [],
                        },
                    },
                },
            ),
            (
                "get_current_game_state",
                {
                    "type": "function",
                    "function": {
                        "name": "get_current_game_state",
                        "description": "Get the current game state (location, ship, missions, etc.)",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                },
            ),
            (
                "get_active_missions",
                {
                    "type": "function",
                    "function": {
                        "name": "get_active_missions",
                        "description": "Get all currently active missions/contracts",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                },
            ),
            (
                "get_trade_ledger",
                {
                    "type": "function",
                    "function": {
                        "name": "get_trade_ledger",
                        "description": "Get trade financial summary and per-item profit breakdown",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "time_range": {
                                    "type": "string",
                                    "description": "Time range filter (default: last_12_hours)",
                                    "enum": [
                                        "last_12_hours",
                                        "last_hour",
                                        "today",
                                        "this_week",
                                        "this_month",
                                        "this_year",
                                        "all",
                                    ],
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Filter by category",
                                    "enum": ["item", "commodity", "all"],
                                },
                            },
                            "required": [],
                        },
                    },
                },
            ),
            (
                "get_trade_entries",
                {
                    "type": "function",
                    "function": {
                        "name": "get_trade_entries",
                        "description": "List individual trade ledger entries for a time period",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "time_range": {
                                    "type": "string",
                                    "description": "Time range filter (default: last_12_hours)",
                                    "enum": [
                                        "last_12_hours",
                                        "last_hour",
                                        "today",
                                        "this_week",
                                        "this_month",
                                        "this_year",
                                        "all",
                                    ],
                                },
                                "category": {
                                    "type": "string",
                                    "description": "Filter by category",
                                    "enum": ["item", "commodity", "all"],
                                },
                                "sort_by": {
                                    "type": "string",
                                    "description": "Sort order: 'type' groups purchases first then sales (default), 'time' sorts by most recent first",
                                    "enum": ["type", "time"],
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Max entries to return (default 50, max 200)",
                                    "default": 50,
                                },
                            },
                            "required": [],
                        },
                    },
                },
            ),
            (
                "donate_logs",
                {
                    "type": "function",
                    "function": {
                        "name": "donate_logs",
                        "description": (
                            "Open the Star Citizen log donation UI in the user's browser. "
                            "The donation UI shows a preview of the logs eligible for donation, "
                            "a consent prompt, and an upload progress indicator. "
                            "Nothing is uploaded until the user explicitly confirms."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                },
            ),
        ]
        return tools

    async def execute_tool(
        self,
        tool_name: str,
        parameters: dict,
        benchmark,
    ) -> tuple[str, str]:
        """Execute a tool and return the result."""
        if tool_name == "get_recent_game_events":
            return await self._tool_get_recent_events(parameters)
        if tool_name == "get_current_game_state":
            return await self._tool_get_current_state(parameters)
        if tool_name == "get_active_missions":
            return await self._tool_get_active_missions(parameters)
        if tool_name == "get_trade_ledger":
            return await self._tool_get_trade_ledger(parameters)
        if tool_name == "get_trade_entries":
            return await self._tool_get_trade_entries(parameters)
        if tool_name == "donate_logs":
            return await self._tool_donate_logs(parameters)

        return "", f"Unknown tool: {tool_name}"

    async def _tool_get_recent_events(self, parameters: dict) -> tuple[str, str]:
        """Get recent game events."""
        count = parameters.get("count", 10)
        event_filter = parameters.get("event_type", "all")

        with self._recent_events_lock:
            events = self._recent_events.copy()

        if event_filter != "all":
            events = [e for e in events if e.event_type == event_filter]

        events = events[-count:]

        if not events:
            return "No recent events found.", ""

        lines = []
        for event in events:
            time_str = event.timestamp.strftime("%H:%M:%S")
            lines.append(f"[{time_str}] {event.event_type}: {event.data}")

        return "\n".join(lines), ""

    async def _tool_get_current_state(self, parameters: dict) -> tuple[str, str]:
        """Get current game state."""
        if not self._active_stack:
            return "Log monitor not running.", ""

        state = self._active_stack.logic.get_combined_state()

        if not state:
            return "No state information available.", ""

        lines = []
        for key, value in sorted(state.items()):
            if value is not None:
                lines.append(f"{key}: {value}")

        return "\n".join(lines) if lines else "No state information available.", ""

    async def _tool_get_active_missions(self, parameters: dict) -> tuple[str, str]:
        """Get active missions."""
        if not self._active_stack:
            return "Log monitor not running.", ""

        missions = self._active_stack.logic.get_active_missions()

        if not missions:
            return "No active missions.", ""

        lines = []
        for mission_id, info in missions.items():
            name = info.get("mission_name", "Unknown")
            objective = info.get("current_objective", "None")
            lines.append(f"- {name}")
            short_id = mission_id[:8] + ("..." if len(mission_id) > 8 else "")
            lines.append(f"  ID: {short_id}")
            lines.append(f"  Objective: {objective}")

        return "\n".join(lines), ""

    async def _tool_donate_logs(self, parameters: dict) -> tuple[str, str]:
        """Open the log donation UI in the user's default browser."""
        if self._donor_window is None or self._donor_server is None:
            return "Donation UI is unavailable. Check the skill logs for details.", ""
        if not self._donor_server.is_running:
            return (
                "Donation UI server is not running. Check the skill logs for details.",
                "",
            )
        self._donor_window.open()
        return f"Opened the donation UI at {self._donor_server.url}.", ""

    # -------------------------------------------------------------------------
    # Trade Ledger Tools
    # -------------------------------------------------------------------------

    def _resolve_time_range(self, time_range: str) -> datetime | None:
        """Convert a time_range enum to a start datetime."""
        from datetime import timedelta

        now = datetime.now()
        if time_range == "last_12_hours":
            return now - timedelta(hours=12)
        if time_range == "last_hour":
            return now - timedelta(hours=1)
        if time_range == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if time_range == "this_week":
            return (now - timedelta(days=now.weekday())).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
        if time_range == "this_month":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if time_range == "this_year":
            return now.replace(
                month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        return None  # "all"

    async def _tool_get_trade_ledger(self, parameters: dict) -> tuple[str, str]:
        """Get trade financial summary and per-item profit breakdown."""
        if not self._active_stack:
            return "Trade data not available.", ""

        time_range = parameters.get("time_range", "last_12_hours")
        category = parameters.get("category", "all")
        start = self._resolve_time_range(time_range)

        entries = self._active_stack.event_log.query(
            event_type=["shop_buy", "shop_sell", "commodity_buy", "commodity_sell"],
            start=start,
            limit=10000,
        )

        if category != "all":
            entries = [e for e in entries if e.data.get("category") == category]

        if not entries:
            return f"No trades found ({time_range}).", ""

        total_purchases = 0.0
        total_sales = 0.0
        by_item: dict[str, dict] = {}

        for e in entries:
            d = e.data
            key = d.get("item_name") or d.get("item_guid", "unknown")
            if key not in by_item:
                by_item[key] = {
                    "bought": 0.0, "sold": 0.0, "net": 0.0,
                    "qty_bought": 0, "qty_sold": 0,
                    "category": d.get("category", "item"),
                    "quantity_unit": d.get("quantity_unit", "units"),
                }
            price = d.get("price", 0.0)
            qty = d.get("quantity", 0)
            if d.get("transaction") == "purchase":
                total_purchases += price
                by_item[key]["bought"] += price
                by_item[key]["net"] -= price
                by_item[key]["qty_bought"] += qty
            else:
                total_sales += price
                by_item[key]["sold"] += price
                by_item[key]["net"] += price
                by_item[key]["qty_sold"] += qty

        label = time_range.replace("_", " ").title()
        lines = [
            f"Trade Summary ({label}):",
            f"{len(entries)} transactions"
            f" | Spent: {total_purchases:,.0f} aUEC"
            f" | Earned: {total_sales:,.0f} aUEC"
            f" | Net: {total_sales - total_purchases:+,.0f} aUEC",
            "",
            "Per Item/Commodity:",
        ]

        for name, info in by_item.items():
            unit = info.get("quantity_unit", "units")
            unit_label = unit.upper() if unit != "units" else "x"
            parts = []
            if info["qty_bought"]:
                if unit_label == "x":
                    parts.append(
                        f"Bought {info['qty_bought']}{unit_label}"
                        f" for {info['bought']:,.0f}"
                    )
                else:
                    parts.append(
                        f"Bought {info['qty_bought']:,.0f} {unit_label}"
                        f" for {info['bought']:,.0f}"
                    )
            if info["qty_sold"]:
                if unit_label == "x":
                    parts.append(
                        f"Sold {info['qty_sold']}{unit_label} for {info['sold']:,.0f}"
                    )
                else:
                    parts.append(
                        f"Sold {info['qty_sold']:,.0f} {unit_label}"
                        f" for {info['sold']:,.0f}"
                    )
            parts.append(f"Net: {info['net']:+,.0f}")
            lines.append(f"- {name}: {' | '.join(parts)}")

        return "\n".join(lines), ""

    async def _tool_get_trade_entries(self, parameters: dict) -> tuple[str, str]:
        """List individual trade entries."""
        if not self._active_stack:
            return "Trade data not available.", ""

        time_range = parameters.get("time_range", "last_12_hours")
        category = parameters.get("category", "all")
        sort_by = parameters.get("sort_by", "type")
        limit = min(parameters.get("limit", 50), 200)

        start = self._resolve_time_range(time_range)

        entries: list[EventLogEntry] = self._active_stack.event_log.query(
            event_type=["shop_buy", "shop_sell", "commodity_buy", "commodity_sell"],
            start=start,
            limit=limit + 1,
        )

        if category != "all":
            entries = [e for e in entries if e.data.get("category") == category]

        if not entries:
            return f"No trades found ({time_range}).", ""

        has_more = len(entries) > limit
        entries = entries[:limit]

        if sort_by == "type":
            purchases = [e for e in entries if e.data.get("transaction") == "purchase"]
            sales = [e for e in entries if e.data.get("transaction") == "sale"]
            entries = purchases + sales

        label = time_range.replace("_", " ").title()
        shown = len(entries)
        header = f"Trade Entries ({label})"
        if has_more:
            header += f" — showing {shown} of {shown}+ entries"

        lines = [f"{header}:"]
        for e in entries:
            d = e.data
            ts = e.timestamp[11:19] if len(e.timestamp) > 19 else e.timestamp
            tx = "PURCHASE" if d.get("transaction") == "purchase" else "SALE    "
            qty = d.get("quantity", 0)
            price = d.get("price", 0.0)

            if d.get("category") == "item":
                desc = f"{d.get('item_name') or d.get('item_guid', '')} x{qty}"
            else:
                unit = d.get("quantity_unit", "scu").upper()
                desc = f"{d.get('item_guid', '')[:8]} (commodity) {qty:,.0f} {unit}"

            lines.append(
                f"[{ts}] {tx} | {e.location}"
                f" | {desc} | {price:,.0f} aUEC"
                f" | Shop: {d.get('shop_name', '')}"
            )

        return "\n".join(lines), ""

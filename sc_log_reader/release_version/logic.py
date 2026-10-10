"""
SC_LogReader - Layer 2: State Logic

Combines atomic states from Layer 3 into derived states and events.
Can run standalone or be imported by Layer 1.

Author: Mallachi
"""

from __future__ import annotations

import copy
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from debug_emitter import emit as _debug_emit
from atomic_io import atomic_write_text
from event_log import EventLog, EventLogEntry
from parser import LogEvent, LogParser


logger = logging.getLogger(__name__)

_ZERO_MISSION_ID = "00000000-0000-0000-0000-000000000000"
_REWARD_COMPONENT_EVENTS = frozenset({"reward_earned", "blueprint_received"})


@dataclass
class DerivedEvent:
    """Represents a derived event produced by combining atomic states."""

    event_type: str
    timestamp: datetime
    message: str
    source_states: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "source_states": self.source_states,
        }


@dataclass
class Rule:
    """
    Declarative rule for deriving events from state combinations.

    A rule fires when:
    1. The trigger_key changes (if specified)
    2. All conditions are satisfied
    """

    name: str
    event_type: str
    message_template: str
    trigger_key: str | None = None  # State key that triggers evaluation
    conditions: list[tuple[str, str, Any]] | None = None  # [(key, op, value), ...]

    def evaluate(
        self,
        states: dict[str, Any],
        changed_key: str | None = None,
    ) -> bool:
        """Check if the rule should fire given current states."""
        # If rule has a trigger, only evaluate when that key changes
        if self.trigger_key and changed_key != self.trigger_key:
            return False

        # Check all conditions
        if self.conditions:
            for key, op, expected in self.conditions:
                actual = states.get(key)
                if not self._check_condition(actual, op, expected):
                    return False

        return True

    def _check_condition(self, actual: Any, op: str, expected: Any) -> bool:
        """Evaluate a single condition."""
        if op == "==":
            return actual == expected
        if op == "!=":
            return actual != expected
        if op == "is":
            return actual is expected
        if op == "is_not":
            return actual is not expected
        if op == "in":
            return actual in expected
        if op == "not_in":
            return actual not in expected
        if op == "exists":
            return actual is not None
        if op == "not_exists":
            return actual is None
        return False

    def format_message(self, states: dict[str, Any]) -> str:
        """Generate the event message using current states."""
        try:
            return self.message_template.format(**states)
        except KeyError:
            return self.message_template


class StateLogic:
    """
    Combines atomic states into derived states and events.

    Subscribes to Layer 3 (LogParser) for state changes and raw events.
    Evaluates rules to produce derived events for Layer 1.
    """

    def __init__(self, parser: LogParser) -> None:
        self._parser = parser
        self._rules: list[Rule] = []
        self._derived_state: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._event_subscribers: list[Callable[[DerivedEvent], None]] = []
        self._raw_event_subscribers: list[Callable[[LogEvent], None]] = []

        # File output (optional)
        self._file_output_enabled = False
        self._file_output_path: Path | None = None
        self._event_history: list[dict[str, Any]] = []

        # Mission tracking
        self._active_missions: dict[str, dict[str, Any]] = {}

        # Hangar sequencing: tracks context when hangar_ready fires.
        # None = no pending hangar event
        self._pending_hangar: str | None = None  # unused; kept for save_state compat

        # Location arrival dedup: suppress consecutive same-location events
        # (e.g. two location_change Orison without leaving first).
        # Resets when a *different* location fires.
        self._last_arrived_location: str | None = None

        # Trade: pending item shop transactions awaiting confirmation
        self._pending_transactions: list[dict] = []
        self._recent_trade_confirmations: list[datetime] = []
        self._recent_reward_fingerprints: dict[str, datetime] = {}
        self._pending_reward_bundles: dict[str, dict[str, Any]] = {}
        self._reward_bundle_timer: threading.Timer | None = None
        self._reward_bundle_window_seconds = 10.0
        self._reward_context_window_seconds = 15.0
        self._last_completed_mission: dict[str, Any] | None = None
        self._event_log: EventLog | None = None
        # Timestamp of the raw event currently being processed — used so that
        # derived events inherit the source log timestamp rather than local clock.
        self._current_event_ts: datetime | None = None
        # Stale pending cleanup interval (seconds)
        self._pending_max_age_seconds = 10.0

        # Setup default rules
        self._setup_default_rules()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def start(self) -> None:
        """Start listening to Layer 3."""
        self._parser.subscribe(self._on_raw_event)
        self._parser.subscribe_state(self._on_state_change)
        logger.info("StateLogic started")

    def stop(self) -> None:
        """Stop and flush outputs."""
        self._flush_reward_bundles()
        self._flush_file_output()
        logger.info("StateLogic stopped")

    def subscribe(self, callback: Callable[[DerivedEvent], None]) -> None:
        """Subscribe to derived events."""
        self._event_subscribers.append(callback)

    def subscribe_raw(self, callback: Callable[[LogEvent], None]) -> None:
        """Subscribe to raw events from Layer 3 (pass-through)."""
        self._raw_event_subscribers.append(callback)

    def get_derived_state(self, key: str | None = None) -> dict[str, Any] | Any:
        """Get derived state. If key provided, returns that value; else returns all."""
        with self._lock:
            if key is None:
                return self._derived_state.copy()
            return self._derived_state.get(key)

    def get_combined_state(self) -> dict[str, Any]:
        """Get both atomic (from parser) and derived states combined."""
        atomic = self._parser.get_state()
        with self._lock:
            derived = self._derived_state.copy()
        return {**atomic, **derived}

    def get_active_missions(self) -> dict[str, dict[str, Any]]:
        """Get currently tracked missions (deep copy for safety)."""
        with self._lock:
            return copy.deepcopy(self._active_missions)

    def set_event_log(self, event_log: EventLog) -> None:
        """Inject the event log (called by main.py during init)."""
        self._event_log = event_log

    def add_rule(self, rule: Rule) -> None:
        """Add a custom rule."""
        self._rules.append(rule)

    def save_state(self) -> dict[str, Any]:
        """Return logic state as a serializable dict for persistence."""
        with self._lock:
            return {
                "active_missions": copy.deepcopy(self._active_missions),
                "derived_state": self._derived_state.copy(),
                "pending_hangar": self._pending_hangar,
                "pending_transactions": copy.deepcopy(self._pending_transactions),
            }

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore logic state from persisted data."""
        with self._lock:
            self._active_missions = data.get("active_missions", {})
            self._derived_state = data.get("derived_state", {})
            # Migrate legacy bool format to new str | None format
            raw = data.get("pending_hangar")
            if raw is True:
                self._pending_hangar = "hangar_access"
            elif isinstance(raw, str):
                self._pending_hangar = raw
            else:
                self._pending_hangar = None
            self._pending_transactions = data.get("pending_transactions", [])

    def on_new_session(self) -> None:
        """Clear mission-related state on new game session.

        Called when session_start is detected. Clears mission tracking,
        pending transactions, and mission-related parser states. Other state
        (location, ship, etc.) is preserved since it persists in the game
        between sessions. The trade ledger is never cleared.
        """
        self._flush_reward_bundles()

        with self._lock:
            self._active_missions.clear()
            self._derived_state["active_mission_count"] = 0
            self._pending_transactions.clear()
            self._pending_reward_bundles.clear()
            self._recent_reward_fingerprints.clear()
            self._last_completed_mission = None

        # Clear mission-related parser states
        mission_state_keys = [
            "current_objective",
            "last_contract_accepted",
            "last_contract_accepted_id",
            "last_contract_completed",
            "last_contract_completed_id",
            "last_contract_failed",
            "last_contract_failed_id",
        ]
        for key in mission_state_keys:
            self._parser.clear_state(key)

        # Clear injury state — session_start fires on respawn, player spawns fully healed
        for key in list(self._parser.get_state().keys()):
            if key.startswith("injury_"):
                self._parser.clear_state(key)

        logger.info("New session: mission and injury state cleared")

    def enable_file_output(self, path: str | Path) -> None:
        """Enable JSON file output for debugging."""
        self._file_output_path = Path(path)
        self._file_output_enabled = True
        logger.info("StateLogic file output enabled: %s", self._file_output_path)

    def disable_file_output(self) -> None:
        """Disable JSON file output."""
        self._flush_file_output()
        self._file_output_enabled = False
        self._file_output_path = None

    # -------------------------------------------------------------------------
    # Injury Helpers
    # -------------------------------------------------------------------------

    def _has_active_injuries(self) -> bool:
        """Check if any injury_* state key has a non-None value."""
        state = self._parser.get_state()
        return any(v is not None for k, v in state.items() if k.startswith("injury_"))

    def _get_active_injuries(self) -> dict[str, str]:
        """Return {body_part: severity} for all active injuries."""
        state = self._parser.get_state()
        injuries: dict[str, str] = {}
        for k, v in state.items():
            if k.startswith("injury_") and v is not None:
                part = k[len("injury_"):]
                injuries[part] = v
        return injuries

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    # Internal events that are pipeline mechanics, not real game events.
    # Trade request events (shop_buy/sell, commodity_buy/sell) are also excluded
    # here because the confirmed versions are written by _write_to_event_log_trade.
    _EVENT_LOG_SKIP: frozenset[str] = frozenset({
        "_money_sent_partial",
        "shop_transaction_result",
        "shop_buy",
        "shop_sell",
        "commodity_buy",
        "commodity_sell",
    })

    def _on_raw_event(self, event: LogEvent) -> None:
        """Handle raw events from Layer 3."""
        self._current_event_ts = event.timestamp

        # Flush complete reward bundles before appending the next unrelated row.
        # EventLog restart dedup assumes append order follows timestamp order.
        if event.event_type not in _REWARD_COMPONENT_EVENTS:
            self._flush_reward_bundles()

        # New session — clear mission tracking
        if event.event_type == "session_start":
            self.on_new_session()

        # Track missions
        self._track_mission(event)

        # Track trade transactions
        self._on_trade_event(event)

        # Handle event-based derived events (not state-based)
        self._handle_event_derived(event)

        # Update derived states based on events
        self._update_derived_state(event)

        # Write to event log — trade events are written at confirmation point,
        # internal accumulator events are skipped entirely.
        if (
            self._event_log is not None
            and event.event_type not in self._EVENT_LOG_SKIP
        ):
            self._write_raw_to_event_log(event)

        # Forward to subscribers
        for callback in self._raw_event_subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in raw event callback")

    def _handle_event_derived(self, event: LogEvent) -> None:
        """Generate derived events from raw events (not state-based)."""
        if event.event_type == "hangar_ready":
            self._emit_derived_event(
                "hangar_access",
                "Hangar access granted",
                {},
            )

        # Location arrival — event-driven so leaving A → B → A still fires.
        # But consecutive same-location events (without leaving) are suppressed.
        if event.event_type == "location_change":
            location_name = self._parser.get_state("location_name")
            if location_name and location_name != "INVALID LOCATION ID":
                if location_name != self._last_arrived_location:
                    self._last_arrived_location = location_name
                    self._emit_derived_event(
                        "location_arrived",
                        f"Arrived at: {location_name}",
                        {"location_name": location_name},
                    )

        # Station departure — disabled pending reliable log signal.
        # AImodule_ATC removed in PTU; replacement fires on terminal use.
        # if event.event_type == "station_departed":
        #     self._last_arrived_location = None
        #     self._emit_derived_event(
        #         "location",
        #         "Departed station",
        #         {},
        #     )

    def _on_state_change(self, key: str, old_value: Any, new_value: Any) -> None:
        """Handle state changes from Layer 3 and evaluate rules."""
        # Flush pending reward bundles before state-derived event-log rows.
        if self._pending_reward_bundles:
            self._flush_reward_bundles()

        # Injury reminder: fire whenever the player enters any armistice zone
        # (direct entry or returning from a hangar), so they don't forget to heal.
        if key == "in_armistice" and new_value is True:
            injuries = self._get_active_injuries()
            if injuries:
                parts = ", ".join(
                    f"{severity} ({part})" for part, severity in injuries.items()
                )
                self._emit_derived_event(
                    "health_injury_reminder",
                    f"Injury reminder: {parts}",
                    {"active_injuries": injuries},
                )

        current_states = self.get_combined_state()

        for rule in self._rules:
            if rule.evaluate(current_states, changed_key=key):
                self._fire_rule(rule, current_states)

    def _fire_rule(self, rule: Rule, states: dict[str, Any]) -> None:
        """Fire a rule and produce a derived event."""
        _debug_emit(
            "logic",
            "rule_fired",
            {
                "rule": rule.name,
                "event_type": rule.event_type,
                "message": rule.format_message(states),
                "conditions": [
                    {"key": k, "op": op, "expected": v, "actual": states.get(k)}
                    for k, op, v in (rule.conditions or [])
                ],
            },
        )

        event = DerivedEvent(
            event_type=rule.event_type,
            timestamp=self._current_event_ts or datetime.now(timezone.utc).replace(tzinfo=None),
            message=rule.format_message(states),
            source_states={k: states.get(k) for k in self._get_rule_keys(rule)},
        )

        # Record for file output
        if self._file_output_enabled:
            self._event_history.append(event.to_dict())
            if len(self._event_history) % 10 == 0:
                self._flush_file_output()

        # Write to event log
        if self._event_log is not None:
            self._write_derived_to_event_log(event)

        # Notify subscribers
        for callback in self._event_subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in derived event callback")

    def _get_rule_keys(self, rule: Rule) -> list[str]:
        """Extract state keys referenced by a rule."""
        keys = []
        if rule.trigger_key:
            keys.append(rule.trigger_key)
        if rule.conditions:
            keys.extend(key for key, _, _ in rule.conditions)
        return keys

    def _emit_derived_event(
        self,
        event_type: str,
        message: str,
        source_states: dict[str, Any],
        source_ts: datetime | None = None,
    ) -> None:
        """Emit a derived event to all subscribers."""
        event = DerivedEvent(
            event_type=event_type,
            timestamp=source_ts or self._current_event_ts or datetime.now(timezone.utc).replace(tzinfo=None),
            message=message,
            source_states=source_states,
        )

        _debug_emit(
            "logic",
            "derived_event",
            {
                "event_type": event_type,
                "message": message,
                "source_states": source_states,
            },
        )

        # Record for file output
        if self._file_output_enabled:
            self._event_history.append(event.to_dict())
            if len(self._event_history) % 10 == 0:
                self._flush_file_output()

        # Write to event log
        if self._event_log is not None:
            self._write_derived_to_event_log(event)

        # Notify subscribers
        for callback in self._event_subscribers:
            try:
                callback(event)
            except Exception:
                logger.exception("Error in derived event callback")

    # -------------------------------------------------------------------------
    # Mission Tracking
    # -------------------------------------------------------------------------

    def _track_mission(self, event: LogEvent) -> None:
        """Track mission lifecycle and generate derived events."""
        data = event.data
        mission_id = data.get("mission_id")

        if event.event_type == "contract_accepted" and mission_id:
            mission_name = data.get("mission_name", "Unknown")
            with self._lock:
                self._active_missions[mission_id] = {
                    "mission_name": mission_name,
                    "status": "active",
                    "accepted_at": event.timestamp.isoformat(),
                    "current_objective": None,
                }
                self._derived_state["active_mission_count"] = len(self._active_missions)
            # Generate derived event for notification
            self._emit_derived_event(
                "mission_accepted",
                f"Contract accepted: {mission_name}",
                {"mission_name": mission_name, "mission_id": mission_id},
            )

        elif event.event_type == "objective_new" and mission_id:
            objective = data.get("objective", "Unknown")
            with self._lock:
                if mission_id in self._active_missions:
                    self._active_missions[mission_id]["current_objective"] = objective
            # Generate derived event for notification
            self._emit_derived_event(
                "mission_objective_new",
                f"New objective: {objective}",
                {"objective": objective, "mission_id": mission_id},
            )

        elif event.event_type == "contract_complete" and mission_id:
            mission_name = data.get("mission_name", "Unknown")
            with self._lock:
                if mission_id in self._active_missions:
                    mission_name = self._active_missions[mission_id].get(
                        "mission_name", mission_name
                    )
                    del self._active_missions[mission_id]
                    self._derived_state["active_mission_count"] = len(
                        self._active_missions
                    )
            if self._is_valid_mission_id(mission_id):
                with self._lock:
                    self._last_completed_mission = {
                        "mission_id": mission_id,
                        "mission_name": mission_name,
                        "timestamp": event.timestamp,
                    }

            # Generate derived event for notification
            self._emit_derived_event(
                "mission_complete",
                f"Contract complete: {mission_name}",
                {"mission_name": mission_name, "mission_id": mission_id},
            )

        elif event.event_type == "contract_failed" and mission_id:
            mission_name = data.get("mission_name", "Unknown")
            with self._lock:
                if mission_id in self._active_missions:
                    mission_name = self._active_missions[mission_id].get(
                        "mission_name", mission_name
                    )
                    del self._active_missions[mission_id]
                    self._derived_state["active_mission_count"] = len(
                        self._active_missions
                    )
            # Generate derived event for notification
            self._emit_derived_event(
                "mission_failed",
                f"Contract failed: {mission_name}",
                {"mission_name": mission_name, "mission_id": mission_id},
            )

    # -------------------------------------------------------------------------
    # Trade Ledger
    # -------------------------------------------------------------------------

    def _on_trade_event(self, event: LogEvent) -> None:
        """Handle shop and commodity trade events."""
        et = event.event_type

        if et in ("shop_buy", "shop_sell"):
            # Item shop: store as pending until confirmed.
            # Use datetime.now() for staleness tracking — event.timestamp
            # is UTC from the log, but _cleanup_stale_pending compares
            # against datetime.now() (local time).
            with self._lock:
                self._cleanup_stale_pending()

                # Deduplicate: game sometimes logs the same request twice.
                # Skip if an identical pending already exists.
                shop_id = event.data.get("shop_id", "")
                kiosk_id = event.data.get("kiosk_id", "")
                item_key = event.data.get(
                    "item_guid", event.data.get("resource_guid", "")
                )
                already_pending = any(
                    p["event_type"] == et
                    and p["data"].get("shop_id") == shop_id
                    and p["data"].get("kiosk_id") == kiosk_id
                    and p["data"].get("item_guid", p["data"].get("resource_guid", ""))
                    == item_key
                    for p in self._pending_transactions
                )
                if already_pending:
                    logger.info(
                        "Trade: skipping duplicate pending %s (shop=%s kiosk=%s)",
                        et,
                        shop_id,
                        kiosk_id,
                    )
                else:
                    self._pending_transactions.append(
                        {
                            "event_type": et,
                            "received_at": datetime.now().isoformat(),
                            "event_timestamp": event.timestamp.isoformat(),
                            "data": event.data.copy(),
                        }
                    )
                    logger.info(
                        "Trade: stored pending %s (shop=%s kiosk=%s) — %d pending",
                        et,
                        shop_id,
                        kiosk_id,
                        len(self._pending_transactions),
                    )

        elif et in ("commodity_buy", "commodity_sell"):
            # Commodity: write immediately (no confirmation log pattern)
            logger.info("Trade: immediate write for %s", et)
            self._write_trade_to_event_log(et, event.data, event.timestamp)

        elif et == "shop_transaction_result":
            self._resolve_pending_transaction(event)

    def _resolve_pending_transaction(self, event: LogEvent) -> None:
        """Match a shop_transaction_result to a pending request and write to ledger."""
        data = event.data
        result = data.get("result", "")
        tx_type = data.get("transaction_type", "")
        shop_id = data.get("shop_id", "")
        kiosk_id = data.get("kiosk_id", "")
        player_id = data.get("player_id", "")

        expected_type = {
            "Buying": "shop_buy",
            "Selling": "shop_sell",
        }.get(tx_type)

        pending: dict | None = None
        match_quality = ""

        with self._lock:
            self._cleanup_stale_pending()
            logger.info(
                "Trade: resolving %s result=%s shop=%s kiosk=%s player=%s - %d pending",
                tx_type or data.get("source_provider", "unknown"),
                result,
                shop_id,
                kiosk_id,
                player_id,
                len(self._pending_transactions),
            )

            # Old ShopUIProvider confirmations include type/shop/kiosk. Prefer
            # that exact match whenever the log provides it.
            if expected_type and shop_id and kiosk_id:
                for i in range(len(self._pending_transactions) - 1, -1, -1):
                    candidate = self._pending_transactions[i]
                    p_data = candidate["data"]
                    if (
                        candidate["event_type"] == expected_type
                        and p_data.get("shop_id") == shop_id
                        and p_data.get("kiosk_id") == kiosk_id
                    ):
                        pending = self._pending_transactions.pop(i)
                        match_quality = "shop_kiosk"
                        break

            # June 2026 ShoppingProvider confirmations often only carry
            # playerId/result. In that dialect, match the most recent compatible
            # pending request for the same player.
            if pending is None:
                for i in range(len(self._pending_transactions) - 1, -1, -1):
                    candidate = self._pending_transactions[i]
                    p_data = candidate["data"]
                    if expected_type and candidate["event_type"] != expected_type:
                        continue
                    if candidate["event_type"] not in ("shop_buy", "shop_sell"):
                        continue
                    if player_id and p_data.get("player_id") != player_id:
                        continue
                    if shop_id and p_data.get("shop_id") != shop_id:
                        continue
                    if kiosk_id and p_data.get("kiosk_id") != kiosk_id:
                        continue
                    pending = self._pending_transactions.pop(i)
                    match_quality = "player_recent"
                    break

        if pending is None:
            logger.warning(
                "Trade: no matching pending for tx_type=%r shop=%s kiosk=%s player=%s",
                tx_type,
                shop_id,
                kiosk_id,
                player_id,
            )
            return

        if result == "Success":
            confirmed_data = pending["data"].copy()
            confirmed_data["confirmation_result"] = result
            confirmed_data["confirmation_source_provider"] = data.get(
                "source_provider", ""
            )
            confirmed_data["confirmation_match"] = match_quality
            logger.info("Trade: match found (%s), writing to event log", match_quality)
            self._write_trade_to_event_log(
                pending["event_type"],
                confirmed_data,
                event.timestamp,
            )
        else:
            logger.info("Trade: match found but result=%s, discarding", result)

    def _write_trade_to_event_log(
        self,
        event_type: str,
        data: dict,
        timestamp: datetime,
    ) -> None:
        """Write a confirmed trade event to the event log - single source of truth."""
        if not self._event_log:
            logger.warning("Trade: _write_trade_to_event_log called but event_log is None")
            return

        location = self._parser.get_state("location_name") or ""
        player_name = self._parser.get_state("player_name") or ""

        if event_type in ("shop_buy", "shop_sell"):
            transaction = "purchase" if event_type == "shop_buy" else "sale"
            movement_verb = "bought" if event_type == "shop_buy" else "sold"
            category = "item"
            item_name = data.get("item_name")
            item_guid = data.get("item_guid", "")
            price = data.get("price", 0.0)
            quantity = data.get("quantity", 1)
            quantity_unit = "units"
            confidence = "high" if data.get("confirmation_match") == "shop_kiosk" else "medium"
            source_events = [event_type, "shop_transaction_result"]
        elif event_type == "commodity_buy":
            transaction = "purchase"
            movement_verb = "bought"
            category = "commodity"
            item_name = None
            item_guid = data.get("resource_guid", "")
            price = data.get("price", 0.0)
            quantity = data.get("quantity_cscu", 0.0) / 100.0
            quantity_unit = "scu"
            confidence = "medium"
            source_events = [event_type]
        elif event_type == "commodity_sell":
            transaction = "sale"
            movement_verb = "sold"
            category = "commodity"
            item_name = None
            item_guid = data.get("resource_guid", "")
            price = data.get("price", 0.0)
            quantity = data.get("quantity", 0)
            quantity_unit = "scu"
            confidence = "medium"
            source_events = [event_type]
        else:
            return

        amount_auec = -price if transaction == "purchase" else price
        fingerprint = "|".join(
            str(part)
            for part in (
                "trade",
                event_type,
                data.get("player_id", ""),
                data.get("shop_id", ""),
                data.get("kiosk_id", ""),
                item_guid,
                price,
                quantity,
                timestamp.isoformat(timespec="seconds"),
            )
        )

        entry = EventLogEntry(
            timestamp=timestamp.isoformat(),
            event_type=event_type,
            location=location,
            player_name=player_name,
            data={
                "transaction": transaction,
                "category": category,
                "item_name": item_name,
                "item_guid": item_guid,
                "price": price,
                "quantity": quantity,
                "quantity_unit": quantity_unit,
                "player_id": data.get("player_id", ""),
                "shop_id": data.get("shop_id", ""),
                "kiosk_id": data.get("kiosk_id", ""),
                "shop_name": data.get("shop_name", ""),
                "source_provider": data.get("source_provider", ""),
                "currency_type": data.get("currency_type", ""),
                "confirmation_match": data.get("confirmation_match", ""),
                "confirmation_result": data.get("confirmation_result", ""),
                "confirmation_source_provider": data.get(
                    "confirmation_source_provider", ""
                ),
            },
            amount_auec=amount_auec,
            item_name=item_name,
            movement_category="economy",
            movement_verb=movement_verb,
            confidence=confidence,
            fingerprint=fingerprint,
            source_events=source_events,
        )
        self._event_log.append(entry)
        self._remember_trade_confirmation(timestamp)
        logger.info(
            "Trade: event log entry written - %s %s %s at %s",
            transaction,
            category,
            item_name or item_guid,
            location,
        )

    def _remember_trade_confirmation(self, timestamp: datetime) -> None:
        self._recent_trade_confirmations.append(timestamp)
        cutoff = timestamp - timedelta(seconds=3)
        self._recent_trade_confirmations = [
            ts for ts in self._recent_trade_confirmations if ts >= cutoff
        ]

    def _is_recent_trade_confirmation(self, timestamp: datetime) -> bool:
        cutoff = timestamp - timedelta(seconds=3)
        self._recent_trade_confirmations = [
            ts for ts in self._recent_trade_confirmations if ts >= cutoff
        ]
        return any(
            0 <= (timestamp - ts).total_seconds() <= 3
            for ts in self._recent_trade_confirmations
        )

    def _write_raw_to_event_log(self, event: LogEvent) -> None:
        """Write a raw (non-trade) event to the event log with normalised fields."""
        amount_auec: float | None = None
        item_name: str | None = None
        movement_category: str | None = None
        movement_verb: str | None = None
        confidence: str | None = None
        # Resolved once for reward_earned (see below) and reused for both the
        # persisted entry and the reward-bundle accumulator, so the two can
        # never disagree on mission_id.
        reward_context: dict[str, Any] | None = None
        et = event.event_type

        if et == "transaction_complete" and self._is_recent_trade_confirmation(
            event.timestamp
        ):
            return

        if et in _REWARD_COMPONENT_EVENTS:
            self._flush_reward_bundles_if_incompatible(event)

        if et == "reward_earned":
            raw_amount = event.data.get("amount")
            if raw_amount is not None:
                try:
                    amount_auec = float(raw_amount)
                except (ValueError, TypeError):
                    pass
            item_name = event.data.get("item_name")
            movement_category = "economy"
            movement_verb = "rewarded"
            confidence = "high" if amount_auec is not None or item_name else "medium"
            # Resolve the mission context ONCE here (embedded mission_id, else
            # recent contract_complete correlation, else unresolved) so the
            # entry written below and the mission_reward bundle it feeds both
            # see the identical resolved mission_id/mission_name.
            reward_context = self._reward_context_for_event(event)

        elif et == "transaction_complete":
            movement_category = "economy"
            movement_verb = "transaction_completed"
            confidence = "low"

        elif et == "fined":
            raw_amount = event.data.get("amount")
            if raw_amount is not None:
                try:
                    amount_auec = -float(raw_amount)
                except (ValueError, TypeError):
                    pass
            movement_category = "reputation"
            movement_verb = "fined"
            confidence = "medium"

        elif et == "money_sent":
            raw_amount = event.data.get("amount")
            if raw_amount is not None:
                try:
                    amount_auec = -float(raw_amount)
                except (ValueError, TypeError):
                    pass
            movement_category = "economy"
            movement_verb = "sent"
            confidence = "medium"

        elif et == "attachment_received":
            item_name = event.data.get("item_short_name")
            movement_category = "inventory"
            movement_verb = "attached"
            confidence = "medium"

        elif et == "cargo_transfer":
            movement_category = "inventory"
            movement_verb = "transferred"
            confidence = "medium"

        elif et == "blueprint_received":
            item_name = event.data.get("blueprint_name")
            movement_category = "inventory"
            movement_verb = "received"
            confidence = "high"

        elif et in {
            "contract_accepted",
            "contract_complete",
            "contract_failed",
            "objective_new",
            "objective_complete",
            "objective_withdrawn",
        }:
            movement_category = "work"
            movement_verb = {
                "contract_accepted": "accepted",
                "contract_complete": "completed",
                "contract_failed": "failed",
                "objective_new": "objective_added",
                "objective_complete": "objective_completed",
                "objective_withdrawn": "objective_withdrawn",
            }[et]
            confidence = "high"

        elif et in {
            "location_change",
            "armistice_zone",
            "restricted_area",
            "jurisdiction_change",
            "entered_monitored_space",
            "exited_monitored_space",
            "quantum_route_set",
            "qt_arrived",
            "hangar_ready",
            "hangar_queue",
            "channel_change",
        }:
            movement_category = "area"
            movement_verb = self._area_movement_verb(event)
            confidence = "medium"

        elif et == "crimestat_increased":
            movement_category = "reputation"
            movement_verb = "crimestat_increased"
            confidence = "medium"

        fingerprint = self._raw_event_fingerprint(event)
        if et == "reward_earned" and self._is_duplicate_reward(
            fingerprint,
            event.timestamp,
        ):
            return

        entry_data = event.data.copy()
        if et == "reward_earned" and reward_context is not None:
            # Stamp the SAME resolved mission_id/mission_name the bundle will
            # carry (see reward_context resolution above), so a downstream
            # consumer reconciling this component against its mission_reward
            # bundle can match on mission_id instead of time alone.
            entry_data["mission_id"] = reward_context.get("mission_id", "")
            entry_data["mission_name"] = reward_context.get("mission_name", "")

        log_entry = EventLogEntry(
            timestamp=event.timestamp.isoformat(),
            event_type=et,
            location=self._parser.get_state("location_name") or "",
            player_name=self._parser.get_state("player_name") or "",
            data=entry_data,
            amount_auec=amount_auec,
            item_name=item_name,
            movement_category=movement_category,
            movement_verb=movement_verb,
            confidence=confidence,
            fingerprint=fingerprint,
            source_events=[et],
        )
        self._event_log.append(log_entry)
        if et in _REWARD_COMPONENT_EVENTS:
            self._record_reward_component(event, log_entry, context=reward_context)


    def _is_valid_mission_id(self, mission_id: Any) -> bool:
        """Return True for usable CIG mission IDs."""
        return bool(mission_id) and str(mission_id) != _ZERO_MISSION_ID

    def _reward_context_for_event(self, event: LogEvent) -> dict[str, Any]:
        """Find the best mission context for a reward component."""
        mission_id = event.data.get("mission_id", "")
        if self._is_valid_mission_id(mission_id):
            return {
                "mission_id": mission_id,
                "mission_name": event.data.get("mission_name", ""),
                "correlation": "mission_id",
                "confidence": "high",
            }

        recent = self._last_completed_mission
        if recent:
            recent_ts = recent.get("timestamp")
            if isinstance(recent_ts, datetime):
                age = (event.timestamp - recent_ts).total_seconds()
                if 0 <= age <= self._reward_context_window_seconds:
                    return {
                        "mission_id": recent.get("mission_id", ""),
                        "mission_name": recent.get("mission_name", ""),
                        "correlation": "recent_contract_complete",
                        "confidence": "medium",
                    }

        return {
            "mission_id": "",
            "mission_name": "",
            "correlation": "timestamp_window",
            "confidence": "low",
        }

    def _flush_reward_bundles_if_incompatible(self, event: LogEvent) -> None:
        """Flush open bundles before a reward that cannot join them is logged."""
        context = self._reward_context_for_event(event)
        with self._lock:
            if not self._pending_reward_bundles:
                return
            compatible = self._find_compatible_reward_bundle_key_locked(
                event,
                context,
            )
        if compatible is None:
            self._flush_reward_bundles()

    def _record_reward_component(
        self,
        event: LogEvent,
        entry: EventLogEntry,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Accumulate reward evidence into a short-lived mission bundle.

        Args:
            context: Reward context already resolved by the caller (see
                `_write_raw_to_event_log`'s reward_earned handling), reused
                here so the bundle's mission_id can never diverge from the one
                stamped on the persisted event-log entry. Resolved fresh when
                omitted (e.g. for blueprint_received, which has no entry-level
                mission_id to keep in sync).
        """
        if event.event_type == "reward_earned" and (
            entry.amount_auec is None and not entry.item_name
        ):
            return
        if event.event_type == "blueprint_received" and not entry.item_name:
            return

        if context is None:
            context = self._reward_context_for_event(event)
        fingerprint = entry.fingerprint or self._raw_event_fingerprint(event)

        with self._lock:
            key = self._find_compatible_reward_bundle_key_locked(event, context)
            if key is None:
                key = self._new_reward_bundle_key(event, context)
                self._pending_reward_bundles[key] = self._create_reward_bundle(
                    event,
                    context,
                )
            bundle = self._pending_reward_bundles[key]
            self._merge_reward_context(bundle, context)

            if fingerprint in bundle["source_fingerprints"]:
                self._schedule_reward_bundle_flush_locked()
                return
            bundle["source_fingerprints"].append(fingerprint)

            if event.event_type == "reward_earned":
                if entry.amount_auec is not None:
                    bundle["amount_auec"] += entry.amount_auec
                if entry.item_name and entry.item_name not in bundle["items"]:
                    bundle["items"].append(entry.item_name)
            elif event.event_type == "blueprint_received":
                if entry.item_name not in bundle["blueprints"]:
                    bundle["blueprints"].append(entry.item_name)

            self._append_unique(bundle["source_events"], event.event_type)
            self._append_unique(
                bundle["notification_ids"],
                event.data.get("notification_id", ""),
            )
            self._append_unique(
                bundle["objective_ids"],
                event.data.get("objective_id", ""),
            )
            if event.timestamp > bundle["last_seen"]:
                bundle["last_seen"] = event.timestamp
            self._schedule_reward_bundle_flush_locked()

    def _find_compatible_reward_bundle_key_locked(
        self,
        event: LogEvent,
        context: dict[str, Any],
    ) -> str | None:
        """Find an open bundle that can absorb this reward component."""
        mission_id = context.get("mission_id", "")
        if mission_id:
            mission_key = f"mission|{mission_id}"
            if mission_key in self._pending_reward_bundles:
                return mission_key

        candidates: list[tuple[float, str]] = []
        for key, bundle in self._pending_reward_bundles.items():
            last_seen = bundle.get("last_seen")
            if not isinstance(last_seen, datetime):
                continue
            delta = abs((event.timestamp - last_seen).total_seconds())
            if delta > self._reward_bundle_window_seconds:
                continue
            bundle_mission = bundle.get("mission_id", "")
            if mission_id and bundle_mission and bundle_mission != mission_id:
                continue
            candidates.append((delta, key))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _new_reward_bundle_key(
        self,
        event: LogEvent,
        context: dict[str, Any],
    ) -> str:
        mission_id = context.get("mission_id", "")
        if mission_id:
            return f"mission|{mission_id}"
        return "|".join(
            str(part)
            for part in (
                "reward_window",
                event.timestamp.isoformat(timespec="seconds"),
                event.data.get("notification_id", ""),
            )
        )

    def _create_reward_bundle(
        self,
        event: LogEvent,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        source_events: list[str] = []
        if context.get("correlation") == "recent_contract_complete":
            source_events.append("contract_complete")
        return {
            "first_seen": event.timestamp,
            "last_seen": event.timestamp,
            "location": self._parser.get_state("location_name") or "",
            "player_name": self._parser.get_state("player_name") or "",
            "mission_id": context.get("mission_id", ""),
            "mission_name": context.get("mission_name", ""),
            "amount_auec": 0.0,
            "items": [],
            "blueprints": [],
            "notification_ids": [],
            "objective_ids": [],
            "source_events": source_events,
            "source_fingerprints": [],
            "correlation": context.get("correlation", "timestamp_window"),
            "confidence": context.get("confidence", "low"),
        }

    def _merge_reward_context(
        self,
        bundle: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        if context.get("mission_id") and not bundle.get("mission_id"):
            bundle["mission_id"] = context["mission_id"]
        if context.get("mission_name") and not bundle.get("mission_name"):
            bundle["mission_name"] = context["mission_name"]
        if context.get("correlation") == "recent_contract_complete":
            self._append_unique(bundle["source_events"], "contract_complete")
        if self._confidence_rank(context.get("confidence")) > self._confidence_rank(
            bundle.get("confidence")
        ):
            bundle["confidence"] = context.get("confidence", "low")
            bundle["correlation"] = context.get("correlation", "timestamp_window")

    def _schedule_reward_bundle_flush_locked(self) -> None:
        if self._reward_bundle_timer is not None:
            self._reward_bundle_timer.cancel()
        timer = threading.Timer(
            self._reward_bundle_window_seconds,
            self._flush_reward_bundles,
        )
        timer.daemon = True
        self._reward_bundle_timer = timer
        timer.start()

    def _flush_reward_bundles(self) -> None:
        """Write all pending canonical reward bundles and clear the buffer."""
        with self._lock:
            if self._reward_bundle_timer is not None:
                self._reward_bundle_timer.cancel()
                self._reward_bundle_timer = None
            bundles = list(self._pending_reward_bundles.values())
            self._pending_reward_bundles.clear()

        if not self._event_log:
            return

        for bundle in bundles:
            self._write_reward_bundle_to_event_log(bundle)

    def _write_reward_bundle_to_event_log(self, bundle: dict[str, Any]) -> None:
        amount = float(bundle.get("amount_auec", 0.0) or 0.0)
        items = list(bundle.get("items", []))
        blueprints = list(bundle.get("blueprints", []))
        if not amount and not items and not blueprints:
            return

        data = {
            "mission_id": bundle.get("mission_id", ""),
            "mission_name": bundle.get("mission_name", ""),
            "money": {"amount_auec": amount} if amount else {},
            "items": items,
            "blueprints": blueprints,
            "notification_ids": list(bundle.get("notification_ids", [])),
            "objective_ids": list(bundle.get("objective_ids", [])),
            "correlation": bundle.get("correlation", "timestamp_window"),
            "first_seen": bundle["first_seen"].isoformat(),
            "last_seen": bundle["last_seen"].isoformat(),
            "component_count": len(bundle.get("source_fingerprints", [])),
        }
        entry = EventLogEntry(
            timestamp=bundle["last_seen"].isoformat(),
            event_type="mission_reward",
            location=bundle.get("location", ""),
            player_name=bundle.get("player_name", ""),
            data=data,
            amount_auec=amount if amount else None,
            movement_category="economy",
            movement_verb="rewarded",
            confidence=bundle.get("confidence", "low"),
            fingerprint=self._reward_bundle_fingerprint(bundle),
            source_events=list(bundle.get("source_events", [])),
        )
        self._event_log.append(entry)

    def _reward_bundle_fingerprint(self, bundle: dict[str, Any]) -> str:
        return "|".join(
            str(part)
            for part in (
                "mission_reward",
                bundle.get("mission_id", ""),
                bundle["first_seen"].isoformat(timespec="seconds"),
                bundle.get("amount_auec", 0.0),
                ",".join(bundle.get("items", [])),
                ",".join(bundle.get("blueprints", [])),
            )
        )

    @staticmethod
    def _append_unique(values: list[str], value: Any) -> None:
        if value and value not in values:
            values.append(str(value))

    @staticmethod
    def _confidence_rank(confidence: Any) -> int:
        return {"low": 1, "medium": 2, "high": 3}.get(str(confidence), 0)

    def _area_movement_verb(self, event: LogEvent) -> str:
        et = event.event_type
        if et == "armistice_zone":
            return event.data.get("action", "crossed_boundary")
        if et == "restricted_area":
            return event.data.get("action", "crossed_boundary")
        if et == "location_change":
            return "arrived"
        if et == "jurisdiction_change":
            return "entered_jurisdiction"
        if et == "entered_monitored_space":
            return "entered_monitored_space"
        if et == "exited_monitored_space":
            return "exited_monitored_space"
        if et == "quantum_route_set":
            return "route_set"
        if et == "qt_arrived":
            return "arrived"
        if et == "hangar_ready":
            return "hangar_ready"
        if et == "hangar_queue":
            return "queued"
        if et == "channel_change":
            return event.data.get("action", "channel_changed")
        return "changed"

    def _raw_event_fingerprint(self, event: LogEvent) -> str:
        data = event.data
        if event.event_type == "reward_earned":
            key = data.get("notification_id") or event.timestamp.isoformat(
                timespec="seconds"
            )
            value = data.get("amount") or data.get("item_name", "")
            return f"reward_earned|{key}|{value}"
        if event.event_type == "blueprint_received":
            key = data.get("notification_id") or event.timestamp.isoformat(
                timespec="seconds"
            )
            value = data.get("blueprint_name", "")
            return f"blueprint_received|{key}|{value}"
        if event.event_type == "transaction_complete":
            key = data.get("notification_id") or event.timestamp.isoformat(
                timespec="seconds"
            )
            return f"transaction_complete|{key}"
        if event.event_type.startswith("contract_"):
            return "|".join(
                str(part)
                for part in (
                    event.event_type,
                    data.get("mission_id", ""),
                    data.get("mission_name", ""),
                )
            )
        if event.event_type.startswith("objective_"):
            return "|".join(
                str(part)
                for part in (
                    event.event_type,
                    data.get("mission_id", ""),
                    data.get("objective", ""),
                )
            )
        return "|".join(
            str(part)
            for part in (
                event.event_type,
                event.timestamp.isoformat(timespec="seconds"),
            )
        )

    def _is_duplicate_reward(self, fingerprint: str, timestamp: datetime) -> bool:
        cutoff = timestamp - timedelta(seconds=30)
        self._recent_reward_fingerprints = {
            fp: ts
            for fp, ts in self._recent_reward_fingerprints.items()
            if ts >= cutoff
        }
        previous = self._recent_reward_fingerprints.get(fingerprint)
        if previous is not None and 0 <= (timestamp - previous).total_seconds() <= 30:
            return True
        self._recent_reward_fingerprints[fingerprint] = timestamp
        return False

    def _write_derived_to_event_log(self, event: DerivedEvent) -> None:
        """Write a derived event to the event log."""
        movement_category, movement_verb = self._derived_movement_metadata(event)
        log_entry = EventLogEntry(
            timestamp=event.timestamp.isoformat(),
            event_type=event.event_type,
            location=self._parser.get_state("location_name") or "",
            player_name=self._parser.get_state("player_name") or "",
            data=event.source_states.copy(),
            movement_category=movement_category,
            movement_verb=movement_verb,
            confidence="high" if movement_category else None,
            fingerprint=self._derived_event_fingerprint(event),
            source_events=[event.event_type],
        )
        self._event_log.append(log_entry)

    def _derived_movement_metadata(
        self,
        event: DerivedEvent,
    ) -> tuple[str | None, str | None]:
        work_verbs = {
            "mission_accepted": "accepted",
            "mission_complete": "completed",
            "mission_failed": "failed",
            "mission_objective_new": "objective_added",
        }
        if event.event_type in work_verbs:
            return "work", work_verbs[event.event_type]

        area_verbs = {
            "zone_entered_armistice": "entered",
            "zone_left_armistice": "left",
            "ship_entered": "ship_entered",
            "ship_exited": "ship_exited",
            "own_ship_entered": "own_ship_entered",
            "location_arrived": "arrived",
            "hangar_access": "hangar_access",
        }
        if event.event_type in area_verbs:
            return "area", area_verbs[event.event_type]

        return None, None

    def _derived_event_fingerprint(self, event: DerivedEvent) -> str:
        states = event.source_states
        return "|".join(
            str(part)
            for part in (
                "derived",
                event.event_type,
                states.get("mission_id", ""),
                states.get("objective", ""),
                states.get("mission_name", ""),
                states.get("location_name", ""),
                event.timestamp.isoformat(timespec="seconds"),
            )
        )

    def _cleanup_stale_pending(self) -> None:
        """Remove pending transactions older than the max age.

        Must be called while self._lock is held.
        """
        if not self._pending_transactions:
            return

        cutoff_dt = datetime.now() - timedelta(seconds=self._pending_max_age_seconds)

        kept = []
        for t in self._pending_transactions:
            received_at_str = t.get("received_at")
            if not received_at_str:
                # No timestamp — discard rather than silently keep
                continue
            try:
                received_dt = datetime.fromisoformat(received_at_str)
            except ValueError:
                continue
            if received_dt >= cutoff_dt:
                kept.append(t)

        removed = len(self._pending_transactions) - len(kept)
        self._pending_transactions = kept
        if removed:
            logger.info("Trade: cleanup removed %d stale pending entries", removed)

    # -------------------------------------------------------------------------
    # Derived State Updates
    # -------------------------------------------------------------------------

    def _update_derived_state(self, event: LogEvent) -> None:
        """Update derived states based on events."""
        # No derived state updates currently needed here.
        # Death tracking was stubbed but the log pattern for player death has not been
        # confirmed — removed to avoid a permanently-zero counter misleading the AI.

    # -------------------------------------------------------------------------
    # Default Rules
    # -------------------------------------------------------------------------

    def _setup_default_rules(self) -> None:
        """Setup default state combination rules."""
        # Armistice transitions
        self.add_rule(
            Rule(
                name="entered_armistice",
                trigger_key="in_armistice",
                conditions=[("in_armistice", "==", True)],
                event_type="zone_entered_armistice",
                message_template="Entered armistice zone",
            )
        )

        self.add_rule(
            Rule(
                name="left_armistice",
                trigger_key="in_armistice",
                conditions=[("in_armistice", "==", False)],
                event_type="zone_left_armistice",
                message_template="Left armistice zone",
            )
        )

        # Ship transitions
        self.add_rule(
            Rule(
                name="entered_ship",
                trigger_key="ship",
                conditions=[("ship", "exists", None)],
                event_type="ship_entered",
                message_template="Entered ship: {ship}",
            )
        )

        self.add_rule(
            Rule(
                name="entered_own_ship",
                trigger_key="ship",
                conditions=[
                    ("own_ship", "==", True),
                    ("ship", "exists", None),
                ],
                event_type="own_ship_entered",
                message_template="Entered own ship: {ship}",
            )
        )

        self.add_rule(
            Rule(
                name="exited_ship",
                trigger_key="ship",
                conditions=[("ship", "not_exists", None)],
                event_type="ship_exited",
                message_template="Exited ship",
            )
        )

        # Location arrival handled in _handle_event_derived (event-based,
        # not state-based) so returning to the same location still fires.

        # Station departure handled in _handle_event_derived (event-based)

    # -------------------------------------------------------------------------
    # File Output
    # -------------------------------------------------------------------------

    def _flush_file_output(self) -> None:
        """Write current state and event history to JSON file."""
        if not self._file_output_enabled or not self._file_output_path:
            return

        output = {
            "timestamp": datetime.now().isoformat(),
            "atomic_state": self._parser.get_state(),
            "derived_state": self.get_derived_state(),
            "active_missions": self.get_active_missions(),
            "recent_derived_events": self._event_history[-100:],
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
    import time

    argparser = argparse.ArgumentParser(description="SC State Logic - Layer 2")
    argparser.add_argument(
        "log_path",
        help="Path to Star Citizen Game.log",
    )
    argparser.add_argument(
        "--output",
        "-o",
        help="Path for JSON output file (optional)",
    )
    argparser.add_argument(
        "--parser-output",
        help="Path for Layer 3 parser JSON output (optional)",
    )
    args = argparser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # Create Layer 3
    parser = LogParser(args.log_path)
    if args.parser_output:
        parser.enable_file_output(args.parser_output)

    # Create Layer 2
    logic = StateLogic(parser)
    if args.output:
        logic.enable_file_output(args.output)

    # Print events to console
    def on_raw_event(event: LogEvent) -> None:
        print(f"\n[RAW] {event.event_type}: {event.data}")

    def on_derived_event(event: DerivedEvent) -> None:
        print(f"\n[DERIVED] {event.event_type}: {event.message}")

    logic.subscribe_raw(on_raw_event)
    logic.subscribe(on_derived_event)

    # Start both layers
    logic.start()
    parser.start()

    print(f"Monitoring: {args.log_path}")
    print("Press Ctrl+C to stop\n")

    try:
        while parser.is_running():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        parser.stop()
        logic.stop()

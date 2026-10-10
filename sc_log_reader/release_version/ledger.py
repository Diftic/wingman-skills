"""
SC_LogReader - Trade Ledger

Standalone module for persistent trade transaction storage.
Writes/reads JSONL (one JSON object per line) for append-friendly I/O.

Author: Mallachi
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class LedgerEntry:
    """A single trade transaction record."""

    timestamp: str  # ISO 8601
    location: str  # Human-readable location name
    transaction: str  # "purchase" or "sale"
    category: str  # "item" or "commodity"
    item_name: str | None  # e.g. "behr_shotgun_ballistic_01" (items only)
    item_guid: str  # itemClassGUID or resourceGUID
    price: float  # aUEC
    quantity: int | float  # Count for items; raw log value for commodities
    quantity_unit: str  # "units", "cscu", or "scu"
    player_id: str
    shop_id: str
    kiosk_id: str
    shop_name: str

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> LedgerEntry:
        """Create a LedgerEntry from a dictionary.

        Unknown keys are silently dropped so old ledger files remain readable
        after a field is added or removed.  Missing required fields still raise
        TypeError, which the caller logs and skips.
        """
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


class TradeLedger:
    """Append-only trade ledger backed by a JSONL file.

    The ledger file is never reset or cleared automatically.
    It persists across sessions, skill reloads, and wingman restarts.
    """

    def __init__(self, ledger_path: Path) -> None:
        self._path = ledger_path

    @property
    def path(self) -> Path:
        """Return the ledger file path."""
        return self._path

    def append(self, entry: LedgerEntry) -> None:
        """Append a single entry to the ledger file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
            logger.info("Ledger: wrote entry to %s", self._path)
        except Exception:
            logger.exception("Failed to append to trade ledger at %s", self._path)

    def query(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        category: str | None = None,
        transaction: str | None = None,
        limit: int = 100,
    ) -> list[LedgerEntry]:
        """Read and filter ledger entries.

        Args:
            start: Only include entries at or after this time.
            end: Only include entries before this time.
            category: Filter by "item" or "commodity".
            transaction: Filter by "purchase" or "sale".
            limit: Maximum entries to return (most recent first).

        Returns:
            List of matching entries, most recent first.
        """
        entries = self._read_all()

        if start:
            start_iso = start.isoformat()
            entries = [e for e in entries if e.timestamp >= start_iso]
        if end:
            end_iso = end.isoformat()
            entries = [e for e in entries if e.timestamp < end_iso]
        if category:
            entries = [e for e in entries if e.category == category]
        if transaction:
            entries = [e for e in entries if e.transaction == transaction]

        # Most recent first, limited
        entries.reverse()
        return entries[:limit]

    def summarize(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> dict:
        """Aggregate financial summary over a time range.

        Returns:
            Dictionary with total_purchases, total_sales, net_profit,
            transaction_count, and per-item breakdown in by_item.
        """
        entries = self.query(start=start, end=end, limit=10000)

        total_purchases = 0.0
        total_sales = 0.0
        by_item: dict[str, dict] = {}

        for entry in entries:
            key = entry.item_name or entry.item_guid
            if key not in by_item:
                by_item[key] = {
                    "bought": 0.0,
                    "sold": 0.0,
                    "net": 0.0,
                    "qty_bought": 0,
                    "qty_sold": 0,
                    "category": entry.category,
                    "quantity_unit": entry.quantity_unit,
                }

            if entry.transaction == "purchase":
                total_purchases += entry.price
                by_item[key]["bought"] += entry.price
                by_item[key]["net"] -= entry.price
                by_item[key]["qty_bought"] += entry.quantity
            elif entry.transaction == "sale":
                total_sales += entry.price
                by_item[key]["sold"] += entry.price
                by_item[key]["net"] += entry.price
                by_item[key]["qty_sold"] += entry.quantity

        return {
            "total_purchases": total_purchases,
            "total_sales": total_sales,
            "net_profit": total_sales - total_purchases,
            "transaction_count": len(entries),
            "by_item": by_item,
        }

    def _read_all(self) -> list[LedgerEntry]:
        """Read all entries from the JSONL file."""
        if not self._path.exists():
            return []

        entries: list[LedgerEntry] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        entries.append(LedgerEntry.from_dict(data))
                    except (json.JSONDecodeError, TypeError, KeyError):
                        logger.warning("Skipping malformed ledger line %d", line_num)
        except Exception:
            logger.exception("Failed to read trade ledger")

        return entries

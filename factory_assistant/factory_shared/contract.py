"""Contract between the single Orchestrator (main.py) and each game's Handler.

The Orchestrator owns Wingman: tools, settings, lifecycle, the map popup and the
background refresh loop. It knows nothing about any game. Each game supplies one
:class:`GameHandler` subclass (``factory_games/<game>/game.py``) that owns that
game's Reader and Handler.

Data flows down only:

    Wingman -> Orchestrator -> GameHandler -> game Handler -> game Reader

The Orchestrator gives each GameHandler a :class:`HandlerContext` with
callbacks. That is the only way a game reaches Orchestrator services (settings,
diagnostics, the map popup), so no game module imports Wingman.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

# Parameters of the neutral planning tool. A game that does not support one
# option ignores it or says so in its reply (see GameHandler.capabilities).
PLAN_OPTIONS = (
    "stage",
    "pace_multiplier",
    "allow_recipes",
    "persist",
    "scope",
    "pin_recipes",
    "ban_recipes",
    "include_construction",
    "create_build_todos",
    "pace_scenarios",
)


@dataclass(frozen=True)
class ActiveSave:
    """Game-neutral view of the active save, used to select the active game.

    ``detected_at`` is when the game last confirmed this save (for example the
    newest log or save-file time). In automatic game selection the confirmed
    save with the newest ``detected_at`` wins.
    """

    game_id: str
    confirmed: bool
    save_name: str | None = None
    detected_at: datetime | None = None
    status: str = ""


@dataclass
class HandlerContext:
    """Orchestrator services handed to a GameHandler (callbacks, never Wingman objects)."""

    generated_dir: Callable[[], Path]
    """Writable per-skill folder. Each game keeps its per-save workspaces here."""

    setting: Callable[[str], Any]
    """Read one custom property by id (just in time, never cached)."""

    diag: Callable[[str], None]
    """Write one diagnostic line to the Wingman server log."""

    show_map: Callable[[Path], str]
    """Open an image in the map popup; returns a short player-facing status."""

    max_response_items: Callable[[], int]
    allow_plan_writes: Callable[[], bool]


class GameHandler(ABC):
    """One game, as the Orchestrator sees it.

    Every tool method returns the short, player-facing text that the
    Orchestrator hands back to Wingman unchanged.
    """

    game_id: ClassVar[str]
    """Stable id, also used in the ``game`` setting (for example ``satisfactory``)."""

    display_name: ClassVar[str]

    setting_ids: ClassVar[tuple[str, ...]] = ()
    """Game-specific custom property ids that the Orchestrator validates."""

    def __init__(self, ctx: HandlerContext) -> None:
        self._ctx = ctx

    def capabilities(self) -> frozenset[str]:
        """Plan options from :data:`PLAN_OPTIONS` that this game supports."""
        return frozenset()

    @abstractmethod
    def prompt(self) -> str:
        """Game-specific instructions for the LLM (game words, what a stage is)."""

    @abstractmethod
    def active_save(self) -> ActiveSave:
        """Resolve the active save cheaply (used for automatic game selection)."""

    @abstractmethod
    async def context(self, focus: str = "", lookup: str = "", locate: str = "") -> str:
        """Active save summary, journal, optional catalog lookup and locate."""

    @abstractmethod
    async def show_map(self, query: str = "") -> str:
        """Find ``query`` and show it on the map; empty query reopens the last map."""

    @abstractmethod
    async def update_journal(self, action: str, **fields: Any) -> str:
        """Add or change a note, job, goal or production setup for the active save."""

    @abstractmethod
    async def calculate(self, mode: str = "plan", **options: Any) -> str:
        """``mode="plan"``: plan production; ``mode="audit"``: read the save."""

    @abstractmethod
    async def auto_refresh_once(self) -> None:
        """Refresh save-derived data when a new save appears (polled by the Orchestrator)."""

    async def close(self) -> None:  # noqa: B027 - optional hook
        """Release resources when the skill unloads."""

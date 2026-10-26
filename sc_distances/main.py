"""SC_distances: distances between Star Citizen locations in the released systems.

The data (data/<system>.json) is read from the game files by tools/rebuild.ps1 and kept current
from GitHub by dependencies/sc_data.py. The lookups live in dependencies/sc_distance.py. Core puts
the dependencies folder on the import path while it loads a custom skill.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from api.interface import SettingsConfig, SkillConfig
from skills.skill_base import Skill, tool
from sc_data import DataStore
from sc_distance import LookupError_, describe, describe_location, distance, find

if TYPE_CHECKING:
    from wingmen.wingman_context import WingmanContext

DATA_DIR = Path(__file__).resolve().parent / "data"
CHECK_EVERY_SECONDS = 6 * 60 * 60
SLEEP_STEP_SECONDS = 5
MAX_FOUND = 6


class SC_distances(Skill):
    def __init__(self, config: SkillConfig, settings: SettingsConfig,
                 wingman: "WingmanContext") -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)
        self._store: DataStore | None = None
        self._run_id = 0

    # --- lifecycle ---

    async def prepare(self) -> None:
        await super().prepare()
        self._store = await asyncio.to_thread(DataStore, DATA_DIR, self.get_generated_files_dir())
        loaded = ", ".join(f"{k} r{r} ({self._store.status.sources[k]})"
                           for k, r in sorted(self._store.status.revisions.items()))
        self.log.info(f"SC distances: loaded {loaded or 'no data'}", server_only=True)
        self._run_id += 1
        self.wingman.run_in_thread(self._update_loop, self._run_id)

    async def unload(self) -> None:
        self._run_id += 1  # the update loop checks this and stops
        await super().unload()

    async def _update_loop(self, run_id: int) -> None:
        while run_id == self._run_id:
            try:
                updated = await self._store.check()
                if updated:
                    self.log.info(f"SC distances: new data for {', '.join(updated)}", server_only=True)
                elif self._store.status.problem:
                    self.log.warning(f"SC distances: {self._store.status.problem}", server_only=True)
            except Exception as error:  # noqa: BLE001 - the loop must survive anything
                self.log.warning(f"SC distances: update check crashed: {error}", server_only=True)
            waited = 0
            while waited < CHECK_EVERY_SECONDS and run_id == self._run_id:
                await asyncio.sleep(SLEEP_STEP_SECONDS)
                waited += SLEEP_STEP_SECONDS

    def _systems(self) -> dict[str, dict]:
        if self._store is None:  # a tool call before prepare(): load the bundled data
            self._store = DataStore(DATA_DIR, self.get_generated_files_dir())
        return self._store.systems

    # --- tools ---

    @tool()
    async def get_distance(self, from_location: str, to_location: str, system: str = "",
                           **kwargs: Any) -> str:
        """Distance between two Star Citizen locations in Stanton, Pyro or Nyx: stations, planets,
        moons, cities, outposts, Lagrange points, gateways.

        Args:
            from_location: Location name, e.g. "Lorville", "ARC-L1" or "Checkmate".
            to_location: Location name.
            system: Only if a name exists in several systems: Stanton, Pyro or Nyx.
        """
        try:
            return describe(distance(self._systems(), from_location, to_location, system or None))
        except LookupError_ as error:
            return f"{error} Use find_location to check the name."

    @tool()
    async def find_location(self, name: str, **kwargs: Any) -> str:
        """Where a Star Citizen location is (system, planet or moon, type, altitude), or which
        locations match a partial name.

        Args:
            name: Full or partial location name.
        """
        hits = find(self._systems(), name)
        if not hits:
            return f"No location matches '{name}'."
        lines = [describe_location(loc) for loc in hits[:MAX_FOUND]]
        if len(hits) > MAX_FOUND:
            lines.append(f"...and {len(hits) - MAX_FOUND} more; give more of the name.")
        return "\n".join(lines)

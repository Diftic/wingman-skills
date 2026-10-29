"""NavPoint Linux probe: a throwaway test skill, not a feature.

Checks, from inside Wingman's own Python, whether NavPoint could see Star Citizen
on this machine. One tool; the work is in navpoint_probe_core.py.
"""

import asyncio
import os
import shutil
import sys
from typing import TYPE_CHECKING

from api.interface import SettingsConfig, SkillConfig
from skills.skill_base import Skill, tool

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

import navpoint_probe_core as probe  # noqa: E402

if TYPE_CHECKING:
    from wingmen.wingman_context import WingmanContext


class NavPointLinuxProbe(Skill):
    def __init__(self, config: SkillConfig, settings: SettingsConfig, wingman: "WingmanContext") -> None:
        super().__init__(config=config, settings=settings, wingman=wingman)

    @tool(
        description="Run the NavPoint Linux probe test. Use when the user asks to run the NavPoint probe or Linux test.",
        summarize=False,
        wait_response=True,
    )
    async def run_navpoint_linux_probe(self) -> str:
        zip_path, verdict = await asyncio.to_thread(
            probe.run_probe, self.get_generated_files_dir(), {"skill_dir": probe.mask(current_dir)})
        home_copy = os.path.join(os.path.expanduser("~"), os.path.basename(zip_path))
        try:
            shutil.copy2(zip_path, home_copy)
        except OSError:
            home_copy = zip_path
        self.log.info(f"NavPoint probe report saved: {home_copy}")
        self.log.info(f"NavPoint probe verdict: {verdict}", server_only=True)
        where = "your home folder" if home_copy != zip_path else "Wingman's generated files folder"
        return f"Probe finished. The report is in {where}, named {os.path.basename(zip_path)}."

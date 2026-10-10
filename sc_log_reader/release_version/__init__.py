"""
SC_LogReader - Star Citizen Log Reader Skill

3-Layer Architecture:
- Layer 3 (parser.py): Log reading and atomic state extraction
- Layer 2 (logic.py): State combination and derived events
- Layer 1 (main.py): WingmanAI skill interface
"""

# Version mirrors the Star Citizen patch this skill is qualified against, so
# dependent skills can verify SC-version compatibility. Within-patch updates
# append a dotted suffix (4.8.2.1, 4.8.2.2, ...).
__version__ = "4.8.3.4"
__sc_target_version__ = "4.8.3"

from .main import SC_LogReader
from .logic import DerivedEvent, Rule, StateLogic
from .parser import LogEvent, LogParser, StateStore

__all__ = [
    "SC_LogReader",
    "LogParser",
    "StateStore",
    "LogEvent",
    "StateLogic",
    "Rule",
    "DerivedEvent",
    "__version__",
    "__sc_target_version__",
]

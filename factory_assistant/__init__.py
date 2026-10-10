"""Factory Assistant: active-save scoped factory planning skill for Wingman AI.

One Orchestrator for all games, one Reader + Handler per game:
- Orchestrator: main.py + factory_orchestrator/ (Wingman tools, settings, lifecycle, map popup, game registry)
- Shared:       factory_shared/ (Orchestrator/Handler contract, per-save journal, helpers)
- Per game:     factory_games/<game>/game.py (GameHandler), handler/ (Layer 2), reader/ (Layer 3)
"""

__version__ = "0.10.0"

__all__ = [
    "__version__",
]

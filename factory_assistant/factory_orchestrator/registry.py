"""Game registry: the only place where the Orchestrator learns which games exist.

Games are loaded by import path so that ``main.py`` and this package never
import a game module statically (``tests/test_layer_boundaries.py`` checks
this). To add a game, add one line here and a ``factory_games/<game>/game.py``
with a :class:`factory_shared.contract.GameHandler` subclass.
"""

from __future__ import annotations

import importlib

from factory_shared.contract import GameHandler, HandlerContext

# game id -> "module:ClassName"
GAMES: dict[str, str] = {
    "satisfactory": "factory_games.satisfactory.game:SatisfactoryHandler",
    "dyson_sphere_program": "factory_games.dyson_sphere_program.game:DysonSphereProgramHandler",
}

AUTO = "auto"


def load_handlers(ctx: HandlerContext, game_ids: list[str] | None = None) -> dict[str, GameHandler]:
    """Create one handler per registered game (or per id in ``game_ids``)."""
    handlers: dict[str, GameHandler] = {}
    for game_id, target in GAMES.items():
        if game_ids is not None and game_id not in game_ids:
            continue
        module_name, _, class_name = target.partition(":")
        handler_cls = getattr(importlib.import_module(module_name), class_name)
        if not issubclass(handler_cls, GameHandler) or handler_cls.game_id != game_id:
            raise TypeError(f"{target} is not the GameHandler for '{game_id}'")
        handlers[game_id] = handler_cls(ctx)
    return handlers


def select_handler(handlers: dict[str, GameHandler], choice: str) -> GameHandler:
    """Pick the handler for ``choice`` (a game id, or ``auto``).

    Auto: the game whose active save was confirmed most recently. When no game
    has a confirmed save, the first registered game answers, so the player gets
    that game's "load a save first" message.
    """
    if not handlers:
        raise LookupError("No games are registered.")
    choice = (choice or AUTO).strip().lower()
    if choice in handlers:
        return handlers[choice]
    if len(handlers) == 1:
        return next(iter(handlers.values()))

    best: tuple[float, GameHandler] | None = None
    for handler in handlers.values():
        try:
            save = handler.active_save()
        except Exception:  # noqa: BLE001 - one broken game must not block the others
            continue
        if not save.confirmed:
            continue
        stamp = save.detected_at.timestamp() if save.detected_at else 0.0
        if best is None or stamp > best[0]:
            best = (stamp, handler)
    return best[1] if best else next(iter(handlers.values()))

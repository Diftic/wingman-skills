"""Layer rules for Factory Assistant: one Orchestrator, one Reader + Handler per game.

    main.py, factory_orchestrator/      Orchestrator (the only one; only place that knows Wingman)
    factory_shared/                     contract + journal + helpers (used by everyone)
    factory_games/<game>/game.py        GameHandler: the game's entry point for the Orchestrator
    factory_games/<game>/handler/       Handler (Layer 2) for that game
    factory_games/<game>/reader/        Reader (Layer 3) for that game

Dependencies point down only. The Orchestrator reaches a game only through
factory_orchestrator/registry.py, which loads it by import path at runtime.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from factory_orchestrator.registry import GAMES, load_handlers, select_handler
from factory_shared.contract import ActiveSave, GameHandler, HandlerContext

SKILL_DIR = Path(__file__).resolve().parent.parent
WINGMAN_ROOTS = {"api", "skills", "wingmen", "services"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
        elif isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
    return found


def _files(*folders: str) -> list[Path]:
    paths: list[Path] = []
    for folder in folders:
        paths.extend(sorted((SKILL_DIR / folder).rglob("*.py")))
    return paths


def _rel(path: Path) -> str:
    return path.relative_to(SKILL_DIR).as_posix()


def _root(module: str) -> str:
    return module.split(".")[0]


@pytest.mark.parametrize(
    "path", [SKILL_DIR / "main.py", *_files("factory_orchestrator")], ids=_rel
)
def test_orchestrator_never_imports_a_game(path: Path) -> None:
    for module in _imports(path):
        assert _root(module) != "factory_games", (
            f"{_rel(path)} imports {module}; register the game in registry.GAMES instead"
        )


@pytest.mark.parametrize("path", _files("factory_orchestrator", "factory_shared", "factory_games"), ids=_rel)
def test_only_main_py_imports_wingman(path: Path) -> None:
    for module in _imports(path):
        assert _root(module) not in WINGMAN_ROOTS, f"{_rel(path)} imports Wingman module {module}"


@pytest.mark.parametrize("path", _files("factory_shared"), ids=_rel)
def test_shared_code_imports_no_game_and_no_orchestrator(path: Path) -> None:
    for module in _imports(path):
        assert _root(module) not in {"factory_games", "factory_orchestrator"}, (
            f"{_rel(path)} imports {module}"
        )


@pytest.mark.parametrize("path", _files("factory_games"), ids=_rel)
def test_game_code_stays_inside_its_game(path: Path) -> None:
    parts = path.relative_to(SKILL_DIR / "factory_games").parts
    if len(parts) == 1:  # factory_games/__init__.py
        return
    game = parts[0]
    is_reader = len(parts) > 2 and parts[1] == "reader"
    for module in _imports(path):
        assert _root(module) != "factory_orchestrator", f"{_rel(path)} imports {module}"
        if _root(module) != "factory_games":
            continue
        pieces = module.split(".")
        assert len(pieces) > 1 and pieces[1] == game, f"{_rel(path)} imports another game: {module}"
        if is_reader:
            assert len(pieces) > 2 and pieces[2] == "reader", (
                f"{_rel(path)} is a Reader and must not import {module} (Handler or game.py)"
            )


def _ctx(tmp_path: Path) -> HandlerContext:
    return HandlerContext(
        generated_dir=lambda: tmp_path,
        setting=lambda key: None,
        diag=lambda message: None,
        show_map=lambda path: "shown",
        max_response_items=lambda: 12,
        allow_plan_writes=lambda: True,
    )


def test_every_registered_game_loads_as_a_complete_game_handler(tmp_path: Path) -> None:
    handlers = load_handlers(_ctx(tmp_path))
    assert set(handlers) == set(GAMES)
    for game_id, handler in handlers.items():
        assert isinstance(handler, GameHandler)
        assert handler.game_id == game_id
        assert handler.display_name
        assert handler.prompt().strip()


class _FakeHandler:
    def __init__(self, game_id: str, confirmed: bool, stamp: float | None) -> None:
        from datetime import datetime

        self.game_id = game_id
        self._save = ActiveSave(
            game_id=game_id,
            confirmed=confirmed,
            detected_at=datetime.fromtimestamp(stamp) if stamp else None,
        )

    def active_save(self) -> ActiveSave:
        return self._save


def test_auto_selection_prefers_the_most_recent_confirmed_save() -> None:
    older = _FakeHandler("a", True, 1_000)
    newer = _FakeHandler("b", True, 2_000)
    unconfirmed = _FakeHandler("c", False, 3_000)
    handlers = {"a": older, "b": newer, "c": unconfirmed}

    assert select_handler(handlers, "auto") is newer
    assert select_handler(handlers, "a") is older


def test_auto_selection_falls_back_to_first_game_without_any_save() -> None:
    first = _FakeHandler("a", False, None)
    second = _FakeHandler("b", False, None)

    assert select_handler({"a": first, "b": second}, "auto") is first


def test_orchestrator_tools_are_game_neutral() -> None:
    main = pytest.importorskip("skills.factory_assistant.main")
    tools = {
        name
        for name, value in vars(main.FactoryAssistant).items()
        if callable(value) and hasattr(value, "_tool_definition")
    }
    assert tools == {
        "get_factory_context",
        "show_factory_map",
        "update_factory_plan",
        "calculate_factory_plan",
    }
    for game_id in GAMES:
        assert all(game_id not in name for name in tools)


def test_orchestrator_tools_delegate_to_the_selected_handler() -> None:
    import asyncio

    main = pytest.importorskip("skills.factory_assistant.main")
    calls: list[tuple[str, dict]] = []

    class _Handler:
        async def context(self, **kw):
            calls.append(("context", kw))
            return "ctx"

        async def show_map(self, **kw):
            calls.append(("show_map", kw))
            return "map"

        async def update_journal(self, action, **kw):
            calls.append(("update_journal", {"action": action, **kw}))
            return "saved"

        async def calculate(self, **kw):
            calls.append(("calculate", kw))
            return "plan"

    stub = SimpleNamespace(_active_handler=lambda: _Handler(), _map_overlay=None)
    cls = main.FactoryAssistant
    assert asyncio.run(cls.get_factory_context(stub, focus="x")) == "ctx"
    assert asyncio.run(cls.show_factory_map(stub, query="oil")) == "map"
    assert asyncio.run(cls.update_factory_plan(stub, action="add_note", title="t")) == "saved"
    assert asyncio.run(cls.calculate_factory_plan(stub, stage=3, allow_recipes="A")) == "plan"
    assert [name for name, _ in calls] == ["context", "show_map", "update_journal", "calculate"]
    assert calls[3][1]["stage"] == 3 and calls[3][1]["allow_recipes"] == "A"

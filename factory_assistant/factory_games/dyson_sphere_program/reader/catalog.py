"""Dyson Sphere Program item, recipe and research catalog.

The catalog is JSON exported from the installed game by
``tools/extract_catalog.py`` (one file per game version in ``data/``). The
newest file is used; a save from another game version still reads, but items
that a newer version or a mod added show as "item <id>".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Recipe:
    id: int
    name: str
    type: str
    seconds: float
    inputs: tuple[tuple[int, int], ...]
    outputs: tuple[tuple[int, int], ...]
    handcraft: bool


@dataclass(frozen=True)
class Catalog:
    game_version: str
    items: dict[int, dict]
    recipes: dict[int, Recipe]
    techs: dict[int, dict]

    def item_name(self, item_id: int) -> str:
        item = self.items.get(item_id)
        return item["name"] if item else f"item {item_id}"

    def find_items(self, query: str, limit: int = 5) -> list[dict]:
        return _search(self.items.values(), query, limit)

    def find_recipes(self, query: str, limit: int = 5) -> list[Recipe]:
        return _search(self.recipes.values(), query, limit)

    def recipes_making(self, item_id: int) -> list[Recipe]:
        return [r for r in self.recipes.values() if any(i == item_id for i, _ in r.outputs)]


def _name_of(entry) -> str:
    return entry["name"] if isinstance(entry, dict) else entry.name


def _search(entries, query: str, limit: int) -> list:
    text = query.strip().lower()
    if not text:
        return []
    exact = [e for e in entries if _name_of(e).lower() == text]
    partial = [e for e in entries if text in _name_of(e).lower() and e not in exact]
    return (exact + partial)[:limit]


def catalog_files() -> list[Path]:
    def key(path: Path) -> tuple[int, ...]:
        version = path.stem.removeprefix("catalog_")
        try:
            return tuple(int(part) for part in version.split("."))
        except ValueError:
            return (0,)

    return sorted(DATA_DIR.glob("catalog_*.json"), key=key)


@lru_cache(maxsize=2)
def load_catalog(path: Path | None = None) -> Catalog:
    if path is None:
        files = catalog_files()
        if not files:
            raise ValueError("No Dyson Sphere Program catalog file is installed.")
        path = files[-1]
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    recipes = {
        r["id"]: Recipe(
            id=r["id"],
            name=r["name"],
            type=r["type"],
            seconds=float(r["seconds"]),
            inputs=tuple((int(i), int(c)) for i, c in r["inputs"]),
            outputs=tuple((int(i), int(c)) for i, c in r["outputs"]),
            handcraft=bool(r.get("handcraft")),
        )
        for r in data["recipes"]
    }
    return Catalog(
        game_version=str(data.get("game_version", "")),
        items={int(i["id"]): i for i in data["items"]},
        recipes=recipes,
        techs={int(t["id"]): t for t in data.get("techs", [])},
    )

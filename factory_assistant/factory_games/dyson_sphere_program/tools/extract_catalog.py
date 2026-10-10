"""Developer tool: export the Dyson Sphere Program catalog from an installed game.

Reads ItemProtoSet, RecipeProtoSet and TechProtoSet from ``DSPGAME_Data/resources.assets``
(UnityPy + TypeTreeGeneratorAPI, types from ``Managed/Assembly-CSharp.dll``) and the
English names from ``Locale/1033``. Writes ``reader/data/catalog_<game version>.json``.

Not used at runtime. Run it once per game update:

    pip install UnityPy TypeTreeGeneratorAPI
    python extract_catalog.py "D:/SteamLibrary/steamapps/common/Dyson Sphere Program"
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RECIPE_TYPES = {
    0: "none", 1: "smelt", 2: "chemical", 3: "refine", 4: "assemble", 5: "particle",
    6: "exchange", 7: "photon_store", 8: "fractionate", 15: "research",
}
ITEM_TYPES = [
    "unknown", "resource", "material", "component", "product", "logistics",
    "production", "decoration", "turret", "defense", "dark_fog", "matrix",
]
UNITY_VERSION_FALLBACK = "2022.3.62f3c1"


def game_version(install: Path) -> str:
    lines = (install / "Updates" / "Versions.txt").read_text(encoding="utf-8").splitlines()
    rows = [line.split(",")[0] for line in lines if line.strip()]
    return rows[-1]


def unity_version(install: Path) -> str:
    log = Path.home() / "AppData/LocalLow/Youthcat Studio/Dyson Sphere Program/Player.log"
    try:
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines()[:40]:
            if line.startswith("Initialize engine version:"):
                return line.split(":", 1)[1].split()[0]
    except OSError:
        pass
    return UNITY_VERSION_FALLBACK


def english_names(install: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    for path in sorted((install / "Locale" / "1033").glob("*.txt")):
        text = path.read_bytes().decode("utf-16", errors="ignore")
        for line in text.splitlines():
            parts = line.split("\t")
            if len(parts) >= 4 and parts[0] and parts[3]:
                names.setdefault(parts[0], parts[3])
    return names


def main(install_dir: str, out_dir: str | None = None) -> Path:
    import UnityPy
    from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

    install = Path(install_dir)
    env = UnityPy.load(str(install / "DSPGAME_Data" / "resources.assets"))
    generator = TypeTreeGenerator(unity_version(install))
    generator.load_local_game(str(install))
    env.typetree_generator = generator

    sets: dict[str, list] = {}
    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        try:
            name = obj.read(check_read=False).m_Name
        except Exception:  # noqa: BLE001 - unrelated behaviours may not decode
            continue
        if name in ("ItemProtoSet", "RecipeProtoSet", "TechProtoSet"):
            sets[name] = obj.read_typetree()["dataArray"]

    en = english_names(install)

    def label(key: str) -> str:
        return en.get(key, key)

    items = [
        {
            "id": p["ID"],
            "name": label(p["Name"]),
            "type": ITEM_TYPES[p["Type"]] if 0 <= p["Type"] < len(ITEM_TYPES) else str(p["Type"]),
            "stack": p["StackSize"],
            "fluid": bool(p["IsFluid"]),
            "mining_from": label(p["MiningFrom"]) if p["MiningFrom"] else "",
            "produce_from": label(p["ProduceFrom"]) if p["ProduceFrom"] else "",
            "can_build": bool(p["CanBuild"]),
        }
        for p in sets["ItemProtoSet"]
    ]
    recipes = [
        {
            "id": p["ID"],
            "name": label(p["Name"]),
            "type": RECIPE_TYPES.get(p["Type"], str(p["Type"])),
            "seconds": p["TimeSpend"] / 60.0,
            "inputs": [[i, c] for i, c in zip(p["Items"], p["ItemCounts"])],
            "outputs": [[i, c] for i, c in zip(p["Results"], p["ResultCounts"])],
            "handcraft": bool(p["Handcraft"]),
            "explicit": bool(p["Explicit"]),
            "productive": not bool(p["NonProductive"]),
        }
        for p in sets["RecipeProtoSet"]
    ]
    techs = [
        {
            "id": p["ID"],
            "name": label(p["Name"]),
            "hash_needed": p.get("HashNeeded", 0),
            "items": [[i, c] for i, c in zip(p.get("Items", []), p.get("ItemPoints", []))],
            "pre_techs": list(p.get("PreTechs", [])),
            "unlock_recipes": list(p.get("UnlockRecipes", [])),
        }
        for p in sets["TechProtoSet"]
    ]
    version = game_version(install)
    out = Path(out_dir) if out_dir else Path(__file__).resolve().parents[1] / "reader" / "data"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"catalog_{version}.json"
    payload = {"game": "dyson_sphere_program", "game_version": version,
               "items": items, "recipes": recipes, "techs": techs}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(items)} items, {len(recipes)} recipes, {len(techs)} techs)")
    return path


if __name__ == "__main__":
    main(*sys.argv[1:3])

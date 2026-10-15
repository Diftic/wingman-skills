"""Build Core's item-name table: the in-game name for each item class the game logs.

The game log names purchased items by class name and GUID only
(itemName[Food_burrito_01_a] itemClassGUID[b9867b9a-...]). This builds
services/sc_gamelog/data/item_names.json for Wingman Core from:

1. the current English localization (Data/Localization/english/global.ini,
   extracted from Data.p4k with unp4k): every item_Name<class> and
   item_Name_<class> key;
2. optionally, names taken from the game's item records by Mallachi's
   sc-bridge extraction (INSERT rows with uuid, class_name, name), keyed by
   GUID; they cover items whose localization key does not follow the class
   name (crlf_medgun_vial_01 -> "ParaMed Refill").

The localization of the current patch wins over older extracted names. Core
looks a class up the same way `lookup` does here: exact class, one key with a
manufacturer prefix (SASU_<class>), then the base item without its colour
variant (..._01_01_07 -> ..._01).

Usage:
    python build_item_names.py --global-ini global.ini [--sc-bridge DIR]
        [--build 12913470] [--logs Game.log ...] --out item_names.json
--logs only reports how many of the items bought in those logs get a name.
"""

import argparse
import glob
import json
import os
import re
from datetime import date

KEY = re.compile(r"^item_name_?(.+)$", re.I)
VARIANT = re.compile(r"^(.+?)(?:_\d\d){1,2}$")
INSERT = re.compile(r"INSERT INTO (\w+) \(([^)]*)\) VALUES \((.*)\);?\s*$")
VALUE = re.compile(r"'((?:[^']|'')*)'|(NULL)|([-\d.]+)|(\(SELECT[^)]*\))")
ITEM = re.compile(rb"itemName\[([^\]]+)\]")
GUID = re.compile(rb"itemClassGUID\[([^\]]+)\]")


def localization(path):
    names = {}
    with open(path, encoding="utf-8-sig", errors="replace") as ini:
        for line in ini:
            key, sep, value = line.rstrip("\r\n").partition("=")
            m = KEY.match(key) if sep else None
            value = value.strip()
            # Placeholders and unfinished strings are not names.
            if m and value and not value.startswith(("@", "<=")) and "PLACEHOLDER" not in value:
                names.setdefault(m.group(1).lower(), value)
    return names


def sc_bridge(root):
    """GUID -> (class name, name) from sc-bridge's generated SQL."""
    rows = {}
    for path in glob.glob(os.path.join(root, "**", "*.sql"), recursive=True):
        with open(path, encoding="utf-8", errors="replace") as sql:
            for line in sql:
                m = INSERT.match(line.strip())
                if not m:
                    continue
                cols = [c.strip() for c in m.group(2).split(",")]
                if not {"uuid", "class_name", "name"} <= set(cols):
                    continue
                vals = [
                    text.replace("''", "'") if text or not (null or num or sub) else None
                    for text, null, num, sub in VALUE.findall(m.group(3))
                ]
                if len(vals) != len(cols):  # A value the simple parser cannot split.
                    continue
                row = dict(zip(cols, vals, strict=True))
                guid, cls, name = (row.get("uuid") or "").lower(), row.get("class_name"), row.get("name")
                if guid and cls and name and not name.startswith("@"):
                    rows.setdefault(guid, (cls, name))
    return rows


def prefixed(by_class):
    """<class> -> names of the keys that are <class> behind one alphabetic prefix."""
    found = {}
    for key, name in by_class.items():
        prefix, sep, rest = key.partition("_")
        if sep and rest and prefix.isalpha():
            found.setdefault(rest, []).append(name)
    return found


def lookup(cls, by_class, by_prefix):
    cls = cls.lower().removesuffix("_scitem")  # Ship components sold as <class>_SCItem.
    if cls in by_class:
        return by_class[cls]
    if len(by_prefix.get(cls, ())) == 1:
        return by_prefix[cls][0]
    m = VARIANT.match(cls)
    while m:
        if m.group(1) in by_class:
            return by_class[m.group(1)]
        m = VARIANT.match(m.group(1))
    return None


def main():
    ap = argparse.ArgumentParser(description="Build Core's item-name table.")
    ap.add_argument("--global-ini", required=True)
    ap.add_argument("--sc-bridge")
    ap.add_argument("--logs", nargs="*", default=[])
    ap.add_argument("--build", default="", help="game build the localization comes from")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    by_class = localization(args.global_ini)
    by_prefix = prefixed(by_class)
    by_guid = {}
    records = sc_bridge(args.sc_bridge) if args.sc_bridge else {}
    for guid, (cls, name) in records.items():
        # The current patch's wording wins over the older extraction.
        by_guid[guid] = lookup(cls, by_class, by_prefix) or name
    for guid, (cls, _) in records.items():
        by_class.setdefault(cls.lower(), by_guid[guid])

    table = {
        "format_version": 1,
        "game_build": args.build,
        "generated": date.today().isoformat(),
        "sources": ["english/global.ini"] + (["sc-bridge item records"] if records else []),
        "by_guid": dict(sorted(by_guid.items())),
        "by_class": dict(sorted(by_class.items())),
    }
    with open(args.out, "w", encoding="utf-8", newline="\n") as out:
        json.dump(table, out, ensure_ascii=False, indent=0, separators=(",", ":"))
        out.write("\n")
    size = os.path.getsize(args.out) // 1024
    print(f"{len(by_class)} class names, {len(by_guid)} GUIDs, {size} KB -> {args.out}")

    bought = {}
    for log in args.logs:
        with open(log, "rb") as f:
            for line in f:
                if b"SShopBuyRequest" in line or b"SShopSellRequest" in line:
                    n, g = ITEM.search(line), GUID.search(line)
                    if n:
                        bought[n.group(1).decode()] = g.group(1).decode().lower() if g else ""
    if bought:
        by_prefix = prefixed(by_class)
        missing = [c for c, g in bought.items() if not (by_guid.get(g) or lookup(c, by_class, by_prefix))]
        print(f"bought items named: {len(bought) - len(missing)}/{len(bought)}")
        for c in sorted(missing, key=str.lower):
            print("  unnamed:", c)


if __name__ == "__main__":
    main()

"""Build data/<system>.json (one file per system) plus data/index.json from walk.py's output.

Usage: build.py <output folder>

Hierarchy: systems -> <System> -> solar (everything in space) and planetary/lunar
(per body, surface locations, distances in the body's own rotating frame).
Reads from the work folder named by SC_DIST_WORK (set by rebuild.ps1).
"""
import hashlib
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from pathlib import Path

S = Path(os.environ["SC_DIST_WORK"])
OUT = Path(sys.argv[1])
SYSTEMS = {"stanton": "Stanton", "pyro": "Pyro", "nyx": "Nyx"}
RELEASED = set(SYSTEMS.values())
SURFACE_MAX_ALT_KM = 100.0
BODY_ICONS = ("Planet", "Moon")


def clean(s):
    return re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()


def load_types():
    root = ET.parse(S / "dcb/libs/foundry/records/starmap/starmapobjecttypes.xml").getroot()
    return {t.get("RecordId").lower(): (t.findtext("name") or "",
                                        t.findtext("validQuantumTravelDestination") == "True")
            for t in root.iter("StarMapObjectType")}


TYPES = load_types()


def exclusion_reason(rec):
    name, desc = clean(rec["name"]), rec["description"]
    if rec["hide_in_starmap"]:
        return "hidden in starmap"
    if "NOT CURRENTLY ACCESSIBLE" in desc.upper():
        return "marked [NOT CURRENTLY ACCESSIBLE] in game data (upcoming)"
    if name == "RSI Event Platform":
        return "event-only marker, no description"
    m = re.match(r"(\w+) Gateway$", name)
    if m and m.group(1) not in RELEASED:
        return f"gateway to unreleased system {m.group(1)}"
    if name.startswith(("@", "<=")) or not name:
        return "no localized name"
    return ""


NAV_KIND = {"Star": "star", "Planet": "planet", "Moon": "moon", "Station": "station",
            "LandingZone": "landing_zone", "Outpost": "outpost"}
NAME_KIND = [(r" L\d$", "lagrange_point"), (r"^Comm Array", "comm_array"),
             (r"^Mining Base #", "mining_base"), (r"^Transit Point", "transit_point"),
             (r"^Cluster ", "asteroid_cluster"), (r"^(RAB|RMB|PYAM)-", "asteroid_base")]


def kind(rec):
    if rec["nav_icon"] in NAV_KIND:
        return NAV_KIND[rec["nav_icon"]]
    name = clean(rec["name"])
    for pattern, label in NAME_KIND:
        if re.search(pattern, name):
            return label
    tname, _ = TYPES.get(rec["type_id"].lower(), ("", False))
    tname = tname.split("_")[0].lower()
    return {"navpoint": "poi", "manmade": "station"}.get(tname, tname or "poi")


def km(v):
    return [round(c / 1000.0, 3) for c in v]


UNPLACED = "in the starmap but not placed in the game world (upcoming, or not linked in the data yet)"
RECORDS = json.loads((S / "starmap_records.json").read_text(encoding="utf-8"))


def star_of(record_id):
    """Name of the star a starmap record belongs to, following its parent chain."""
    seen = set()
    rec = RECORDS.get(record_id)
    while rec and record_id not in seen:
        seen.add(record_id)
        if rec["nav_icon"] == "Star":
            return clean(rec["name"])
        record_id = rec["parent_record"]
        rec = RECORDS.get(record_id)
    return ""


def unplaced_names(sys_name, placed):
    """Visible, named records of this system that nothing in the world places."""
    names = set()
    for rid, rec in RECORDS.items():
        if rid in placed or star_of(rid) != sys_name or exclusion_reason(rec):
            continue
        names.add(clean(rec["name"]))
    return sorted(names)


def build_system(sys_key):
    sys_name = SYSTEMS[sys_key]
    nodes = [n for n in json.loads((S / f"nodes_{sys_key}.json").read_text(encoding="utf-8")) if n["rec"]]
    by_smr = {}
    for n in nodes:
        by_smr.setdefault(n["smr"], n)
    excluded, seen_smr = {}, set()
    solar, bodies = {}, {}
    star = next(n for n in nodes if n["rec"]["nav_icon"] == "Star")
    star_pos = star["pos_m"]

    def body_of(n):
        return next((by_smr[c] for c in reversed(n["chain"])
                     if c in by_smr and by_smr[c]["rec"]["nav_icon"] in BODY_ICONS), None)

    for n in nodes:
        rec = n["rec"]
        if n["smr"] in seen_smr:
            continue
        seen_smr.add(n["smr"])
        name = clean(rec["name"])
        why = exclusion_reason(rec)
        if why:
            if why != "hidden in starmap":
                excluded.setdefault(why, set()).add(name)
            continue
        tname, qt = TYPES.get(rec["type_id"].lower(), ("", False))
        entry = {"type": kind(rec), "qt_destination": qt}
        body = body_of(n) if rec["nav_icon"] not in BODY_ICONS else None
        if body is not None:
            off = [p - b for p, b in zip(n["pos_m"], body["pos_m"])]
            radius_m = body["rec"]["size"]
            alt_km = (math.hypot(*off) - radius_m) / 1000.0
            if alt_km < SURFACE_MAX_ALT_KM:
                bname = clean(body["rec"]["name"])
                b = bodies.setdefault(bname, {"body": body, "locations": {}})
                entry.update({"pos_km": km(off), "altitude_km": round(alt_km, 2)})
                b["locations"][(name, n["smr"])] = entry
                continue
        if rec["nav_icon"] in BODY_ICONS:
            parent = by_smr.get(rec["parent_record"])
            entry["radius_km"] = round(rec["size"] / 1000.0, 1)
            entry["orbits"] = clean(parent["rec"]["name"]) if parent else sys_name
        rel = [p - s for p, s in zip(n["pos_m"], star_pos)]
        entry["pos_km"] = km(rel)
        entry["from_star_km"] = round(math.hypot(*rel) / 1000.0)
        solar[(name, n["smr"])] = (entry, n["pos_m"])

    def unique(keys):
        counts = {}
        for name, _ in keys:
            counts[name] = counts.get(name, 0) + 1
        return counts

    # nearest planet or moon by altitude above its surface (the record's parent can be far away)
    body_list = [(name, pos, entry["radius_km"]) for (name, _smr), (entry, pos) in solar.items()
                 if entry["type"] in ("planet", "moon")]
    for (name, _smr), (entry, pos) in solar.items():
        if entry["type"] in ("planet", "moon", "star") or not body_list:
            continue
        bname, alt = min(((b, math.dist(pos, bpos) / 1000.0 - r) for b, bpos, r in body_list),
                         key=lambda t: t[1])
        entry["nearest_body"] = bname
        entry["altitude_km"] = round(alt, 1)

    # solar group
    counts = unique(solar)
    # Coordinates only: the skill computes every distance from pos_km on demand.
    sol_locs = {}
    for (name, smr), (entry, _pos) in sorted(solar.items(), key=lambda kv: (kv[1][0].get("from_star_km", 0), kv[0][0])):
        label = name if counts[name] == 1 else f"{name} ({entry.get('nearest_body', smr[:8])})"
        sol_locs[label] = entry

    planetary, lunar = {}, {}
    for bname, b in sorted(bodies.items()):
        body = b["body"]
        counts = unique(b["locations"])
        locs = {}
        for (name, smr), entry in sorted(b["locations"].items()):
            label = name if counts[name] == 1 else f"{name} ({smr[:8]})"
            locs[label] = entry
        # No pairwise table here: it grows with the square of the location count.
        # tools/distance.py computes any surface distance from pos_km on demand.
        group = {
            "radius_km": round(body["rec"]["size"] / 1000.0, 1),
            "orbits": clean(by_smr[body["rec"]["parent_record"]]["rec"]["name"]) if body["rec"]["parent_record"] in by_smr else sys_name,
            "locations": locs,
        }
        (planetary if body["rec"]["nav_icon"] == "Planet" else lunar)[bname] = group

    for name in unplaced_names(sys_name, {n["smr"] for n in nodes}):
        excluded.setdefault(UNPLACED, set()).add(name)

    return sys_name, {
        "star": clean(star["rec"]["name"]),
        "solar": {"locations": sol_locs},
        "planetary": planetary,
        "lunar": lunar,
        "excluded": {why: sorted(names) for why, names in sorted(excluded.items())},
    }


FORMAT = 1  # bump only when readers must change; the skill refuses files with a higher format
INDEX_NAME = "index.json"


def header(sys_name, manifest, revision):
    return {
        "name": f"Star Citizen distances: {sys_name}",
        "system": sys_name,
        "format": FORMAT,
        "revision": revision,
        "units": "km (straight-line)",
        "source": {
            "game_branch": manifest.get("Branch"),
            "game_version": manifest.get("Version"),
            "build": manifest.get("RequestedP4ChangeNum"),
            "data": "LIVE Data.p4k: ObjectContainers (positions) + DataCore starmap records (names, types) + english global.ini",
            "extracted": date.today().isoformat(),
        },
        "how_to_read": {
            "hierarchy": "One file per system: solar | planetary.<planet> | lunar.<moon>. Distances between systems are not covered.",
            "solar": "Everything in space: star, planets and moons (as points at their centre), stations, Lagrange points, jump-point gateways, asteroid bases, comm arrays. pos_km is relative to the star. Planets and moons do not orbit in-game, so these distances are fixed.",
            "planetary_lunar": "Surface locations (less than 100 km altitude) on that body, stored as coordinates only. pos_km is in the body's own frame (centre = 0), so distances between two locations on the same body hold whatever the body's rotation: straight line = |pos_A - pos_B|.",
            "body_distance": "Distances to a planet or moon in `solar` are to its centre; subtract radius_km for distance to the surface.",
            "lookup": "The file holds coordinates only. The SC_distances skill (dependencies/sc_distance.py) computes any distance from pos_km: space to space exact, same body straight line plus over the ground, and a min-max range for a surface location to anywhere else as the body rotates. By hand: straight line = |pos_A - pos_B| within the same group.",
            "nearest_body": "Space locations name the nearest planet or moon and their altitude_km above its surface.",
            "duplicate_names": "If a name occurs twice in one group, the label gets the nearest body or a short record id in brackets.",
            "revision": "Higher revision = newer data. format changes only when readers must change.",
        },
        "rules": {
            "included": "Released systems only, one file each. Locations shown in the starmap and placed in the game world in the current LIVE build.",
            "excluded": "Starmap-hidden markers, records with no localized name, locations marked NOT CURRENTLY ACCESSIBLE, event-only markers, gateways to unreleased systems, and starmap entries nothing places in the world. What was left out is listed under `excluded`.",
        },
    }


def main():
    build_id = (Path(r"D:\Roberts Space Industries\StarCitizen\LIVE\build_manifest.id")).read_text(encoding="utf-8")
    manifest = json.loads(build_id)["Data"]
    revision = int(datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))
    OUT.mkdir(parents=True, exist_ok=True)
    files = {}
    for key in SYSTEMS:
        name, d = build_system(key)
        path = OUT / f"{key}.json"
        raw = json.dumps({**header(name, manifest, revision), **d}, indent=1, ensure_ascii=False).encode("utf-8")
        path.write_bytes(raw)
        files[key] = {"system": name, "file": path.name, "revision": revision,
                      "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
        print(name, "solar:", len(d["solar"]["locations"]),
              "| planetary:", {k: len(v["locations"]) for k, v in d["planetary"].items()},
              "| lunar:", {k: len(v["locations"]) for k, v in d["lunar"].items()},
              "| bytes:", len(raw))
        for why, names in d["excluded"].items():
            print("   excluded:", why, "->", len(names), names[:6])
    index = {"format": FORMAT, "revision": revision, "game_version": manifest.get("Version"),
             "build": manifest.get("RequestedP4ChangeNum"), "systems": files}
    (OUT / INDEX_NAME).write_text(json.dumps(index, indent=1), encoding="utf-8")
    print("index revision:", revision)


if __name__ == "__main__":
    main()

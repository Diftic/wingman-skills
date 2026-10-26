"""Walk a system's ObjectContainer tree and dump every node that carries a starMapRecord.

Output: nodes_<system>.json, a list of dicts with world position (m), the ancestor chain
of starmap-tagged nodes, and the joined starmap record + English name.
Reads and writes in the work folder named by SC_DIST_WORK (set by rebuild.ps1).
"""
import json
import math
import os
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python -I leaves the script folder off
import cryxml  # noqa: E402

S = Path(os.environ["SC_DIST_WORK"])
SOC_ROOT = S / "p4k_all"
SM_ROOT = S / "dcb" / "libs" / "foundry" / "records" / "starmap"
INI = next((S / "p4k_loc").rglob("global.ini"))
MAX_DEPTH = 12

# ---------- quaternion helpers (w, x, y, z) ----------


def qmul(a, b):
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def qrot(q, v):
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z) or 1.0
    q = (w / n, x / n, y / n, z / n)
    p = (0.0, *v)
    qc = (q[0], -q[1], -q[2], -q[3])
    r = qmul(qmul(q, p), qc)
    return (r[1], r[2], r[3])


def vec(s, default):
    if not s:
        return default
    return tuple(float(t) for t in s.split(","))

# ---------- localization ----------


def load_ini():
    out = {}
    with open(INI, encoding="utf-8-sig", errors="replace") as f:
        for line in f:
            if "=" not in line:
                continue
            k, v = line.rstrip("\n").split("=", 1)
            k = k.split(",")[0].strip().lower()
            out.setdefault(k, v)
    return out


INI_MAP = load_ini()


def loc(key):
    if not key:
        return ""
    if key.startswith("@"):
        return INI_MAP.get(key[1:].lower(), key)
    return key

# ---------- starmap records ----------


def load_starmap():
    recs = {}
    by_file = {}
    for p in SM_ROOT.rglob("*.xml"):
        try:
            root = ET.parse(p).getroot()
        except ET.ParseError:
            continue
        rid = root.get("RecordId")
        if not rid or root.get("Type") != "StarMapObject":
            continue
        g = lambda t: (root.findtext(t) or "")  # noqa: E731
        parent = root.find("parent")
        type_el = root.find("type")
        recs[rid.lower()] = {
            "record": rid.lower(),
            "file": str(p.relative_to(SM_ROOT)).replace("\\", "/"),
            "name_key": g("name"),
            "name": loc(g("name")),
            "description": loc(g("description")),
            "nav_icon": g("navIcon"),
            "type_id": type_el.get("RecordId") if type_el is not None else "",
            "parent_file": parent.get("ReferencedFile", "") if parent is not None else "",
            "hide_in_starmap": g("hideInStarmap") == "True",
            "hide_in_world": g("hideInWorld") == "True",
            "block_travel": g("blockTravel") == "True",
            "size": float(g("size") or 0),
        }
        by_file[p.resolve()] = rid.lower()
    # resolve parent record ids
    for r in recs.values():
        pf = r["parent_file"]
        r["parent_record"] = ""
        if pf.startswith("file://"):
            rel = pf[len("file://"):]
            # path is relative to the libs/... tree; normalise against SM_ROOT's ancestor
            m = re.search(r"libs/foundry/records/starmap/(.+)$", rel)
            if m:
                target = (SM_ROOT / m.group(1)).resolve()
                r["parent_record"] = by_file.get(target, "")
    return recs


# ---------- socpak reading ----------
_cache = {}


def soc_index():
    idx = {}
    for p in SOC_ROOT.rglob("*.socpak"):
        rel = str(p.relative_to(SOC_ROOT)).replace("\\", "/").lower()
        idx[rel] = p
    return idx


SOC = soc_index()


def socpak_root(name):
    key = name.replace("\\", "/").lower()
    if key in _cache:
        return _cache[key]
    p = SOC.get(key)
    root = None
    if p is not None:
        stem = p.stem.lower()
        with zipfile.ZipFile(p) as z:
            cand = [n for n in z.namelist() if n.lower() == f"{stem}.xml"]
            if cand:
                try:
                    root = ET.fromstring(z.read(cand[0]))
                except ET.ParseError:
                    root = None
    _cache[key] = root
    return root


_ale_cache = {}


def ale_entities(name):
    """Star map entities listed in a container's .ale (placed without a child container)."""
    key = name.replace("\\", "/").lower()
    if key in _ale_cache:
        return _ale_cache[key]
    found = []
    p = SOC.get(key)
    if p is not None:
        stem = p.stem.lower()
        try:
            with zipfile.ZipFile(p) as z:
                cand = [n for n in z.namelist() if n.lower() == f"{stem}.ale"]
                if cand:
                    found = cryxml.starmap_entities(cryxml.find_embedded(z.read(cand[0])))
        except (zipfile.BadZipFile, ValueError, struct.error) as error:
            print(f"warning: could not read {key} .ale: {error}", file=sys.stderr)
    _ale_cache[key] = found
    return found


def emit_ale(name, pos, rot, depth, chain, out, seen, path):
    for e in ale_entities(name):
        key = path + "/ale/" + (e["guid"] or e["name"])
        if key in seen:
            continue
        seen.add(key)
        wp = tuple(p + d for p, d in zip(pos, qrot(rot, vec(e["pos"], (0.0, 0.0, 0.0)))))
        out.append({
            "guid": e["guid"], "entity": e["name"], "socpak": name + "#ale", "class": e["class"],
            "smr": e["record"], "pos_m": wp, "rot": qmul(rot, vec(e["rot"], (1.0, 0.0, 0.0, 0.0))),
            "chain": [x["smr"] for x in chain], "depth": depth,
        })


def walk(el, pos, rot, depth, chain, out, seen, path):
    kids = el.find("ChildObjectContainers")
    if kids is None or depth > MAX_DEPTH:
        return
    for c in kids.findall("Child"):
        a = c.attrib
        lp = vec(a.get("pos"), (0.0, 0.0, 0.0))
        lr = vec(a.get("rot"), (1.0, 0.0, 0.0, 0.0))
        wp = tuple(p + d for p, d in zip(pos, qrot(rot, lp)))
        wr = qmul(rot, lr)
        guid = a.get("guid", "")
        key = path + "/" + guid
        if key in seen:
            continue
        seen.add(key)
        smr = (a.get("starMapRecord") or "").lower()
        node_chain = chain
        if smr:
            node = {
                "guid": guid, "entity": a.get("entityName", ""), "socpak": a.get("name", ""),
                "class": a.get("class", ""), "smr": smr, "pos_m": wp, "rot": wr,
                "chain": [x["smr"] for x in chain], "depth": depth,
            }
            out.append(node)
            node_chain = chain + [node]
        inline = c.find("ChildObjectContainers")
        if inline is not None and len(inline):
            walk(c, wp, wr, depth + 1, node_chain, out, seen, key)
        if a.get("external") == "1" and a.get("name"):
            sub = socpak_root(a["name"])
            if sub is not None:
                walk(sub, wp, wr, depth + 1, node_chain, out, seen, key)
            emit_ale(a["name"], wp, wr, depth + 1, node_chain, out, seen, key)


def main(system):
    recs = load_starmap()
    root_name = f"data/objectcontainers/pu/system/{system}/{system}system.socpak"
    root = socpak_root(root_name)
    out, seen = [], set()
    origin, identity = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0)
    walk(root, origin, identity, 0, [], out, seen, "")
    emit_ale(root_name, origin, identity, 0, [], out, seen, "")
    for n in out:
        n["rec"] = recs.get(n["smr"])
    (S / f"nodes_{system}.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    (S / "starmap_records.json").write_text(json.dumps(recs, indent=1), encoding="utf-8")
    named = sum(1 for n in out if n["rec"])
    print(system, len(out), "nodes,", named, "with records,", len(_cache), "socpaks read")


if __name__ == "__main__":
    for s in sys.argv[1:]:
        main(s)

"""Find Star Citizen locations and compute distances between them from the data/<system>.json files.

Pure logic, no Wingman imports: the skill and the tests use it, and so can any other skill.
Maintainer check from a shell:

    python sc_distance.py "Lorville" "HDMS-Edmond"
    python sc_distance.py --find edmond

Same body: exact straight line plus the distance over the ground. Both in space: exact.
Surface to anywhere else: planets rotate in game, so the answer is a range around the
centre-to-centre distance (closest and farthest the rotation can make it).
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
INDEX_NAME = "index.json"
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class Location:
    system: str
    body: str | None  # None for a location in space
    name: str
    entry: dict

    @property
    def where(self) -> str:
        return f"{self.name} [{self.system}{' / ' + self.body if self.body else ''}]"


class LookupError_(LookupError):
    """A name that matches nothing, or too many things."""


def load_dir(folder: Path | str = DATA_DIR) -> dict[str, dict]:
    """Read every system file in a folder: {system name: file contents}."""
    systems = {}
    for path in sorted(Path(folder).glob("*.json")):
        if path.name == INDEX_NAME:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        systems[data["system"]] = data
    return systems


def _norm(text: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", text.casefold())


def all_locations(systems: dict[str, dict], system: str | None = None) -> list[Location]:
    out = []
    for sys_name, s in systems.items():
        if system and _norm(sys_name) != _norm(system):
            continue
        out.extend(Location(sys_name, None, n, e) for n, e in s["solar"]["locations"].items())
        for group in ("planetary", "lunar"):
            for body, g in s[group].items():
                out.extend(Location(sys_name, body, n, e) for n, e in g["locations"].items())
    return out


def find(systems: dict[str, dict], text: str, system: str | None = None) -> list[Location]:
    """Exact name (ignoring case, spaces and punctuation), else names starting with it, else containing it."""
    q = _norm(text)
    if not q:
        return []
    locs = all_locations(systems, system)
    for test in (lambda n: n == q, lambda n: n.startswith(q), lambda n: q in n):
        hits = [loc for loc in locs if test(_norm(loc.name))]
        if hits:
            return hits
    return []


def _resolve(systems: dict[str, dict], text: str, system: str | None) -> Location:
    hits = find(systems, text, system)
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise LookupError_(f"No location matches '{text}'.")
    shown = "; ".join(h.where for h in hits[:MAX_CANDIDATES])
    more = f" (+{len(hits) - MAX_CANDIDATES} more)" if len(hits) > MAX_CANDIDATES else ""
    raise LookupError_(f"'{text}' matches {len(hits)} locations: {shown}{more}")


def _resolve_pair(systems, a_text, b_text, system):
    """Resolve both names; a name found in several systems takes the other location's system."""
    try:
        a = _resolve(systems, a_text, system)
    except LookupError_:
        b = _resolve(systems, b_text, system)
        return _resolve(systems, a_text, b.system), b
    try:
        b = _resolve(systems, b_text, system)
    except LookupError_:
        b = _resolve(systems, b_text, a.system)
    return a, b


def _radius(systems, loc: Location) -> float:
    s = systems[loc.system]
    return (s["planetary"].get(loc.body) or s["lunar"][loc.body])["radius_km"]


def _centre(systems, loc: Location) -> tuple[list[float], float]:
    """Star-relative position (km) of a space location, or of a surface location's body plus its offset."""
    if loc.body is None:
        return loc.entry["pos_km"], 0.0
    body = systems[loc.system]["solar"]["locations"][loc.body]
    return body["pos_km"], math.hypot(*loc.entry["pos_km"])


def distance(systems: dict[str, dict], a_text: str, b_text: str, system: str | None = None) -> dict:
    """Distance between two named locations. Raises LookupError_ with a readable message."""
    a, b = _resolve_pair(systems, a_text, b_text, system)
    result = {"from": a.where, "to": b.where}
    if a.system != b.system:
        raise LookupError_(f"{a.where} and {b.where} are in different systems; "
                           "there is no straight-line distance between systems.")
    if a.body is not None and a.body == b.body:
        pa, pb = a.entry["pos_km"], b.entry["pos_km"]
        cos = sum(x * y for x, y in zip(pa, pb)) / (math.hypot(*pa) * math.hypot(*pb))
        result.update(kind="same body", straight_km=round(math.dist(pa, pb), 1),
                      over_ground_km=round(_radius(systems, a) * math.acos(max(-1.0, min(1.0, cos))), 1))
        return result
    if a.body is None and b.body is None:
        result.update(kind="space", straight_km=round(math.dist(a.entry["pos_km"], b.entry["pos_km"])))
        return result
    for x, y in ((a, b), (b, a)):  # a surface location and its own body's centre
        if x.body is not None and y.body is None and y.name == x.body:
            result.update(kind="to own body centre", straight_km=round(math.hypot(*x.entry["pos_km"]), 1))
            return result
    (ca, ra), (cb, rb) = _centre(systems, a), _centre(systems, b)
    d = math.dist(ca, cb)
    result.update(kind="varies as the body rotates", centre_to_centre_km=round(d),
                  min_km=round(max(0.0, d - ra - rb)), max_km=round(d + ra + rb))
    return result


def km_text(value: float) -> str:
    """Readable distance: 3.4 km, 1,174 km, 39,653,165 km (39.7 million km)."""
    if value < 10:
        return f"{value:.1f} km"
    if value < 1_000_000:
        return f"{value:,.0f} km"
    return f"{value:,.0f} km ({value / 1e6:.1f} million km)"


def describe(result: dict) -> str:
    """One or two short lines for the AI to pass on."""
    head = f"{result['from']} to {result['to']}: "
    if "min_km" in result:
        return (head + f"between {km_text(result['min_km'])} and {km_text(result['max_km'])} "
                f"depending on the body's rotation (about {km_text(result['centre_to_centre_km'])} "
                "via the body centre).")
    text = head + f"{km_text(result['straight_km'])} in a straight line"
    if "over_ground_km" in result:
        text += f", {km_text(result['over_ground_km'])} over the ground"
    return text + "."


def describe_location(loc: Location) -> str:
    e = loc.entry
    kind = str(e.get("type", "location")).replace("_", " ")
    if loc.body:
        return f"{loc.name}: {kind} on {loc.body} ({loc.system}), {e['altitude_km']:,} km altitude."
    if e.get("type") in ("planet", "moon"):
        return (f"{loc.name}: {kind} in {loc.system}, orbits {e.get('orbits')}, radius {e['radius_km']:,} km, "
                f"{km_text(e['from_star_km'])} from the star.")
    near = (f", nearest planet or moon: {e['nearest_body']}, {km_text(e['altitude_km'])} above its surface"
            if e.get("nearest_body") else "")
    return f"{loc.name}: {kind} in space in {loc.system}{near}, {km_text(e['from_star_km'])} from the star."


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Distance between two Star Citizen locations.")
    p.add_argument("a", nargs="?")
    p.add_argument("b", nargs="?")
    p.add_argument("--system")
    p.add_argument("--find", metavar="TEXT")
    p.add_argument("--dir", default=DATA_DIR)
    args = p.parse_args(argv)
    systems = load_dir(args.dir)
    try:
        if args.find:
            for loc in find(systems, args.find, args.system):
                print(describe_location(loc))
            return 0
        if not (args.a and args.b):
            p.error("give two location names, or --find TEXT")
        print(describe(distance(systems, args.a, args.b, args.system)))
    except LookupError_ as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

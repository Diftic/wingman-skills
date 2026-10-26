"""Compare data/stanton.json against CaptSheppard's Aaron Halo route lengths and band radii.

The chart transcription lives outside this repo; the check is skipped when it isn't there.
"""
import json
import math
import sys
from pathlib import Path

HALO = Path(r"D:\SC-Aaron-Halo-Nav\aaron-halo-nav.json")
if not HALO.exists():
    print(f"Aaron Halo check skipped: {HALO} not found")
    sys.exit(0)
halo = json.loads(HALO.read_text(encoding="utf-8"))
st = json.loads((Path(__file__).resolve().parent.parent / "data" / "stanton.json")
                .read_text(encoding="utf-8"))["solar"]
locs = st["locations"]
dist = {a: {b: round(math.dist(locs[a]["pos_km"], locs[b]["pos_km"])) for b in locs} for a in locs}


def resolve(code):
    if code in locs:
        return code
    if code.replace("-", " ") in locs:  # Lagrange points without a station, e.g. "CRU L3"
        return code.replace("-", " ")
    hits = [k for k in locs if k.startswith(code + " ")]
    return hits[0] if len(hits) == 1 else None


worst, n = 0.0, 0
band_err = []
for ref in halo["refineries"]:
    a = resolve(ref["refinery"])
    for route in ref["routes"]:
        b = resolve(route["destination"])
        if not a or not b:
            print("unresolved", ref["refinery"], route["destination"])
            continue
        ours = dist[a][b]
        chart = route["route_length_km"]
        radius = locs[b].get("radius_km", 0)
        diff = ours - chart
        n += 1
        worst = max(worst, abs(diff) if not radius else abs(diff), key=abs)
        print(f"{ref['refinery']:7} -> {route['destination']:9} chart={chart:>12,} ours={ours:>12,} diff={diff:>+10,} km ({diff / chart:+.4%}) radius={radius}")
        # band check: point along the straight line at to_destination from B, distance from star
        pa, pb = locs[a]["pos_km"], locs[b]["pos_km"]
        for band in route["bands"]:
            t = band["to_refinery_km"] / ours
            p = [x + (y - x) * t for x, y in zip(pa, pb)]
            r = math.hypot(*p)
            spec = next(x for x in halo["bands"] if x["band"] == band["band"])
            band_err.append(r - spec["peak_km"])
print("routes compared:", n)
print("band points: n=%d, mean(r - peak)=%.0f km, max |r - peak|=%.0f km" % (
    len(band_err), sum(band_err) / len(band_err), max(abs(e) for e in band_err)))

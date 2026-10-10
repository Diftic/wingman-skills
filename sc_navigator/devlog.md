# SC Navigator - Development Log

## Version: 4.8.0.0 (Star Citizen 4.8.0 live-test baseline, 2026-05-25)

Adopted the SC-patch versioning convention from
[`skills/Versioning.md`](../Versioning.md) and bumped to `4.8.0.0` for the
cross-skill 4.8.0 live-test baseline. Added `__init__.py` exposing
`__version__` / `__sc_target_version__`; added `VERSION` / `SC_TARGET_VERSION`
class attributes on `SC_Navigator`; updated `skill_installer_config.json`.

**CAVEAT — the version bump does NOT mean the data is requalified.** The
bundled `sc_distances.json` is still the pre-4.7 dataset (see status below).
The version is being aligned now so dependent skills can compare SC patches
uniformly; the data refresh is a separate, still-pending task.

## 2026-07-11 — Decision: INDEFINITE HOLD until planet-tech releases

Decision by Lars, same reasoning as `sc_navpoint` (see its Devlog, same date):
CIG's planet-tech (his estimate: initial release late 2026 to early 2027) will
put moons and planets in orbital motion, which invalidates any static distance
matrix between locations. Regenerating `sc_distances.json` against the current
4.8.x universe now would be wasted work if the layout goes dynamic within
months. On planet-tech release: reassess whether a static distance dataset is
still meaningful (possibly per-system or time-invariant subsets); until then,
no data regeneration and no code work. The OUTDATED status below still applies.

## Status: OUTDATED — pre-SC 4.7 (2026-04-25)

This skill was built before Star Citizen patch 4.7, which delivered a major overhaul
of navigation points across the universe. The bundled `sc_distances.json` (364
locations, ~134K routes) reflects the pre-4.7 layout — locations, gateway pairs, and
distances are no longer accurate. The skill still runs and produces routes, but the
output should not be trusted for in-game decisions until the dataset is regenerated
against 4.7 nav data.

**To refresh:** rebuild `sc_distances.json` from current 4.7 location data, re-validate
the gateway pairs (Stanton ↔ Pyro ↔ Nyx etc.) against the new universe, update Devlog
status, and remove the "Outdated" tag from `default_config.yaml`.

---

## 2026-02-26 - Initial Implementation

### Task
Build a wingman-ai skill that provides traveling salesman route optimization for Star Citizen.

### Use Cases
- Multiple hauling contracts with pickup/delivery locations
- Selling mining ore to multiple buyer locations
- Buying ore from multiple seller locations
- General multi-stop route planning

### Architecture
- **Pattern**: @tool decorator (recommended by wingman-ai)
- **Algorithm**: Brute-force (<=8 waypoints) or Nearest Neighbor + 2-opt (9+)
- **Data**: Precomputed distance matrix (sc_distances.json, 364 locations, 134K routes, Gigameters)
- **Cross-system**: Routes through gateway pairs (Stanton-Pyro, Stanton-Nyx, Pyro-Nyx)

### Tools
1. `plan_route` - Optimize visit order for N waypoints (TSP)
2. `get_distance` - Distance lookup between two locations
3. `find_location` - Fuzzy location name search

### TODO
- [x] Create devlog.md
- [x] Copy distance data and set up package structure
- [x] Implement route_optimizer.py (RouteOptimizer class)
- [x] Create default_config.yaml
- [x] Create main.py (SC_Navigator skill class)
- [x] Test standalone
- [x] Update devlog with results

### File Structure
```
skills/sc_navigator/
├── main.py                     # SC_Navigator(Skill) - 3 @tool methods
├── route_optimizer.py          # RouteOptimizer class (TSP solver)
├── default_config.yaml         # Skill config, prompt, keywords
├── devlog.md                   # This file
└── data/
    └── sc_distances.json       # 364 locations, 134K routes (4.7 MB)
```

### Test Results (Standalone)
All tests pass. Performance is sub-millisecond for both algorithms.

**Brute-force (4 waypoints, start=Port Olisar):**
```
Port Olisar → Area 18 (42.29 Gm) → Lorville (22.88 Gm) → Everus Harbor (0.01 Gm) → New Babbage (38.40 Gm)
Total: 103.58 Gm | Algorithm: brute_force | Time: <1ms
```

**NN + 2-opt (10 waypoints incl. cross-system, start=Lorville):**
```
Lorville → Everus Harbor (0.01) → HUR-L1 (1.29) → ARC-L1 (20.59) → Area 18 (2.89)
→ Ruin Station (99.24) → Port Olisar (116.49) → CRU-L1 (1.91) → MIC-L1 (51.72) → New Babbage (4.35)
Total: 298.49 Gm | Algorithm: nearest_neighbor_2opt | Time: <1ms
```

**Round trip (Port Olisar → 3 stops → Port Olisar):**
```
Port Olisar → New Babbage (57.47) → Lorville (38.40) → Area 18 (22.88) → Port Olisar (42.29)
Total: 161.04 Gm
```

**Error handling:**
- Unknown locations reported clearly with name
- Case-insensitive resolution works ("lorville" → "Lorville")
- Fuzzy search finds partial matches ("lorv" → Lorville, "port" → Port Olisar, Port Tressler, etc.)

### Notes
- Cross-system distances (e.g. Lorville→Ruin Station) are available directly in the distance matrix from the original measured data, no gateway routing needed for those pairs
- GrimHEX is not in our location data (not in UEX API or route spreadsheet) - it may be listed under a different name or not yet catalogued
- Gateway routing (2-hop) is implemented for Stanton↔Pyro, Stanton↔Nyx, Pyro↔Nyx paths when direct distances aren't available

## 2026-02-26 - Prompt & Tool Description Update

### Changes
- **default_config.yaml**: Rewrote the wingman prompt to:
  - Clarify routes are one-way by default (start → destinations), not round trips
  - Add explicit presentation format with per-leg distances between each stop
  - Instruct wingman to only use `return_to_start=True` when the player explicitly requests it
  - Add gateway mention guidance for cross-system legs
- **main.py**: Updated `plan_route` tool description from "traveling salesman" to "one-way route" framing to avoid misleading the LLM into round-trip behavior

### Rationale
The LLM was not consistently presenting per-leg distances and the "traveling salesman" framing implied round trips by default. The route optimizer already defaults `return_to_start=False`, so this aligns the prompt with the actual behavior.

## 2026-02-26 - Skill Structure Fix (Release Build Compatibility)

### Problem
Skill failed to activate in the release build (PyInstaller exe) with:
`Error activating skill 'SC_Navigator': No module named 'skills.sc_navigator'`

### Root Cause
Non-bundled skills are loaded via `spec_from_file_location` in release builds, not `import_module`. Absolute imports like `from skills.sc_navigator.sc_navigator.route_optimizer import RouteOptimizer` fail because `skills.sc_navigator` isn't registered in the bundled Python import system. Bundled skills (e.g. uexcorp) don't hit this because `import_module` succeeds for them.

### Fix
1. **Flattened structure** — Removed nested `sc_navigator/sc_navigator/` sub-package. Moved `route_optimizer.py` and `data/` directly under `skills/sc_navigator/`.
2. **Adopted sys.path import pattern** — Following the regolith skill's proven approach: add the skill's own directory to `sys.path`, then import sibling modules by bare name. This works in both dev and release builds.

```python
# Before (broken in release):
from skills.sc_navigator.sc_navigator.route_optimizer import RouteOptimizer

# After (works everywhere):
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
from route_optimizer import RouteOptimizer
```

### Lesson
Non-bundled skills must avoid absolute `skills.xxx` imports for their own sub-modules. Use `sys.path` insertion + bare module names instead.

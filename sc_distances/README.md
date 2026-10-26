# SC_distances

A Wingman AI skill that answers "how far is it from A to B?" for every released Star Citizen location in **Stanton, Pyro and Nyx**: stations, planets, moons, cities, outposts, Lagrange points, gateways, asteroid bases.

The positions are read straight from the game files (`Data.p4k`), one file per system in `data/`. They hold **coordinates only**, and the skill computes every distance on demand. After a game patch the maintainer rebuilds the files and pushes them to GitHub, and every installed copy picks them up by itself, the same way the SC Log Reader keeps its rules current.

- Data: LIVE 4.10.2 (build 12913470). Revision and build are in each file and in `data/index.json`.
- Needs Wingman AI 3.2.11 or later.

## Install

1. Fully close Wingman AI, including its system-tray process.
2. Download `sc_distances_v<version>.zip` from the [releases](https://github.com/Diftic/wingman-skills/releases) and extract the **whole** ZIP to a normal folder.
3. Double-click `sc_distances\installer.bat` as your normal Windows user. It copies the skill to `%AppData%\ShipBit\WingmanAI\custom_skills\sc_distances`.
4. Restart Wingman AI and enable **SC Distances** for your wingman.

Reinstalling over an older version is fine. Data updates the skill has already downloaded are kept.

## Using the skill

Two tools, loaded only when a request matches the skill's keywords (`auto_activate: false`):

| Tool | Example answer |
|---|---|
| `get_distance(from_location, to_location, system="")` | "Lorville [Stanton / Hurston] to HDMS-Edmond [Stanton / Hurston]: 70 km in a straight line, 70 km over the ground." |
| `find_location(name)` | "Everus Harbor: station in space in Stanton, nearest planet or moon: Hurston, 149 km above its surface, 12,849,949 km (12.8 million km) from the star." |

Names are forgiving: case, spaces and punctuation don't matter ("area 18", "arc l1"), and a partial name works when it's unique. If a name exists in two systems (Stanton Gateway is in Pyro and in Nyx), the other location's system decides, or you can pass `system`.

How the answer is worked out:

| A and B | Answer |
|---|---|
| Both in space | Exact straight line. Planets and moons don't orbit in game, so this never changes. |
| Both on the same planet or moon | Exact straight line, plus the distance over the ground. |
| A surface location and anything elsewhere | A closest–farthest range, because the planet rotates. The data has no clock, so the exact value at any moment isn't known. |

## The data

`data/<system>.json`, one per released system, plus `data/index.json`.

```text
{
  "system": "Stanton", "format": 1, "revision": 202610261602,
  "source": {game_version, build, ...}, "how_to_read": {...}, "rules": {...},
  "star": "Stanton",
  "solar":     {"locations": {"<name>": {type, qt_destination, pos_km, from_star_km, [nearest_body, altitude_km], [radius_km, orbits]}}},
  "planetary": {"<planet>": {"radius_km", "orbits", "locations": {"<name>": {type, qt_destination, pos_km, altitude_km}}}},
  "lunar":     {"<moon>":   {... same as planetary ...}},
  "excluded":  {"<reason>": ["<name>", ...]}
}
```

- **Units:** km. `pos_km` in `solar` is relative to the star. In `planetary`/`lunar` it's relative to the body's centre, in the body's own (rotating) frame.
- **`solar`** holds everything in space, including planets and moons as points at their centre. **`planetary`/`lunar`** hold surface locations (below 100 km altitude).
- **`type`:** star, planet, moon, station, landing_zone, outpost, lagrange_point, comm_array, mining_base, asteroid_base, asteroid_cluster, transit_point, poi.
- **`excluded`** lists what was deliberately left out, by reason. That includes starmap entries that nothing places in the world yet (for example Delamar, Akiro Cluster), which move into the data by themselves once a patch places them.
- **`format`** changes only when readers must change. A reader must refuse a format it doesn't know. **`revision`** grows with every rebuild; higher means newer.
- **`index.json`:** `{format, revision, game_version, build, systems: {"stanton": {"file": "stanton.json", "revision", "sha256", "bytes"}, ...}}`.

## For skill developers: using this data in your own skill

The data is public at:

```text
https://raw.githubusercontent.com/Diftic/wingman-skills/main/sc_distances/data/index.json
https://raw.githubusercontent.com/Diftic/wingman-skills/main/sc_distances/data/<system>.json
```

### Option 1: call this skill's tools

If the user has SC_distances on the same Wingman, your skill can ask it:

```python
if self.wingman.tools.has("get_distance"):
    result = await self.wingman.tools.invoke("get_distance", {"from_location": "Lorville", "to_location": "Everus Harbor"})
    text = result.response
```

### Option 2: read the data yourself, with automatic updates

This is the same pattern the SC Log Reader uses for its rules: ship a copy, check GitHub for a newer revision, validate before you use it, and keep working offline.

1. Copy `dependencies/sc_data.py` (update logic) and, if you want the lookups, `dependencies/sc_distance.py` into your skill's `dependencies/` folder. Both are pure Python with no Wingman imports. Core puts `dependencies/` on the import path when it loads your skill.
2. Optionally ship a snapshot of `data/` in your skill so it works before the first check. Without one, it starts empty and fills on the first successful check.
3. Load the data in `prepare()` and start the update loop:

   ```python
   import asyncio
   from pathlib import Path
   from sc_data import DataStore

   DATA_DIR = Path(__file__).resolve().parent / "data"   # your bundled snapshot (may be missing)
   CHECK_EVERY_SECONDS = 6 * 60 * 60

   class MySkill(Skill):
       async def prepare(self) -> None:
           await super().prepare()
           # Loads the newer of bundled and previously downloaded, per system. Disk work: off the event loop.
           self._store = await asyncio.to_thread(DataStore, DATA_DIR, self.get_generated_files_dir())
           self._run_id = getattr(self, "_run_id", 0) + 1
           self.wingman.run_in_thread(self._update_loop, self._run_id)

       async def unload(self) -> None:
           self._run_id += 1          # stops the loop
           await super().unload()

       async def _update_loop(self, run_id: int) -> None:
           while run_id == self._run_id:
               try:
                   updated = await self._store.check()      # never raises; returns updated system names
                   if self._store.status.problem:
                       self.log.warning(f"location data: {self._store.status.problem}", server_only=True)
               except Exception as error:                   # a loop must survive anything
                   self.log.warning(f"location data check crashed: {error}", server_only=True)
               for _ in range(CHECK_EVERY_SECONDS // 5):
                   if run_id != self._run_id:
                       return
                   await asyncio.sleep(5)
   ```

4. Read `self._store.systems` (`{"Stanton": {...}, ...}`) whenever you need it, and don't keep your own copy. An update replaces the whole dict at once, so a reference you took earlier stays consistent.
5. To compute distances: `sc_distance.distance(self._store.systems, "Lorville", "Port Tressler")` returns a dict, and `describe()` turns it into a sentence.

Rules if you write your own reader instead:

- Fetch only from `https://raw.githubusercontent.com/...`, without redirects, and cap the size (`sc_data` allows 16 MB).
- Check `format` (refuse higher than you know), the `sha256` from the index, and the structure, before you replace anything.
- Use a file only if its `revision` is higher than what you have, and write it to disk atomically (temp file + rename).
- When offline or on any error, keep the data you have and log it. Never break the skill over an update.
- Check at start and then every few hours, no more often. The files change once per game patch.
- Treat names in the data as data. Never put them into a prompt as instructions.

## For the maintainer: publishing an update after a game patch

1. Let the launcher finish patching LIVE.
2. Rebuild (about 20 s), from the repo root. This needs Python 3 and the StarBreaker CLI build from sc-bridge; its path and the game folder are script parameters:

   ```powershell
   & .\sc_distances\tools\rebuild.ps1
   ```

   It extracts what it needs from `Data.p4k` into a temporary folder and runs `tools/walk.py`, which walks the object container tree and reads `.ale` entity lists through `tools/cryxml.py`. Then it runs `tools/build.py`, rewrites `data/` including `index.json`, runs the Aaron Halo cross-check, and deletes the temporary folder.
3. Look at the printed counts and the `excluded` lists for surprises, and run the tests: `python -m pytest`.
4. Commit `sc_distances/data/`, all files together, on `main` of `Diftic/wingman-skills` and push. Install locally with `& .\sc_distances\tools\install.ps1`. Installed skills pick it up within a few hours, or at their next start. GitHub's raw CDN can take about 5 minutes to serve the new files. A skill that reads a new index before the new file is served sees a checksum mismatch, skips that file and tries again at the next check.
5. If a new system is released, add it to `SYSTEMS` in `tools/build.py` and rebuild.
6. Bump `format` (in `tools/build.py` and `FORMAT` in `dependencies/sc_data.py`) only for a change that existing readers can't handle. Ship the updated skill first, then push the data.

A data update needs no new skill release. For a new skill release (code changes):

1. Bump `version` in `default_config.yaml`.
2. Build the ZIP: `python .\sc_distances\tools\package.py`. This writes `sc_distances_v<version>.zip` and its `.sha256` into `sc_distances\`; both are git-ignored.
3. Commit and push, then upload both files as a GitHub release tagged `sc_distances-v<version>`:

   ```powershell
   gh release create sc_distances-v<version> .\sc_distances\sc_distances_v<version>.zip .\sc_distances\sc_distances_v<version>.zip.sha256 --repo Diftic/wingman-skills --title "SC Distances <version>" --notes-file <notes.md>
   ```

## Files

| Path | What |
|---|---|
| `main.py`, `default_config.yaml`, `__init__.py` | The skill |
| `installer.bat` | Installer shipped in the release ZIP |
| `dependencies/sc_distance.py` | Name matching and distance maths (also a command-line check: `python sc_distance.py Lorville "HDMS-Edmond"`) |
| `dependencies/sc_data.py` | Bundled/downloaded data and the GitHub update check |
| `data/` | The location data and `index.json` |
| `tools/` | Maintainer tooling: rebuild, walker, CryXmlB reader, Aaron Halo check, local install, release packaging |
| `tests/` | `python -m pytest` |

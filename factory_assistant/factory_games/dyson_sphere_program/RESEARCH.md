# Dyson Sphere Program - research notes (2026-10-02)

Installed game: 0.10.35.29104 (D:\SteamLibrary\steamapps\common\Dyson Sphere Program, Unity 2022.3.62f3c1).

## Where things are

| What | Location |
|---|---|
| Saves | `<Documents>\Dyson Sphere Program\Save\*.dsv` (here: OneDrive\Documents, so resolve the Windows Documents known folder; do not hard-code) |
| Autosaves | `_autosave_0..3.dsv` (rotating) and `_lastexit_.dsv`; `.moddsv` beside them only when the DSP Mod Save mod is installed |
| Log | `%USERPROFILE%\AppData\LocalLow\Youthcat Studio\Dyson Sphere Program\Player.log` - says "Game save file wrote" but NOT which save. Cannot identify the active save like Satisfactory does |
| Item/recipe data | `DSPGAME_Data\resources.assets`: MonoBehaviours `ItemProtoSet` (175 items), `RecipeProtoSet` (162 recipes), `TechProtoSet`, `ModelProtoSet`. Read with UnityPy + TypeTreeGenerator (types from Managed\Assembly-CSharp.dll), about 4 s |
| English names | `Locale\1033\*.txt` (UTF-16, tab separated: Chinese key, ..., English) |
| Game version | `Updates\Versions.txt` (last line) |

## .dsv format (header)

`"VFSAVE"`, int64 file length, int32 header version (7), bool sandbox, bool peace,
int32 major/minor/release/build, int64 gameTick (60/s), int64 DateTime ticks,
int32 PNG size + PNG screenshot, AccountData, uint64 dyson energy, then GameData.

GameData order: version, patch, AccountData, gameName, **GameDesc** (galaxy seed, star count),
gameTick, achievements, prefs, **GameHistoryData** (research), **GalaxyData** (veins),
2 bools, **GameStatData** (production statistics), then player, logistics, **factories** (machines, belts), dyson spheres, ...

Everything a player asks most ("what do I make per minute, what is short, power") is in
**GameStatData**, BEFORE the factories. A "light read" stops there:

| Save | Size | Read | Time (generic Python parser) |
|---|---|---|---|
| _lastexit_ (new game, modded) | 7.8 MB | 2 MB | 0.25 s |
| homewrecker (44 planets) | 789 MB | 61 MB | 5.5 s |

ProductStat per item per planet: `total[14]` = produced[7] + consumed[7] for the stat periods
(index 0 = last 10 s, 1 = 1 min, 2 = 10 min, 3 = 1 h, 4 = 10 h, 5 = 100 h, 6 = all time; verified against the Statistics panel 2026-10-03). PowerStat gives energy per period. Most of the 61 MB is the
`count[7200]` history arrays, which a custom reader can skip with seek.

Save identity: `GameDesc.galaxySeed` + `starCount` (stable across autosaves and renames).

## Version risk

The format changes between game releases. Saves here: 0.10.32 (Aug 2025), 0.10.33 (Oct-Nov 2025),
0.10.34 (Apr-May 2026). A parser built for 0.10.34.28529 read 0.10.34.28518 but failed on 0.10.33.
Mods that patch Assembly-CSharp (Orbital Ring) change the factory part, not the light-read part.

## Existing parsers

- qhgz2013/dsp_save_parser (Python, full format, 0.10.34.28529, updated 2026-06). NO LICENSE file: use only as a reference, do not ship it.
- phoenixx-666/dsvfile (Python, MIT, versions unclear), GreyHak/dsp-save-parser (C++, BSD-3).

## Open points

- Machine speeds (assembler Mk1-3, smelters) are on prefabs, not in ModelProtoSet.
- Modded items (LDBTool/Orbital Ring) are not in the vanilla catalog.

## Status (short reader built)

- `reader/save_file.py`: own code from the game's Import methods. Sequential read to `gameTick`, then a validated search for ProductionStatistics (the power-pool signature, then a walk back over the fixed-size ProductStat records). Tested on all local saves: 0.10.33 and 0.10.34 read in 0.01-0.2 s (also 789 MB and 1 GB saves). 0.10.32 does not read (older statistics layout).
- `reader/catalog.py` + `data/catalog_0.10.35.29104.json` (175 items, 162 recipes, 315 techs, English names).
- Power pools: 0 generated, 1 consumed, 2 charged, 3 discharged, 4 research hash, 5 exported. Energy totals are per-tick energy, so watts = total / seconds of the period.
- Next: real 0.10.35 saves from the player for verification; then planet names (factory planet ids are after the statistics) and the factory part.

## Live data (investigated 2026-10-03)

- The game has no export, API, pipe or local server for statistics (HttpManager / Steam classes are for the game's own online use).
- Live values are in memory: `GameMain.statistics.production.factoryStatPool[i]` (FactoryProductionStat) with `productPool[].total` (updated every tick), plus fields that are NOT in the save: `refProductSpeed`, `refConsumeSpeed` (panel "Reference Rate"), `storageCount`, `trashCount`, `importStorageCount`, `exportStorageCount`. Reference rate and storage are calculated on request by the panel (`UIProductEntry.OnRefreshRefSpeedClick`, `OnRefreshStorageCountClick`, `UIStatisticsWindow.RefreshProductionExtraInfo`).
- Power tab values come from `UIStatisticsWindow.ComputePowerTab` (power networks), not only from the statistics pools.
- Options: (A) read-only BepInEx plugin that writes a JSON snapshot every 1-2 s (recommended); (B) external memory reading of the Mono process (fragile, per-version offsets; not recommended); (C) shorter autosave interval (save stutter on large factories).

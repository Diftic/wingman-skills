# Factory Assistant - handover (2026-10-02)

## 1. Goal

One Wingman AI skill for many factory games, built like SC Log Reader:
**one Orchestrator for all games, one Reader + one Handler per game.**
Games now: Satisfactory (complete, from Satisfactory Assistant 0.9.1) and
Dyson Sphere Program (short reader, first version).

Folder: `D:\PycharmProjects\wingman-ai\skills\factory_assistant` (not committed to git).
Read `ARCHITECTURE.md` and `AGENTS.md` first.

## 2. Decisions made (by the user)

| Decision | Result |
|---|---|
| Layers | Orchestrator = Wingman only; Handler = game logic; Reader = save + catalog |
| Orchestrator count | Exactly one. Each game may have its own Reader AND Handler |
| Data source | Read the newest autosave in full (snapshot), not a stream |
| Update frequency | Equals the game's autosave interval (set in the game, not Wingman). Told in the Game setting hint and the skill prompt (the description is kept to one line in the Skills list) |
| Location | New folder `factory_assistant`; `satisfactory_assistant` is unchanged (reference and fallback) |
| Game selection | Setting `game`: Auto (most recently confirmed save wins) or a fixed game |
| Tool names | Game-neutral: `get_factory_context`, `show_factory_map`, `update_factory_plan`, `calculate_factory_plan` (`phase` -> `stage`, `include_alternates` -> `allow_recipes`) |
| Tests | Logic tests target the game handler; thin Orchestrator routing tests |
| DSP | Build the short reader first, then wait for new test saves from the user |

## 3. Structure

```text
main.py                         Orchestrator (FactoryAssistant), the only Wingman import
factory_orchestrator/           map_overlay, overlay_win32, registry (GAMES)
factory_shared/                 contract.py (GameHandler, HandlerContext), journal, workspace, store, coerce
factory_games/satisfactory/     game.py, handler/ (pipeline, solver, ...), reader/ (save parser, Docs, data, Node tool)
factory_games/dyson_sphere_program/
                                game.py, handler/report.py, reader/ (save_file, saves, catalog, data/catalog_0.10.35.29104.json),
                                tools/extract_catalog.py, RESEARCH.md
tests/                          579 tests; test_layer_boundaries.py checks the layer rules; test_dsp.py + dsp_save_builder.py
```

Version 0.10.0 (`RELEASE_NOTES_v0.10.0.txt`). Installer: `install.bat` -> `custom_skills\factory_assistant`.

## 4. Verification status

| Check | Result |
|---|---|
| Test suite (Linux VM, ctypes shim for Win32 overlay) | 579 passed, 13 skipped (skips need a local Satisfactory install) |
| DSP real-save test (`DSP_SAMPLE_SAVE=homewrecker.dsv`, 789 MB) | Passed, 0.2 s |
| DSP reader on all local saves | 0.10.33 and 0.10.34 read; 0.10.32 does not (older layout) |
| Windows test run | NOT DONE - run `python -m pytest` in the skill folder (expect about 579 passed) |
| Live Wingman test | NOT DONE - run `install.bat`, restart Wingman, enable FactoryAssistant |
| DSP 0.10.35 saves | First saves read OK (2026-10-02): `Absolutist` + 4 autosaves, galaxy seed 32570482, vanilla, 0.01 s each. Early game (15 min, hand work only): only all-time totals have values. Mid-game comparison with the Statistics panel still open |

## 5. Next steps

1. User: make more DSP 0.10.35 test saves with clear names (first one: `Absolutist`, early game):
   new game (1 planet); 2+ planets; a known shortage (for example too few iron smelters);
   one planet short of power; if mods are used, one save with and one without mods.
2. Compare the reader's numbers with the in-game Statistics panel for each save.
3. DSP next features: planet names (planet ids are in the factory part, after the statistics),
   research state (GameHistoryData), then factory layout / map / planning.
4. Windows test run and live Wingman test (see section 4).
5. Optional: import notes/plans from Satisfactory Assistant (data is not copied now).

## 6. Things to know

- The git working tree of `skills/satisfactory_assistant` went back to v0.5.0 on 2026-10-01.
  The real v0.9.1 is on branch `backup/local-wip-2026-10-01` (commit 9eccb63) plus untracked
  overlay files and two tests. Factory Assistant was built from that. Restore satisfactory_assistant from that branch.
- DSP saves are in `C:\Users\larse\OneDrive\Documents\Dyson Sphere Program\Save` (Documents is in OneDrive);
  the reader uses the Windows Documents known folder, setting `dsp_save_dir` overrides it.
- The DSP log does not name the loaded save, so the newest complete `.dsv` is the active save.
- qhgz2013/dsp_save_parser has no license: reference only, not shipped. The DSP reader is own code
  from the game's Import methods (decompiled IL of the installed 0.10.35 Assembly-CSharp.dll).
- After a DSP game update: run `factory_games/dyson_sphere_program/tools/extract_catalog.py "<install dir>"`
  (needs `pip install UnityPy TypeTreeGeneratorAPI`).
- Per-planet power counts discharged accumulators/exchangers as supply.
- Session side effects: one stale `.git/index.lock` in wingman-ai was created by a read-only git call and removed
  (user approved); no other git changes. Delete permission was granted for wingman-ai for that session only.

## 7. Log 2026-10-02 (evening)

- New DSP saves (0.10.35.29104): `Absolutist.dsv` and `_autosave_0..3` (autosave every 2 min). All read; game name "Absolutist" is in every autosave.
- Finding: with only hand crafting and mecha mining, the period totals (1 min ... 100 h) are 0 and only the all-time total counts. The report now says "No machines produced anything ..." and lists all-time totals.
- Autosaves now show the game name: "Active save: Absolutist (from autosave)".
- Tests: 579 passed (cloud copy).

## 8. Log 2026-10-02 (21:48 UTC)

- Absolutist at 47 min play time, autosave every 2 min: 4 autosaves read, newest selected correctly. Machines now run: coal, iron, copper, magnets; power 0.3-0.5 MW.
- Finding: in DSP, generation follows use (generators only make what is consumed), so "use >= generation" is always true. The power-shortage warnings (total and per planet) were wrong and are removed. The statistics cannot show spare capacity; real shortage detection needs the factory part (power networks) later.
- Still open: compare the per-minute numbers with the in-game Statistics panel.

## 9. Log 2026-10-03 - first check against the in-game Statistics panel

- Panel "10 minutes", local planet, vs the save: Coal 240.0/min = 2400/10; Iron Ingot use 225.0 = 2250/10; Copper Ingot use 135.0 = 1350/10; Energetic Graphite 120.0 vs 1201/10. Small differences are because the panel and the autosave are from different moments.
- Result: the period index mapping was wrong by one. Correct: total[0] = last 10 s, [1] = 1 min, [2] = 10 min, [3] = 1 h, [4] = 10 h, [5] = 100 h, [6] = all time. Fixed in `reader/save_file.py` (PERIOD_MINUTES) and tests (new test with the real panel numbers).
- All earlier DSP numbers in this chat were about 10x too low for the "10 min" view (they used the 1-min total divided by 10).
- Power: with the fixed mapping the save gives generated 31 MW, consumed 10 MW (10 min). Not yet checked against the Power tab.

## 10. Log 2026-10-03 00:46 UTC - second panel check (passed)

- Panel screenshots ("10 minutes", local planet) were taken between autosaves 00:44:25 and 00:46:25.
- 17 of 18 compared values lie between the two autosaves (factory was winding down, so values fell between saves); exact matches where production was steady: Stone 60/60, Stone Brick 60/60, Steel 20/20, Foundation 20/0, Proliferator Mk.I 180, Crude Oil 167.8 vs 167.7-168.0. Refined Oil use 68.2 vs 67.9/67.5 (small fluctuation).
- Result: production and consumption rates are verified for the 10-minute view. Power (Power tab) is still not verified.
- Energy Matrix 'made 13.6/min, used 0' confirmed correct by the player (no research was running).

## 11. Log 2026-10-03 00:52 UTC - Power tab check (passed, model corrected)

- Power tab (10 min, local planet): Generation Capacity 30.9 MW, real-time demand 20.5 MW, consumption 20.3 MW, Total Energy Consumption 150 GJ, sufficiency 100 %.
- Save 00:50:25: pool "generated" 31.0-31.1 MW = the generation CAPACITY (not energy used). Pool "consumed" all-time = 149.2 GJ = Total Energy Consumption (the energyConsumption field is the same). Last 10 s / 1 min use 18.9 MW and rising (research had just started), 10-min average 13.3 MW. Units: pool totals are joules, watts = total / seconds of the period.
- Earlier claims "generation follows use" and "spare capacity is not in the statistics" were wrong. The report now shows capacity, use (last minute), share of capacity and the window average, and warns at >= 95 % of capacity (total and per planet). New test with the real numbers.
- DSP short reader is now verified for production, consumption and power.

## 12. Log 2026-10-03 - live data investigation and current state

- The Statistics panel updates many times per second; the skill only knows the last autosave (2 min interval now). All panel checks passed with this in mind (panel values lay between the autosave before and after).
- Live extraction investigated in the game code (details: `factory_games/dyson_sphere_program/RESEARCH.md`, section "Live data"). No built-in export exists. Recommended: a small read-only BepInEx plugin that writes a JSON snapshot every 1-2 s; the DSP Reader reads it first and falls back to the autosave. Extra data it could give: Reference Rate, Storage Amount, import/export, power per network, planet names, research.
- DECISION PENDING (user): build the BepInEx plugin (method A) or not. BepInEx is not installed now (doorstop files remain in the game folder, the BepInEx folder is gone). The plugin should be compiled on the user's PC (the cloud environment cannot reach NuGet).

### State at end of session

- Skill: `skills/factory_assistant` 0.10.0, 581 tests pass (Linux VM). Not committed to git.
- Satisfactory: complete (from 0.9.1). Not yet tested on Windows or live in Wingman.
- DSP short reader: verified against the game for production, consumption and power (0.10.35, save "Absolutist", galaxy seed 32570482).
- Open: Windows test run; live Wingman test; planet names; research state; DSP factory part (map, planning); plugin decision; restore `skills/satisfactory_assistant` from branch `backup/local-wip-2026-10-01`.

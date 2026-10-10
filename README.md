# wingman-skills (private)

Mallachi's own Wingman AI skills and R&D — everything that is **not** part of ShipBit's Wingman AI Core.

Backup snapshot created 2026-10-10 from `D:\PycharmProjects\wingman-ai\skills\` (working tree, incl. files that were never committed).

## What lives where
| Thing | Home |
|---|---|
| SC Log Reader **reader code** + SC Accountant | ShipBit `wingman-ai` `develop` (`services/sc_gamelog/`, `skills/sc_accountant/`) — change via PR |
| SC Log Reader **rules** (`instructions.json`) | `Diftic/wingman-ai` → `main` → `skills/sc_log_reader/updates/instructions.json` — **live for all users, do not move** |
| Everything in this repo | here |

## Contents
| Folder | What |
|---|---|
| `sc_log_reader/` | Old v2 skill + Log Reader 2 R&D (`src/`, `tests/`, `tools/`, `docs/`, `reference/`, `integrations/`), log donor, plans/specs |
| `sc_navpoint/` | NavPoint (latest local version, newer than `contrib/sc-navpoint` of 2026-09-21) |
| `factory_assistant/` | Factory Assistant (Satisfactory + Dyson Sphere Program), successor of `satisfactory_assistant/` |
| `satisfactory_assistant/`, `sc_navigator/`, `sc_radio/`, `youtube_video_player/` | Older/other skills |
| `contribution-tools/` | Sept 2026 PR-prep tooling (Check.ps1, allowlists, validators, publication notes) |
| `contribution-tools/pending-patches/` | Uncommitted description edits from the contribution clones (NavPoint one still relevant) |

## Not in git (kept locally only)
- `sc_log_reader/reports/` (~11 GB test/benchmark runs)
- `sc_navpoint/_vendor/` (vendored `opencv-python 5.0.0.93`, ~86-113 MB — reinstall from pip), old models `specialist_v5/v6`, `ocr_dev/captures/` + `screenshots/` (~480 MB screenshots). Runtime model `specialist_v8` IS included.
- release `*.zip` bundles, `.venv/`

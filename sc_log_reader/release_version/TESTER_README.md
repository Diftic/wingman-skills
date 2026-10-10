# SC_LogReader v4.8.3.4 - Community Tester Guide

Thanks for testing! This guide gets you installed and explains what to look
for and how to report back.

---

## What this is

`sc_log_reader` is a Wingman AI skill that watches Star Citizen's `Game.log`
in real time and feeds events to your Wingman - contracts, mission objectives,
location changes, ship enter/exit, injuries, quantum jumps, refinery, trading,
blueprints, mission rewards, and more.

**This build is qualified against Star Citizen `4.8.3`.** If you're on a newer
SC patch, expect possible breakage and please report it.

---

## Install

### Requirements
- Wingman AI desktop app, already installed
- Star Citizen LIVE (PTU/HOTFIX also supported, auto-detected)
- Windows

### Steps

1. Unzip the package somewhere convenient (Desktop is fine).
2. Open the unzipped `sc_log_reader_v4.8.3.4` folder.
3. **Double-click `install.bat`.** It copies the skill into:
   ```
   %AppData%\ShipBit\WingmanAI\custom_skills\sc_log_reader\
   ```
4. You should see `Install complete!` followed by `Press any key to continue...`.
5. Restart Wingman AI.

### Verify the install worked

In your Wingman AI logs (or the console where Wingman runs), look for:

```
SC_LogReader v4.8.3.4 initializing...
```

If you see `v4.8.3.4`, you're on the right build. If you see a different version
or no banner at all, something went wrong with the install - please report it.

In the Wingman AI UI, open your wingman's settings → Skills → confirm
**Star Citizen Log Reader** is listed and enabled.

---

## Configuring the skill

In skill settings:

- **Star Citizen Path** — leave empty for auto-detect, or set explicitly to
  your `StarCitizen` folder (e.g. `D:/Roberts Space Industries/StarCitizen`).
  The skill scans `LIVE`, `PTU`, and `HOTFIX` subfolders automatically.
- **Debug File Output** — leave off unless asked. Turning it on writes parser
  state to JSON files for diagnostics.
- **Notification toggles** — `notify_contracts`, `notify_zones`, `notify_ships`,
  etc. Tune to taste; they don't affect what gets logged, only what gets sent
  to the AI as proactive notifications.

Restart the skill after changing the SC path.

---

## What to test

You don't need to follow a script — just play normally and watch for:

- **Skill loads cleanly** — no Python tracebacks, no error dialogs.
- **Events get reported** — contract accepted, objective complete, location
  arrived, ship enter/exit, quantum target set, refinery submitted,
  blueprint received, mission reward earned, injuries, party invites.
- **Stability over a long session** — run for an hour or more; memory should
  stay flat, no slowdowns, no crashes.
- **Game restart resilience** — alt-F4 SC, restart it, confirm the skill
  resumes monitoring the new `Game.log` without restarting Wingman.
- **Performance** — no noticeable FPS hit in SC, no AI response delay.
- **AI tools** — try asking your wingman things like:
  - "Where am I?" / "What ship am I in?"
  - "What's my active mission?"
  - "What just happened?"
  - "Show me my trade ledger" / "How much profit have I made today?"

---

## Reporting back

For every issue, please include:

1. **Star Citizen version** — LIVE / PTU / HOTFIX, and the build number if you
   know it.
2. **OS / hardware** — Windows version, GPU, RAM (rough is fine).
3. **What you were doing** — "I had just accepted a bounty contract", etc.
4. **What you expected** vs **what happened**.
5. **Game.log if possible.** Located at:
   ```
   <your StarCitizen path>\LIVE\Game.log
   ```
   (or `PTU\` / `HOTFIX\` depending on which build you played). The file gets
   overwritten when SC starts, so grab it BEFORE relaunching after an issue.
6. **Wingman AI log / console output** if there's a Python traceback.

### Severity

- **Critical** — Wingman crashes, skill won't load, blocks other skills,
  any data loss.
- **Major** — Events missed, wrong data, performance issues.
- **Minor** — Cosmetic, edge cases, nice-to-haves.

### Where to send it

> _[Tester feedback channel — fill in: Discord link / email / Google Form / GitHub Issues]_

---

## Known limitations

- Only events emitted to `Game.log` after the skill starts are detected.
  Events from before the skill loaded won't backfill.
- Quantum-target Lagrange-point names (`LOCRRS#L#`) are mapped for the four
  Stanton planets; uncommon orbits may show the raw code.
- Cosmetic item ports (Beard, Piercings, Tattoo, Scar) are intentionally
  filtered out of `attachment_received` to avoid noise.

---

## Thanks!

Feedback from this round goes directly into the regression test corpus and
the next patch (likely `v4.8.2.1` if any critical/major issues land, or
`v4.8.1` when CIG ships the next SC patch).

- Mallachi

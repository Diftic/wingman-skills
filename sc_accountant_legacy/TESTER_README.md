# SC_Accountant v4.8.3.1 — Community Tester Guide

Thanks for testing! This guide gets you installed and explains what to look
for and how to report back.

---

## What this is

`sc_accountant` is a Wingman AI skill that turns Star Citizen into a real
accounting system. It tracks income, expenses, your balance sheet, your fleet,
trade positions, and provides:

- **23 AI voice tools** — talk to your wingman to log transactions, ask for
  reports, plan trades, manage your fleet.
- **A standalone web dashboard** — runs locally, accessible from your tablet/
  phone over LAN via a QR code.
- **Auto-sync from SC_LogReader** — buy/sell trades, mission rewards, and
  blueprint asset registrations are imported automatically.

**This build is qualified against Star Citizen `4.8.3`.**

---

## Strongly recommended companion

`sc_accountant` works standalone, but its **trade auto-import**, **mission
reward import**, and **blueprint → asset registration** features need
`SC_LogReader v4.8.3.4`. Install both for the full experience.

`SC_Accountant` will log a warning at startup if `SC_LogReader` is missing or
on a mismatched SC patch — that warning is intentional, not a bug. Report it
only if `SC_LogReader v4.8.3.4` is installed and the warning still fires.

---

## Install

### Requirements
- Wingman AI desktop app, already installed
- Windows
- (Optional but recommended) `SC_LogReader v4.8.3.4` already installed

### Steps

1. Unzip the package somewhere convenient.
2. Open the unzipped `sc_accountant_v4.8.3.1` folder.
3. **Double-click `install.bat`.** It copies the skill into:
   ```
   %AppData%\ShipBit\WingmanAI\custom_skills\sc_accountant\
   ```
4. You should see `Install complete!` followed by `Press any key to continue...`
5. Restart Wingman AI.

### Verify the install worked

In your Wingman AI logs (or the console where Wingman runs), look for:

```
SC_Accountant v4.8.3.1 initializing...
```

About 5 seconds later you should also see one of:

- `SC_Accountant: SC_LogReader compatibility OK (v4.8.3)` — both skills are
  on the same SC patch, you're good.
- A warning if `SC_LogReader` is missing or on a different SC patch.

In the Wingman AI UI, open your wingman's settings → Skills → confirm
**SC Accountant** is listed and enabled.

---

## Configuration

In skill settings:

- **Starting Balance** — set this **once** on first use (your current aUEC).
- **Auto-Sync Interval** — `30s` default. Set `0` to disable trade auto-import.
- **Currency Format** — `Full` (`1,234,567 aUEC`) or `Short` (`1.2M aUEC`).
- **Complexity Tier** — controls which AI tools are surfaced:
  - **Casual** — basic income/expense, balance, simple P&L.
  - **Engaged** *(default)* — adds fleet, positions, planning, credits/debts,
    hauling.
  - **Industrial** — full feature set incl. scenario modelling.
- **Auto-Generate Opportunities** — generate trade opportunities when market
  data refreshes.
- **Min Opportunity Profit** — threshold for the above (default `1,000`).
- **Auto-Track Positions** — open/close positions on commodity trades.

---

## What to test

You don't need to follow a script. Play normally and watch for:

### Core
- **Skill loads cleanly** — no Python tracebacks, no error dialogs.
- **Stability over a long session** — run for an hour or more; memory flat.
- **Dependency-version check fires correctly** — see "Verify the install"
  above.

### Voice tools
Try asking your wingman things like:
- "How much profit did I make today?" — Income Statement.
- "What's my balance sheet?" — Assets / Liabilities / Equity.
- "Log a 50,000 aUEC repair expense."
- "What ships do I own?" — Fleet listing.
- "What's a good cargo run from Lorville right now?" — Trade opportunity.
- "Open a position for 100 SCU of titanium at 25 aUEC."
- "Plan a 200 SCU titanium run, break-even at 28 aUEC, target 32."

### Auto-sync (with `SC_LogReader` installed)
Play SC normally and confirm:
- **Commodity trades** — sell at a Trade & Development Company terminal,
  ask "show me my recent trades", expect the sale to appear within ~30s.
- **Mission rewards** — complete a cargo haul mission, expect a
  `Mission Reward: <name>` income entry shortly after.
- **Blueprint registration** — receive a blueprint reward, check
  "what assets do I own?" — expect the blueprint to appear (type: blueprint,
  value: 0).

### Web dashboard
- **Open the dashboard** — your wingman should respond to "open my dashboard"
  by launching the local URL.
- **About tab** — should show a QR code for LAN access.
- **Scan the QR with your phone on the same network** — dashboard should load.
- All tabs (Statements, Fleet, Positions, etc.) populate from your data.

---

## Reporting back

For every issue, please include:

1. **Skill versions** — confirm `SC_Accountant v4.8.3.1` from the banner. If
   `SC_LogReader` is installed, confirm it's also `v4.8.3.4`.
2. **Star Citizen version** — LIVE / PTU / HOTFIX, and build number if known.
3. **OS / hardware** — Windows version, GPU, RAM (rough is fine).
4. **What you were doing** — "I had just sold 50 SCU of laranite", etc.
5. **What you expected** vs **what happened**.
6. **Wingman AI log / console output** if there's a Python traceback.
7. **For dashboard issues** — browser, whether it was localhost or LAN.

### Severity

- **Critical** — Wingman crashes, skill won't load, data corruption,
  wrong financial totals.
- **Major** — Auto-sync misses transactions, voice tools return wrong data,
  dashboard tab broken.
- **Minor** — Cosmetic, edge cases, nice-to-haves.

### Where to send it

> _[Tester feedback channel — fill in: Discord link / email / Google Form / GitHub Issues]_

---

## Known limitations

- **Combat / bounty mission rewards** are not auto-imported. CIG only logs
  `"Awarded N aUEC:"` for cargo haul completions — combat cash rewards have
  no log line. Log them manually with "log income".
- **Starting balance is set once.** Changing it later won't backdate; it just
  posts an adjustment.
- **Web dashboard is LAN-only by default.** No external exposure, no auth.
  Don't port-forward it to the public internet.
- **Auto-tracked positions** assume one open position per commodity per
  location at a time.

---

## Thanks!

Feedback from this round goes directly into the next patch — likely
`v4.8.0.1` if any critical/major issues land, or `v4.8.1` when CIG ships
the next SC patch.

— Mallachi

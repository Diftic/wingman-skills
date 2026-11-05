# Local support model vs Jev vs main model — what broke, and whose fault it was

Two evenings of Wingman AI Core 3.2.13 logs (2026-11-04 and 2026-11-05), read against the
Star Citizen `Game.log`, the installed skills and the Core source. Every problem is attributed
to one of three models or to code/config, with the evidence. Written so the fixes can be
aimed at the right layer.

Machine: Ryzen 7 7700X (16 threads), RTX 4070 Ti 12 GB, Star Citizen LIVE 4.x. Wingman Ultra.

## The three models

| Model | Where it runs | What it does |
|---|---|---|
| **Support model** — Qwen3.5-4B Q4_K_M | local, llama.cpp on CPU (`llama_cpp.mode: local`, `gpu_backend: cpu`) | event reaction lines (`sc_game_events`), filler lines, memory checkpoints, tool-result summaries |
| **Jev / System One** | ShipBit Gateway (cloud) | which wingman answers; is this a command, which one; vocabulary fixes |
| **Main model** — DeepSeek V4.1 flash | ShipBit Gateway (cloud) | everything the wingman says in conversation, every tool call |

## Findings by owner

### Support model (local 4B on CPU) — most of the noise

The reaction prompt (`sc_game_events/reaction_prompt.md`) already forbids each failure below
(exact names, no invented facts, "you" not a name, keep tense and weight). The model broke them
anyway. A Q4 4B is near the floor of what can do this task at all.

Wrong content, 11-04 and 11-05:

- Invented facts: "hunting Vanduul-rated targets" (report: CrimeStat targets), "hangar door
  stands open", "Stanton Station's docks", "Shields are down, you are landed" (ship moving, no
  shield value in telemetry), "Captain is offline; I stand by." (report: user at main menu).
- Numbers: 500 aUEC read as "Fifty hundred" (3×) and "one thousand"; the backpack purchase
  (−2,280) spoken as "2,546" — the previous purchase's price.
- Addressee: "You are off grid, Laura." (the user called by the wingman's name).
- Garbled/truncated: "Quantum drive active and engaged, you.", "You just walked away",
  "Monitored space entered, you." (2×, 11-05).

Latency, 11-05 (on foot in Orison; Star Citizen at 81 % of 16 threads):

- Medbed heal: `Game.log <MED BED HEAL>` 21:38:31.9 → spoken 21:39:26 = **54 s**. Log reader
  polls every 0.25 s; nothing else was queued on the support server; reasoning is off. The
  time is generation.
- Measured on the live CPU server: 544-token prompt → 35.8 s wall, 18 prompt tok/s,
  4.6 gen tok/s. The reaction prompt is ~1,000 tokens. Filler lines "ready after" 11–132 s.
- The day before (in space, lighter CPU load) the same model answered in seconds — the
  slowness scales with the game's CPU use.

GPU test (11-04, 21:33–21:48): `gpu_backend: cuda` with Star Citizen running. llama-server
got 503 MB of dedicated VRAM (SC held 10.7 of 12.3 GB) and paged the rest: 1.0 prompt tok/s,
12 gen tok/s, 112 s to start, 24 s for a 3-token prompt. **A local support model cannot use
this GPU while Star Citizen runs.** Reverted the same evening.

Two small code contributors in `sc_game_events` (installed live-test copy), not changed yet:

1. Amounts are formatted as floats (`amount 500.0 aUEC`, `notifications.py` ~L466).
2. The anti-repetition hint feeds the first four words of the last lines back, numbers
   included ("You spent 2,546 aUEC on"), which is where the wrong backpack price came from.
3. (Gap) `_phrase()` duration is not logged, so a slow model and a slow reader look alike.

**Decision 2026-11-05 21:45: support model switched to `llama_cpp.mode: cloud`.** Removes the
CPU contention and uses a stronger model. Hardware route for a local model: a second GPU for AI,
or a 24 GB card.

### Jev / System One — one serious false fire

- 11-05 20:46:49: "Yeah, we're gonna have to empty bags first." → `Jettison Cargo` at **0.84**,
  above the 0.8 bar (`services/jev_gate.py` `COMMAND_CONFIDENCE`); Core pressed alt+j. The
  command had no instant-activation phrases; the criterion was its description "Dump the
  cargo out of the hold, right now." The question already says "decide by what the speaker
  wants done, not by which words appear".
- Design gap: one bar for every command, irreversible or not. Logged as
  `sc_log_reader/docs/CORE_UPDATE_REQUESTS.md` **item 17** (per-command confidence flag or a
  confirmation step; related: "View 3" at 0.88 for "Contract three", item 16 footnote).
- Workaround applied in `Laura.yaml`: the description now says what the command is not
  ("Emptying bags, backpacks, pockets or the inventory is NOT this command").
- Otherwise healthy: ~0.5 s per turn, right wingman every time checked. One vocabulary
  timeout (11-04 20:25, 1.5 s deadline) — gateway latency, not local.

### Main model (DeepSeek flash) — behaviour, not breakage

- Opened the YouTube player unasked (11-04 20:01) answering "I'm not in the hangar yet, am I?":
  `show_player` → `get_player_status` → `star_citizen_status`. Two `stop_player` calls did not
  clear the screen; only `hide_player` did.
- "My name is not Laura." → "Noted — Orin, then. Call me Orin." (a name from nowhere).
- Confident wrong explanations of its own lines ("fleet shorthand", "wrong call sign",
  "the delay is on the report delivery").
- Reflex "Acknowledged, Captain." / "Sir." to thanks and small talk (persona).

### Code fixes applied (user side, local, not pushed to any skill release)

`%APPDATA%\ShipBit\WingmanAI\custom_skills\youtube_video_player\` (v1.0.1, not bumped):

- `stop_player` now also hides the overlay (the player's idle auto-hide only runs on the YouTube
  ENDED state, so it never fired after a stop). Description covers "close the player".
- `show_player` description and skill prompt: call only on an explicit "show player"; never to
  check status or because the player is hidden; non-music questions never touch the player.
- The copy in this repo (`youtube_video_player/`) is an older build without hide/show and was
  not touched. The skill self-updates from `Diftic/Wingman-Player` releases.

### Config changes applied

| File | Change | Status |
|---|---|---|
| `3_2_13\configs\settings.yaml` | `gpu_backend: cpu → cuda → cpu` (11-04) | reverted, backup `settings.yaml.bak-2026-11-04-cpu` |
| `3_2_13\configs\settings.yaml` | `llama_cpp.mode: local → cloud` (11-05 21:45, by the user in the client) | live |
| `3_2_13\configs\Star Citizen\Laura.yaml` | Jettison Cargo description (11-05) | live, survived a client save |

## Still open

- Verify the cloud support model: next reaction lines vs `Game.log` timestamps (latency) and
  against the rules (wording).
- `sc_game_events` small fixes 1–3 above.
- Mic input overflows (SteelSeries Sonar, ~40 on 11-04, 7 on 11-05) — not investigated.
- NavPoint "screen grab failed: Star Citizen is not foreground" warnings — noisy, harmless.
- Core items 16 and 17 for ShipBit.

## Evidence

- Core logs: `%APPDATA%\ShipBit\WingmanAI\3_2_13\logs\wingman-core.2026-11-04_19-16-16.log`,
  `…21-33-06.log` (CUDA), `…21-48-30.log`, `wingman-core.2026-11-05_20-30-25.log`, `…21-04-19.log`.
- Game log: `D:\Roberts Space Industries\StarCitizen\LIVE\Game.log` (UTC timestamps; local = +1 h).
- Claude action log: `~/.claude/logs/D-/2026-11-04.jsonl`, `2026-11-05.jsonl`.
- Session handovers: `D:\PycharmProjects\wingman-ai\.claude\HANDOVER.md`, this repo's `.claude\HANDOVER.md`.

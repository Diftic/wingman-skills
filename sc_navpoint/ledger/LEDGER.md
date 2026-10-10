# sc_navpoint LEDGER — the local OCR effort

Built 2026-08-02 after the user called a halt: "I feel like we have been
stumbling around in circles for the past 2 days."

**Scope:** the local OCR effort, 2026-07-27 onward. Earlier Vision-era history
stays in `Devlog.md` as archive.

## Why this exists

`Devlog.md` is 2,556 lines, `TODO.md` is 1,200+, the session journal is 699.
All three are chronological and append-only. **Nothing is indexed by question,
only by date.** So a correction gets filed where it was DISCOVERED and never
reaches where the number is USED.

Nine headline numbers were revised in six days. Every revision was found by
honest re-measurement and recorded honestly. Several of the originals are still
sitting in the documents, being read as current.

**The rule this ledger enforces: one canonical row per quantity. Everything else
cites it and never restates it.** Today the read-cost figure lives in six places
and correcting one leaves five wrong.

## The three files

| file | answers |
|---|---|
| `LEDGER.md` (this) | what is the current number, and what do the sources disagree about |
| `REFUTED.md` | what was tried and failed, and must not be retried |
| `CORPUS.md` | what capture data exists, and what each one actually shows |

---

# CANONICAL NUMBERS

## Current installed build — 2026-09-20

This section describes the Wingman 3.2.2 test installation. Earlier OCR
performance tables below document the retired fixed-font reader and its
historical experiments; they are not measurements of the current V8 runtime.

| quantity | current value | evidence / limit |
|---|---|---|
| Full skill tests | **1,269 passed in 24.29 s** | Wingman 3.2.2 API update; automated evidence only |
| Verified package files | **83 release / 81 installed** | v4.9.0.26 deployment manifest; installer.bat and tester readme are package-only |
| Installed version / startup | **4.9.0.26 / auto_activate true** | actual installation verified; full Wingman restart pending |
| Runtime OCR readers | **1: V8 FrameAwareReader** | installed model load passed; experimental selector removed |
| Catalog calibration audit | **151 sites + 28 planets, no guard failures** | all catalog entries exercised; legacy bypasses subsequently removed |
| Site replay data | **75 distinct-time Levski pairs** | `site-calibration-replay.json` |
| Site replay maximum residual | **0.184 m training / 0.146 m held-back prediction** | positional fit; live direction alignment still pending |
| Calibration position tolerance | **50 m** | user-selected limit, shared by site/planet fit gates |
| Arrival stop distance | **250 m default** | surface/site and confirmed same-session space target; consecutive valid readings required |
| ERROR display threshold | **8 consecutive failures** | retains last valid dot; elapsed time depends on actual capture cadence |
| Saved shutdown waypoints | **1: Landing Deck 4, levski_all-001** | read-only SQLite snapshot; no waypoint removed |

Manifest/evidence root:
`D:/Navpoint-background-20260909/live-v322-v49026-20260920/`.
Historical shutdown snapshot: `D:/Navpoint-background-20260909/live-v211-20260915-224128/shutdown-20260915-235301/`.
Resume checklist: [HANDOVER_2026-09-15.md](../HANDOVER_2026-09-15.md).
Latest cleanup: [VISION_CLEANUP_2026-09-17.md](../VISION_CLEANUP_2026-09-17.md).
Cleanup backup/evidence: `D:/Navpoint-background-20260909/vision-cleanup-20260917-224325/`.

One row per quantity. If you need a number, take it from here. If you change a
number, change it **here** and nowhere else.

## Reader performance

| quantity | current value | tier | superseded values, do not use |
|---|---|---|---|
| read cost, full block, game running | **4.5 to 4.9 s** | MEASURED | 5.18 ms (wrong artifact), 26.4 s (idle, 20 rows), 1.7 s (idle) |
| read cost, live in-skill | **831 ms median = 1.20 Hz** | MEASURED | |
| CamDir-only read | 14x cheaper than ten rows | MEASURED, **ratio only** | absolute timings from 07-31 evening are untrustworthy |
| block grab vs full monitor | 4.3 ms vs 104 ms | MEASURED | |
| character accuracy, in-sample | 359/359 = 100.00% | MEASURED, **in-sample** | 98.33% (tool was broken) |
| character accuracy, out-of-sample | 305/321 = 95.02% | MEASURED | |
| usable rate, open space (live flight) | **17/20 = 85%** | MEASURED, 20 frames of ONE flight | |
| usable rate, sunlit terrain | **62 to 100% of cells REFUSE** | MEASURED, on real ground | |
| usable rate, P5 L2 sitting still | 12/15 clean payloads | MEASURED | |
| usable rate, stored corpus | 13/43, pessimistic by design | MEASURED | 4/43 before 07-31 |
| **what decides a refusal** | **block background median RGB: 76-95 refused EVERY frame, 8-34 parsed EVERY frame** | MEASURED 2026-08-10, `jumppoint-pyro-nyx`, **same pose, same overlay, only brightness varying** | the cleanest control yet on the bright limit; one wrong character in `Root` or `Pos:` refuses the whole stack |
| usable rate, live jump point | 29/40 = 72% | MEASURED 2026-08-10 | |
| usable rate, live descent + daylit surface | 39/96 = 41% | MEASURED 2026-08-10, `pyro3-bloom-approach` | consistent with the sunlit row above |

## Reader performance, MEASURED 2026-08-11 (`ocr_dev/bench_reader.py`)

1028 frames, 23 sessions, 768.7 s. Report at `ocr_dev/baseline-2026-08-11.md`.
**CONTAMINATED RUN: read that report's caveat before quoting a millisecond.**
Star Citizen was running at the start and EXITED mid-run, and a competing
benchmark process overlapped an unrecoverable early portion. Absolute times are
an UPPER BOUND; the ratios are the durable part, since both sides of each saw
the same contention.

| quantity | value | tier |
|---|---|---|
| read, warm alignment | **468.1 ms** p50 (n=724) | MEASURED |
| read, cold alignment | **901.2 ms** p50 (n=38) | MEASURED |
| read, warm + SELF-HEAL | **1266.1 ms** p50 (n=196) | MEASURED |
| self-heal frequency | **196 of 958 decoded frames, ~1 in 5** | MEASURED |
| alignment fit, timed directly | **384.4 ms** p50 (n=63) | MEASURED |
| block decode | **546.5 ms** p50 | MEASURED |
| semantic parse | **0.1 ms** p50 | MEASURED |
| decode-attempt rate | 958/1028 = 93.2% | MEASURED |
| accepted rate | 647/1028 = 62.9%, **62.6% once the menu phantom is refused** | MEASURED |
| measurement noise floor | 0.5% over 5 identical-pixel reads | MEASURED, **flatters the run** (taken last, after the game exited) |

**The ledger's old "about 300 ms of a 870 ms read" was a source comment carrying
a hypothesis. Measured, the fit is 384.4 ms and 42.7% of a cold read**, higher
than the guessed 34%.

**THE SELF-HEAL IS THE COMPOUNDING COST.** A warm read that decodes nothing
trusted makes `read` invalidate, refit and decode a SECOND time, so it costs
2.70x a plain warm read, and it fires on the scenes that were already refusing:
`starfield`/`vote-fast` 80%, `terrain-01` 60%, `bright-01/02` 56%, against 0% on
`surface-01`, `p5l2`, `game-mid`. **One exception matters**: `nosignal-01`
accepts 0% but self-heals on only 10%, because with the overlay OFF all 8 rows
decode EMPTY with zero refused cells and therefore count as trusted. The trigger
is "no row decoded", not "no payload produced". An empty scene is cheap; an
unreadable one is expensive.

### Brightness is NOT monotonic, and a brightness-only rule would be wrong

| session | background median | accepted |
|---|---|---|
| `red-01` | **52.0** | **74%** |
| `starfield` | **53.0** | **0%** |
| `vote-fast` | 48.7 | 0% |

`starfield` is the Nyx glacier ring: bright ice debris on dark teal, so it is
STRUCTURED rather than bright. **Structure and brightness are separate causes
and this run cannot separate them.** `nosignal-01`'s 0% is the overlay being
off and is not a brightness data point at all. Any preprocessing aimed only at
bright backgrounds should be expected to leave the structured cases unfixed.

### The 5 Hz cadence gate is not reachable with this reader

`Supercalifragilistic.md` §17 asks for 5 accepted fixes per second, a 200 ms
budget. The structural warm lane is **468 ms before any grab is added**, 2.3x
over, and 6.3x over on a self-healing frame. Latency is CPU-bound on one core
(p50 wall 533.7 ms against CPU 515.6 ms). This is the evidence-backed
bottleneck report §18 Wave 5 accepts in place of the target.

**Never quote these three throughputs**: `camdir-01` 129 Hz, `game-bright` 160,
`ice-bright` 186. They are precondition REJECTIONS, not fast reads;
`game-bright` and `ice-bright` never decoded a single frame.

**Harness cross-check:** it reproduces the acceptance rates `CORPUS.md` derived
with a DIFFERENT tool and a different parser, exactly: `jumppoint-pyro-nyx`
29/40, `pyro3-bloom-approach` 39/96, `pyro5-vuur` 78/156.

## Thresholds and constants

| constant | value | tier | note |
|---|---|---|---|
| `REFUSE_COST` | 15.0 | CHOSEN | **hard ceiling ~17**: orange digit floor 17.13, nearest known-bad 17.94 |
| real headroom | **2.94 units** | MEASURED | not 23.56 |
| `REFUSE_MARGIN` | 8.0 | CHOSEN | **inert**: zero decisions changed over 28,234 known-bad + 680 known-good |
| ink contradiction | `max(50, 6 * row bg median spread)` | MEASURED | K in 4-8 identical; K=10 loses detection |
| flat-white | spread <5, mean >=250, >=40 above row bg | MEASURED | 0 fires in 1980 real blanks |
| capture precondition | reject if any row >=15% clipped | MEASURED | on FIXED geometry, never the fitted origin |
| precondition reject rate | **7 of 153** | MEASURED | not 9 |
| `_BODY_SCALE_M` (floor) | 50 km | CHOSEN | sits in a measured empty band |
| `_CONTAINER_SCALE_M` (ceiling) | 15,000 km | **CHOSEN, NOT MEASURED** | largest real body scale is unmeasured |
| `_MIN_WORLD_ROOT_M` | 1,000,000 m | **CHOSEN, inside a MEASURED ten-decade empty band** | main menu **1.740 m** (`login`+`login-black`, 5/5 frames); smallest real Root magnitude anywhere **1.3889e10 m** (`pyro5-vuur`, minimum over 647 accepted stacks in 23 sessions). Safe range **1e4 to 1e9**, derived 2026-08-11. LOW is the safe direction inside the band: the lower endpoint is exactly known and reproducible, the upper is a sample minimum from one player and two systems. **Do not raise it** |
| `POSITION_ROWS` | 8 | CHOSEN | rows 8+ are the second pitch class; do not go below 8 |
| block width | 88 cells / 660 px | MEASURED plateau | 96 gives the gain back, 104 loses 8 rows |
| character pitch | exactly 7.5 px | MEASURED | 7.496 was the JPEG-era estimate |
| row pitch | exactly 13 px, 8 px body | MEASURED | |
| second pitch class | 6.595 px | MEASURED | no line the skill reads is in it |
| `MARK_CAPTURE_ATTEMPTS` | 5, 60 ms apart | **CHOSEN, no derivation** | added 2026-08-01 |

## Frames and drift

| quantity | value | tier |
|---|---|---|
| rotating body frame drift, Pyro 3 | 137.6 m/s (89 pairs), 148.9 (74 pairs), 63.4 (17 pairs) | MEASURED |
| rotating body frame drift, Daymar | 122.7 m/s, 37.5 km over 5 min, dz exactly 0 | MEASURED |
| **rotating body frame drift, Vuur (Pyro 5 moon)** | **146.472 m/s**; stationary player moved **0.000 m** in the body frame and **9,752.227 m** in Root over 66.6 s | MEASURED 2026-08-10, `vuur-return-outside`, 14 consecutive decoded frames |
| stationary player, body vs system frame | 25.46 m vs **26.039 km** over 189 s | MEASURED |
| rest-stop container `P5_?2` drift | 0.000 m/s (111 pairs) | MEASURED |
| cargo bay, hangar, parked ship drift | 0.000 to 0.047 m/s | MEASURED |
| ring station drift | 0.001 m/s, **ONE pair, 2 s apart** | MEASURED but **insufficient** |
| jump point drift | **0 m, byte-identical Root over frames 11-14 while stationary** | MEASURED 2026-08-10 (`jumppoint-pyro-nyx`); was "no pair exists" |
| P5 L2 container scale | **44,707 km** | MEASURED | (41,726 km was its x axis) |
| Z pass-through, world containers | 330 exact matches, 0 exceptions | MEASURED |
| Z pass-through, vehicles/interiors | 288 or 295 never-match (see #1) | MEASURED |


## Coordinate stack (schema 1), added 2026-08-10

| constant | value | tier | note |
|---|---|---|---|
| `LOCAL_TRACKING_MAX_M` | 3,000,000 m | **CHOSEN by the user** | twice the ~1.5 Mm largest OM1-to-OM2 separation. A product invariant, deliberately not a YAML property |
| `LOCAL_TRACKING_ENABLED` | **False** | GATE | the outermost-pre-Solar-row hypothesis is UNMEASURED; see below |
| coordinate schema | 1 | | database schema v4, additive; legacy rows carry 0 and a NULL Root |
| test count | **862** | MEASURED 2026-08-10 | 678 baseline plus 184 |

**The 3 Mm ceiling does NOT rest on the disputed 15,000 km numbers.** It is a
separate quantity with a separate justification, and the body/container scale
window is not consulted by any stack route.

### What the stack rework did NOT establish

Stated plainly, because the routing code is written and looks finished.

- **"The row immediately before SolarSystem is the body or area frame" has
  never been measured AS A UNIVERSAL, and the replay below shows it selecting a
  SHIP.** No paired capture exists across two ships, a landed ship against
  standing outside it, or a jump point. If it selects a MOVABLE container, a
  waypoint would track whoever owns that ship.
  `LOCAL_TRACKING_ENABLED = False` is what stands between that and the player.
- ~~No stack has ever been parsed from real pixels.~~ **Superseded
  2026-08-10 by the corpus replay below.** It was true when written.
- ~~No live capture has been taken since 2026-07-31 22:07:10.~~ **Superseded
  2026-08-10**: three live sessions taken during the evidence-gate flight, see
  `CORPUS.md` "LIVE CAPTURES". The availability figures still govern whether any
  of it runs at all.
- ~~Whether a Pyro 3 surface capture now SUCCEEDS in the field is untested.~~
  **Superseded 2026-08-10**: `pyro3-bloom-approach` produced 19 frames the
  legacy parser refused and the stack accepted, live, at a new site.

### Corpus replay, MEASURED 2026-08-10 (Wave 5 step 1)

Tool `ocr_dev/stack_replay.py`, which decodes each retained PNG with the
shipping reader at `overlay_reader.POSITION_ROWS` and feeds the decoded rows to
BOTH parsers. Report and per-frame JSON are session scratchpad only.

| quantity | value | tier |
|---|---|---|
| sessions / frames replayed | 19 / **536** | MEASURED |
| frames the precondition found usable | 472 | MEASURED |
| frames producing a schema-1 stack | **355** | MEASURED |
| frames with a local candidate | 341 | MEASURED |
| stack accepts where the legacy parser REFUSED | **246** | MEASURED |
| legacy accepts where the stack refused | **0** | MEASURED |
| Root disagreements between the two parsers | **0** of 109 | MEASURED |
| unit-scale continuity flags | **0** of 309 pairs | MEASURED |

**Four boundaries on those numbers, each of which makes them narrower than they
look.** They were found by a skeptic pass over the report, not by its author.

1. **The replay stops at the PARSERS.** It never runs `scanner.parse_payload`,
   which holds the echo canaries and the stack echo check. "The stack parses"
   is one layer short of "the capture succeeds", and neither is a live capture.
2. **175 of the 536 frames are not the shipping window.** `dark-01`,
   `preflight` and `red-01` were captured at 640 px, which yields **84 cells
   against the 88 the runtime reads**, so they decode clipped. This is
   contradiction #2 biting. No result here changes, but 123 of 341 candidate
   observations and 97 of 309 continuity pairs come from those three.
3. **"0 legacy accepts lost" covers the SPACE branch only.** All 109 legacy
   accepts carry `local_frame: False`; the legacy local/`OOC_` branch accepted
   **nothing** in the whole corpus, matching `CORPUS.md`.
4. **The two parsers in the Root cross-check are not independent.** Same
   decoded string, same `coordinate_stack.token_to_m`, and the population is
   pre-filtered because the stack refuses on Root/Solar disagreement. Only the
   two regexes' extraction is under test.

### The Pyro 3 surface change, now MEASURED on real pixels

`surface-01` is **90 of 90** accepted by the stack parser and **0 of 90** by the
legacy one, which refuses every frame at `body_scale`. `fov-01` and `camdir-01`,
a ship inside `pyro3`, add 92 more stack-only frames. This is the first time any
stack has been built from real pixels rather than a transcription.

Still NOT established: field success. One session, one body, one pose, 189 s
standing still.

### The local candidate IS a movable ship frame when no world container exists

`dark-01`, the player in the Drake Clipper in open space with no body row.

| measurement | value | tier |
|---|---|---|
| candidate is the ship row | 12 of 12 accepted stacks | MEASURED |
| candidate Z passes through to SolarSystem | **0 of 12** | MEASURED |
| candidate Z pass-through, every other session | 329 of 329 | MEASURED |
| **candidate position span across the session** | **0.239 m** | MEASURED |
| **Root position span across the same frames** | **1.913e9 m** | MEASURED |

**The last two rows are the finding, and they need no name, no prefix, no scale
and no Z**, so nothing in `REFUTED.md` touches them. The player's position
inside the candidate frame held within a quarter of a metre while that frame
travelled 1.9 million km through the system. The frame is co-moving with the
player's vehicle by direct measurement.

The same measurement across the corpus, as a description and **NOT** as a
discriminator (a threshold on it would be the refuted scale rule):

| session | candidate span | Root span | ratio | what it is |
|---|---|---|---|---|
| `dark-01` | 0.239 m | 1.913e9 m | 8.0e9 | ship, co-moving |
| `surface-01` | 25.460 m | 26,038 m | 1.0e3 | rotating body |
| `flight-01`, `p5l2`, `red-01`, `preflight` | | | 1.000 | static world container |
| `camdir-01`, `fov-01` | | | 2.5 / 0.96 | ship moving inside `pyro3` |

**A rotating body is a moving frame too**, so this separates moving frames from
static ones and does NOT by itself separate a vehicle from a body.

### LIVE FLIGHT 2026-08-10: the candidate changes identity mid-flight

**MEASURED, twice, in ordinary manoeuvres, on real pixels.** Provenance and the
full table in `CORPUS.md`, "LIVE CAPTURES".

Leaving the Nyx gateway, the jump-point row drops out of the stack and the SHIP
becomes the candidate, at a named frame boundary. Entering Pyro 3's zone, the
body becomes the candidate. So two captures minutes apart at what a player would
call the same place can be measured in two different frames of reference, and
**nothing in the code can detect that it happened**: `select_route` compares a
saved candidate position against the current one as bare numbers.

The failure that implies, still theoretical because the flag is off: mark a
waypoint at a jump point, return while the ship is the candidate, and the
comparison is a jump-point-relative coordinate against a seat-relative one. Both
are small, so it yields a small distance and could announce arrival while the
player is thousands of km away.

**This upgrades the `dark-01` finding from a corpus curiosity to a live,
ordinary-play event.** It is the strongest argument yet for
`LOCAL_TRACKING_ENABLED = False`.

### LIVE FLIGHT 2026-08-10: the seated-versus-standing pair HOLDS

The evidence gate's highest-value row, captured for the first time. Landed at
Bloom the stack is `[ship, pyro3]` seated and `[pyro3]` standing outside, and
**the candidate is `pyro3` in both**. Movement across the transition reads
24.76, 9.05, 14.44, 1.74, 0.73, 0.00 m: a person walking, then standing. A
silent frame switch would have shown a discontinuity of kilometres.

**Repeated at Vuur the same day**, a moon rather than a planet: seated
`[ship, pyro5f]`, standing clear `[pyro5f]`, candidate `pyro5f` in both.

**Scope, and it is still narrow: two sites, two body classes, ONE ship, one
system.** The gate asks for two different ships and this is one, flown twice.
Pyro only. Evidence FOR the hypothesis in the pose that matters most, and it
does not open the flag on its own.

**A methodological finding from the near miss.** The first Vuur landing produced
the seated half and NO standing half: every frame after stepping out refused on
the bright surface, and it was recovered only by flying back. **A pose that is
not decoded did not happen**, so a capture plan must verify frames are landing
WHILE the player still holds the pose, not afterwards. Standing beside the hull
also keeps the ship row in the stack, which would have confounded the pair even
if it had decoded; step clear.

### The login screen emits a phantom stack, and schema 1 does not cause it

**Resolves contradiction #4 on side A.** At the main menu both `login` and
`login-black` decode:

```
Zone: SolarSystem_200000000001 Pos: -0.00m 0.04m 1.74m
Zone: Root                     Pos: -0.00m 0.04m 1.74m
```

**5 of 5 in both sessions, accepted by BOTH parsers**, and the skeptic pass
carried one through `scanner.parse_payload` (ACCEPTED, `frame_id`
`200000000001`) to `main.py`'s `framed=True` and `KIND_OK`. So the main menu
produces a complete markable capture on the shipping path today. The legacy
parser accepts it too, so this **predates schema 1** and is not a regression.

**DECIDED by Lars 2026-08-11: REFUSE captures at the main menu.** This unblocks
the one required test in the plan's §16 that could not be written without a
product decision. Fixtures are already on disk at `ocr_dev/captures/login/` and
`login-black/`.

**THE DISCRIMINATOR IS MEASURED, 2026-08-11, across all 23 corpus sessions and
every accepted stack in them. Both endpoints are recorded so the threshold can
be re-derived instead of trusted, which is the failure the 15,000 km ceiling
still suffers from.**

| endpoint | value | source |
|---|---|---|
| main-menu Root magnitude | **1.740 m**, identical on 5 of 5 frames | `login`, `login-black` |
| SMALLEST real Root magnitude anywhere | **1.3889e10 m** | `pyro5-vuur` |

**The empty band is ten orders of magnitude**, a factor of about 8e9. Any
threshold between roughly 1e1 and 1e9 m refuses the menu and accepts all 647
accepted stacks in the corpus. Unlike the 15,000 km ceiling, this margin is not
close to anything.

`REFUTED.md` kills magnitude ONLY as a ROUTING key (which row is the local
frame). "Are we in a game world at all" is a different question and is not
covered by that refutation.

**THE STRUCTURAL ALTERNATIVE IS REFUTED, and it would have caused harm.** "No
nested rows" looks like a clean signature of the menu and is wrong: `dark-01`
contains a legitimate deep-space frame with ZERO nested rows, because the ship
row failed to decode that frame. A structural gate would refuse a real capture.

Per-session minimum Root magnitudes, for anyone re-deriving this:
`login`/`login-black` 1.740 m; then the smallest real ones, `pyro5-vuur`
1.3889e10, `preflight` 1.4998e10, `game-mid` 1.5001e10, `pyro3-bloom-approach`
1.7796e10, rising to `dark-01` 4.9384e10.

### Printr convention: the plan's rule is stricter than the API, MEASURED 2026-08-10

`Supercalifragilistic.md` §14.5 asks for "synchronous calls only with
`server_only=True`; awaited async calls for client-visible messages". Applied
literally to this skill it would silence eleven player-facing badges, and it is
not what the API requires.

| fact | evidence |
|---|---|
| `Printr.print` sends to the GUI from SYNC code | `services/printr.py:182-194`, via `ensure_async`, commented "send to GUI without print() having to be async" |
| that works with no running loop | `services/websocket_user.py:18-25`: running loop gives `create_task`, otherwise `asyncio.run` |
| NavPoint call sites | 14 total: 3 already `server_only=True`, **11 sync and client-visible** |
| bare `print` in runtime code | **none**; the only ones are in `update_release.py`, a hand-run build script |

The 11 include the server-change wipe notice, the echo-canary refusal and the
space-direction test-mode warning: safety messages the player is meant to see,
and several run on the poll thread where nothing can be awaited.

**NOT CHANGED. DECIDED by Lars 2026-08-10: leave the eleven badges visible.**
Converting them would be a behaviour change to what the player sees, on a thread
that cannot await, for no functional gain, and it cuts against the standing
preference for surfacing conditions as chat badges. §14.5 of the plan is
therefore satisfied by the "no bare `print`" half only, and the sync/async half
does not apply to this skill.

### Two guards proven unreachable rather than load-bearing

Recorded so a future reader does not mistake them for protection:

- the `stack_decision is None` guards on the legacy frame-id and cross-body
  gates: a stack row carries an empty `frame_id` and an empty `body`, so those
  gates cannot fire on one anyway;
- the stack branch in `navigation.ring_deflection`: a stack target has neither a
  body nor a system frame, so no bubble was reachable for it before the branch
  existed.

All three stay for explicitness. None of them is what stops the failure.

## Token cost, the thing that started this

| quantity | value | tier |
|---|---|---|
| Vision cost per capture | ~3050 tokens | MEASURED |
| at 5 s poll | ~2.2 M/hour | MEASURED |
| at 10 Hz | ~110 M/hour | MEASURED |
| local reader | 0 tokens | MEASURED |

**But see `REFUTED.md`:** the local reader cannot reach 10 Hz either. Its best
live figure is 1.20 Hz, and at 4.5 s per capture with the game running it is
slower than the Vision call it replaced. The token argument does not survive.
The **correctness** argument does: four confabulation incidents in 2026, one of
which deleted six waypoints.

---

# CONTRADICTION REGISTER

**Unresolved by instruction (Lars, 2026-08-02: flag, do not resolve).** Each is
recorded with both sides so nobody re-derives a winner by accident.

| # | quantity | side A | side B | consequence |
|---|---|---|---|---|
| 1 | Z pass-through never-match count | 288 (frame-drift report) | 295 (journal, memory) | none; the difference is whether `rsi_polaris_kaboos_ext` (5) and `rs_int_ptn_set` (2) are counted |
| 2 | strip / block width and cutover | 640 px before `terrain-01` | 640 px only for `preflight`, `red-01`, `dark-01`; **or** 675 px from `red-01` onward | decides which sessions decode clipped, so it affects every corpus statistic |
| 3 | `game-mid` red wall | R 96 / G 2 | R 89 / G 2 / B 8 | none; the harvest rule depends on the green channel, which agrees |
| 4 | ~~`login` payload~~ **RESOLVED 2026-08-10, side A** | 5/5 emitted | "produces none, NOT verified either way" | the main menu emits a full stack on both parsers and reaches `KIND_OK`; see "The login screen emits a phantom stack" above |
| 5 | largest observed body scale | 410 km | 414.0045 km | **or** `pyro3` max 606.7193 km | feeds the 15,000 km ceiling's justification |
| 6 | surface refusal counts | 62 of 62 emitted before the guard | 0 emitted / 90 refused after | probably two different runs, never stated as such |
| 7 | 2026-07-13 corpus size | 40 shots (and 40 files on disk) | "the 41-JPEG corpus" | none |
| 8 | template bank | "77 templates over 46 characters" | "83 of 113 pairs present" | same day; only consistent if they count different things |
| 9 | alignment cache saving | ~37% of cost | 32% of a cold read | none |
| 10 | alphabet gap size | "three pairs, not thirty" (`k`/0, `O`/0, `u`/1) | at minimum `O V D R A K C L` missing | **material**: decides whether the glyph gap is nearly closed or wide open |
| 11 | breach mechanism | "every breach is a LOW-INK glyph" | "any glyph that ADDS ink above or left"; `n`→`h` is full-ink | **material**: the first is the wrong threat model |
| 12 | ship-landed-on-surface capture | exists, 2026-07-13, 4.8 JPEG | "still owed" x3, all about 4.9 | **material**: see `CORPUS.md`; both are true for different patch versions |
| 13 | `RING_NO_BEARING` fix | "WRITTEN, NOT INSTALLED" (441 tests) | install section reports 439 tests and sits below it | unclear whether the fix ever reached the live install |
| 14 | release file count | 18/18 (midday) | 13/13 (evening) | probably a manifest change, never stated |
| 15 | was v4.9.0.20 installed? | "INSTALLED 2026-07-28", 14 files hash-verified, and the **installed copy** measured drawing 2875 px | "Internal update, NOT a requalification. **NOT yet installed to the live environment**" | **both sentences are in the SAME Devlog entry**, 8 lines apart |
| 16 | the per-kind FULL-shape row gate | recommended 2026-07-29 as "the real Phase 2 work, not the classifier", to close three demonstrated gaps | **no later entry records it being built** | fabricated tokens still decode trusted at cost <2.5; `Zone: Root Pos:` with no coordinate still comes back trusted at cost 0.00 |
| 17 | `ocr_dev/reader.py` alignment | "aligned, verified case by case" (Devlog L105-112) | "Also unfixed ... still holds the anchored copy" (L132-136) | **RESOLVED 2026-08-02: it IS aligned.** Both sentences were in ONE entry, 25 lines apart, written in one sitting. The stale one was written before the fix and never revisited. Corrected in place |

| 18 | `P5_02` container scale | 28,000 km (07-31) | 19,125 km, as the low end of a stated container range (08-01) | **load-bearing, see below** |
| 19 | largest observed body scale | 330 km (07-31, from a table of Clio 123-313 and pyro3 219-330) | 410 km (08-01), **source not stated, and no new body capture recorded between the two dates** | **load-bearing, see below** |
| 20 | time to read ten rows | 2181 ms (07-31 evening) | 1303 ms (07-31 late, game running) | the widely-quoted **14x** CamDir ratio is computed FROM the 2181 ms figure, which that same entry disclaims: "absolute timings from tonight should not be quoted, only ratios" |
| 21 | block width | 660 px (88 cells x 7.5) | 667 px (used for "the block", and the live grab region reads `width: 667`) | probably 660 + a 7 px right margin, **but the record never says so** and both are used for "the block" in one entry |
| 22 | were the overlay modules in the release? | "BOTH RELEASE MANIFESTS UPDATED" 07-31 late | release folder was a 07-28 snapshot "missing `overlay_fields.py`, `overlay_glyphs.npz` and `overlay_reader.py` outright" 08-01 | reconcilable as manifests-updated-but-folder-not-rebuilt, and the same entry does say "release_version still holds a Vision build". The distinction is never stated |
| 23 | test count 439 to 453 | 439 at 07-31 late | 453 at 08-01 early | **no entry accounts for the 14 tests.** The 07-31 close entry sits between them and states no count |

## THE 15,000 km CEILING RESTS ON TWO DISPUTED NUMBERS

This is the most consequential thing the contradiction register surfaced, and it
was invisible until #18 and #19 sat next to each other.

The ceiling's entire justification is that it sits in an **empty band between the
largest observed body and the smallest observed container**. Both endpoints are
contradicted:

- largest body: **330 km or 410 km** (#19). The 410 figure's source is not stated
  anywhere, and no new body capture is recorded between the entry that says 330
  and the entry that says 410.
- smallest container: **19,125 km or 28,000 km** (#18).

So the band is somewhere between "410 to 19,125" and "330 to 28,000", and
15,000 km was chosen as "the highest value that still clears the smallest
container observed" — which is the endpoint in dispute.

**This does not mean the ceiling is wrong.** Every candidate value still sits in
open space between bodies and containers, and P5 L2 at 44,707 km clears all of
them by 3x. It means the stated justification cannot currently be checked, and
anyone defending or raising the ceiling must re-measure both endpoints first.

The measured alternative was named on 2026-08-01 and not taken: decide by
BEHAVIOUR, since a rotating body's frame drifts at 137.6 m/s while containers are
static within noise. That needs no threshold and cannot be fooled by an
unfamiliar body size. See `REFUTED.md` for why scale alone failed as a router.

**Contradiction #17 is the clearest evidence for this ledger's existence.** It
was committed on 2026-08-02, inside the entry that describes this exact failure
mode, by the person writing the ledger. Not carelessness: the paragraph was true
when written and false forty minutes later, and nothing in a chronological
document connects a claim to its own later correction. Found only because an
agent read the file end to end.

---

# THE DECISION THAT WAS BLOCKING EVERYTHING

**CURRENT, resolved 2026-08-02 (later the same day): NO VISION AT ALL, OCR
ONLY.** Lars's call, stated three times in one exchange: "no, we will not use
vision at all, only OCR". The local deterministic reader is the ONLY reader.
There is no fallback of any kind and no router. Full record at the top of
`TODO.md`.

Consequence, put to Lars before he decided and accepted by him: the local reader
has produced ZERO successful field captures since 2026-07-31 22:07:10, seven
failures over two days (the 2026-08-01 pair had no sub-reason and took 1.1 s and
1.2 s; the 2026-08-02 pair reported `no_system_line` and took 11.1 s and
11.0 s). With no fallback, fixing the reader is the entire product rather than a
side investigation.

**CORRECTED 2026-08-02. This paragraph originally read "seven failures over two
days IN AT LEAST TWO DISTINCT SHAPES". That claim is REFUTED.** The 08-01 lines
lack the gate name and the `attempts=` field, both of which the current code
writes UNCONDITIONALLY, so that build simply had neither the gate
instrumentation nor the retry loop. It is ONE failure mode observed through two
builds, not two failure modes, and the duration gap is the same arithmetic at
one attempt against five rather than two different scenes. **The count, the
dates and the durations above are unaffected.** Treating it as two would have
sent the reader work chasing a phantom.

**STILL GENUINELY UNEXPLAINED, and deliberately not smoothed over by the
correction:** 11.1 s over five attempts is roughly 2.2 s each against 1.1 s for
the single-attempt build, and that doubling is not accounted for. Instrumentation
item I7 measures it. The leading candidate is the alignment self-heal refit,
measured at +310 ms per read and firing whenever nothing decodes as trusted
(`overlay_reader.py:725`). That measurement lives in Devlog 2026-08-02 (evening)
and is deliberately NOT a canonical row here: it is a hypothesis about the cause,
not an established cause.

The 62 to 100 per cent sunlit-terrain refusal rate in the table above is NOT
disproved by this. It is an accepted cost. Its instruction "plan a router" is
void.

The Vision path in `scanner.py` is STILL not stripped, deliberately. That is the
only reason this question could be answered three ways in three days at zero
rebuild cost. Do not strip it without an explicit instruction from Lars.

**SUPERSEDED, kept because the sequence is the record: resolved 2026-08-02
(earlier the same day): BUILD THE ROUTER.** Vision returns as a fallback for
frames the local reader refuses. Never implemented.

It had been unresolved since 2026-07-31, when `TODO.md` acquired both of these,
80 lines apart, same day, neither referencing the other:

- L405: *"CONSEQUENCE: Vision stays required for daylit surfaces. Do not plan a
  Vision retirement; plan a router."*
- L322: *"DECISION 2026-07-31: Vision AI is OUT of this skill, permanently."*

The question meant to settle it, *"is the surface use case mostly daylit?"*, was
logged as **"the most important open item in the project"** and was never
answered until 2026-08-02, when Lars answered it: *sometimes in a ship in space,
mostly in a ship on a surface, rarely on foot, never inside a base, building or
cave.*

**So the skill's primary use case was served by a reader measured unable to serve
it, with the fallback deleted by decision.** That, not any gate, is why marking
worked at one location and not others.

---

# WHAT IS STILL NOT ESTABLISHED

Stated plainly, because every one of these has been quietly assumed at least once.

- **The reader's usable rate is unknown in both regimes.** The 85% space figure
  is 20 frames of one flight, and the 2026-08-02 failure was in space with
  scattered `?` on all 8 rows. Written when this was the router's trigger rate;
  with the OCR-only decision it is now the availability of the whole skill, so
  it matters more, not less.
- **The OOC_ branch has never run on real pixels.** Its tests are synthetic.
- **The label-search change's clearing path has only been exercised where
  clearing was CORRECT.** None of the 7 frames whose output changed had an
  `OOC_` line.
- **The 15,000 km ceiling is a chosen number.** The largest real body scale is
  unmeasured.
- **Station drift rests on one pair, 2 seconds apart.**
- **Nothing installed on 2026-08-01 has run inside Wingman on a surface.**
- **The corpus is one player, one ship, one body, one rest stop, one station.**

# WHAT COLLAPSED ON 2026-08-02

Lars's "never inside a base, building or cave" dissolves the nested-container
problem that blocked the local-frame routing rule since 31 July. The elevator's
transit carriage, hangar and cargo bay are not cases that need solving.

**The deepest realistic stack is `ship -> body -> SolarSystem -> Root`.**

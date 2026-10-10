# CORPUS — what data exists, and what each capture actually shows

Built 2026-08-02 from the sources' own words, not from label names. Where a
source does not state something, this file says **UNSTATED** rather than
guessing. `surface-01` and `terrain-01` sound alike and are not the same thing.

**Why this file exists:** on 2026-08-02 a claim that "the player in a ship
landed on a surface was never captured" was made from directory names and was
wrong. The data had been sitting in `screenshots/` since 13 July.

---

## The question that keeps being asked: is there a ship-landed-on-a-surface capture?

**YES on SC 4.8, as lossy JPEG. NO on SC 4.9, lossless.** Both statements are in
the record and both are true.

`screenshots/overlay-field-inventory-2026-07-13.md` L13-16:

> 36 shots 22:08:11-22:19:25: one journey at level 1, **in a Drake Clipper**:
> open space (far from any body) -> quantum to Clio (Stanton 4b) -> descent ->
> **landed on the surface**.

The validated transcription of `ScreenShot-2026-07-13_22-19-25-CDE.jpg`:

```
Zone: DRAK_Clipper_698212607305     Pos: 0.03m 11.57m 2.81m
Zone: OOC_Stanton_4b_Clio           Pos: 123.2375km -313.5352km 14.9327km
Zone: SolarSystem_653869999737      Pos: 22476440.7100km 37091195.6577km 14.9327km
Zone: Root                          Pos: 22476440.7100km 37091195.6577km 14.9327km
CamPos Planet Zone: 123237.455097 -313535.207901 14932.665921
Radius: 337170.000000  ElevationUnderCam: 37.562500  Altitude 8.661078
```

**Three caveats that matter, all from the record itself:**

1. The inventory says only "in a Drake Clipper". **Whether the player was seated
   in the cockpit or standing inside the hull is UNSTATED.**
2. It is **SC 4.8** (build `pub-euw1b-sc-alpha-480-12061511`) and carries a
   `CamPos Planet Zone` line. **SC 4.9 omits that line on a surface**, so the 4.9
   version of this capture behaves differently and does not exist.
3. The journal records a seated-in-a-landed-ship capture as **still owed** three
   separate times, all dated 2026-07-26 and all about 4.9.

The near-miss that is not the same thing: the 2026-07-26 Daymar sweeps were shot
**on foot INSIDE the ship** (`DRAK_Clipper` innermost, confirmed visually), which
is a player standing on a body surface inside a hull, not seated.

---

## Session table

Frame counts are `files on disk / frames the analysis decoded`.
All `ocr_dev/captures/*` are lossless PNG. The 2026-07-13 set is lossy JPEG.

| label | where the player was | lighting / background | frames | what it settles |
|---|---|---|---|---|
| `login-black` | login screen, **no container at all** | backdrop exactly black, 87543/87543 px | 8/5 | Phase 1 grid, pitch, colours, first templates |
| `login` | same | same | 11/5 | same |
| `game-bright` | **UNSTATED** | blown sky | 8/5 | where the black-only model breaks |
| `game-mid` | inside an RSI Polaris at a ring station | **red wall**, the reference harvest source | 10/5 | shadow transmission H; the join test |
| `ice-bright` | **UNSTATED** | ice field | 5/5 | bright/structured failure envelope |
| `starfield` | in the Clipper at a ring station | Nyx glacier ring, dark teal + bright ice debris | 5/5 | forced the ink threshold to become hybrid |
| `vote-fast` | **UNSTATED** | **UNSTATED** | 5/5 | **UNSTATED** |
| `preflight` | ring station, player in a ROOM | **UNSTATED** | 6/5 | the `k` phase 0 hunt; station drift |
| `dark-01` | in the Clipper; one frame at the Pyro-Nyx jump point | a darkness hunt that failed its purpose | 21/20 | refusal statistics |
| `red-01` | an **ELEVATOR**, three nested containers, plus a cargo bay | red-lit, deliberately | 151/150 | `k` phase 0 harvested here |
| `flight-01` | **open space in a ship** | **UNSTATED** | 21/20 | in-space usability: 17/20 usable |
| `bright-01` | in the Clipper, ship-only stack | bright | 12/11 | bright-scene refusal stats |
| `bright-02` | same | bright | 11/10 | same |
| `terrain-01` | in the Clipper, **flying**, no body row at all | **sunlit terrain** | 21/20 | **the bright-terrain limit on ordinary daylit ground** |
| `nosignal-01` | **UNSTATED** | overlay OFF (`r_displayinfo 0`) | 21/20 | NO SIGNAL vs GLARE, on real pixels |
| `camdir-01` | in the Clipper inside `pyro3` | **UNSTATED** | 61/60 | **UNSTATED** (label implies a CamDir test) |
| `fov-01` | in the Clipper inside `pyro3` | **UNSTATED** | 81/80 | **UNSTATED** (label implies an FOV test) |
| `surface-01` | **ON FOOT, OUTSIDE THE SHIP, on Pyro 3** | frame_0000 has green channel 0.0, the darkest source in the corpus | 91/90 | Pyro has no `OOC_`; the 50 km guard; `y` phase 0 |
| `p5l2` | sitting at P5 L2 in a ship | background stars fell inside the block | 16/15 | the Lagrange fix; 12/15 clean payloads |
| `screenshots/` (07-13) | on foot in a hangar (4 shots) + **a Drake Clipper flying to and landing on Clio** (36 shots) | includes a dawn sky where white lines wash out | 40 JPEG | the field inventory the whole reader was specified against |

**`camdir-01` and `fov-01` are the closest thing to the primary use case in the
lossless corpus**: a ship inside `pyro3`. But whether the ship was landed,
hovering or flying is UNSTATED in every source, and their container drift rates
(168 m/s and 669 m/s) suggest motion rather than parked. Do not treat them as
the ship-landed case without checking.

---

## LIVE CAPTURES, 2026-08-10, the first since 2026-07-31 22:07:10

Taken during a single deliberate evidence-gate flight, one grab every 5 s,
`--keep-all` so a stationary pose still produces a time series. All lossless
PNG at the full 88-cell width.

| label | where | frames | stacks | what it settles |
|---|---|---|---|---|
| `jumppoint-pyro-nyx` | Nyx gateway on the Pyro side, stationary refuelling, then departing | 40 | 29 (72%) | **the first jump-point stack ever parsed**; jump-point drift; a live candidate CHANGE |
| `pyro3-bloom-approach` | gate to Bloom on **Pyro 3**, descent, landing, **then standing outside the ship** | 96 | 39 (41%) | **the first seated-versus-standing pair ever captured**; the space-to-body transition |
| `pyro5-vuur` | Bloom takeoff, past Orbituary, interplanetary transit, landing on **Vuur**, a moon of Pyro 5 | 156 | 78 (50%) | **the first second body**; the candidate changing TWICE in one session |
| `vuur-return-outside` | return to Vuur, landing, **stepping clear of the ship and holding still for 66.6 s** | 200 | see below | **Vuur's rotation rate**; the second seated-versus-standing pair |

**`pyro3-bloom-approach` was recorded live under the label `pyro2-approach` and
renamed the same session.** The destination was chosen as Pyro 2 and the flight
ended at Bloom, whose zone reads `pyro3`. The folder name was corrected because
a label that names the wrong body is the exact trap this file exists for. **It
is therefore the SAME body as `surface-01`, and the corpus still has no second
planet.**

### What these two settled

**The candidate CHANGES IDENTITY MID-FLIGHT, measured twice, in ordinary
manoeuvres.** Leaving the jump point (`jumppoint-pyro-nyx` frame 28) the
jump-point row drops out and the SHIP becomes the candidate. Entering Pyro 3's
zone the body becomes the candidate. Split by identity:

| session | run | candidate span | Root span | ratio | what it is |
|---|---|---|---|---|---|
| `jumppoint-pyro-nyx` | at the gate | 1037.144 m | 1037.082 m | **0.9999** | static world container |
| `jumppoint-pyro-nyx` | after departure | 0.010 m | 9.323e9 m | 9.3e11 | **the ship** |
| `pyro3-bloom-approach` | in space | 0.090 m | 3.780e10 m | 4.2e11 | **the ship** |
| `pyro3-bloom-approach` | in Pyro 3's zone | 622,856 m | 641,083 m | 1.029 | body, dominated by his own descent |

**The seated-versus-standing pair HOLDS.** Landed and seated the stack is
`[ship, pyro3]`; standing outside it is `[pyro3]`. **The candidate is `pyro3` in
both**, so the ship row leaving the stack does not move the frame of reference.
Position across the transition reads 24.76, 9.05, 14.44, 1.74, 0.73, 0.00 m,
which is a person walking then standing. A silent frame switch would have shown
a discontinuity of kilometres. **One site, one ship, one pair.**

**Jump-point drift now exists.** Frames 11 to 14, stationary while refuelling,
carry byte-identical Root positions. `LEDGER.md` previously recorded jump-point
drift as unmeasurable because the jump point appeared in exactly one frame.

**A SECOND BODY, and its rotation measured.** `pyro5f` is Vuur, a moon of Pyro
5, and the first body in the corpus that is not Pyro 3. Standing perfectly still
outside the ship for **66.6 s across 14 consecutive decoded frames**:

| frame | movement |
|---|---|
| body frame (the candidate) | **0.000 m** |
| Root / system frame | **9,752.227 m** |
| implied surface drift | **146.472 m/s** |

Its candidate Z passes through to SolarSystem, the world-anchored signature.
This is the cleanest statement of why a surface waypoint cannot live in Root
alone: the spot walks away at roughly 10 km per minute.

**The SECOND seated-versus-standing pair, on a moon, behaves like Bloom.**
Seated the stack is `[ship, pyro5f]`, standing clear it is `[pyro5f]`, and the
candidate is `pyro5f` in both. **Two sites, two body classes, one ship.**

**A near miss worth recording.** The FIRST Vuur landing produced no standing
half at all: every frame after stepping out refused, and every accepted stack in
`pyro5-vuur` still contains the ship row. It was recovered only by flying back.
The cause was brightness, and standing beside the hull rather than clear of it
would have confounded it anyway.

**Brightness, not location, decides whether a frame parses.** Same pose, same
overlay, same reader: block background median RGB 76 to 95 refused every frame,
8 to 34 parsed every frame. The daylit descent and surface is where
`pyro3-bloom-approach` lost most of its 59%.

## What the corpus was replayed through, 2026-08-10

`ocr_dev/stack_replay.py`, Wave 5 step 1. **All 19 session folders, 536 frames**,
decoded with the shipping reader rather than read from any OCR text log. That
matches this table's own decoded column session for session.

**Two filename schemes, and missing the second silently dropped seven sessions
from the first run.** The logger writes `frame_NNNN.png`; the seven earliest
hand-taken sessions (`login`, `login-black`, `game-bright`, `game-mid`,
`ice-bright`, `starfield`, `vote-fast`) use `shot_NN.png`. Everything else in
those folders is a debug crop, confirmed by dimension: `rows_*.png` 1200x240,
`strip.png` 8x408, `view_full.png` 1024x288, `cells_row1.png`, `ends.png`.

Nothing lossy was counted: `screenshots/` holds 40 JPEGs and one .md, zero PNG,
and it is correctly outside the replay.

**Contradiction #2 measured directly rather than argued.** The tool reports each
session's usable cell count from `overlay_reader.block_columns`:

| cells | sessions |
|---|---|
| **84, CLIPPED** | `dark-01`, `preflight`, `red-01` (175 frames) |
| 88, the shipping width | the other 16 |

So three sessions decode four cells narrower than the runtime reads. It changed
no result in this replay, but 123 of 341 candidate observations and 97 of 309
continuity pairs come from those three.

**The replay will keep counting `login` and `login-black` as producing stacks,
and that is CORRECT, not a bug.** From 2026-08-11 the main-menu phantom is
refused by a `no_game_world` gate in `scanner.parse_payload`, which is
DOWNSTREAM of both parsers. `stack_replay.py` stops at the parsers (boundary 1
in `LEDGER.md`), so it will go on reporting 5/5 accepted for both login
sessions forever. Anyone who "fixes" that has moved the gate to the wrong
layer. The corpus-wide accepted-stack rate is therefore 10 frames optimistic
against what the runtime would accept.

**What the replay could NOT contribute, despite covering everything:**

- **the jump point.** `dark-01/frame_0001` is the corpus's only jump-point frame
  and it REFUSED at `stack_no_root`, so the evidence gate's jump-point row gets
  nothing;
- **the legacy `OOC_` branch**, which accepted zero frames in the whole corpus,
  consistent with the entry below;
- **anything live.** Every frame is stored, and no live capture has succeeded
  since 2026-07-31 22:07:10.

## What the corpus does NOT contain

- **A lossless, SC 4.9, seated-in-a-landed-ship capture.** This is the primary
  use case stated by the user on 2026-08-02 and it has never been captured in
  the regime the local reader actually runs in.
- Any capture where the OOC_ branch has run on **real pixels**. Its tests are
  synthetic. Z-identity for Stanton rests on a 2026-07-13 transcription.
- A second body, a second ship, a second rest stop, a second station or a second
  jump point. **One ship (entity id 742164815970) appears in eight of the
  nineteen sessions.** Broad in frames, narrow in places.
- A drift pair for the jump point: it appears in exactly ONE frame.

## Known defects in the corpus

- **Strip width is inconsistent and the cutover session is disputed.** Values of
  640, 660, 667 and 675 px appear across the sources with three different
  cutover claims. Sessions before the cutover decode slightly clipped. See
  `LEDGER.md` contradiction #2.
- Seven sessions have no `index.jsonl` and therefore no timestamps, so they
  contribute nothing to any drift measurement: `game-bright`, `game-mid`,
  `ice-bright`, `login`, `login-black`, `starfield`, `vote-fast`.
- **`p5l2` was captured AFTER both `zone-stacks-2026-08-01.md` and
  `frame-drift-2026-08-01.md` were written.** It appears in neither and is
  invisible to any analysis built on them.
- `surface-01`'s 90 frames sample ONE location: the player stood still for
  189.2 s.
- `bright-01` and `bright-02` were captured with the focus filter armed while
  the game did not hold focus, which is the failure mode that later forced the
  mandatory `--window=` flag.

## Capture tool, non-negotiable for this user

```
python session_log.py --label NAME --window= --interval 2 --max-frames 20 --delay 12
```

`--window=` in the **equals form**. `--window ""` as a separate token is dropped
by PowerShell before argparse sees it. He plays windowed-borderless with the
terminal on top and does not alt-tab, so the game rarely holds focus and the
default filter skips nearly every grab.

Verify a session by watching the **frame count climb**, never by checking that a
process exists: Python here is `python3.13.exe`, which broke that check three
times in one night.

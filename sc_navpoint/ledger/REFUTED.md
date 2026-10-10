# REFUTED and REVERTED — do not retry these

The most expensive knowledge in this project. Every entry cost real time to
establish and at least three have already been re-derived by accident.

Read this before proposing any approach to the reader, the routing rule or the
alphabet. If an idea appears here, it has been tried and it failed for a stated
reason.

Format: what was tried, why it seemed right, what killed it, and where the
evidence lives.

---

## Reader model and alphabet

### Phase synthesis: deriving a missing glyph phase from its partner
**Killed 2026-07-31. Do NOT retry. The question is closed.**

Seemed right because the two phases look like the same glyph resampled half a
pixel. They are not: they are separate rasterisations.

Four methods (linear and sinc, both directions) over 35 positive controls, every
character holding both phases, scored on the inner columns the matcher actually
uses. Best mean absolute error **0.1106 against 0.1196 for applying NO shift at
all**. A true resample relation would have crushed that baseline.

Held out against the real refused cell whose truth was known independently: all
four methods still refuse, zero regressions.

**Consequence: a missing phase MUST be captured.** There is no shortcut.
Devlog 2026-07-31, L843-856.

### Recovering the drop-shadow transmission H from a saturated background
**Killed 2026-07-29.**

Inconsistency 0.21 to 0.42 on a quantity bounded in 0..1, with some derived
values NEGATIVE, which is unphysical. Clipping destroys the linear relation the
solve depends on.

Recorded explicitly "so nobody repeats it". The working method is the red wall,
whose channels split the job. LocalOcrPlan P:193-200.

### Hunting DARKNESS for a harvest source
**Killed 2026-07-31. The criterion was wrong, not the effort.**

`harvest.py` reads `frame[:,:,1]`, hardcoded green. What is needed is a
near-zero GREEN channel, not a dark scene. A dim GREY area lights every channel
a little and zeroes none: the `dark-01` hunt reached only 11.34 mean on its best
channel, while the red wall reference sits at green mean 2.07.

**Seek RED lighting. A bright red surface beats a dark grey one.** Hunting
darkness got to 11; hunting red light got to 4.34 and the harvest succeeded.
TODO L482-488.

### A phase rule derived from character position
**Killed 2026-07-31. Do NOT re-derive.**

`phase = (1 + i) mod 2` was fitted to ONE recorded misread, and a twenty-body
ranking table plus a user recommendation were built on it before anyone checked
a case it should fail.

It wrongly predicts that `CamDir:` needs a `D` phase 1 template, which is absent
from the bank while that row decodes clean and trusted in every capture.

**The correct model is length parity**, which predicts the fitted offset on 109
of 117 trusted rows; all 8 exceptions are `ShardId:` at n=31. Devlog L889-898.

### Character composition as the driver of per-row offset
**Killed 2026-07-31.**

Within each parity class the digit fraction spans 0.28 to 0.65 under a single
consistent offset. If glyph width varied by character class that spread would
have split the offsets. It does not.

### One block-wide sub-pixel offset
**Killed 2026-07-29.**

Decodes matching-parity rows perfectly and turns every other row to garbage,
which reads as a flaky reader rather than a systematic fault. **Fit each row's
own origin.**

### The min-cost (OR) rule across multiple grabs
**Killed 2026-07-30, despite scoring BEST on coverage (45/45 and 28/31).**

Taking the minimum across five grabs is arithmetically a relaxation of the floor
from 15 to about 30, given the measured per-cell cost wobble of 14 to 19 units.
That crosses both proven floors: orange's digit floor at 17.13 and the nearest
known-bad candidate at 17.94.

**Use the MEDIAN.** Also killed the same day: an AND rule, recommended an hour
earlier and reversed by the data (11/45 against the median's 37/45).

### "REFUSE_COST has headroom to 30"
**Killed 2026-07-29.**

A bound over the box of physically achievable observations beats a sample of two
captures. Orange's proven digit floor is **17.13**, and the nearest known-bad
candidate of 28,234 sits at **17.94**.

**REFUSE_COST must never exceed about 17.** Real headroom is 2.94 units, not the
23.56 originally recorded (that figure counted only wrong top-1 picks and never
saw the near-misses among the 41 losing candidates per cell).

### The absolute ink-contradiction threshold of 50
**Superseded 2026-07-30, not wrong so much as incomplete.**

Zero false contradictions over 2756 blank cells, but only on SMOOTH backgrounds.
On a structured background (`starfield`, the Nyx glacier ring) it wrongly refuses
14.6 per cent of decoder-accepted blank cells.

Replaced by `threshold(row) = max(50, 6 * row background median spread)`.
K anywhere in 4 to 8 behaves identically; K=10 loses detection, K=15 loses it
entirely.

---

## Routing: how to tell a rotating body from a container

### The `OOC_` prefix as the local-frame router
**Killed 2026-07-31, and it was actively dangerous.**

Pyro does not use the prefix. On Pyro 3 the stack is
`Zone: pyro3 Pos: 330.74km ...` with no `OOC_` anywhere. Stanton still used it
as of 2026-07-26, so BOTH conventions are live.

Consequence before it was guarded: the reader concluded open space and emitted a
SYSTEM-frame position while the player stood on a rotating body, **62 frames of
62**. That is the 2026-07-11 data-loss failure through a different door.

The gate survives only as a REFUSAL guard, never as the router.

### The row-index rule (row 2 is the local frame, or row 3 if row 2 is a ship)
**Killed 2026-08-01 by the corpus.**

Right on exactly the two cases it was designed for. In `preflight` row 2 is a
ROOM (`rs_int_ptn_set`, 0.73 km) and in `red-01` it is a CARGO BAY
(`rs_cargo_001`, 86 m), **so it keys waypoints to furniture.**

### "The outermost row before SolarSystem is ALWAYS the body or area frame"
**Killed AS A UNIVERSAL 2026-08-10 by the corpus replay. The rule itself is not
dead; the word ALWAYS is.**

It holds in eight of the nine sessions that produce a candidate, which is
exactly why it is dangerous: a reader who checks a few sessions finds it perfect
and flips `LOCAL_TRACKING_ENABLED`.

**`dark-01` is the counterexample.** In the Clipper in open space there is no
world container at all, so the outermost pre-Solar row IS THE SHIP, in 12 of 12
accepted stacks. Measured three independent ways: the decoded name
(`????_?lipper_742164815970`, matching the entity id `CORPUS.md` records for
that session), Z pass-through failing 0 of 12 against 329 of 329 everywhere
else, and decisively **the candidate position holding within 0.239 m while Root
travelled 1.913e9 m**.

A waypoint marked in that regime with local tracking on would be keyed to the
ship and would follow it. This is the exact hazard
`COORDINATE_STACK_IMPLEMENTATION_PLAN.md` names as a stop condition.

**What this does NOT license.** The plan's stop condition turns on the candidate
selecting a movable frame ACROSS DIFFERENT VEHICLES, and this corpus contains
one ship. And do not "fix" it with a name, prefix, row-number or scale test:
all four are already dead further down this file. The measurement above is a
description, not a proposed discriminator, because a rotating body is a moving
frame too (`surface-01`, ratio 1.0e3).

Numbers in `LEDGER.md`, "The local candidate IS a movable ship frame".

### Z pass-through as the body-versus-container discriminator
**Killed 2026-08-01 afternoon, PROPOSED AND REVERTED THE SAME DAY.**

The transform is `system_z = body_z` for a rotating body as much as for a static
container, so a body passes the test too: `pyro3` matches **184/184**.

"World-anchored" in `reference_sc_coordinate_frames` means attached to the world,
NOT non-rotating. The memory was right and was misapplied.

Caught immediately by the real Pyro 3 fixture in `test_body_scale_guard.py`. No
test was altered to accommodate it. **Do not reach for this again.**

### Scale alone as the router
**Killed 2026-08-01 in both directions.**

- Under-detects: `glaciemring_segment` is a world container at 1.46 to 2.10 km,
  far below any threshold that keeps ships out.
- Over-refuses: `?umppoint_pyro_ny` is a 597 km container in open space, so the
  shipped 50 km guard calls a jump point a body surface and refuses.

**That false refusal is LIVE in 4.9.0.22 today.** Judged a cost, not a danger.
The guard stays as the fail-closed backstop.

---

## Architecture

### Vision AI removal (2026-07-31)
**REVERSED 2026-08-02 by Lars. See TODO.md "DECISION 2026-08-02: BUILD THE
ROUTER".**

**THEN RE-DECIDED IN THE OTHER DIRECTION, later on 2026-08-02: no Vision at all,
OCR only.** Lars's call, stated three times in one exchange. So the OUTCOME now
matches this 07-31 entry, but this entry is not the reason for it and must not
be cited as live. The operative decision is at the top of `TODO.md`; the
reasoning that killed the router is in `LEDGER.md` under "THE DECISION THAT WAS
BLOCKING EVERYTHING". Neither the router nor the strip was ever implemented.

It was taken the same night as, and in the opposite direction to, a measurement
recorded 80 lines below it in the same file (sunlit terrain refuses 62 to 100
per cent of cells; "Vision stays required for daylit surfaces"). Neither entry
referenced the other and the question meant to decide between them was never
answered until 2026-08-02.

**Reversing was free only because the strip step was ordered LAST as the
irreversible one and was never taken.** That ordering saved the project a
rebuild.

### The 5.18 ms feasibility figure
**CORRECTED, but the original is still sitting in LocalOcrPlan §2.1 as the
reason to build the reader.**

It timed a grab-and-threshold of the CamDir strip, not the least-squares reader.
The reader is three to four orders of magnitude slower: 23.6 to 26.4 s for a
full 20-row read, ~1 s for a single cached row, and 4.5 to 4.9 s per capture with
Star Citizen actually running, which is **slower than the ~3 s Vision call it
replaced**.

The token argument that justified the swap does not survive. **The correctness
argument does** and is independently strong: four confabulation incidents in
2026, one of which deleted six waypoints.

### 10 Hz as the rate target, and the 10-per-cent-of-a-core CPU gate
**Both dropped 2026-07-30 by user decision.** "A speed of 10 fps is more than
enough, even half of that is good enough." Target relaxed to about 5 Hz; the CPU
gate stops being a gate. Candidate-alphabet restriction (worth ~3x) and the
staggered parallel pipeline were dropped with reasons recorded.

Consequence: the "CPU target is NOT met" conclusion and the un-prototyped
per-cell-loop collapse it recommends are **mooted, not resolved**.

### Reusing the Vision capture path for the local reader
**Killed 2026-07-30, measured.**

`capture_screen_b64` has two transforms and both destroy this reader:
`_detail_crop` applies `ImageOps.autocontrast(cutoff=1)`, and the context image
is resized to 1200 px (a 4.27x downscale on a 5120 px monitor).

Fed the `game-mid` frame: native reads **8 of 8** rows trusted; autocontrasted
**0 of 8**; downscaled-then-restored **0 of 8**.

The model solves for the background in raw 0-255 units, so a contrast stretch
changes the quantity being solved for, and a resample mixes neighbouring cells.
**The reader needs its own raw `mss` grab.**

---

## Claims that were weakened rather than killed

### "Root agreeing with SolarSystem is a correctness check"
**It is a confabulation tripwire ONLY.**

Both lines independently decoded the SAME wrong coordinate on the bright capture
(5050km for a truth of 5059km). Two mechanisms: they share an identical
coordinate tail landing on the same x positions AND the same sub-pixel phases,
and they sit 13 px apart in one background regime, so background-driven errors
correlate.

Never describe it as independent verification and never loosen the floor for it.

### "Every breach is a low-ink glyph"
**Wrong population.** The mechanism is that a glyph can be corrupted into any
glyph that ADDS ink above or to the left of it, because the drop shadow reaches
only right and down, so those pixels have transmission exactly 1 and the
background owns them.

Confirmed on a FULL-INK letter: `n` read as `h` in a real body name, row trusted,
cost 7.1. **Digits are the SAFEST class**, which inverts the assumption the
project carried for weeks.

### The wipe-on-relog rule: "three consecutive captures agreeing"
**Does NOT survive a deterministic reader. Unfixed by raising the count.**

The rule assumes independence between reads. The local reader is deterministic
on identical pixels, and the dangerous failure is driven by the local background
level under one cell, so three frames a moment apart under the same lighting
decode the same wrong way.

This is exactly the class that deleted six waypoints in July: the Vision model
misread the same server token the same way twice, and two agreeing MISREADS
satisfied a two-capture confirmation. **Raising a count cannot fix a correlated
error in either reader.**

The shard token's underscores are structural delimiters, so an anchored shape
regex does catch the confirmed erasure. The hex GUID and the digit runs have no
such protection.

Mitigated for now by the local reader deliberately **never emitting
`server_id`**, so it cannot drive a wipe at all. That mitigation disappears the
moment anything else feeds the rule.

### "Repetition across captures is evidence"
**Only when the pixels differ.** The reader is deterministic on identical pixels
(bit-identical over five runs), so five grabs of a static scene are one sample
computed five times.

Character CHOICE is invariant across time-separated grabs (0 of 152 cells vary);
only the ACCEPT decision wobbles. Therefore a disagreement between grabs can only
mean the underlying TEXT changed, which makes disagreement a tripwire rather than
noise to vote away.

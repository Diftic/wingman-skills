# SC NavPoint Local OCR Plan

Status: IN PROGRESS (Phase 1 started 2026-07-28)
Created: 2026-07-27
Scope: `skills/sc_navpoint/`

Replace Vision AI as the reader of the `r_displayinfo` overlay with a
deterministic local reader, so position and facing can be sampled several times
per second at zero token cost. Decided with the user 2026-07-26 after a full
evening of live testing. Evidence and measurements below are from that session;
the narrative is in [`Devlog.md`](Devlog.md) entries of 2026-07-26.

## 1. Product outcome

The skill reads the overlay itself, locally and deterministically, at 10 Hz or
better during active navigation. Vision AI is no longer in the position path.

Three problems close together:

- **Cost.** The current reader cannot be run fast enough to be useful.
- **Correctness.** Every confabulation incident in this skill's history comes
  from a language model reading digits. A deterministic reader cannot invent one.
- **Visibility.** A smooth ring needs a high sample rate to be worth drawing at
  all, whichever surface eventually draws it.

## 2. Why, with the numbers

### 2.1 Cost, measured 2026-07-26

Per capture, input only: extraction prompt 6650 chars (~1662 tokens), context
image 1200x337 (~595 tokens), detail crop 1100x500 (~595 tokens), plus overhead.
About **3050 tokens per capture**.

| poll interval | tokens/hour |
|---|---|
| 5 s (as shipped) | ~2.2 M |
| 1 s | ~11 M |
| 10 Hz (the target) | ~110 M |

Local reading of the same pixels: **0 tokens, 5.18 ms, no network.** The
user's stated first constraint for skills is token usage, so the target rate is
unreachable by the current design, not merely expensive.

### 2.2 Correctness: what a deterministic reader deletes

Incidents this year, all of them a model reading numbers:

- 2026-07-20: prompt example echoed verbatim, phantom waypoint stored.
- 2026-07-22: worked example RECOMBINED into a plausible payload that the
  exact-echo tripwire missed.
- 2026-07-26: `CamPos` vanished from the surface overlay and the model filled the
  gap from its example rather than reporting nothing.
- 2026-07-26: the server token misread twice the same way
  (`pub-euw1b-5c-alpha-...`, an `s` as `5`), which "confirmed" a server change
  and DELETED six waypoints mid-session.

Machinery that exists ONLY because of the above, and which becomes unnecessary
once the reader is deterministic: `_ECHO_MARKERS`, `_ECHO_RAW_TOKENS`,
`_ECHO_COORDS` and the echo tripwire; the `implausible_body` plausibility gate;
the "never guess digits" prompt engineering; the canary discipline in the prompt.
Net effect is a SIMPLIFICATION, not a swap of equal complexity.

Retained regardless, because they guard parsing rather than hallucination: the
mandatory unit suffix (a dropped `k` is a 1000x error), the CamPos-versus-OOC
cross-check where both are present, the SolarSystem-versus-Root agreement check,
and the server-token shape gate.

### 2.3 Feasibility, measured 2026-07-26

- Grab and threshold the CamDir strip: **5.18 ms** (about 193 Hz ceiling).
  Full-screen grab for comparison: 49.3 ms (20 Hz). Reading a strip is the
  cheap path; do not grab the whole screen per sample.
- Glyph geometry on a 5120x1440 capture: text rows ~6..14 (about 9 px tall),
  column pitch 7 to 8 px, block right-aligned with its right edge at x=5113.
- **Rendering is effectively deterministic.** Identical text (`FStop: 64.0`)
  across 12 frames with completely different backgrounds: normalised
  cross-correlation 0.949 to 0.999 (mean 0.993), and only **1 to 8 differing
  pixels out of 1296** at a fixed threshold. The variation is anti-aliasing
  where glyph edges blend with whatever is behind them.
- The live path is EASIER than the validation corpus: `mss` captures are
  lossless, while the stored screenshots are JPEGs the game compressed.

## 3. Validation corpus, already on disk

`D:\Roberts Space Industries\StarCitizen\LIVE\Screenshots\` holds the 2026-07-26
frames whose values were read by hand and are recorded in `Devlog.md`:

- three 13-frame surface sweeps (WolfPoint, Nuen, Dunlow) with known CamDir
  triples and known compass headings;
- one 13-frame hangar sweep (Nyx) with known CamDir triples;
- open-space frames with known SolarSystem positions;
- the marker frame (`23-56-25`) with a known CamDir, position and FOV 48.

This is enough to measure accuracy BEFORE anything runs live, which is the
discipline that every failure this session lacked.

## 4. Phases

### Phase 1: reader and classifier, offline only

**2026-07-29: SOLVED on a lossless capture, 0.00% in-sample error.** The
prediction in 2.3 held: the JPEG corpus was the whole problem. Constants and
the measured model are in the next subsection; the JPEG-era narrative that
follows it is kept because it records what failed and why.

#### The model, measured 2026-07-29

Captured with `mss` while Star Citizen sat on its in-game main menu with the
overlay over the black right-hand third of an ultrawide screen. Tools:
`ocr_dev/capture_overlay.py`, `analyze_black.py`, `grid_fit.py`,
`label_cells.py`, `templates.py`. Every figure below is reproducible by
re-running them against capture set `login`.

| quantity | value | how established |
|---|---|---|
| character pitch | **exactly 7.5 px** | ink-fold fit gave 7.4985; least squares on labelled repeats gave 7.5000 with 0.00 px residual on `F`; cell occupancy segments cleanly across 58 cells |
| second pitch | **6.595 px** | a SECOND class of rows exists (`Phys`, `RL`, clocks, `Render`, the bracket line). The July note that "rows 8+ are laid out differently" was this: they are at a different pitch, not a different layout. None of the lines the skill reads are in this class. |
| row pitch | **exactly 13 px**, body 8 px tall | vertical ink profiles; bodies start at block rows 1, 14, 27, 40, 53 |
| block right edge | last ink column = screen width minus 7 | reproduces the July constant exactly, from a different capture path |
| colours | white (255,255,255), orange (255,164,0), yellow (239,230,139) | brightest-pixel clusters on a pure-black backdrop |
| backdrop | exactly (0,0,0), 87543 of 87543 px | sampled away from any ink |

**Sub-pixel phase, and why the first attempt still failed.** A line's left edge
is snapped to an integer pixel and characters then advance by exactly 7.5 px,
so every glyph in a line sits at phase 0.0 or 0.5 and WHICH ONE is fixed by the
parity of that line's character count. Keying templates on cell parity instead
is only valid within a single row and scored 33.51%. Fitting each row's origin
(its own repeated characters are the ruler, no external reference needed) drops
within-row deviation to exactly 0.00.

**Results.**

- In-sample classification: **185/185, 0.00% error.**
- Bitmap identity: 37 classes with two or more instances, **0 inconsistent**,
  worst deviation 0.42 coverage units, which is below one quantisation step.
- Colour normalises away: dividing by the row's colour makes a yellow glyph and
  its white counterpart agree to **0.53 coverage units**, so ONE template set
  serves all three colours and colour survives as a free field discriminator.
- Match margin: min 4.45, median 20.13, and **zero** instances under 1.0. The
  classifier is not deciding anything by a hair, which is what makes a
  refuse-rather-than-guess confidence floor practical.
- Rendering is not merely "effectively deterministic" as the JPEG corpus
  suggested: on lossless captures **13 of 19 text rows were bit-identical
  across five frames**, and the six that changed were the volatile ones (FPS,
  frame times, clocks). Zero rendering noise.

**What this does NOT yet establish, and must not be reported as if it did:**

1. Everything above is over a **pure black backdrop**. See the in-game finding
   below: the model is INCOMPLETE, not merely untested.
2. Character coverage is only what the login screen happened to show, 65
   (character, phase) templates over 41 characters. Confirmed insufficient in
   game: `3` and `k` are both absent, so `-33` reads as `-5S` and `km` as `-m`.
3. The 6.595 px row class is unmodelled. Acceptable while the skill reads only
   pitch-7.5 lines, but a reader must not silently apply the wrong grid: detect
   the row's pitch, and refuse a row that fits neither.

#### In-game capture, 2026-07-29: THE OVERLAY HAS A DARK SHADOW

Capture set `game-bright`, taken in PTU over a bright sky. It carries the full
line stack the skill needs, including `Zone: OOC Stanton 2 Crusader Pos: ...`.

Decoding it with the login templates gets the low-background parts of each line
right (`CamDir:`, `Zone:`, `Stanton`, `Crusader`, `Pos:`, `5295.4275`) and
fails wherever the background is bright. Inspecting those pixels shows why, and
it is not anti-aliasing:

**The glyphs are drawn with a dark shadow or outline.** Over the near-white sky
the text appears as DARK shapes, and the dark pattern matches the login
template's own coverage map. On the black login screen a black shadow over
black is invisible, which is exactly why the backdrop measured as pure black
with no halo and why nothing in the Phase 1 work hinted at it.

So the compositing model has a third term, and the two captures each see only
part of it:

    observed = G * colour + H * background

where `G` is the glyph coverage map, ALREADY MEASURED on black, and `H` is the
background's remaining transmission after the shadow, which black cannot
reveal. `H` is not `1 - G`: the shadow makes it smaller.

This is tractable and does not invalidate the Phase 1 result. `G` is correct.
`H` is one more map per (character, phase), measurable from a capture over a
KNOWN, UNIFORM, NON-BLACK background, and once both exist a cell is matched on
any background by solving the single unknown `background` by least squares,
exactly as `decode.py` already does with one map.

**The capture that resolves it: the overlay over a uniform mid-tone surface**,
neither black nor saturated white. Saturated white is nearly as bad as black
here, because a clipped background destroys the linear relation the fit needs.

That last claim was TESTED against `game-bright` rather than assumed, and the
test failed, which is why the mid-tone capture is required rather than
optional. Extracting `H` from the saturated sky (where `observed` should reduce
to `255 * (G + H)`) gave a between-instance inconsistency of 0.21 to 0.42 on a
quantity bounded in 0..1, with some derived values NEGATIVE, which is
unphysical. Clipping is the likely cause: the composite was computed against a
pre-clip background the 8-bit capture no longer carries. Recorded so nobody
repeats it: do not try to recover the shadow from a blown-out background.

Also learned from this capture, both to be handled by fitting rather than
assuming: the vertical origin of the block is not identical between captures,
and a row's decode must not be scored against one phase, because a row's cells
ALTERNATE phase with cell parity. Scoring a whole row at one phase was a real
bug in the first `decode.py` and it corrupted every other character.

#### `H` MEASURED, shadow model confirmed (capture set `game-mid`)

Taken over a large red interior wall. Its channel statistics are what made it
work, and they are worth looking for again: **R sits at 96 unclipped, G at 2,
B at 8**, with only 0.6% of pixels at 255 (the glyph cores). That is two useful
properties at once:

- The **green channel is a near-black-background view** of the same text, so
  the Phase 1 templates apply to it directly with no shadow term. Use it to fit
  alignment and to read the text.
- The **red channel carries the shadow**, because its background is high enough
  to be attenuated measurably.

Alignment fitted on green: y origin 6, sub-pixel offset 0.5, mean match cost
**0.0143 against about 0.10 at every neighbouring alignment**, so the fit is
decisive rather than marginal.

`H` then comes out consistent across instances, which is what confirms the
model:

| cell columns used | mean deviation | median | classes tight (<0.15) |
|---|---|---|---|
| all 8 | 0.412 | 0.472 | 12 of 33 |
| **mask 1 column each side** | **0.103** | **0.046** | **31 of 33** |
| mask 2 columns each side | 0.101 | 0.043 | 31 of 33 |

**The shadow extends about 1 px beyond its glyph and crosses into the
neighbouring cell.** Masking one column fixes it; a second column adds nothing,
which bounds the bleed at exactly one column. Any matcher must therefore either
mask the cell's outer columns or model neighbours jointly; scoring the full
8 px cell mixes in whatever character happens to sit next door.

The two classes still loose are consistent with label contamination rather than
model error: labels came from the decoder, and with `3` absent from the
template set every `3` is filed under `5` or `S`.

#### `H` IS DERIVABLE FROM `G`, so the alphabet costs nothing extra

Tested six candidate shadow shapes against the measured `H` (interior columns,
mean absolute error):

| shape | error |
|---|---|
| **dilate down-right (0,0),(0,1),(1,0),(1,1)** | **0.068** |
| drop shadow (0,0) | 0.144 |
| drop shadow (1,1) | 0.167 |
| drop shadow (1,0) | 0.203 |
| drop shadow (0,1) | 0.210 |
| dilate 3x3 | 0.225 |

So `H = 1 - dilate_down_right(G)`, reproducing the measurement to 0.068 against
a measurement noise floor of 0.046. **No shadow needs measuring per character**:
extending the alphabet only needs new `G` maps, which a black or
near-black-channel capture yields directly.

#### `reader.py`: the working prototype

Implements the full model: `G` from templates, `H` synthesised, cell outer
columns masked, background solved per cell per channel by least squares, colour
chosen per row, alignment fitted, rows identified by label.

On `game-mid` it fits y origin 6 and decodes all rows, labelling `CamDir`,
three `Zone` lines and `Session` correctly. Every remaining error traces to a
missing glyph, none to the model.

**One more real bug found and fixed here, worth remembering as a class:** the
sub-pixel offset must be fitted PER ROW, not once per block. A line's phase
follows the parity of its own character count, so a single block-wide offset
decodes the rows that happen to share its parity perfectly and turns every
other row into garbage, which looks like a flaky reader rather than a
systematic fault.

#### Where this stands, 2026-07-29

DONE: colour model, grid, phase model, shadow model, background solving,
self-location, per-row label identification, and the tooling to learn new
glyphs without hand transcription (`learn.py` groups unmatched cells by bitmap
and renders them for identification, which avoids the eye-transcription step
that has now been wrong twice).

NEXT, and small: label the 16 rendered unknown glyph shapes and fold them into
the template set. The four highest-count ones are unambiguous (`3` at both
phases, `k`, `g`) and match the observed substitutions exactly. Then re-run
`reader.py` on `game-mid` and `game-bright` and report a real in-game character
accuracy against text verified by cell occupancy, NOT by eye.

#### IN-GAME ACCURACY MEASURED: 98.33%

Template set extended to 77 templates over 46 characters (`extend.py`), with
labels taken from magnified single-glyph renders rather than line transcription.
Measured by `measure.py` on `game-mid`, over a red interior wall:

    CHARACTER ACCURACY: 353/359 = 98.33%   (error 1.67%)
    errors: 'i'->'1', 'x'->'-', 'P'->'R', ']'->',', 'h'->'n', 'I'->'1'

**All six errors are a missing (character, phase) template. None is a model
failure.** `x`, `h` and `I` are absent entirely; `i`, `P` and `]` have only one
of their two phases.

**The lines the skill depends on decode EXACTLY**, with zero errors:

    Zone: SolarSystem_729968885550 Pos: 6470453.8383km 13533871.9753km -33.29m
    Zone: Root Pos: 6470453.8383km 13533871.9753km -33.29m
    Session: ce34bb31-37d7-a247-a7fb-4b6b662bdcf6

Truth strings are verified against measured cell occupancy before being used,
and a row that disagrees is EXCLUDED rather than allowed to skew the figure.
That check fired: the CamDir truth was wrong in its leading spaces (the third
time this project has miscounted spaces on that same line) and row 0 was
dropped from the measurement.

**Refusal separation is clean**, which is what Phase 1 asks for. On the same
frame the unmodelled pitch-6.595 rows score cost 30.4 to 61.5 with margins 2.5
to 5.6, against cost 11.7 to 19.0 and margins 16.6 to 44.6 for the rows the
reader does model. A confidence floor between them refuses the rows it cannot
read instead of inventing digits.

A labelling error was made and caught here, worth keeping: glyph 13 was
labelled `5`, which regressed every real `5` at that phase into `S`. The tell
was `extend.py` reporting it as REPLACING an existing template rather than
adding one. Overwriting an existing template should be treated as a red flag,
not a routine outcome.

#### Six missing glyphs added, re-measured

`harvest.py` extracts a missing (character, phase) from a row whose truth has
ALREADY passed occupancy, so the label is certain rather than judged. It never
overwrites an existing template, because doing that once turned every `5` at
one phase into an `S`. It picked up exactly the six: `I`/1, `P`/1, `]`/0,
`h`/1, `i`/0, `x`/1, and correctly skipped row 0, whose truth still fails
occupancy. Template set: 83 templates over 49 characters.

    game-mid   CHARACTER ACCURACY 359/359 = 100.00%

**That 100% is PARTLY IN-SAMPLE and must not be quoted bare**: those six glyphs
were harvested from this very capture. The pre-harvest figure on the same
capture, 98.33%, is the clean one.

#### Out-of-sample, on the pathological background: much weaker

`game-bright` (white text over a saturated, clouded sky) is fully out of
sample. It went badly, in two distinct ways worth separating:

    1 of 6 rows could be verified at all
    that row: 26/31 = 83.87%   errors 'u'->'c' x2, '9'->'0' x2, 'S'->'5'

1. **The verification tooling fails there.** The occupancy gate detects a blank
   cell by local contrast, and over a textured bright sky a genuinely blank
   cell still shows large spread, so five of six rows could not be certified
   and were excluded. The gate refused rather than certifying wrongly, which is
   the correct failure mode, but it means there is no broad out-of-sample
   figure yet.
2. **The reader itself degrades there.** On the one certified row, 83.87% with
   real confusions on a 31-character sample, which is too small to quote as a
   rate but is clearly worse than the mid-tone case.

Fixed along the way, and a genuine improvement rather than a test patch: the
reader now carries a SPACE template (`G = 0`, `H = 1`), so a blank cell is
explained as pure background by the same least-squares fit instead of being
forced onto the least-bad glyph.

HONEST SUMMARY: the reader is essentially exact on a normal in-game background
and degrades on a blown-out one. The skill's real use (surfaces, space, station
interiors) resembles `game-mid`, not `game-bright`, but the bright case is not
solved and must not be assumed away.

#### Confidence floor: CALIBRATED and in place

Thresholds were measured, not chosen. Over 359 known-correct cells and 560
known-bad ones (the unmodelled pitch-6.595 rows, wrong by construction):

| | residual p50 | p99 / max | margin p50 | min |
|---|---|---|---|---|
| correct | 9.59 | 12.47 / **12.69** | 43.94 | **13.69** |
| known bad | 48.18 | 89.42 / 94.78 | 4.39 | 0.03 |

`REFUSE_COST = 15.0`, `REFUSE_MARGIN = 8.0`, both sitting in that gap with
headroom on the correct side. The asymmetry is deliberate: refusing a readable
cell costs a Vision fallback, accepting an unreadable one costs a waypoint in
the wrong place.

**Fails closed at ROW level.** A row is trusted only if EVERY cell in it was
read. One refused digit inside a coordinate makes the whole coordinate
unusable, so a partial number is never emitted looking complete.

Behaviour, which is exactly the intent:

    game-mid     rows 0-7  (pitch 7.5)      ACCEPTED, all correct
                 rows 8+   (pitch 6.595)    REFUSED, every cell
    game-bright  all rows  (blown-out sky)  REFUSED, every row

The bright capture is refused wholesale, including the row that had scored
83.87%. That is over-conservative on that row and correct in direction: the
reader now declines the conditions it gets wrong instead of guessing through
them.

Also added: a SPACE template (`G = 0`, `H = 1`), so a blank cell is explained
as pure background by the same least-squares fit rather than forced onto the
least-bad glyph.

REMAINING before Phase 2, rewritten 2026-07-29 after a 25-agent parallel audit
(full results in the session journal of that date):

**STATUS 2026-07-30.** Items 1, 10, 12, 13 and 15 are BUILT and tested in
`overlay_reader.py` (four guards, content classification after the label,
per-kind full-line shapes, fail-closed field parser) plus the join test this
file asked for first. Item 9's rule is honoured by construction: the reader
emits no `server_id` at all, so it cannot drive a wipe. Items 6 and 7 remain
open on the two captures. Corrections found while building:
- the precondition rejects 7 of 153 real screenshots as implemented here, not 9
- batching is a PREREQUISITE, not a Phase 3 nicety: the per-template loop took
  17.3 s to read ten rows, slower than the Vision call it replaces. Stacked, it
  is 1.7 s with output that agrees to 2.8e-14, so "bit-identical" is too strong
- the space branch needed a stronger gate than item 10 implies. It is a claim
  about ABSENCE, so a `kind`-based check misses a row corrupted past its own
  label. Any unreadable row ABOVE the SolarSystem line now refuses the capture,
  because the Zone stack nests inside out and an OOC line always sits up there

0. **THE THREAT MODEL, corrected by the red team after the first version of this
   list named the wrong population.** The fail-closed claim holds on every
   unmodified capture (20 lossless frames, about 1470 truth cells, zero wrong
   characters emitted), under noise to sigma 30, gamma 0.67 to 2.0, roughly 290
   synthetic backgrounds across two independent sweeps, 1152 configurations of
   real text rendered behind the overlay (about 125,000 cell reads, one accepted
   error in a row the gate refused anyway), and 800 rows of out-of-distribution
   4.8 JPEG.
   The mechanism when it breaks is NOT "low-ink glyphs". It is this: **a glyph can
   be corrupted into any glyph that ADDS ink above or to the left of it, because
   the drop shadow only reaches right and down.** Those pixels have transmission
   exactly 1, so the background controls them completely and the reader holds no
   evidence against the addition. Every confirmed breach is an instance:
   - `n` read as `h`, a FULL-INK letter, in a real body name on the real capture:
     `wtn-014` became `wth-014`, row trusted, cost 7.1, margin 41.1. `h` is `n`
     plus an ascender, and the ascender lives where the shadow does not reach.
   - `-` read as `9` on an orange row, cost 12.20: `-24.59m` became `924.59m`.
     This is the worst case found anywhere, because it stays GRAMMATICAL, so the
     structural shape gate of item 12 passes it while both the sign and the
     magnitude are wrong.
   - an underscore or hyphen read as a SPACE, which is the same mechanism with
     zero ink added rather than some: saturation or dimming removes the evidence
     instead of the background overwriting it.
   - the cheapest hit found on the real capture: three white pixels at one exact
     sub-cell position turn `1.26m` into `-1.26m`, trusted at cost 6.0. Lengths
     2, 4, 5 and 6 refuse everywhere, so the accepted window is narrow.
   Three things bound this, all measured rather than hoped:
   - **Digits are PROVEN safe against any background**, by minimising a wrong
     candidate's cost over the whole box of physically achievable observations
     rather than by sampling. The floors are 25.06 (white), 17.13 (orange) and
     20.27 (yellow) against a threshold of 15. No background can make a
     coordinate digit accept a wrong character.
   - **CONSTRAINT that follows from that proof: `REFUSE_COST` must not rise above
     about 17.** Orange's digit floor is 17.13, so a floor of 18 would open digit
     corruption on orange rows. This REFUTES the earlier threshold sweep's reading
     that cost had headroom to 30; a bound over achievable inputs outranks a
     sample of two captures.
   - **Every coordinate row in every capture fits WHITE** (measured across
     game-mid, starfield and ice-bright; only the FPS line fits yellow), so
     orange's weaker geometry, which has 203 attackable pairs against white's 169
     because its blue channel is zero and carries no ink evidence, does not reach
     coordinate lines in practice.
   - **The alignment attack fails outright.** At any wrong y origin only 4 to 16
     of 80 cells even have a cost floor below 15, against 15.51 at the true
     origin, and the row gate requires every cell read, so a wrong origin cannot
     produce a trusted row whether or not it wins the fit.
   Caveat the red team stated and this list preserves: the `n` to `h` attack
   depends on the DERIVED shadow being right at partially-inked pixels, which the
   docstring puts within 0.068 against a 0.046 noise floor. The space-fill and
   dash attacks are immune to that, since they only touch pixels whose
   transmission is exactly 1. The maximum background value the `n` to `h` attack
   needed was 213.9, inside the achievable range, so it is realisable in
   principle; whether real scenery ever places those exact pixels in that exact
   sub-cell position is a different question, and the structured-background
   measurement in item 1 is the reason to take it seriously rather than dismiss it.
1. **Two guards, both measured, neither optional.** Digits are the SAFEST class in
   the alphabet under the classifier's own distance, which inverts this project's
   prior assumption; the danger is in the low-ink and add-ink classes above.
   - **Ink contradiction test**, per cell, template-free: per-channel spread
     maxed over channels, threshold 50, calibrated blank 0-19 against ink 99-255
     over 680 verified cells. A cell that contains ink and decodes as blank is
     refused. Catches all three dimming breaches (spread 97.4, 83.5, 69.6),
     agrees with the correct read at full brightness (spread 232), and produced
     ZERO false contradictions over 2756 verified blank cells spanning all four
     captures and six gamma variants, the highest spread on any real blank cell
     being 35.0 against the threshold of 50. It also closes most of the
     single-cell saturation class: where a one-cell clip attack first produced an
     accepted wrong blank, the red channel had clipped while green and blue had
     not, so spread was still 55 and the contradiction fired. The residue is one
     narrow case, a single cell flat at 255 in ALL THREE channels inside an
     otherwise clean row, and a third layer CLOSES it (validated below), so there
     is no open residue in this class.
   - **Per-cell flat-white test**, the third layer: refuse a cell whose interior
     spread is below 5 AND whose mean is at or above 250 AND which sits at least
     40 units above its row's own background level (the mean of the row band's
     three per-channel medians). Validated: it fires on exactly the one attack
     point that beat the other two guards (the full clip at offset 255) and on
     nothing else along that attack's range, and it fired 0 times across 540 real
     blank cells from three populations, including 159 on the blown-out sky where
     the mean reaches 236.
     WHY IT WORKS, and this is the useful part: real captured background never
     achieves a bit-flat interior. Across 159 blank cells on a blown sky the
     spread never fell below 9, because compression, quantisation and subtle
     gradients always leave variation. Only genuine clipping produces perfect
     flatness, so a spread floor of 5 selects for "flat because DESTROYED" rather
     than "flat because bright", which is exactly the distinction the guard needs
     and the reason it does not collide with legitimately bright backgrounds.
     Combined coverage of the three layers over the full single-cell clip attack:
     the mid range is refused by cost and margin, offset 200 by the ink
     contradiction, offset 255 by this rule. No point on the range gets through.
     **RISK CONFIRMED, and the threshold as specified is NOT viable as an absolute
     number.** The zero false-positive rate was measured only on smooth
     backgrounds. A capture taken 2026-07-30 inside the Nyx glacier ring
     (`captures/starfield`, dark teal with bright ice debris, block mean 68.9,
     p5 0, p95 213, 2.1 per cent clipped) is the first genuinely high-frequency
     background in the corpus, and it breaks the calibration:
     - Over 1440 background cells the spread runs median 43, p95 163, max 242,
       against median 7 and p95 11 on the smooth capture. An ice-chunk edge inside
       a blank cell carries as much local contrast as ink does.
     - The rate that matters, measured on the reader's own grid over cells the
       decoder ACCEPTS AS BLANK: the contradiction would wrongly refuse 21 of 144
       (14.6 per cent) on the structured background, against 0 of 167 (0.0 per
       cent) on the smooth one.
     A coordinate row contains several spaces, so a 14.6 per cent per-cell rate
     refuses most rows over such a background. That is SAFE but expensive: it
     would have made the reader fall back to Vision almost everywhere in space
     while passing every test in the audit, because the audit had no structured
     background in it.
     **SOLVED, measured 2026-07-30. Use a hybrid threshold, not an absolute one:**

         threshold(row) = max(50, K * median spread of that row's background cells)

     with K = 6 (anything in 4 to 8 behaves identically on the data). Measured
     against both halves at once, detection on the three real dimming breaches at
     two sign cells and false positives on decoder-accepted blank cells:

     | K | breaches caught | FP smooth | FP structured |
     |---|---|---|---|
     | 0, absolute only | 6/6 | 0 of 126 | 16 of 110, 14.5 per cent |
     | 4, 6, 8 | 6/6 | 0 of 126 | 0 of 110 |
     | 10 | 4/6 | 0 of 126 | 0 of 110 |
     | 15 | 0/6 | 0 of 126 | 0 of 110 |

     Why it works: a smooth row's background median spread is 7, so `K * 7` stays
     below 50 and the absolute floor governs, which preserves detection exactly as
     before; a structured row's median is several times higher, so the relative
     term lifts the threshold above ordinary background variation and the misfires
     vanish. Strictly better than the absolute rule on every population measured.
     An independent sweep of 153 real screenshots reached the same conclusion from
     the false-positive side alone, cutting misfires to 0.5 and 1.7 per cent with
     relative rules, but without measuring detection; this pair of numbers is what
     settles the constant.
     TENSION that remains, and it is inherent rather than a tuning problem: on a
     structured row the relative threshold rises above the spread a DIMMED glyph
     would show, so the ink test loses the dimming class exactly where backgrounds
     are busy. Faint ink and background structure are not separable by local
     contrast alone. Two things bound the exposure: structured backgrounds push
     cells toward refusal anyway on cost (24 of 168 background cells already
     refused there against 1 of 168 on the smooth capture, and whole rows refuse
     at cost 11 to 39 against 4 to 9 on a dark wall), and the capture-quality
     precondition is cheap to run. Do not present the ink test as the primary
     defence on busy backgrounds.
     The flat-white test is unaffected: it fired 0 times in 1440 structured cells,
     as its `spread < 5` gate is the opposite condition to background structure.
     SETTLED, a concern raised earlier and now closed: the row-level statistic is
     not too coarse for partial erasure. A row whose background is bright enough
     to erase any glyph is already far over the 15 per cent threshold on its
     background alone (the minimum row fraction in every bright case at every
     gamma was 29.41 per cent), regardless of which individual notches survived.
   - **Capture-quality precondition** for the saturation class, which NO local
     test can catch: the two gamma breaches read spread 9.0 and 7.1, genuinely
     indistinguishable from blank, because the information is destroyed rather
     than degraded. Now specified and validated. Reject the capture if ANY row's
     clipped-pixel fraction (any channel at or above 250) reaches 15 per cent,
     measured over the block columns at `BLOCK_TOP + row * ROW_PITCH`. Across 20
     real frames plus gamma variants (32 cases) that separates perfectly: the
     worst safe row ever reaches 5.91 per cent, the best unsafe row never drops
     below 29.41, so the threshold sits in a 23-point empty gap with zero wrong
     accepts and zero wrong rejects.
     **Compute it on the FIXED, hardcoded block geometry, never on the reader's
     own fitted origin.** Under gamma 0.5 the alignment fit itself jumps from
     y0=6 to y0=2, because extreme saturation confuses the alignment search too,
     so a guard that consumes `fit_alignment` output inherits the failure it
     exists to catch. This also means the two originally-reported breach cells
     could not be reproduced through a re-fitting pipeline: the fit moved first.
   - **Per-cell clipped fraction**, the companion the row statistic cannot
     replace. Confirmed by direct attack rather than reasoned about: clipping ONE
     cell to 100 per cent (simulated bloom behind a single character) leaves the
     row at 3.09 per cent and the frame at 2.17, both comfortably safe, while
     that cell decodes as an accepted wrong blank at cost 10.17 with margin
     15.53. Refuse any cell whose own clipped fraction exceeds about 50 per cent
     regardless of cost and margin; the separation is clean (0 per cent at
     baseline, 94 to 100 per cent exactly where the failure starts), though the
     threshold itself was not swept exhaustively.
     Resolved, not a defect: the two accepted-and-wrong cells this agent saw on
     `login-black` are a test artifact, not a saturation failure. It reused
     `login`'s truth string for both captures, and the frametime field genuinely
     differs between the two sessions (another agent independently measured
     login at 1.7 to 1.8 ms and login-black at 1.9 to 2.2 ms). The frame is only
     1.35 per cent clipped, nowhere near saturated.
2. **The confidence floor is the only thing protecting this reader, and its
   headroom is 2.94 cost units, not 23.56.** An exhaustive known-bad
   reconstruction (28234 wrong candidates over 680 cells) puts the nearest wrong
   candidate at cost 17.94 against REFUSE_COST 15, and it is blank-versus-
   underscore, the same weak population. The earlier figure counted only wrong
   top-1 picks, all high-cost outliers. The same reconstruction reproduced this
   file's own calibration numbers exactly (known-good p99 12.47, max 12.69,
   smallest margin 13.69), which proves the original floor was calibrated on
   game-mid's seven rows ALONE. REFUSE_MARGIN 8 changes zero decisions across
   28234 known-bad and 680 known-good samples: unexercised defence in depth.
3. **Redundancy is not a second source.** `Zone: Root` and
   `Zone: SolarSystem_<id>` share an identical coordinate tail landing on the
   same x positions AND the same sub-pixel phases, and sit 13 px apart in one
   background regime. On the bright capture both independently decoded the SAME
   wrong coordinate. Keep the agreement check as a confabulation tripwire; never
   describe it as independent verification, and never loosen the floor for it.
4. **A sign flip is the highest-consequence reachable error and no existing
   guard catches it.** The unit-suffix regex makes the sign optional, `CamPos` is
   absent on 4.9 surfaces so that cross-check never runs, and the Root agreement
   lives only on the space branch. The magnitude identity held back elsewhere in
   this project is PROVABLY blind to it, since flipping one component's sign
   leaves the magnitude unchanged. Surface cost is 49-76 m, the plausibly-nearby
   kind of wrong; system-frame cost is tens of millions of km, which anything
   catches. The ink contradiction test above is the cheapest guard that works.
5. **Phase is a pure function of position, not of line length.** Measured over
   24 rows in four captures: the fitted offset always cancels the line's length
   parity (`offset_bit = 1 - (n mod 2)`), so a character at index i from the left
   always sits at phase `(1 + i) mod 2`. One unexplained exception, both
   `ShardId:` rows (n=31, fitted offset 0.5); the 6.595 px second pitch class was
   tested and refuted as the cause. Consequence for the alphabet: because zone
   names are open vocabulary, no missing pair is structurally unreachable, so the
   gap list does not shorten and the fix is capture variety.
6. **The alphabet gap is three pairs, not thirty.** Only `k` phase 0, `O` phase 0
   and `u` phase 1 are exercised by real overlay lines, and all three occur only
   in the unharvestable bright capture; two are already misreading there
   (`OOC_Stanton_2_Crusader` decodes as `OuC_Stanton_2_Crdsader`). One capture
   with an `OOC_` line and the `ShardId` row over a dark surface closes all
   three in principle, but `O` occurs once per frame so its phase is a coin
   flip, and bursting one standing position cannot help because identical digits
   give identical phases. Two captures at different locations is the practical
   ask. `C` phase 0 and `D` phase 1 come free from body names (Crusader, Daymar);
   `V` phase 1 is CamDir-exclusive and low consequence.
7. **Held candidate, deliberately NOT adopted:** an attenuated shadow
   (`a = 0.5` weighted sum instead of the hard three-way OR) beat the current
   model on every measured axis on both captures, and four of eight alternative
   shadow shapes BROKE `fit_alignment` outright on the bright capture rather than
   merely decoding worse, which the original single-capture derivation could not
   have seen. Two captures is not enough to re-fit a load-bearing model
   parameter, so this waits for the third capture above. Whatever ships must be
   validated end to end against alignment and occupancy, not per-cell margin
   alone.
8. Still open from before: a decision on whether to widen the reader's working
   range for bright scenes or let Vision cover them. The audit answers it in
   practice: the bright capture yields 0 of 30 trusted rows, so blown-sky scenes
   are already 100 per cent Vision fallback at this floor.
9. **THE LOCAL READER MUST NOT DRIVE THE WAYPOINT WIPE ON ITS OWN.** The live
   rule requires three consecutive captures agreeing on a new shard token before
   deleting waypoints, which assumes the three reads are independent. They are
   not.
   VERIFIED 2026-07-30, in answer to the user's question: five runs of the reader
   over the SAME screengrab, with a fresh Reader each time, produce bit-identical
   output on both a clean and a hard capture, fingerprinted over text, cost,
   margin, refusal count and trusted flag at full float precision. There is no
   randomness in the path. So repetition over unchanged pixels is not evidence at
   all: five runs is one sample computed five times.
   IMPLEMENTABLE RULE that follows, and it is cheap: a confirming capture only
   counts as evidence if the PIXELS in the cells carrying the token actually
   differ from the previous capture's. Compare that patch between captures and
   discard a confirmation whose input is identical. Otherwise the confirmation
   count measures nothing but elapsed time. Note the contrast with the Vision path
   this replaces: its errors varied per call (24 of 73 captures corrupted while
   the player stood still), so repetition bought some independence there, yet even
   THAT was not enough, because the July incident produced two agreeing misreads
   of the same token and is exactly why the threshold was raised to three. Raising
   a count cannot fix a correlated error in either reader. The reader is deterministic on identical pixels and the dangerous failure
   is driven by local background LEVEL under one cell, so three frames a moment
   apart, same camera, same surface, decode the SAME wrong way. Repetition is
   worthless against a lighting-deterministic error, which is exactly the class
   that deleted six waypoints in July. Mitigations, in order of cheapness: a
   mandatory delimiter-shape check (the shard token's three underscores and the
   Session GUID's four hyphens are structural, and a regex anchored on them
   rejects the confirmed underscore-erasure case); a region-token allowlist,
   since those are a small closed set; and a non-reader confirmation step for any
   wipe. Note the limit honestly: shape checking gives ZERO protection on the
   homogeneous runs, because a hex-for-hex or digit-for-digit substitution is
   invisible to any shape rule.
10. **The row `kind` field is not safe to consume as-is.** Every frame tested
    carries two to four rows all labelled `zone`, with nothing in the row dict to
    tell the ship-interior zone from `OOC_`, `SolarSystem_<id>` or `Root`. Taking
    the first `zone` match returns a DIFFERENT kind of line depending on game
    state, which is the row-index fragility the label rule exists to prevent,
    moved up one level. Worse, synthetic rows carrying a fabricated SolarSystem
    id, a fabricated shard token, and a zone named `Root_Cellar_042` were all
    accepted as trusted at cost under 2.5, because the reader does no shape
    validation at all. Porting `kind` without adding content rules would discard
    the three hardening layers scanner.py gained after the July confabulation
    incidents. Required: classify on the content AFTER the label, anchor Root on
    the full token (`^Zone: Root Pos:`, never a bare prefix), and treat anything
    else beginning `Zone:` as informational only.
11. **Template coverage gap beyond the three measured pairs:** lowercase `v`,
    `j`, `q` and `z` have NO template at either phase, so the `Server:` line is
    structurally unreadable regardless of image quality. That is why every
    Server row refused in every capture. Not urgent (the skill reads the shard
    line, not Server) but it should be recorded rather than rediscovered.
12. **`trusted` does not mean "contains a payload", DEMONSTRATED not theorised.**
    A row rendered as `Zone: Root Pos:` with the coordinate region left as bare
    background comes back `trusted=True`, `kind="zone"`, `refused=0`, cost 0.00,
    margin 19 to 28, at three different backgrounds. Blank cells decode as spaces
    at zero cost, so an absent payload is indistinguishable from a real short
    line by any field in the row dict. A consumer gating on
    `trusted and kind == "zone"` accepts it and then parses three empty
    coordinates. The natural fix does NOT work: a minimum non-space count passes
    this row, because the label alone is 15 characters. The binding gate must be
    a per-kind FULL-shape match against the whole stripped text, for example
    `^Zone:\s*\S+\s+Pos:\s*-?[\d.]+(m|km)\s+-?[\d.]+(m|km)\s+-?[\d.]+(m|km)$`,
    with the inked-cell count kept only as a cheap early exit. Ten trusted
    empty rows also occur naturally in the corpus, below the overlay's live
    content in both login captures, at cost 0.00 and margin 26.50.
    Related good news, measured over 7 backgrounds by 10 noise levels by 9 JPEG
    qualities: mid-grey is confirmed the fragile background (crossing into
    refusal at sigma 16-20 against black's 50, and at JPEG quality 25-55 against
    black's 15) but the fragility is SAFE. Zero accepted-and-wrong across all 630
    combinations, because the margin always collapsed before the cost fell far
    enough to accept a wrong glyph.
13. **OCCLUSION IS THE ONE FAILURE REACHABLE BY ORDINARY PLAY, and it produces a
    trusted truncated coordinate.** An opaque flat occluder over part of the block
    (a menu panel, a loading screen, any solid HUD element) is pixel-uniform, so
    it fits the all-zero space template with residual near zero: far under the
    cost floor and with a large margin over every real character. The reader
    cannot tell "the game rendered nothing here" from "something is covering the
    text", so occluded cells decode as CONFIDENT SPACES and `.strip(" _.-")` then
    removes them, which makes a coordinate cut off at 62 of 77 characters look
    like a complete shorter reading. Measured on the frame that otherwise reads
    359 of 359: at only 20 per cent coverage of the block, six of eight rows came
    back trusted with their correct `kind`, zero refused cells, and text such as
    `Zone: SolarSystem_729968885550 Pos: 6470453.8383km 1353387`, missing the rest
    of the second axis and all of the third. Reproduced from the left edge, the
    right edge and the middle, at every coverage step from 20 to 80 per cent.
    Only total coverage degrades safely to empty text.
    MITIGATION: this is the third independent reason for the full-shape gate in
    item 12. A pattern requiring three unit-suffixed axes rejects that exact
    string, and so does the mandatory unit suffix the Vision path already
    enforces, since `1353387` carries no `m` or `km`. Neither the confidence floor
    nor the ink test of item 1 can help: the occluded pixels genuinely contain no
    ink, so every local measurement correctly agrees they are blank. The gate has
    to be structural.
    Safe by comparison, from the same sweep: absent input (uniform frames, or the
    overlay region replaced by scene pixels) yields trusted-but-EMPTY rows with no
    label, which is harmless; a faded overlay refuses cleanly at alpha 0.75 with
    no intermediate confident-wrong band; and vertical displacement inside the
    searched range follows exactly. One instructive coincidence at a 9 px shift:
    the fit locked onto the wrong origin but `ROW_PITCH` aliasing put row index 1
    on the true content, so seven rows came back byte-correct and INDEX-SHIFTED by
    one. That is precisely why rows must be identified by label and never by
    index, and it is the first direct evidence for a rule this project adopted on
    judgement.
14. **OUT-OF-DISTRIBUTION RESULT, the strongest evidence in the audit.** The
    reader was run over the 40 JPEG screenshots from 2026-07-13: a different game
    patch (4.8), lossy compression, and templates trained on 4.9 lossless PNG.
    800 rows examined. 36 trusted (4.5 per cent), 764 refused. ZERO
    trusted-but-wrong, with 11 of the 36 verified character for character against
    magnified crops of the actual images, spanning all four trusted row kinds
    including the punctuation-heavy Session GUID and the underscore-delimited
    shard token.
    The result that matters most: EVERY `Zone:` and `Pos:` row across all 800 was
    refused, never once trusted. On input this reader was never designed for, its
    high-confidence output was confined to frame-rate telemetry and identity
    strings, and never once to coordinate data. Fails closed precisely where a
    failure would become a waypoint.
    Also confirms the test was valid rather than measuring the wrong thing: all 40
    files are 5120x1440 and `fit_alignment` converged on y0=6, the exact hardcoded
    block top, in every single file, so this measured compression and patch
    difference rather than misalignment.
    **INDEPENDENT VALIDATION, found by accident and worth more than most of the
    audit.** The user's screenshot folder holds 103 files from the 2026-07-26
    session, which are the frame-stability probe frames this project's whole
    coordinate-frame model was built on. Decoding six of them: the reader returns
    `CamDir: 8 33 159` for the 14:00:32 frame and `CamDir: 35 0 -126` for the
    14:03:16 frame, which match the values in TODO.md's table EXACTLY. That table
    was produced weeks earlier by hand transcription plus a separate analysis path,
    so this is two fully independent readings of the same pixels agreeing, on
    lossy JPEG, at cost 3.3 and 3.8. Across all six frames the Session GUID and
    shard token also decode identically to each other
    (`b2dc9845-7293-314e-a581-2cac59fa6201`, `pub_euw1b_12269732_040`), and NO
    coordinate row was trusted in any of them, consistent with all 800 rows of the
    4.8 corpus. Nothing in the audit was designed to produce this check; it exists
    because the user pointed at a folder.
15. **Most of the structural gate ALREADY EXISTS, on the consumer side, so Phase 2
    is smaller than items 10 to 14 make it sound.** Verified in `scanner.py`:
    `_coords_from_pos_raw` returns None unless the value is a sequence of EXACTLY
    three elements, and `_parse_length_m` via `_LENGTH_RE` rejects any component
    without an `m` or `km` suffix. That pair already rejects the occlusion
    truncation (`1353387` carries no suffix, and two tokens is not three) and the
    empty-payload row (no tokens at all). `main.py`'s `_SERVER_ID_RE` already
    shape-checks the shard token, and the `_KNOWN_SYSTEMS` body-token gate already
    rejects a fabricated body name.
    So what Phase 2 must BUILD is not a new validation layer, it is the
    reader-side FIELD PARSER that turns a decoded row into those fields, written
    to fail closed: emit three unit-suffixed tokens or emit nothing. The existing
    gates then catch the structural failures for free. What the parser must add
    beyond that: distinguishing the four `Zone:` line variants by their content
    (`OOC_` prefix, `SolarSystem_<digits>`, `Root` anchored on the full token,
    everything else informational), since `kind` alone cannot, and refusing to
    emit anything from a row that failed the per-cell guards. This is also where
    the untested-join risk concentrates, because today the reader's row dict and
    `_capture_position`'s pos_data share no code path at all and every test on
    either side supplies its own already-final fixture.

**Rows are addressed by LABEL, never by index** (user, 2026-07-29): which lines
appear in the stack changes with context (in a base, on foot, in a ship, seated
in a chair), so a line's row number is not stable between captures. The line
SPACING is always the same, which is what makes this tractable: anchor the
vertical grid at the block top, step 13 px, read every row, then identify each
one by its leading label (`CamDir:`, `Zone:`, `Pos:`). A reader that trusts a
row index will silently read the wrong line the first time the player sits down.

**Read-time phase selection needs no labels.** `fit_origin` uses known text to
find a row's origin, which is a development convenience, not a runtime
requirement. At read time, decode the row at BOTH phases and keep the one with
the lower total match cost. With a worst-case margin of 4.45 against a median
of 20, the wrong phase loses by a wide margin, and a row where the two phases
score close is exactly the row that should be refused rather than guessed.

**NEXT ACTION: an in-game capture over a dark surface**, then the same
measurement, then a deliberately BRIGHT background to find where the model
breaks. Risk 7.2 named that case; it should be measured now rather than
discovered in the field.

#### The JPEG-era attempt, kept for the record

#### Geometry, measured on the 5120x1440 frames

| quantity | value | how it was established |
|---|---|---|
| character pitch | **7.496 px** | period search over the ink profile, then refined by minimising ink landing on cell boundaries; at 7.496 the boundary ink is **exactly 0.000** on rows 0 to 7 |
| grid phase | **7.10 px** left of the block's right edge | same fit; the glyph fills 0.0 to 5.5 px of each cell, the gap sits at 5.6 to 7.5 |
| block right edge | screen width minus 7 px | measured; express it relative to the right edge, never absolutely |
| first text row | y = 7 | row pitch about 12.9 px, rows 8 to 9 px tall |
| rows that share one grid | rows 0 to 7 | rows 8+ (Session, ShardId, the bracket line) do NOT fit it and are laid out differently. Everything the skill needs (CamDir and the four Zone/Pos lines) is in the clean set. |

7.510 was the first estimate and it is WRONG in a way that hides: over a
76-character line the 0.014 px error accumulates past a full pixel, which
silently shreds template matching while every individual glyph still looks fine.

#### The labelling method, which works and should be reused

Every line is **right-aligned**, so cell k counting right to left is character
`len(text) - 1 - k`. Verified by rendering the rightmost six cells of five rows
and matching them against the known text character for character
(`5 . 0 _ : p`, `m 3 8 . 2 _`, `m k 7 8 2 9`). One transcribed frame therefore
yields several hundred labelled glyphs with no hand-labelling by eye, which is
the step most likely to introduce silent errors.

It also self-checks. Comparing a transcription's length against the measured
ink span caught a real error in mine: the CamDir line measured exactly 2 cells
shorter than typed, so its run of spaces was wrong. Always run that check
before trusting a transcription.

#### Where it stopped, and why

Templates built that way classify **25% of characters wrong IN SAMPLE**, with
systematic confusions: `5` and `S`, `3` and `S`, `0` and `D`, `o` and `c`/`g`/`p`,
`2` and `Z`. In-sample failure means the representation cannot separate these
glyphs; more data will not help.

The cause is resolution against noise. A glyph is about 5.5 by 9 px, roughly 50
pixels of information, and at that size `0` and `8` differ by two or three
pixels, which is the same magnitude as the JPEG artefacts in the corpus.

#### NEXT ACTION, and it is a small one

**Build the templates from a LOSSLESS capture instead of the JPEG corpus.**
Section 2.3 above already predicted this: `mss` grabs are lossless where the
stored screenshots are JPEGs the game compressed. Take one `mss` still of the
overlay strip with Star Citizen running, transcribe it, apply the labelling
method above, and re-measure the in-sample error. If it collapses, Phase 1 is
essentially done; if it does not, the glyph size is a hard limit and the answer
is to match whole FIELDS rather than characters.

Do not spend another evening tuning thresholds against JPEG frames. That was
tonight's mistake: four attempts at collapsing a clustering that was noise-limited
from the start.

### Phase 2: make it the position source

Wire the reader into `_capture_position`, with the Vision path retained as an
explicit fallback behind a flag.

Acceptance:

1. A live capture produces a position and CamDir with no LLM call, verified by
   token usage staying flat in the log.
2. The existing frame routing, unit handling and cross-checks all still hold;
   the whole suite passes unchanged.
3. Fallback is exercised by a test that forces a refusal.

### Phase 3: ACCURACY FIRST, rate second (user decision, 2026-07-30)

The user settled the trade explicitly: "accuracy is what I was trying to aim for,
not speed. A speed of 10 fps is more than enough, even half of that is good
enough." So the acceptance target below (10 Hz under 10 per cent of one core) is
RELAXED to about 5 Hz, and the spare budget is spent on correctness instead.

What that decision removes from scope:
- **Candidate-alphabet restriction is dropped.** It was worth about 3x, but it
  couples correctness to a hand-maintained per-field alphabet, and an incomplete
  table refuses a genuinely correct read. Not needed at 5 Hz.
- **The staggered parallel pipeline is dropped.** It converts latency into
  throughput without reducing total work (40 updates per second is 40 decodes per
  second however they are arranged), and the cores would come out of the game's
  budget. Batching alone reaches about 60 ms per row, which is 16 Hz single
  threaded, already over the requirement.
- The 10-per-cent-of-a-core figure stops being a gate. At 5 Hz with a 60 ms row
  the duty cycle is about 30 per cent of one core, and the ring interpolates
  between samples at its existing 30 fps render (0.431 ms per frame), which is
  what makes the motion look continuous regardless of sample rate.

What the decision buys, and this is the substance of the phase: a MULTI-GRAB
ESTIMATE, affordable now that the rate target is relaxed. Five successive grabs
0.025 to 0.1 s apart, decoded as one batched operation over the grab axis, then
per cell:
- If every grab agrees on the character, use the MEDIAN cost and margin for the
  accept decision. That is pure variance reduction: it does not move the decision
  boundary, so it cannot relax safety, and it measured +5 and +7 characters over a
  single grab on a hard capture (37/45 and 22/31 against 32/45 and 15/31).
- If the grabs DISAGREE on the character, the text changed inside the window (the
  player turned, a counter ticked) or something is unstable. Refuse the cell, or
  fall back to the newest grab alone. Disagreement is a SIGNAL, not noise to vote
  away.
This last rule is what makes multi-grab safe for a changing field like CamDir.
The character choice was measured INVARIANT to background change (0 of 152 cells
varied across five grabs while 39,000 to 50,000 background pixels moved), so a
disagreement can only mean the underlying text changed, which is exactly the
condition under which aggregating would have been wrong.
Do NOT use the min-cost (OR) rule despite it scoring best on coverage (45/45 and
28/31): taking the minimum across five grabs is arithmetically a relaxation of
the floor from 15 to about 30, given the measured per-cell cost wobble of 14 to 19
units, and that crosses both proven floors (orange digit corruption at 17.13, and
the nearest known-bad candidate at 17.94).

### Phase 3 (original framing): raise the rate

**A SAMPLE IS NOT CHEAP, measured 2026-07-29 on a Ryzen 7 7700X.** This phase was
written on the premise that a local read costs about 5 ms, which came from timing
a grab-and-threshold of the CamDir strip. The actual least-squares reader costs
three to four orders of magnitude more, and the premise has to be corrected
before the phase is planned around it:

- Full 20-row read: 23.6 to 26.4 s of CPU, about 0.04 Hz. The cost is 530,400
  `match` calls at roughly 50 to 56 us each, verified by COUNTING the calls and
  multiplying back to within noise of the observed total.
- Single CamDir row with the alignment cached: 906 ms to 1.03 s of CPU, roughly
  1 Hz, saturating a core while it runs. An order of magnitude short of 10 Hz.
- Measured twice, under about twelve concurrent processes and again with none
  observed, because the whole audit was running on this machine. Wall time moved
  25.9 per cent between the two, CPU time only 10.6 per cent, so CPU time and
  call counts are the figures to carry forward. The load-independent ratio of a
  full block to a single row is exactly 26.0x by call count; the less contended
  timed run reproduced it at 26.1x, the contended one inflated it to 29.4x.
- The cost is linear in cells times templates (2.17 versus 2.24 ms per cell at
  two different cell counts), so per-cell template scoring IS the cost. The
  alignment grid and the offset-and-colour search are multipliers on top of it,
  not separate cost centres.

Four wins, each measured rather than estimated:

- **Cache the alignment across frames.** The fitted (y origin, offset, colour)
  was bit-identical across all 20 frames of all four capture sets, including a
  blown-out sky and a pure-black backdrop. Removes the 6.4 s fit from every poll
  after the first, and is the whole 0.14 to 0.90 Hz jump above. Re-validate
  periodically rather than caching once forever: nothing else in the reader would
  notice a silent invalidation, and the sample never varied resolution or UI
  scale.
- **Batch the per-template loop into one numpy operation.** Prototyped and
  verified BIT-IDENTICAL to the existing loop (maximum score difference 0.0
  across 39 real templates on a real cell), for a measured 16.13x. Same maths,
  batched over the template axis, so there is no accuracy or safety cost. This is
  the single highest-value change and it should be done before anything else.
- **Grab only the overlay strip.** A 620x280 corner grab measured 4.13 ms
  against 42.87 ms for the full 5120x1440 monitor, a 10.4x saving with no new
  assumption: the block is already right-aligned to width minus `RIGHT_MARGIN`.
- **Restrict the candidate templates per field** (CamDir needs digits and a few
  punctuation marks, not the whole alphabet). Real headroom, deliberately NOT
  prototyped, because it couples correctness to a hand-maintained per-label
  alphabet and an incomplete table would refuse a genuinely correct read. Do it
  after batching, and only for the rows the high-rate path actually needs.

Honest position on the acceptance target. Caching plus batching projects to
between 58 and 95 ms per row, so 10.5 to 17.4 Hz. The spread is not measurement
noise, it is an assumption: the low end applies the 16.13x to the whole row time,
the high end applies it only to the portion that is actually `match` calls, which
is the conservative and more defensible reading. Either way the RATE target is
met, and the projection survived a 26 per cent swing in machine load, so it is
directionally solid. It rests on one extrapolation that was never re-measured end
to end: that a speedup measured on one cell's candidate set scales across all
eighty cells of a row.

The CPU target is NOT met and that conclusion is stable across both load
conditions: 56 to 64 ms of CPU packed into a 58 to 69 ms cadence is 80 to 95 per
cent of one core, against a budget of 10 per cent. Closing that needs roughly
another order of magnitude, which candidate restriction alone (plausibly two to
four times) will not deliver. The remaining path is collapsing the per-cell Python
loop so every cell in a row is scored against all its candidates in one operation.
That was not prototyped and carries no measured number, which is the right place
to leave it rather than guess.

Design consequence worth taking seriously before optimising further: the ring does
not actually need the coordinate stack at high rate. Facing dominates its motion,
so one row at 10 Hz plus the full block occasionally is the shape of the answer,
and the honest alternative to chasing another order of magnitude is to interpolate
the ring between slower samples rather than to sample everything faster.

- The poll loop already runs on its own thread with its own event loop
  (v4.9.0.15), so this is a constant, not a redesign.
- Position and facing do NOT need the same rate: facing dominates ring motion,
  position changes slowly. Sample CamDir fast, the full zone stack less often.

Acceptance:

1. Ring updates at 10 Hz or better with a measured CPU cost under 10% of one
   core.
2. No LLM calls during steady-state navigation.

### Phase 4: standalone overlay, DONE 2026-07-28, ahead of Phases 1 to 3

Taken first by user decision. The ring is now drawn in a click-through Win32
layered window over the game, anchored to the top centre of the screen
(`overlay_win32.py`, `ring_overlay.py`, v4.9.0.20; see Devlog for the evidence).

The precedent that won was not `wingman-player` but Wingman's own
`hud_server/overlay/overlay.py`, which does exactly this inside the frozen
process. That also sidesteps the blocker a standalone distributable would have
inherited: the Diftic GitHub account is shadow-hidden, so any new download would
be undeliverable to other users.

This changes what Phases 1 to 3 are worth rather than what they are. The surface
now updates at 30 fps while its input arrives every 5 seconds, so the ring is
smooth between stale fixes: the sample rate is the only thing still standing
between here and a usable instrument.

## 5. Out of scope

- Replacing Vision AI anywhere except the overlay read. The Vision skill and any
  other use stay as they are.
- A general-purpose OCR. This is one fixed font, one fixed position, roughly
  twelve glyph shapes. Resist generalising it.
- Removing the confabulation defences before the reader is the sole path. They
  cost nothing while both paths exist.

## 6. Open dependency, tracked separately

Direction in the SYSTEM frame is NOT calibrated. Measured 108.7 degrees out
against a known in-game marker on 2026-07-26, so deep-space guidance currently
reports distance only, gated by `navigation.SPACE_DIRECTION_CALIBRATED`. This is
independent of the OCR work: the reader changes HOW the numbers arrive, not what
the convention means. Calibration needs two or three frames with the target
marker centred on the crosshair, which yields exact CamDir plus known-direction
pairs.

## 7. Risks

- **Font or overlay changes between game patches.** The reader must fail closed
  (refuse, and say so once) rather than misread. A patch that moves the overlay
  should degrade to the Vision fallback, not to wrong coordinates.
- **Anti-aliasing over bright backgrounds.** The corpus includes a dawn-sky frame
  where the white text washed out; that case must be in the accuracy measurement,
  not discovered later.
- **My own validation habit.** Three separate times this session a passing test
  encoded my expectation rather than reality, and once a diagnostic used a
  channel that reached no log. For this work: validate against the labelled
  corpus, state the accuracy as a measured number, and prove any probe emits
  before trusting its silence.

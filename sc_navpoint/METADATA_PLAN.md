# NavPoint metadata plan: stop the VisionAI pre-activation, align the record with local OCR only

Planning agent. Revised 2026-08-02 after the user's instruction that there is no
Vision at all, only local OCR. That instruction supersedes the 2026-08-02 router
decision, and the skill's own records now say so: the operative entry is
`TODO.md:26` and `Devlog.md:3`, with the router marked SUPERSEDED at `TODO.md:68`,
`Devlog.md:102`, `ledger/LEDGER.md:177` and `ledger/REFUTED.md:167-169`. All file
citations in this document were re-verified against those updated records. See
section 10.

No code was written and no file was changed to produce this document. Everything
was verified against the dev tree, the live 2.1.1 tree at
`D:\PycharmProjects\wingman-ai-live`, the AppData install, and `Laura.yaml`.
Verification notes are inline so a validator can re-check without repeating the
search.

---

## 0. The mechanism, which decides what this plan can and cannot fix

Verified in `D:\PycharmProjects\wingman-ai-live\services\skill_registry.py`:

- `SkillManifest.from_skill` (`:83`) takes `description` from
  `skill.config.description.en`.
- `get_discovery_description` (`:97-113`) builds
  `description + ". Keywords: " + discovery_keywords + " [tags]"`.
- `get_meta_tools` (`:312-354`) concatenates that string for EVERY discoverable
  skill into the single `activate_skill` tool description, and `activate_skill`
  takes exactly one `skill_name` from an enum.

And in `D:\PycharmProjects\wingman-ai-live\wingmen\open_ai_wingman.py:1556-1574`,
`get_context` includes a skill's `prompt` only `if skill.name in
active_skill_names`.

**Consequence.** At the moment the model chose between VisionAI and SC_NavPoint,
the only NavPoint text it had ever seen was the description, the keywords and the
tags. The prompt had not been injected and cannot have influenced the choice.

- The description fix is the entire lever on the misfire.
- The prompt fix is correctness hygiene for behaviour AFTER activation. It cannot
  prevent a VisionAI pre-activation and this plan does not claim it will.
- NavPoint's description sits in that concatenated block next to VisionAI's own
  line and currently says "via Vision AI", which is a semantic bridge to the
  adjacent enum value. Removing it is the fix.

VisionAI's competing line, from
`D:\PycharmProjects\wingman-ai-live\skills\vision_ai\default_config.yaml`:
`"Screen vision - analyse what's on your screen, see images, read text, describe
visual content."` with keywords including `OCR`, `screen capture`, `text
recognition`, `what's on my screen`. Its `name:` is `VisionAI`, which is the exact
enum value, so naming it in NavPoint's description targets one enum member rather
than adding vocabulary.

---

## 1. What I found wrong in the direction-change message

Two understatements, one instruction that conflicts with its own stated principle,
and one correction to my own previous draft.

### 1.1 My previous draft's section 1.1 is VOID

I previously argued that `overlay_reader.py:26`, `overlay_fields.py:358` and
`:434` were correct and should be left alone. Under the router decision they were.
Under the no-Vision instruction they are wrong. They are in the fix list below.

### 1.2 UNDERSTATEMENT: scanner.py's Vision code is not idle, the test suite runs on it

The message says "None of it is called from main.py". That is true and I verified
it: `main.py` touches `NavPointScanner()` (`:139`), `parse_payload` (`:371`) and
`last_reject_reason` (`:377`, `:407`, `:981`), and nothing else.

But the implication that the code is therefore inert is wrong. Measured call sites
outside `release_version/`:

| Vision-facing member | Called by |
|---|---|
| `_parse_json_response` | about 30 assertions across `tests/test_scanner.py`, `tests/test_scanner_echo.py`, `tests/test_plausibility.py`, `tests/test_pos_raw_units.py`, `tests/test_space_waypoints.py` |
| `parse_completion` | `tests/test_scanner.py` (4), `tests/test_server_change.py:126`, plus docstring references at `navigation.py:408` and `:491` |
| `_detail_crop` | `tests/test_plausibility.py` (5) |

The entanglement is worse than a count suggests. Those tests are not Vision tests.
`test_pos_raw_units.py` and `test_space_waypoints.py` exercise the unit-suffix
requirement and the space-frame rules, and `test_plausibility.py` exercises the
plausibility gate. All of them are guards that are STILL LIVE for the local
reader, and the tests reach them through `_parse_json_response` because that is
the entry point that builds the payload dict. `scanner.py:478` says so in its own
comment: `parse_payload` was "Split out of `_parse_json_response` so the LOCAL
overlay reader can feed" it.

So stripping the Vision half does not remove dead weight. It removes the test
harness's entry point into logic the skill still depends on, and it would break a
large fraction of the 536-test suite. This makes the "do not strip" answer much
stronger than the message assumed. See OQ-5.

### 1.3 UNDERSTATEMENT: there is no git recovery for the current scanner.py

The message says stripping is "irreversible without git recovery" and that the
skill has only two commits. The commits are right (`94546d8`, `da00a22`), but git
recovery does not exist here in the sense implied:

- `scanner.py` IS tracked, but `HEAD`'s copy is **196 lines** against **646**
  today. `HEAD` is the 4.8.0.0 version alignment commit. Recovering from git would
  return a file predating the entire 4.9 line, not the current one.
- `overlay_reader.py`, `overlay_fields.py` and `ring_overlay.py` are **entirely
  untracked**. The whole local reader has no git protection at all right now.

So the accurate statement is: a strip of `scanner.py` is **unrecoverable**, full
stop, unless someone commits or copies the file first. That is a stronger reason
not to do it, and it is also a standing risk to the reader files that has nothing
to do with this plan. Flagged as R7.

### 1.4 Your instruction in point 3 conflicts with the principle you gave with it

You wrote: leave the local-only comments alone except where they cite the
2026-07-31 decision by date. And you gave the reason: "a comment should state what
the code does, not adjudicate which decision won."

Those point different ways. `main.py:85` ("Since Vision was removed this is the
only way a refusal is ever visible"), `main.py:647` ("with Vision gone"),
`ring_overlay.py:77` and `:445` all adjudicate without citing a date. Under your
principle they should go; under your instruction they stay.

**I have followed the instruction.** Only the date-citing ones are in the plan,
plus one borderline case argued below. My recommendation to drop the rest of the
clauses is OQ-2, not a unilateral edit, because the Vision question has now been
decided three times in three days and a planner quietly widening scope on that
question is the wrong instinct.

The borderline case I did include: `main.py:286` says "now that Vision is **being
removed**". That is present progressive. It describes a migration in progress, and
there is no migration: nothing is being removed, and per OQ-5 nothing should be.
It is not a decision-adjudication clause, it is a status claim that is not true of
anything. Fixing it is C2. Say the word and I will drop it.

### 1.5 Everything else verified

- `TODO.md:513-516` confirmed verbatim, including "Do this LAST; it is the
  irreversible step".
- The two-layer merge: `wingmen/wingman.py:274-283` and `:398-405` copy exactly
  `custom_properties` and `prompt`. `description` and `discovery_keywords` are
  never copied, so `default_config.yaml` governs both.
- `save_wingman_config` keeps `prompt` and `discovery_keywords` on mere presence:
  `services/config_manager.py:911-938`.
- Three `default_config.yaml` copies byte-identical,
  `md5 = 70855a05e45be65f25fda02c77a189ea`.
- Version `4.9.0.22` in `__init__.py`, `release_version/__init__.py`,
  `skill_installer_config.json`, `main.py:4`, `main.py:73`.
- Six custom properties, matching one-to-one between `default_config.yaml:42-72`
  and `Laura.yaml:811-823`: `display`, `poll_interval`, `arrival_alert_distance`,
  `arrival_stop_distance`, `overlay_size`, `space_direction_test`.
- `Laura.yaml` prompt occupies lines 703 to 781 inclusive. Line 702 is
  `- module: skills.sc_navpoint.main`, line 782 is `  discovery_keywords:`.
- VisionAI is in Laura's `discoverable_skills` (`Laura.yaml:828`), same enum as
  SC_NavPoint (`:832`).
- No `@tool` description in `main.py` names a reader. `main.py:1170-1171` says
  only "Captures and analyzes the screen to extract coordinates from the
  r_displayinfo overlay". This matches `SUPERVISION.md`'s own REFUTED verdict on
  the same PM claim.

**Unrelated observation, not planned work:** `skills/sc_navpoint/` currently holds
about twelve junk untracked files from shell redirect accidents (`'`, `(1`, `0`,
`0.5,+`, `18`, `4.9.0.22`, `8s}`, `False`, `None`, `block_columns`, `captured`,
`dict`). Same pattern as the ones deleted from `satisfactory_assistant`. They
matter here only because they make "no new untracked files" unusable as a bare
acceptance check, so AC-10 compares against a captured baseline instead.

### 1.6 Carried over from the first draft: `preserve_on_update`

`skill_installer_config.json:22-24` declares `"preserve_on_update":
["default_config.yaml"]`. No consumer exists anywhere in the repo (searched all
`.py`, `.json`, `.bat`, `.md`; the only hits are seven skills declaring the same
key). Today `install.bat`'s `robocopy ... /E /IS /IT /XF install.bat
TESTER_README.md` DOES overwrite `default_config.yaml`, so the fix propagates.

The hazard is latent: a future installer honouring that declaration would never
deliver a description fix, and the description is the only lever on skill
selection. OQ-7.

Also verified: `install.bat` overwriting `default_config.yaml` does not clobber
user settings. Custom property VALUES live in `Laura.yaml:811-823`.

---

## 2. Governing principle for the text

Three decisions on Vision in three days. The cheapest defence is not a better
dated claim. It is to write sentences that do not depend on the question.

Where a sentence works without its Vision clause, the clause goes and nothing
replaces it. Where the subject genuinely IS the reader architecture, the text
states what the code does now, in the present tense, with no decision history and
no promise about the future. The single exception is the `scanner.py` class
docstring, which gets a deliberately explicit retention note, because its job is
to stop the next agent deleting code that `TODO.md` says must not be deleted yet.

**No new text in this plan promises a fallback of any kind.**

---

## 3. Change list

| # | File | What | Ships the fix? |
|---|---|---|---|
| M1 | `default_config.yaml:11` | description | **Yes, this is the fix** |
| M2 | `default_config.yaml:92-95` | prompt, Prerequisites | No, hygiene |
| M3 | `default_config.yaml:98-102` | prompt, `mark_location` bullet | No, hygiene |
| M4 | `default_config.yaml:130` | prompt, overlay-missing rule | CLEARED 2026-08-02, may land |
| M5 | `Laura.yaml:703-781` | delete the `prompt:` key | Enables M2/M3/M4 to take effect |
| V1 | `main.py:214-219` | "falls through to the Vision path below" | Record |
| V2 | `overlay_reader.py:24-26` | "Vision stays the fallback" | Record |
| V3 | `scanner.py:222-223` | class docstring, plus retention note | Record, and a guard |
| V4 | `overlay_fields.py:358-359` | "costs a Vision fallback" | Record |
| V5 | `overlay_fields.py:428-435` | "unlike on the Vision path", "costs a Vision fallback" | Record |
| C2 | `main.py:284-287` | "now that Vision is being removed" | Record, borderline, see 1.4 |
| C3 | `main.py:382-392` | dated 2026-07-31 justification | Record |
| C8 | `navigation.py:477-481` | dated 2026-07-31 justification | Record |
| P1 | run `update_release.py` | dev to `release_version/` | Propagation |
| P2 | run `release_version/install.bat` | `release_version/` to live | Propagation |

---

### M1. The description. `default_config.yaml:10-11`

The only string the model reads before it decides which skill to activate.

**BEFORE** (line 11, one physical line):

```yaml
description:
  en: "Save, log or mark the player's OWN current position as a personal waypoint in Star Citizen, anywhere: in open space or on a planet or moon surface. Then navigate back to it later with distance and direction. Reads the player's coordinates from the r_displayinfo overlay via Vision AI. USE THIS whenever the player wants their current position remembered ('log this spot', 'save my location', 'mark where I am', 'drop a pin') or wants to return to a place they marked earlier ('navigate back to X', 'take me back to X'). Do NOT use the route planner for these: that plans between named in-game destinations and knows nothing about the player's own saved waypoints. Do NOT answer with a HUD information card either: that displays text and stores no position."
```

**AFTER** (line 11, one physical line):

```yaml
description:
  en: "Save, log or mark the player's OWN current position as a personal waypoint in Star Citizen, anywhere: in open space or on a planet or moon surface. Then navigate back to it later with distance and direction. Every NavPoint tool that needs a position captures and reads the game screen itself, inside its own call, and no NavPoint tool accepts a position argument. Do NOT activate the VisionAI skill before a save, log or mark request: it cannot pass a position to NavPoint and only adds a wasted screen capture. USE THIS whenever the player wants their current position remembered ('log this spot', 'save my location', 'mark where I am', 'drop a pin') or wants to return to a place they marked earlier ('navigate back to X', 'take me back to X'). Do NOT use the route planner for these: that plans between named in-game destinations and knows nothing about the player's own saved waypoints. Do NOT answer with a HUD information card either: that displays text and stores no position."
```

Changed:

- Removed `Reads the player's coordinates from the r_displayinfo overlay via Vision AI.`
- Added a self-sufficiency sentence and an explicit negative naming `VisionAI`.
- Untouched: the opening, USE THIS, the route-planner disambiguation, the HUD-card
  disambiguation.

Naming `VisionAI` rather than the words "vision", "OCR" or "screenshot" is
deliberate and is a better answer than either option I offered before the
direction change. `VisionAI` is the literal enum value in the same
`activate_skill` tool description (`Laura.yaml:828`, and `name: VisionAI` in its
own `default_config.yaml`), so the instruction targets exactly one enum member.
Using the generic words would have pushed VisionAI's vocabulary into NavPoint's
discovery string, risking a pull in the opposite direction. This wording carries
none of that risk, which retires the concern behind the old OQ-1.

Two claims of fact in the new text, both verified: no NavPoint tool takes a
position argument (checked against all eight `@tool` signatures in `main.py`), and
VisionAI cannot pass a position to NavPoint (it returns free text and there is no
argument for it to arrive in).

No fallback is promised or implied.

### M2. Prompt, Prerequisites. `default_config.yaml:92-95`

**BEFORE** (inside `prompt: |`, two-space indent):

```
  **Prerequisites:** The player must have r_displayinfo 2 (or higher) active in game.
  Enable it: open the console with the tilde key (~) and type: r_displayinfo 2.
  The player must type this personally: this skill never sends input to the game,
  so it cannot open the console or enable the overlay for them.
```

**AFTER:**

```
  **Prerequisites:** The player must have r_displayinfo 2 (or higher) active in game.
  Enable it: open the console with the tilde key (~) and type: r_displayinfo 2.
  The player must type this personally: this skill never sends input to the game,
  so it cannot open the console or enable the overlay for them.
  Every NavPoint tool that needs a position captures and reads the screen itself,
  inside the tool call. Never use the VisionAI skill or any other skill to look at
  the screen for NavPoint, and never try to supply coordinates: no NavPoint tool
  takes a position argument.
```

### M3. Prompt, `mark_location` bullet. `default_config.yaml:98-102`

**BEFORE:**

```
  - `mark_location(name)`: Capture the current position and save it as a named
    waypoint, on a surface OR in open space. Extracts coordinates from the
    r_displayinfo overlay via Vision AI. Refused only when neither frame is
    readable. If no name provided, use a default like "Location 1" and ask the
    player for a better name.
```

**AFTER:**

```
  - `mark_location(name)`: Capture the current position and save it as a named
    waypoint, on a surface OR in open space. It captures and reads the
    r_displayinfo overlay itself and takes no position argument. Refused only
    when neither frame is readable. If no name provided, use a default like
    "Location 1" and ask the player for a better name.
```

### M4. Prompt, the overlay-missing rule. `default_config.yaml:130`

**CLEARED 2026-08-02 by `plan-capture`. It may land with the rest of the plan.**

The assumption this change rested on is now confirmed rather than assumed.
`plan-capture` records it as their CONFIRMATION C1: `KIND_ABSENT` means
`overlay_is_present(frame)` returned False at `main.py:330`, and it is the ONLY
failure kind carrying the `r_displayinfo` hint. Present-but-unreadable is five
separate kinds, none of which carries it. Their acceptance criteria 3 and 4 check
that mechanically: the hint is present if and only if the kind is absent.

So the phrase `NOT PRESENT on screen` below has a real failure class behind it,
and the "different failure" clause has five.

**BEFORE** (line 130, one physical line):

```
  - Player asks to "enable position overlay", "activate r_displayinfo", "turn on position tracking", or a NavPoint tool reports the overlay is missing → tell the player to open the console with the tilde key (~) and type: r_displayinfo 2. This skill has no tool to enable the overlay and must never claim it can; the player types it manually.
```

**AFTER** (line 130, one physical line):

```
  - Player asks to "enable position overlay", "activate r_displayinfo", "turn on position tracking", or a NavPoint tool reports that the overlay is NOT PRESENT on screen → tell the player to open the console with the tilde key (~) and type: r_displayinfo 2. This skill has no tool to enable the overlay and must never claim it can; the player types it manually. If a tool reports a DIFFERENT failure, for example that the overlay is present but could not be read, do NOT give this command: relay what the tool actually said.
```

Line `:131` (relay the `hint` verbatim) unchanged. It is correct and reinforces
whatever failure messages `plan-capture` defines.

**Why this matters more without a fallback:** a refused frame is now a failed
capture rather than a routed one, so the remedy message is all the player gets.
`SUPERVISION.md:42` records the present state, that `mark_location` collapses every
failure into the `r_displayinfo 2` hint at `main.py:1191-1199`. That is the bug
this line stops the model amplifying.

Constraint 2 holds in both versions: the player types the command themselves and
the skill "must never claim it can".

### V1. `main.py:214-219`

**BEFORE:**

```python
    def _local_reader(self):
        """The deterministic overlay reader, loaded once.

        The glyph bank is about 90 KB and stacking the templates is not free, so
        this is built on first use and kept. Returns None when the bank or its
        dependencies are missing, which falls through to the Vision path below.
        """
```

**AFTER:**

```python
    def _local_reader(self):
        """The deterministic overlay reader, loaded once.

        The glyph bank is about 90 KB and stacking the templates is not free, so
        this is built on first use and kept. Returns None when the bank or its
        dependencies are missing, and there is nothing to fall through to: the
        capture fails and the ring says so.
        """
```

### V2. `overlay_reader.py:24-26`

`overlay_reader.py:3` ("Replaces the Vision AI call as the position source") is
true and stable. It is NOT changed.

**BEFORE:**

```python
WHERE IT WORKS: smooth dark backgrounds decode at 100 per cent. Bright or
structured backgrounds are REFUSED nearly wholesale, which is the design
working: Vision stays the fallback for those scenes rather than being retired.
```

**AFTER:**

```python
WHERE IT WORKS: smooth dark backgrounds decode at 100 per cent. Bright or
structured backgrounds are REFUSED nearly wholesale. Refusing is the design
working, but nothing runs behind it: a refused frame is a failed capture, so
this reader's coverage IS the skill's availability.
```

The last clause is not a new claim. `TODO.md:526` already reaches it: "with no
fallback, availability becomes usability".

### V3. `scanner.py:222-223`

The one place a longer docstring earns its length. Its job is to stop the next
agent deleting the code, which is the failure `TODO.md:516` exists to prevent and
which section 1.2 shows would also break the test suite.

**BEFORE:**

```python
class NavPointScanner:
    """Captures the screen and provides message data for position extraction via Vision AI."""
```

**AFTER:**

```python
class NavPointScanner:
    """Validates and normalises overlay position payloads.

    `parse_payload` is the live entry point: the local reader feeds it, and it
    applies the plausibility gate, the unit-suffix requirement and the Root
    agreement check.

    The Vision-facing half (`_EXTRACTION_PROMPT`, `capture_screen_b64`,
    `build_extraction_messages`, `parse_completion`) is NOT called by `main.py`.
    It is retained deliberately, not by neglect: `TODO.md` orders "strip the
    Vision path ... Do this LAST; it is the irreversible step", and much of the
    test suite reaches the guards above through `_parse_json_response`. Do not
    delete any of it without an explicit decision.
    """
```

### V4. `overlay_fields.py:358-359`

**BEFORE:**

```python
    # Refusing here costs a Vision fallback. It is deliberately stricter than
    # the row-level gate, which only proves each row it trusts.
```

**AFTER:**

```python
    # Refusing here costs the capture outright, since nothing runs after a
    # refusal. It is deliberately stricter than the row-level gate, which only
    # proves each row it trusts.
```

### V5. `overlay_fields.py:428-435`

**BEFORE:**

```python
    # THE ROOT LINE IS MANDATORY HERE, unlike on the Vision path. The scanner's
    # agreement check runs only `if root is not None`, which is right for a
    # model that can silently omit a field, and wrong for a deterministic
    # reader: an absent Root line means an UNREADABLE Root line, which is
    # exactly the fail-closed case. Without it a payload ships with no
    # independent cross-check at all, and 3 of 16 usable frames measured on
    # 2026-07-31 were in that state. Refusing costs a Vision fallback; emitting
    # an unverified coordinate costs whatever it is wrong by.
```

**AFTER:**

```python
    # THE ROOT LINE IS MANDATORY HERE, unlike in `scanner.parse_payload`, whose
    # agreement check runs only `if root is not None`. That was right for a
    # model that can silently omit a field, and it is wrong for a deterministic
    # reader: an absent Root line means an UNREADABLE Root line, which is
    # exactly the fail-closed case. Without it a payload ships with no
    # independent cross-check at all, and 3 of 16 usable frames measured on
    # 2026-07-31 were in that state. Refusing costs the capture; emitting an
    # unverified coordinate costs whatever it is wrong by.
```

The 2026-07-31 date here is a MEASUREMENT date, not a decision citation. It stays.

### C2. `main.py:284-287`. Borderline when written, CONFIRMED 2026-08-02

Raised in 1.4 as my judgement call and confirmed by the supervisor: the present
progressive is a status claim untrue of anything, not a decision adjudication, so
it falls on the fixable side of the line. C2 proceeds.

**BEFORE:**

```python
        decodes identically). Sets `self._reader_state` to what the ring should
        say, which is the only channel that reports a refusal now that Vision is
        being removed. The caller retries, so the state the ring ends up showing
        is the last attempt's, which is the one the player's mark rests on.
```

**AFTER:**

```python
        decodes identically). Sets `self._reader_state` to what the ring should
        say, which is the only channel that reports a refusal. The caller
        retries, so the state the ring ends up showing is the last attempt's,
        which is the one the player's mark rests on.
```

### C3. `main.py:382-392`

Only the dated middle paragraph goes. "NO model in the loop" is true. "costs no
tokens" is true again and stable under no-Vision, so it stays.

**BEFORE:**

```python
    async def _capture_position(self, attempts: int = 1) -> dict | None:
        """Capture the screen and extract position, with NO model in the loop.

        Vision AI was removed by decision on 2026-07-31 (Devlog of that date):
        every confabulation this skill has suffered was a language model reading
        digits, so the deterministic reader is the only reader. A frame it
        cannot read produces None and a ring message, never a guess and never a
        fallback.

        Still `async` because every caller awaits it and the signature is the
        seam; the work underneath is synchronous and costs no tokens.
```

**AFTER:**

```python
    async def _capture_position(self, attempts: int = 1) -> dict | None:
        """Capture the screen and extract position, with NO model in the loop.

        The deterministic reader is the only reader, because every confabulation
        this skill has suffered was a language model reading digits. A frame it
        cannot read produces None and a ring message, never a guess and never a
        fallback: nothing runs after a refusal, so this reader's coverage IS the
        skill's availability.

        Still `async` because every caller awaits it and the signature is the
        seam; the work underneath is synchronous and costs no tokens.
```

### C8. `navigation.py:477-481`

**BEFORE:**

```python
    `ring_deflection` stays the single authority on whether a bubble may be
    drawn; this wraps it so the message can never contradict it. Since Vision
    was removed on 2026-07-31 the ring is the only channel that can tell the
    player why a fix is missing, so a refusal has to become visible here or it
    becomes invisible everywhere.
```

**AFTER:**

```python
    `ring_deflection` stays the single authority on whether a bubble may be
    drawn; this wraps it so the message can never contradict it. The ring is the
    only channel that can tell the player why a fix is missing, so a refusal has
    to become visible here or it becomes invisible everywhere.
```

---

## 4. Deliberate no-ops

**`main.py:85`, `main.py:647`, `main.py:990`, `ring_overlay.py:77`,
`ring_overlay.py:445`: NO CHANGE**, per your point 3. They adjudicate without
citing a date. See 1.4 and OQ-2.

**`main.py:645` ("The setting was removed on 2026-07-31 (user's call)"): NO
CHANGE.** It cites a date, but for the `overlay_enabled` property removal, which
is unrelated to the Vision question and still factual.

**`overlay_reader.py:3` ("Replaces the Vision AI call as the position source"): NO
CHANGE.** True and stable.

**`main.py:410-447` printr badges: not mine.** Two say "Vision AI" (`:411`,
`:419`). `plan-capture` owns them.

**`discovery_keywords` (`default_config.yaml:12-40`): NO CHANGE.** The 29 keywords
contain no vision, OCR or screenshot term, so they are not part of the misfire.
They are appended verbatim to the description in `get_discovery_description`, so
adding to them dilutes the description without adding a lever it does not already
have.

**`scanner.py`'s Vision machinery: NOT DELETED.** See OQ-5. V3 adds a docstring
arguing against deleting it.

**No new files**, so constraint 5 does not bite and neither
`skill_installer_config.json` nor `RELEASE_FILES` needs an entry. Both already
list every file this plan touches.

**No git commit.** Constraint 6.

**No version bump proposed.** OQ-6.

---

## 5. The `Laura.yaml` operation

Unchanged by the direction change. The only edit outside the repository,
explicitly authorised by the user. Backup first, no exceptions.

Target: `C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml`

### 5.1 Why the backup goes where it goes

`services/config_manager.py:446` enumerates wingmen with
`if filename.endswith(".yaml") and not filename.startswith(".")`. A backup named
`Laura.backup.yaml` in that directory would load as a SECOND wingman. Keep it out
of the scanned tree entirely.

**Backup path:**
`C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\backups\Laura.yaml.2026-08-02.bak`

Create `backups\` if absent. It sits above `2_1_1\configs\` and is never scanned.

### 5.2 Preconditions

1. **Wingman AI fully closed**, including ending `WingmanAiCore` in Task Manager
   if it stays in the tray. A running core can rewrite `Laura.yaml` on any
   settings save and silently undo the edit.
2. Confirm the file still has 849 lines and line 702 is
   `- module: skills.sc_navpoint.main`. If either differs, the file changed since
   this plan was written: STOP and re-locate the block by content, not line number.

### 5.3 The edit

Delete lines **703 to 781 inclusive**: the entire `prompt:` key and every
continuation line of its YAML-escaped scalar.

- Line 703 begins `  prompt: "You have access to a Star Citizen navigation assistant through the SC_NavPoint\`
- Line 781 ends `    repeat or re-issue them yourself.\n"`
- Lines 702 and 782 both SURVIVE.

Resulting shape:

```yaml
- module: skills.sc_navpoint.main
  discovery_keywords:
  - star citizen
  ...
  custom_properties:
  - id: display
    value: 1
  ...
```

The six custom properties at 811 to 823 are not to be disturbed (constraint 4).

### 5.4 Verification, before restarting the core

**V-A, the file parses and the entry survived:**

```
python -c "import yaml,io; p=r'C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml'; d=yaml.safe_load(io.open(p,encoding='utf-8')); s=[x for x in d['skills'] if x['module']=='skills.sc_navpoint.main'][0]; assert 'prompt' not in s, 'prompt still present'; ids=[q['id'] for q in s['custom_properties']]; assert ids==['display','poll_interval','arrival_alert_distance','arrival_stop_distance','overlay_size','space_direction_test'], ids; print('OK', sorted(s.keys()), len(d['skills']), 'skill entries')"
```

Expected: `OK ['custom_properties', 'discovery_keywords', 'module'] 2 skill entries`

The `2` matters. Only `skills.hud.main` and `skills.sc_navpoint.main` have saved
overrides; a drop to 1 means the NavPoint entry was destroyed, so restore the
backup.

**V-B, no orphaned custom property id.** This is the check that would have caught
the 2026-08-01 `overlay_enabled` incident before it killed the core four times. The
failure mode is a saved id with no definition in `default_config.yaml`, which
reaches Pydantic with no `name` and no `property_type`.

```
python -c "import yaml,io; base=r'D:\PycharmProjects\wingman-ai\skills\sc_navpoint\default_config.yaml'; live=r'C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml'; dflt={p['id'] for p in yaml.safe_load(io.open(base,encoding='utf-8'))['custom_properties']}; s=[x for x in yaml.safe_load(io.open(live,encoding='utf-8'))['skills'] if x['module']=='skills.sc_navpoint.main'][0]; saved={p['id'] for p in s['custom_properties']}; assert saved<=dflt, 'ORPHANED IDS: %s' % (saved-dflt); print('OK, no orphans;', len(saved), 'saved of', len(dflt), 'defined')"
```

Expected: `OK, no orphans; 6 saved of 6 defined`

**V-C, the diff is exactly the prompt key:**

```
diff "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\backups\Laura.yaml.2026-08-02.bak" "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml"
```

Expected: a single deletion hunk of 79 lines, no additions, no other hunks.

### 5.5 Then restart

Start Wingman AI. It must reach a running state with the Star Citizen config
loaded and NavPoint in Laura's skills. A Pydantic validation error at startup is
the 2026-08-01 signature: roll back immediately.

Once running, `default_config.yaml`'s prompt is what Layer 2 supplies, because
`wingman.py:282` copies the saved prompt only `if user_config.prompt` and there is
no longer one. The further fallback at `open_ai_wingman.py:1568` (auto-generate
from tool descriptions `if not prompt`) is not reached, since `default_config.yaml`
has a prompt.

### 5.6 Rollback

```
copy /Y "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\backups\Laura.yaml.2026-08-02.bak" "C:\Users\larse\AppData\Roaming\ShipBit\WingmanAI\2_1_1\configs\_Star Citizen\Laura.yaml"
```

Restart the core. That is the whole rollback: nothing else in this plan touches
anything outside the repo. Keep the backup afterwards. It is the only copy of the
frozen prompt text, and R2 means the situation can recur.

---

## 6. Acceptance criteria

Mechanically checkable without having read the reasoning.

### AC-1. No model-facing or user-facing string claims Vision

```
grep -rn -i "vision" skills/sc_navpoint/default_config.yaml skills/sc_navpoint/release_version/default_config.yaml "C:/Users/larse/AppData/Roaming/ShipBit/WingmanAI/custom_skills/sc_navpoint/default_config.yaml"
```

Expected: exactly one match per file, the `Do NOT activate the VisionAI skill`
sentence on line 11. No occurrence of `via Vision AI` anywhere.

### AC-2. The description carries the new negative instruction

`default_config.yaml:11` contains, verbatim:

```
Do NOT activate the VisionAI skill before a save, log or mark request
```

and

```
no NavPoint tool accepts a position argument
```

### AC-3. The description's surviving disambiguations are intact

`default_config.yaml:11` still contains all three of:

- `Do NOT use the route planner for these`
- `Do NOT answer with a HUD information card either`
- `USE THIS whenever the player wants their current position remembered`

### AC-4. No surviving text promises a fallback

```
grep -rn -i "fallback" skills/sc_navpoint/default_config.yaml
```

Expected: no matches.

```
grep -rn "Vision fallback" skills/sc_navpoint/overlay_fields.py
grep -rn "Vision path below" skills/sc_navpoint/main.py
grep -rn "Vision stays the fallback" skills/sc_navpoint/overlay_reader.py
```

All three: no matches.

### AC-5. The dated decision citations are gone

```
grep -rn "Vision AI was removed by decision" skills/sc_navpoint/main.py
grep -rn "Since Vision was removed on 2026-07-31" skills/sc_navpoint/navigation.py
grep -rn "now that Vision is" skills/sc_navpoint/main.py
```

All three: no matches.

### AC-6. The entries that must NOT have been touched are unchanged

Exactly one match each:

```
grep -n "Since Vision was removed this is the only way" skills/sc_navpoint/main.py
grep -n "with Vision gone" skills/sc_navpoint/main.py
grep -n "made the ring responsible" skills/sc_navpoint/main.py
grep -n "which is a normal condition since Vision was removed" skills/sc_navpoint/ring_overlay.py
grep -n "since Vision was removed this is the only channel" skills/sc_navpoint/ring_overlay.py
grep -n "The setting was removed on 2026-07-31" skills/sc_navpoint/main.py
grep -n "Replaces the Vision AI call as the position source" skills/sc_navpoint/overlay_reader.py
```

An implementer who also "fixed" these has exceeded the plan. Section 1.4 explains
why they were left to the supervisor.

### AC-7. scanner.py's Vision machinery still exists

```
grep -c "_EXTRACTION_PROMPT" skills/sc_navpoint/scanner.py
grep -n "def capture_screen_b64\|def build_extraction_messages\|def parse_completion\|def _parse_json_response\|def _detail_crop" skills/sc_navpoint/scanner.py
wc -l skills/sc_navpoint/scanner.py
```

Expected: `_EXTRACTION_PROMPT` present, all five defs present, line count 646 plus
only the net lines the V3 docstring adds. Any large drop means someone stripped the
Vision path against OQ-5.

The new docstring must carry the retention warning:

```
grep -n "it is the irreversible step" skills/sc_navpoint/scanner.py
```

Expected: one match.

### AC-8. Custom properties untouched

```
grep -c "^  - id: " skills/sc_navpoint/default_config.yaml
```

Expected: 6, ids in order `display`, `poll_interval`, `arrival_alert_distance`,
`arrival_stop_distance`, `overlay_size`, `space_direction_test`.

### AC-9. The three trees are consistent again

```
md5sum skills/sc_navpoint/default_config.yaml skills/sc_navpoint/release_version/default_config.yaml "C:/Users/larse/AppData/Roaming/ShipBit/WingmanAI/custom_skills/sc_navpoint/default_config.yaml"
```

All three equal, none equal to the pre-change `70855a05e45be65f25fda02c77a189ea`.
Repeat the equality check for `main.py`, `navigation.py`, `overlay_reader.py`,
`overlay_fields.py` and `scanner.py`.

### AC-10. No new files, no manifest changes, nothing new outside `skills/`

Capture a baseline BEFORE any edit, because the skill directory already holds about
a dozen junk untracked files (see 1.5):

```
git status --short > <scratchpad>/baseline.txt      # before
git status --short > <scratchpad>/after.txt         # after
diff <scratchpad>/baseline.txt <scratchpad>/after.txt
```

Expected: no new `??` lines, no new lines outside `skills/sc_navpoint/`, and
`skill_installer_config.json` and `update_release.py` absent from the diff. Note
`services/config_manager.py` is already modified from earlier unrelated work; the
check is that this change adds nothing NEW outside `skills/`.

### AC-11. `Laura.yaml`

V-A, V-B and V-C from 5.4 all pass.

### AC-12. The test suite still passes

```
python -m pytest skills/sc_navpoint/tests -q
```

536 tests per `Devlog.md:113`. No test asserts on any string this plan changes, so
count and outcome should be unchanged. **AC-12 is also the tripwire for OQ-5:** a
drop in collected tests means someone deleted `scanner.py` code the suite depends
on. If a test fails, the implementation deviated: fix the implementation, never the
test.

### AC-13. M4 landed

Added when M4 was cleared on 2026-08-02. `default_config.yaml:130` contains, verbatim:

```
a NavPoint tool reports that the overlay is NOT PRESENT on screen
```

and

```
If a tool reports a DIFFERENT failure, for example that the overlay is present but could not be read, do NOT give this command: relay what the tool actually said.
```

and no longer contains `reports the overlay is missing`.

Line `:131` is unchanged and still contains `relay the hint's key names and console
commands to the player verbatim`.

Constraint 2 check, on the same line: it still contains `the player types it
manually` and `must never claim it can`, and NavPoint still sends no input to the
game.

### BLOCKED ON USER, live session required

**BU-1, the core starts.** After the `Laura.yaml` edit, launch Wingman AI and
confirm it reaches a running state with `_Star Citizen` loaded and NavPoint in
Laura's skill list. A Pydantic `name`/`property_type` error means roll back per
5.6. **User action:** launch Wingman AI, confirm no error banner, confirm NavPoint
appears under Laura's Skills.

**BU-2, the misfire is gone.** Say to Laura: *"mark this location"*. Check
`wingman-core.log` for `activate_skill` calls in that turn. **PASS** is a single
call with `skill_name: SC_NavPoint`. **FAIL** is `VisionAI` appearing at all. This
is the criterion the plan exists for and no file check substitutes for it. **User
action:** issue that utterance, send the surrounding core-log lines.

**BU-3, no collision the other way.** Say: *"what's on my screen"*. Expected:
`VisionAI` activates, `SC_NavPoint` does not. Lower risk than under my earlier
generic wording, because M1 names the enum value rather than adding vision
vocabulary, but still worth one utterance. **User action:** issue it, report which
skill activated.

**BU-4, the default prompt is in force.** After a session with the core running,
`Laura.yaml` should still have no `prompt:` key under `skills.sc_navpoint.main`.
**User action:** close Wingman AI, re-run V-A.

**BU-2 tests skill SELECTION only.** It does not test whether the capture then
succeeds. Per `SUPERVISION.md:26-28` the skill has produced no successful field
capture since 2026-07-31 22:07:10, seven attempts over two days. So a PASS on BU-2
alongside a failed mark is the expected outcome right now and is NOT a failure of
this plan. That failure is `plan-capture`'s subject.

---

## 7. Ordering and dependencies

**The metadata change lands FIRST and can ship on its own.**

The description is the only lever on skill selection, the misfire is live, and the
change is text-only with no runtime code path. It does not depend on anything
`plan-capture` produces.

The `Laura.yaml` deletion must precede ANY prompt edit, in this plan or the capture
plan. Until it is done, every prompt edit in `default_config.yaml` is a runtime
no-op. Doing it early unblocks the capture plan's prompt-side work as a side
effect, which is a reason to do it first rather than to bundle it.

The V-set and C-set corrections are self-contained and describe the operative
design, so they do not wait.

**The carve-out is gone.** M4 was held pending `plan-capture` and was cleared on
2026-08-02 (OQ-3), so the plan lands as one unit with no part waiting on another
agent. The metadata change still does not DEPEND on the capture change: it can land
before, after, or alongside it.

**`main.py:218` and `scanner.py:223` are now MINE (V1 and V3).** In my previous
draft I deferred both to `plan-capture` because their correct wording depended on a
router design. There is no router, so that reason is void and your reassignment is
right.

**Propagation runs last, once per landing.** Order fixed by constraint 3:

1. Edit the DEV TREE only: `skills/sc_navpoint/`.
2. `python skills/sc_navpoint/update_release.py`. Verified: `RELEASE_FILES` already
   lists `default_config.yaml`, `main.py`, `navigation.py`, `overlay_fields.py`,
   `overlay_reader.py`, `ring_overlay.py` and `scanner.py`, so no manifest edit is
   needed. It deletes and recreates `release_version/`, so any hand-edit there is
   destroyed, which is the intended safeguard.
3. `skills/sc_navpoint/release_version/install.bat` robocopies into
   `AppData\Roaming\ShipBit\WingmanAI\custom_skills\sc_navpoint\`. It excludes only
   `install.bat` and `TESTER_README.md`, so `default_config.yaml` IS overwritten,
   which is what this change needs.
4. Wingman AI fully closed for step 3, restarted after.

**If the capture change lands after this one and also edits any of these files,
steps 2 to 4 must be re-run**, or the live install keeps the intermediate version
and AC-9 fails silently.

---

## 8. Risks

**R1. Deleting 79 lines from `Laura.yaml` destroys the skill entry or breaks the
file.** Detection: V-A, under a second, no Wingman AI needed. Consequence if
missed: core fails to start, or NavPoint silently loses its custom property values.

**R2. The next settings save re-freezes the prompt into `Laura.yaml`.**
`config_manager.py:918-923` keeps `prompt` whenever merely present, with no
comparison against defaults. The prompt reaching the save path will be the
CORRECTED one, so the immediate outcome is benign. The lasting consequence is that
the repo silently stops being the source of truth again and a future
`default_config.yaml` prompt edit becomes a no-op with no error. Detection: re-run
V-A after any settings save. **This belongs on the NavPoint release checklist, not
only in this plan.** I have not added it there, because that is a file edit outside
this document.

**R3. An implementer strips `scanner.py`'s Vision code while "cleaning up" under
the no-Vision instruction.** The highest-consequence risk in the plan, because per
1.3 it is unrecoverable. Three defences: V3's docstring says do not, OQ-5 asks the
supervisor explicitly, and AC-7 plus AC-12 detect it. Consequence if missed:
permanent loss, plus a broken test suite.

**R4. An implementer also "fixes" the five comments section 4 protects**, because
the original brief listed them as stale. Detection: AC-6, seven greps.

**R5. The description's new sentence pulls genuine VisionAI requests toward
NavPoint.** Much lower than under my earlier generic wording, since M1 names the
enum value instead of using vision vocabulary. Detection: BU-3, one utterance.

**R6. Wingman AI is running during the `Laura.yaml` edit and overwrites it.**
Detection: V-C, run immediately after the edit. Precondition 1 in 5.2 prevents it.

**R7. The entire local reader is untracked and unbacked.** Not caused by this plan
and not fixable within it (constraint 6 forbids committing), but `overlay_reader.py`,
`overlay_fields.py` and `ring_overlay.py` have no git protection, and `scanner.py`'s
tracked copy is 196 lines against 646 today. Any accident in the skill directory is
currently unrecoverable. Detection: `git status --short skills/sc_navpoint`, which
already shows it. Raised because it is the user's call whether to commit.

**R8. `preserve_on_update` makes this fix unpropagatable by a future installer.**
Latent, no consumer today. Detection:
`grep -rn "preserve_on_update" --include=*.py .` returning a hit means a consumer
now exists. OQ-7.

---

## 9. Open questions for the supervisor

### OQ-5 first, because it is the irreversible one

**Should `scanner.py`'s Vision machinery be stripped, now that there is no Vision
at all?**

**My recommendation: NO, and not soon. Keep it, and let V3's docstring say why.**

In order of weight:

1. **It is unrecoverable.** Section 1.3: `scanner.py` is tracked but `HEAD` holds a
   196-line 4.8.0.0 file against 646 today, so git restores nothing usable. Nothing
   else in this plan is irreversible; this is.
2. **It is not dead code.** Section 1.2: about 40 test call sites across five test
   files reach through `_parse_json_response`, `parse_completion` and
   `_detail_crop`, and several of those tests exercise guards STILL LIVE for the
   local reader. Stripping breaks a large fraction of 536 tests and removes the
   harness's entry point into logic the skill depends on. Re-homing those tests onto
   `parse_payload` is real work and is not a metadata task.
3. **Its deferral is the only reason two reversals cost nothing.**
   `TODO.md:513-516` ordered it last on purpose, and `ledger/REFUTED.md:184-186`
   records that the ordering "saved the project a rebuild". The question has been
   decided three times in three days. Spending the option on the third answer, hours
   after the second, is the one move that cannot be undone if there is a fourth.
4. It costs nothing to keep. It is not imported at runtime beyond the class
   `main.py` already constructs, and it adds no tokens.

**If the user wants it gone anyway**, the safe sequence is: commit or archive
`scanner.py` first so recovery exists, then re-home the affected tests onto
`parse_payload`, then strip, as a separate change with its own plan. Not as part of
a metadata edit.

### OQ-1. Resolved, no longer a question

Your instruction to name the VisionAI skill explicitly settles the wording question
I raised before the direction change, and settles it better than either option I
offered. `VisionAI` is the literal enum value, so the instruction targets one enum
member without pushing vision vocabulary into NavPoint's discovery string. M1 is
written that way. Recorded so the earlier version of this document is not consulted.

### OQ-2. RESOLVED 2026-08-02: leave them

**Supervisor's decision: LEAVE THEM.** The clauses are currently true, the churn is
not worth it while the decision has moved three times in three days, and AC-6
protecting them is the correct shape. The principle in 1.4 stands as a principle
and is deliberately not applied here.

My recommendation is kept below, unchanged, so a future session can revisit it
without re-deriving the argument. It is a recommendation on the record, not a
pending decision.

#### The recommendation, recorded

`main.py:85`, `main.py:647`, `main.py:990`, `ring_overlay.py:77`,
`ring_overlay.py:445` all justify the ring's role with "since Vision was removed"
or "with Vision gone", without citing a date.

**Option A, what the plan does.** Leave them, per your point 3. They are true under
the current decision.

**Option B, my recommendation.** Delete the clause in each, leaving the surviving
sentence ("the ring is the only channel that reports why a fix is missing"), which
is true under all three decisions and under any future reader. Five small
deletions, no replacement text.

I recommend B because it follows the principle you gave alongside the instruction,
and because a clause asserting the Vision question is settled is exactly the shape
of text that has needed revising three times. Your call; the plan as written does A.

### OQ-3. RESOLVED 2026-08-02: M4 is cleared

`plan-capture` confirmed the distinction my wording depended on and recorded it as
their CONFIRMATION C1, so the assumption is documented rather than implied.
`KIND_ABSENT` means `overlay_is_present(frame)` returned False at `main.py:330` and
is the only kind carrying the `r_displayinfo` hint; present-but-unreadable is five
separate kinds, none carrying it. Their acceptance criteria 3 and 4 check it
mechanically.

**The whole plan now lands together: M1 to M5, V1 to V5, C2, C3, C8.** No part is
held on another agent.

### OQ-4. Should the inert `discovery_keywords` also come out of `Laura.yaml`?

The user authorised deleting the `prompt` key. `Laura.yaml:782-810` also holds a
saved `discovery_keywords` list which I verified is **completely inert**: Layer 2
(`wingman.py:274-283`) copies only `custom_properties` and `prompt`, so the saved
list never reaches `SkillConfig`.

**Option A, my recommendation.** Delete 782 to 810 as well. Changes nothing at
runtime, removes a 29-line copy that looks authoritative and is not. The entry
survives, because `config_manager.py:918` keeps it when custom properties are
present.

**Option B.** Leave it. Strictly within what the user authorised.

I recommend A but will not do it without an explicit answer, because the
authorisation named the prompt specifically and this is the user's live config.

### OQ-6. Version bump

**Recommendation: no bump for this change; bump once, jointly with the capture
change.**

The version appears in five places (`__init__.py`, `release_version/__init__.py`,
`skill_installer_config.json`, `main.py:4`, `main.py:73`) and is pinned by a test
whose FILENAME encodes it, `tests/test_version_49022.py`, with assertions at `:37`,
`:41`, `:46`, `:50`, `:54`. A bump means renaming that file and rewriting its
assertions, which under rule 10 is real work. Doing it twice in two days for two
halves of one fix is waste.

**Counter-argument to weigh:** if the metadata change ships to the live install
standalone and the capture change lags, the live install carries changed behaviour
that no version string distinguishes from `4.9.0.22`. If shipping standalone, bump.

### OQ-7. `preserve_on_update`, and the untracked reader

Two things outside this plan's scope that the supervisor should know.

`preserve_on_update: ["default_config.yaml"]` has no consumer today, so nothing is
broken, but it declares an intent that conflicts with the fact that the description
is the only lever on skill selection. Recommend leaving it and recording the
hazard, since changing a declaration with no consumer is speculative and the right
answer depends on an installer nobody has built. It is set across seven skills.

Separately, R7: `overlay_reader.py`, `overlay_fields.py` and `ring_overlay.py` are
untracked and `scanner.py`'s tracked copy predates the whole 4.9 line. The skill's
current state exists only in the working tree. Constraint 6 forbids me planning a
commit, so this is purely for awareness, but it is a second reason OQ-5's answer
should be "no".

---

## 10. Records this plan does NOT update. RESOLVED 2026-08-02

This section originally warned that `TODO.md:26`, `Devlog.md:54`,
`ledger/LEDGER.md:177` and `ledger/REFUTED.md:167` all still recorded the router
decision as operative, and that no agent owned fixing it. That was true when
written and is no longer.

A separate agent completed the work. The router decision is marked SUPERSEDED in
place in all four files, the OCR-only decision is recorded as the operative entry,
and both `TODO.md` and `Devlog.md` now carry a "what the installed code does today"
statement citing `main.py:382-405`.

**The renumbering that caused has been absorbed.** Every citation this document
makes into those four files was re-verified against the updated records and
corrected in place, so no reference below is stale. What moved:

| Cited for | Was | Now |
|---|---|---|
| "strip the Vision path ... Do this LAST; it is the irreversible step" | `TODO.md:460-463` | `TODO.md:513-516`, verbatim |
| "with no fallback, availability becomes usability" | `TODO.md:468-472` | `TODO.md:526` |
| "the strip step was ordered LAST ... saved the project a rebuild" | `ledger/REFUTED.md:177-179` | `ledger/REFUTED.md:184-186` |
| The router decision | `TODO.md:26` | `TODO.md:68`, labelled SUPERSEDED |
| The operative decision | did not exist | `TODO.md:26`, `Devlog.md:3` |

Line numbers for code and for `default_config.yaml` were unaffected and were
verified independently.

The one citation an implementer must reproduce in shipped code is inside V3's new
docstring: "strip the Vision path ... Do this LAST; it is the irreversible step".
It is quoted as text rather than by line number, and it survived the supersession
word for word. Copy it as written in V3.

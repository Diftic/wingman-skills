# SC Radio — Full Project Scope
**Project:** Star Citizen GTA-Style Radio Station App  
**Author:** Mallachi  
**Version:** 1.0  
**Target:** Claude Code handoff document — sufficient to build and run the full pipeline

---

## Project Summary

A standalone Python application that simulates GTA-style in-game radio for Star Citizen. 25 unique stations, each with distinct music, hosts, commercials, news, and chatter — all pre-generated locally, assembled at runtime by a playlist engine, and played as background audio while playing Star Citizen.

**This is not a mod.** It is a standalone desktop app that runs alongside the game.

---

## Reference Documents

All in the same directory as this file:

| File | Contents |
|---|---|
| `sc_radio_stations.md` | All 25 station profiles, music models, voice counts, tone |
| `sc_radio_content_spec.md` | Block taxonomy, chatter rules, stack architecture, variant counts |
| `sc_radio_songs.md` | Music generation prompts per station, model assignments, song counts |

Read all three before coding anything.

---

## Architecture Overview

```
[Stage 1: Script Generation]
  Claude API → generate ~1,498 chatter scripts
  Output: scripts/  (JSON manifest + individual .txt files per block)

[Stage 2: Music Generation]  
  YuE / Stable Audio Open / ACE-Step / DiffRhythm (local, GPU)
  Output: assets/music/{station_id}/track_{N}.wav

[Stage 3: Chatter Generation]
  Wingman AI v2.1 TTS (local)
  Input: scripts/ manifest
  Output: assets/chatter/{station_id}/{block_type}/{variant_N}.wav

[Stage 4: Post-Processing]
  ffmpeg — normalize audio, apply comms filters, convert to MP3
  Output: assets/processed/{station_id}/...

[Stage 5: Runtime Player]
  Python playlist engine — reads manifest, assembles stacks, plays audio
  UI: minimal system tray app or simple tkinter window
```

---

## Technology Stack

| Component | Technology | Notes |
|---|---|---|
| Language | Python 3.11+ | |
| Music gen (vocal) | YuE | Apache 2.0, runs on 4070 Ti 12GB |
| Music gen (ambient) | Stable Audio Open | Apache 2.0, fast on 12GB |
| Music gen (alternative) | ACE-Step, DiffRhythm | Fallback/comparison |
| TTS / Chatter | Wingman AI v2.1 | Local TTS already installed |
| Audio post-processing | ffmpeg | Normalize, filter, convert |
| Lore data | Galactapedia API | For Ark Hour script seeding |
| Audio playback | pygame or vlc-python | Cross-platform |
| Script generation | Anthropic Claude API | claude-sonnet-4-6 |
| Config | config.py + .env | API keys, paths, settings |
| Logging | DEVLOG.md + Python logging | Per coding session + runtime |

**Excluded by policy:** OpenAI, Meta/Facebook, any Altman/Zuckerberg-affiliated tools.

---

## Hardware

- **GPU:** NVIDIA RTX 4070 Ti, 12GB VRAM
- **OS:** Windows (primary), Linux compatible
- **YuE requirement:** 8GB VRAM minimum — 12GB gives full quality, no quantization needed
- **Stable Audio Open:** Runs fast on 12GB, low memory footprint
- **Wingman AI:** Already installed and operational

---

## Repository Structure

```
sc_radio/
├── config.py                  # Version, paths, API keys, model settings
├── .env                       # API keys (gitignored)
├── DEVLOG.md                  # Development log — update every session
├── clean.py                   # Removes __pycache__, *.pyc, build/, dist/
├── README.md
│
├── scripts/                   # Generated chatter scripts
│   ├── manifest.json          # Master index of all scripts
│   └── {station_id}/
│       └── {block_type}/
│           └── variant_{N}.txt
│
├── assets/
│   ├── music/
│   │   └── {station_id}/
│   │       └── track_{N}.wav
│   ├── chatter/
│   │   └── {station_id}/
│   │       └── {block_type}/
│   │           └── variant_{N}.wav
│   └── processed/             # Post-processed final audio
│       └── {station_id}/
│           ├── music/
│           └── chatter/
│
├── manifests/
│   ├── stations.json          # Station configs, voice assignments
│   ├── music_manifest.json    # All music tracks with metadata
│   └── chatter_manifest.json  # All chatter blocks with metadata
│
├── generators/
│   ├── script_generator.py    # Calls Claude API to write chatter scripts
│   ├── music_generator.py     # Drives YuE / Stable Audio / ACE-Step
│   └── chatter_generator.py   # Drives Wingman TTS API
│
├── pipeline/
│   ├── postprocess.py         # ffmpeg normalization, filters, MP3 conversion
│   ├── manifest_builder.py    # Scans assets/, builds JSON manifests
│   └── content_id_check.py    # Flags tracks for manual review
│
├── player/
│   ├── playlist_engine.py     # Stack assembler + randomizer
│   ├── audio_player.py        # pygame/vlc playback wrapper
│   └── ui.py                  # Minimal UI (system tray or tkinter)
│
└── data/
    ├── stations_config.json   # Station profiles (from sc_radio_stations.md)
    ├── galactapedia_cache.json # Cached lore from Galactapedia API
    └── lore_events.json       # Shared event pool for cross-station framing
```

---

## Module Specifications

### config.py
```python
VERSION = "0.1.0"
PROJECT_NAME = "SC Radio"
AUTHOR = "Mallachi"

# Paths
ASSETS_DIR = "assets/"
SCRIPTS_DIR = "scripts/"
MANIFESTS_DIR = "manifests/"

# Audio settings
SAMPLE_RATE = 44100
OUTPUT_FORMAT = "mp3"
MP3_BITRATE = "320k"
NORMALIZE_TARGET_LUFS = -16.0

# Station count
STATION_COUNT = 25

# Generation targets
TARGET_STATION_DURATION_MIN = 270  # 4.5 hours

# Claude API
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8192
SCRIPT_CHUNK_MAX_CHARS = 2800  # Keep under Wingman TTS limit with margin

# Galactapedia API
GALACTAPEDIA_BASE_URL = "https://api.star-citizen.wiki/api/galactapedia"
GALACTAPEDIA_LOCALE = "en_EN"
```

### clean.py
Removes: `__pycache__/`, `*.pyc`, `*.pyo`, `build/`, `dist/`  
Standard across all Mallachi Python projects.

---

## Module: script_generator.py

**Purpose:** Calls Claude API to generate all ~1,498 chatter scripts.

**Input:** `data/stations_config.json` + content spec rules  
**Output:** `scripts/manifest.json` + individual `.txt` files

**Per script, the manifest entry must include:**
```json
{
  "station_id": "uee_public_broadcasting",
  "block_type": "news_flash",
  "variant_index": 3,
  "duration_target_sec": 30,
  "speakers": ["anchor_male"],
  "voice_ids": ["wingman_voice_id_here"],
  "script_text": "...",
  "audio_tags": ["[pause]"],
  "file_path": "scripts/uee_public_broadcasting/news_flash/variant_3.txt",
  "generated": false,
  "audio_path": null
}
```

**Claude prompt structure:**
- System prompt: Full content rules (no calls to action, lore-grounded, station tone)
- User prompt: Station profile + block type + duration target + variant index
- Request JSON output: one script per call, or batch multiple variants per call
- Temperature: 0.9 (creative variation between variants)

**Galactapedia integration (Ark Hour only):**
- Before generating Ark Hour scripts, fetch 10–20 relevant Galactapedia articles
- Pass article summaries into Claude prompt as lore context
- Cite article title/ID in script metadata for traceability

---

## Module: music_generator.py

**Purpose:** Drives local music models to generate all ~600–820 tracks.

**Models and when to use each:**

| Model | Use case | Station examples |
|---|---|---|
| YuE | Vocal tracks, structured songs | Hurston Heavy, Pyro Free, Galaxy Goss |
| Stable Audio Open | Ambient, atmospheric, instrumental | Nul Static, Vanduul, Xi'an, Stanton Drift |
| ACE-Step | Fast diverse generation, fallback | microTech Pulse, Banu Bazaar |
| DiffRhythm | High-fidelity instrumental | The Exchange, CrusaderCast |

**Per track, metadata to store:**
```json
{
  "station_id": "hurston_heavy",
  "track_index": 4,
  "model_used": "yue",
  "prompt": "Heavy industrial rock...",
  "duration_sec": 243,
  "file_path": "assets/music/hurston_heavy/track_004.wav",
  "content_id_checked": false,
  "content_id_safe": null,
  "processed_path": null
}
```

**Batch generation approach:**
- Run overnight / unattended
- Generate per-station in full before moving to next
- Checkpoint after each station — resume from checkpoint on failure
- Log generation time per track for estimation

**YuE integration notes:**
- Install via: `pip install yue` or clone from github.com/multimodal-art-projection/YuE
- Use full quality (12GB VRAM allows this — no quantization needed)
- Expected speed: ~5–15 min per 4-minute song on 4070 Ti
- Total time estimate for 600 songs: 50–150 hours (run overnight over 1–2 weeks)

**Stable Audio Open integration:**
- Install via: `pip install stable-audio-tools`
- Much faster than YuE for instrumental
- Expected speed: ~2–5 min per track

---

## Module: chatter_generator.py

**Purpose:** Drives Wingman AI v2.1 TTS to render all ~1,498 chatter scripts.

**Input:** `scripts/manifest.json`  
**Output:** `assets/chatter/{station_id}/{block_type}/variant_{N}.wav`

**Wingman TTS integration:**
- Wingman AI v2.1 exposes a local TTS API — check Wingman documentation for endpoint
- Each station has defined voice IDs (assigned in `data/stations_config.json`)
- Multi-speaker blocks: generate each speaker's lines separately, concatenate with ffmpeg
- Respect max character limit per call (verify exact limit from Wingman docs)

**Multi-speaker dialogue flow:**
```
For each dialogue block:
  1. Split script into speaker-tagged lines
  2. Generate each line with corresponding voice_id
  3. Add 100–300ms silence between turns (natural gap)
  4. Concatenate all lines into single output file
  5. Save as variant_{N}.wav
```

**Callin blocks (comms filter):**
- Generate host lines and caller lines separately
- Apply comms filter to caller track (see postprocess.py)
- Mix caller track slightly lower (-3dB) than host
- Concatenate interleaved

---

## Module: postprocess.py

**Purpose:** ffmpeg pipeline for all post-processing.

**Operations:**

1. **Normalize all audio** to -16 LUFS (loudness standard for broadcast)
   ```
   ffmpeg -i input.wav -af loudnorm=I=-16:TP=-1.5:LRA=11 output_normalized.wav
   ```

2. **Comms/radio filter** for caller tracks:
   ```
   ffmpeg -i caller.wav -af "equalizer=f=300:width_type=o:width=2:g=-10,
   equalizer=f=3000:width_type=o:width=2:g=3,aecho=0.8:0.9:20:0.5" caller_filtered.wav
   ```

3. **Distortion filter** for Vanduul Frequency, Nul Static static segments:
   ```
   ffmpeg -i input.wav -af "aeval=val(0)*0.3+random(0)*0.7:c=same" distorted.wav
   ```

4. **Convert to MP3 320kbps:**
   ```
   ffmpeg -i input.wav -codec:a libmp3lame -b:a 320k output.mp3
   ```

5. **Add silence padding** between chatter blocks (50–200ms configurable)

---

## Module: playlist_engine.py

**Purpose:** Runtime stack assembler. Reads manifests, constructs playback sequences.

**Core logic:**

```python
def build_station_playlist(station_id: str, duration_min: int = 270) -> list:
    """
    Assembles a playlist of (music_track, chatter_stack) pairs
    targeting total duration_min minutes.
    Returns ordered list of audio file paths.
    """
```

**Stack assembly rules:**
1. Select next music track (avoid recent repeats — minimum gap = 10 tracks)
2. Determine chatter stack duration based on station archetype targets
3. Select block types allowed for this station (from content spec)
4. Randomly select variants (avoid recent repeats — minimum gap = all variants played)
5. Validate total stack duration within min/max bounds
6. Return: [music_path, block_path_1, block_path_2, ..., block_path_N]

**Station archetype stack targets (from content spec):**
```python
STACK_TARGETS = {
    "ambient": {"min_sec": 8, "max_sec": 30, "avg_sec": 15},
    "mainstream": {"min_sec": 60, "max_sec": 240, "avg_sec": 150},
    "talk_heavy": {"min_sec": 180, "max_sec": 480, "avg_sec": 300},
    "outlaw": {"min_sec": 30, "max_sec": 180, "avg_sec": 90},
    "commerce": {"min_sec": 60, "max_sec": 300, "avg_sec": 180},
    "entertainment": {"min_sec": 120, "max_sec": 360, "avg_sec": 210},
}
```

---

## Module: audio_player.py

**Purpose:** Cross-platform audio playback.

**Requirements:**
- Seamless crossfade between tracks (50–200ms configurable)
- Station switching without gap (pre-buffer next station)
- Volume control
- Current track/station display

**Library preference:** `vlc-python` for broad codec support. Fallback: `pygame.mixer`.

---

## Module: ui.py

**Purpose:** Minimal user interface.

**MVP (Phase 1):** System tray icon with station selector dropdown.  
**Phase 2:** Simple tkinter window with:
- Station list (scrollable)
- Now playing: station name + current block type
- Volume slider
- Skip button (skips current music track)

**No web UI, no Electron, no heavy framework.**

---

## Data: stations_config.json

Derived from `sc_radio_stations.md`. Full station definitions including:

```json
{
  "stations": [
    {
      "id": "uee_public_broadcasting",
      "name": "UEE Public Broadcasting",
      "tagline": "Authorized. Accurate. Always On.",
      "archetype": "mainstream",
      "music_model": "stable_audio_open",
      "music_ratio": 0.50,
      "voice_assignments": {
        "anchor_male": "wingman_voice_id_1",
        "field_reporter_female": "wingman_voice_id_2"
      },
      "allowed_block_types": [
        "station_id", "commercial_15", "commercial_30", "commercial_60",
        "news_flash", "news_segment_short", "news_segment_full",
        "host_banter_quip", "host_banter_mono",
        "nav_report", "security_report_flash", "security_report_full",
        "station_promo"
      ],
      "advertisers": ["RSI", "UEE Advocacy", "Crusader Industries", "MedPen"]
    }
  ]
}
```

---

## Galactapedia API Reference

Used for seeding lore-accurate content, primarily for The Ark Hour.

```
Base URL: https://api.star-citizen.wiki/api/galactapedia
Auth: None required

Single article: GET /api/galactapedia/{id}
Search:         GET /api/galactapedia?filter[query]={text}&locale=en_EN
Pagination:     &page[Number]={N}  (30 results/page, NOT &page=N)
Include:        &include[]=related

Returns markdown-formatted article body.
```

Cache all fetched articles to `data/galactapedia_cache.json` — rate limit respectfully.

---

## Development Phases

### Phase 0 — Setup (start here)
- [ ] Initialize repo with above structure
- [ ] config.py with all constants
- [ ] clean.py
- [ ] DEVLOG.md (first entry)
- [ ] .env template
- [ ] Load `sc_radio_stations.md` → generate `data/stations_config.json`
- [ ] Verify Wingman AI TTS API endpoint and test a single voice call
- [ ] Verify YuE installation + test one music generation
- [ ] Verify Stable Audio Open installation + test one generation

### Phase 1 — Script Generation
- [ ] `generators/script_generator.py`
- [ ] Generate scripts for 3 stations (UEE PB, Pyro Free Radio, Stanton Drift) as pilot
- [ ] Review output quality, adjust prompts
- [ ] Run full generation for all 25 stations
- [ ] Build `scripts/manifest.json`

### Phase 2 — Music Generation
- [ ] `generators/music_generator.py`
- [ ] Generate music for 3 pilot stations
- [ ] Benchmark generation speed on 4070 Ti
- [ ] Run full overnight batch for all stations
- [ ] Content ID check flagging (manual review workflow)
- [ ] Build `manifests/music_manifest.json`

### Phase 3 — Chatter Generation
- [ ] `generators/chatter_generator.py`
- [ ] Wingman TTS integration, multi-speaker concatenation
- [ ] Callin comms filter post-processing
- [ ] Run full chatter generation
- [ ] Build `manifests/chatter_manifest.json`

### Phase 4 — Post-Processing
- [ ] `pipeline/postprocess.py`
- [ ] Normalize all audio
- [ ] Apply station-specific filters (distortion, comms filter)
- [ ] Convert all assets to MP3 320kbps
- [ ] Final manifest update with processed paths

### Phase 5 — Player
- [ ] `player/playlist_engine.py` — stack assembler
- [ ] `player/audio_player.py` — playback
- [ ] `player/ui.py` — minimal tray UI
- [ ] End-to-end test: one station, 30 minutes continuous play

### Phase 6 — Polish
- [ ] All 25 stations tested
- [ ] Seamless crossfade tuning
- [ ] Volume normalization verified across all content types
- [ ] README with install and usage instructions

---

## DEVLOG Instructions

Update `DEVLOG.md` at the start and end of every coding session. Minimum entry:

```markdown
## [DATE] v[VERSION] — [Session summary]

**Completed:**
- ...

**In progress:**
- ...

**Blockers:**
- ...

**Next session:**
- ...
```

Version must be bumped in `config.py` with every substantive change.

---

## Hard Rules (Non-Negotiable)

1. **No calls to action** in any generated script. Events are reported, not solicited.
2. **No OpenAI, Meta/Facebook, or any Altman/Zuckerberg-affiliated tools** anywhere in the stack.
3. **clean.py** must exist and remove: `__pycache__/`, `*.pyc`, `*.pyo`, `build/`, `dist/`
4. **All project attribution:** Mallachi
5. **DEVLOG.md** updated every session — this is the continuity record for AI-assisted development.
6. **Version bump** in config.py with every substantive change.
7. **Confirm approach before implementing** — advisory mode by default.

---

## Known Constraints and Open Questions

| Item | Status | Notes |
|---|---|---|
| Wingman TTS API endpoint | Unknown — verify | Check Wingman v2.1 docs for local API format |
| Wingman max chars per call | Unknown — verify | Assumed ~3,000, confirm from Wingman docs |
| YuE generation speed on 4070 Ti | Unknown — benchmark Phase 0 | Estimate 5–15 min/song |
| Stable Audio Open max duration | Unknown — verify | May have 30sec or 90sec limits |
| Content ID check automation | Manual for MVP | YouTube Studio manual check workflow |
| Wingman voice ID mapping | Unknown | Need to enumerate available Wingman voices |

---

## Quick Start for Claude Code

1. Read `sc_radio_stations.md`, `sc_radio_content_spec.md`, `sc_radio_songs.md` first.
2. Initialize repo structure exactly as specified above.
3. Create `config.py`, `clean.py`, `DEVLOG.md`.
4. Verify Wingman TTS works with a test call before touching anything else.
5. Verify YuE with one test generation before batch scripting.
6. Follow Phase 0 → Phase 1 → ... in order. Do not skip phases.
7. All implementation decisions go into DEVLOG.md.
8. Ask before implementing if anything is ambiguous — Mallachi reviews before execution.

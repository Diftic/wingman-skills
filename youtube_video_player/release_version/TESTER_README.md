# YouTube Video Player — Tester README

## Install (two parts — player first, then skill)

### 1. Install Wingman Player

Wingman Player is the overlay this skill drives. It ships separately so it can
update its own codecs and code independently.

1. Open https://github.com/Diftic/Wingman-Player/releases/latest
2. Download `Wingman-Player-Setup.msi`
3. Run it. The MSI is per-user — installs to:
   ```
   %LocalAppData%\Programs\Wingman Player\
   ```
4. Optional sanity check: launch Wingman Player from the Start Menu. The
   overlay should appear; close it again, the skill will relaunch it on demand.

### 2. Install the skill

1. Double-click `install.bat`.
2. Restart Wingman AI.
3. Open your wingman's config in Wingman, find **YouTube Video Player** in the
   skills list, and activate it.

The bat copies the skill into:
```
%AppData%\ShipBit\WingmanAI\custom_skills\youtube_video_player\
```

## First-run setup

- **YouTube API key.** On first activation, Wingman pops a secret prompt asking
  for your YouTube Data API v3 key. If you don't have one yet, follow the steps
  in `RELEASE_NOTES_v0.1.0.txt` (5 minutes, free, no billing).
- **Player path is auto-resolved.** The skill probes the canonical MSI install
  location (`%LocalAppData%\Programs\Wingman Player\Wingman-Player.exe`) and
  launches from there. The `Player Executable Path (override)` setting is left
  empty by default — only set it if you keep a different build (e.g. a local
  dev build).

## What to test

### Strong-confidence path
Say: **"Play *Never Gonna Give You Up* by *Rick Astley*."**
Expect: skill auto-launches the player, hits the API, and the official Rick
Astley video starts playing. Wingman speaks something like *"Playing 'Rick
Astley - Never Gonna Give You Up' by Rick Astley."*

### List path
Say: **"Find me something by *The Beatles*."**
Expect: skill returns a top-5 list. Wingman speaks all 5 options. You then say
**"play 2"** (or "the third one") and the chosen video starts.

### Transport
- "Pause"
- "Resume"
- "Stop"
- "Skip 30 seconds" / "Rewind 10 seconds"
- "Go to 1 minute 30"
- "What's playing?"

### Recovery — API key
If you accidentally close the API key prompt, say: **"Set the YouTube API
key."** The prompt reopens. Alternatively, enter the key via Wingman's
Settings → Secrets — the skill picks it up automatically without restart.

### Recovery — player missing
If you skipped the player install, the first playback request returns a
spoken/written hint pointing at the GitHub installer URL. Install the player,
then say your request again — no Wingman restart needed.

## What to report back

If anything goes sideways, please grab from Wingman:

1. The user message you said
2. The tool name(s) the LLM called (if shown in the UI)
3. The string the tool returned (the LLM's response usually paraphrases this — the raw value is more useful)
4. The Wingman log line for any error or warning

Good things to flag specifically:
- LLM picking the wrong tool (e.g. calling `search_and_play_youtube` when you said "pause")
- Auto-play firing on the wrong result (composite confidence too generous?) or never firing on clear requests (too strict?)
- Player auto-launch failing or taking too long
- "Can't reach Wingman Player" message after the MSI was installed (path resolution miss)
- Any crash, traceback, or "skill failed to initialize" error

Thanks for testing.

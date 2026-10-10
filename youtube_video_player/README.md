# YouTube Video Player

Voice-driven YouTube video playback for Wingman AI. **Bundles the media player overlay** — one install, no separate downloads, no external paths to configure.

## What it does

| You say... | What happens |
|------------|--------------|
| "Play *Bohemian Rhapsody* by *Queen*" | Searches YouTube, auto-plays the top result if confidence is high |
| "Play that one Queen song you know" | Returns top 5 results — Wingman speaks them, you pick |
| "Find me something by *The Beatles*" | Top-5 list to choose from |
| "Play 2" / "the third one" | Plays the chosen item from the most recent list |
| "Pause" / "Resume" / "Stop" | Transport — straight pass-through to the player |
| "Skip to the next song" / "Previous track" | Playlist navigation (when in a playlist) |
| "Skip ahead 30 seconds" / "Go to 1:30" | Seek (relative or absolute) |
| "What's playing?" | Returns current title, state, position, duration |
| "Set the YouTube API key" | Re-opens the API key prompt if you dismissed it |

Volume is intentionally **not** controlled by the skill — the player is part of the wider Wingman audio pipeline; per-app volume is the OS / Wingman audio router's job.

---

## Requirements

- **Wingman AI** installed
- **Free YouTube Data API v3 key** — see setup below
- That's it. The media player overlay is bundled inside this skill.

---

## Setup

### 1. Get a YouTube Data API key

1. Go to **https://console.cloud.google.com**
2. Create a project (or pick an existing one) — name it "Wingman" or similar
3. Sidebar → **APIs & Services → Library** → search **"YouTube Data API v3"** → click **Enable**
4. Sidebar → **APIs & Services → Credentials**
5. **+ Create Credentials → API key** → copy the key
6. **Recommended:** click **Restrict Key** → **API restrictions** → select only "YouTube Data API v3". This limits damage if the key ever leaks.

The key never leaves your machine — Wingman's SecretKeeper stores it locally. Default daily quota is 10,000 units (≈ 95 searches/day with the skill's caching).

### 2. Install the skill

Run the bundled `install.bat` from the release zip. It robocopies the skill (and the bundled player overlay) into:

```
%AppData%\ShipBit\WingmanAI\custom_skills\youtube_video_player\
```

### 3. First launch

When Wingman activates the skill it'll prompt for the YouTube API key. Paste it once — SecretKeeper handles it from there.

If you accidentally dismiss the prompt, either:
- Open Wingman Settings → Secrets and enter the key (skill picks it up automatically), or
- Say *"Set the YouTube API key"* and the prompt re-opens.

You're ready: say **"play Never Gonna Give You Up by Rick Astley"** and the bundled player launches and starts playing.

---

## Configuration

All knobs live in `default_config.yaml` under `custom_properties`:

| Property | Default | What it does |
|----------|---------|--------------|
| `daily_search_limit` | 100 | Max searches per UTC day. Each costs 100 units of the 10,000-unit free quota, so 95–100 is the practical ceiling. |
| `cache_ttl_minutes` | 60 | In-memory cache TTL for identical normalized queries. Repeats inside the window are free. |
| `auto_play_threshold` | 0.98 | Composite confidence (LLM + heuristic) above which the top result auto-plays. Lower = more eager auto-play. |
| `player_host` | 127.0.0.1 | Bundled player command server host |
| `player_port` | 17330 | Bundled player command server port |
| `player_exe_path` | (empty) | **Optional override.** Leave empty to use the bundled player. Set to a custom path only if you want to run a different build (e.g. a local dev build). |
| `auto_launch_player` | true | If true, the skill launches the bundled player automatically when needed |

---

## How confidence works

Auto-play uses a composite score from two sources:

**LLM confidence (0–1)** — the Wingman LLM's read on how clearly the user named what they want:

| User said | LLM confidence |
|-----------|----------------|
| "Play *X* by *Y*" (specific song + artist) | ~0.85–0.95 |
| "Play *X*" (specific song, no artist) | ~0.70–0.85 |
| "Find something by *Y*" (artist only) | ~0.40–0.60 |
| "Play that *Y* song you know" (vague reference) | ~0.30–0.50 |
| "Find me something good" (no specifics) | ~0.10–0.20 |

**Heuristic boost (0–0.30)** — applied by the skill based on the top YouTube result:

- Channel matches the artist (substring or 60%+ similarity) → +0.15
- Title contains the song name (substring or 50%+ similarity) → +0.10
- Weaker matches → smaller boosts

**Composite = LLM + boost**, capped at 1.0. Auto-plays if `composite ≥ auto_play_threshold` (default 0.98). Otherwise the skill returns a numbered top-5 list and the LLM speaks it.

The default threshold is intentionally strict — the skill prefers showing options to picking wrong. Lower it (e.g. 0.85) if you want more eager auto-play.

---

## Files

- `main.py` — `YoutubeVideoPlayer(Skill)` with all tools and lifecycle
- `youtube_search.py` — Data API v3 client + per-day quota tracker + per-query cache
- `player_client.py` — HTTP client for the bundled media player overlay (with auto-launch)
- `confidence.py` — composite confidence math (B + C: heuristic + LLM)
- `default_config.yaml` — manifest, prompt, custom properties
- `skill_installer_config.json` — file manifest for the Wingman installer
- `player/Wingman-Player.exe` — bundled media player overlay (~170MB self-contained)
- `player/Renderer/` — HTML/CSS/JS UI files served to the embedded WebView2

The media player source lives at https://github.com/Diftic/Wingman-Player. The bundle inside this skill is a snapshot of a release build; the player's own auto-updater can refresh it in place from GitHub Releases without re-installing the skill.

---

## Troubleshooting

**"Wingman Player isn't running and I couldn't auto-launch it"**
The bundled player should launch automatically. Check that `player/Wingman-Player.exe` exists in the skill folder. If you're running from a dev source without the bundle, set `player_exe_path` to a local build of `Wingman-Player.exe`.

**"YouTube search failed (403)"**
Almost always one of:
- Wrong / revoked API key — check `console.cloud.google.com` → Credentials
- Daily 10,000-unit quota exceeded (Google's, not the skill's local cap) — wait until midnight UTC
- API key restriction blocking the request — check the **Restrict Key** settings, ensure only "YouTube Data API v3" is allowed

**"Daily YouTube search limit reached"**
Local cap (`daily_search_limit`) hit. Resets at midnight UTC. Raise it in the skill config if you want more headroom.

**"YouTube API key isn't configured"**
The prompt was dismissed, or the key was deleted from Wingman's secrets. Recovery: open Wingman Settings → Secrets and enter the key, or say *"Set the YouTube API key"* to re-open the dialog.

**Top result auto-plays the wrong video**
Lower the LLM confidence in your prompt, or raise `auto_play_threshold` to 0.99+. Or accept that searching for a generic title (e.g. "Yesterday") will sometimes pick a cover instead of the original.

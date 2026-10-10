# SC Radio — Master Content Specification
**Project:** Star Citizen GTA-Style Radio Station App  
**Author:** Mallachi  
**Version:** 2.0  
**Updated:** Architecture revised to fully local generation

---

## Architecture

| Component | Tool | Cost |
|---|---|---|
| Music generation | YuE / Stable Audio Open / ACE-Step / DiffRhythm (local) | Free |
| TTS / Chatter | Wingman AI v2.1 local TTS | Free |
| Script generation | Claude | ~$0 |
| Content ID pre-check | YouTube Studio free checker | Free |
| Hardware | RTX 4070 Ti, 12GB VRAM | Owned |

**Total ongoing cost: $0**

---

## Global Content Rules

1. **No calls to action.** Radio reports world events. The listener decides what to do.
2. **No prompts to respond, assist, sell, buy, travel, or act.**
3. **Events are reported after the fact**, or as ongoing news — never as directives.
4. **Framing test:** Could an NPC say this in a quest? If yes, rewrite it as pure information.
5. All content must be **lore-grounded** in the Star Citizen universe.
6. Each block type requires **5–8 script variants per station** to prevent repetition.
7. Delivery tone must match the **station's worldview and character**.
8. Scripts chunked to **≤3,000 characters** per TTS call (Wingman limit — verify).
9. **Station-flavored framing of shared events** is the highest-value immersion technique.

---

## Block Taxonomy

### 1. Station ID / Ident
| Property | Value |
|---|---|
| Duration | 5–10 sec |
| Format | Single voice |
| Variants per station | 6–8 |
| Usage | Transitions, top of hour, between any blocks |

Station name + tagline + brief mood signal. No information content. Pure identity marker.

---

### 2. Commercial
| Duration | Format | Variants |
|---|---|---|
| 15 sec | Single voice | 6 per station |
| 30 sec | 1–2 voice dialogue | 6 per station |
| 60 sec | Full narrative, 2 voices | 4 per station |

**Advertiser pool by station type:**

| Station type | Advertisers |
|---|---|
| UEE / Mainstream | RSI, Crusader Industries, Advocacy, MedPen, Stor-All |
| Corporate | Hurston Dynamics, microTech, ArcCorp, Covalex, Shubin |
| Frontier / Outlaw | Drake, GrimHEX vendors, unlicensed pharmacies, unnamed importers |
| Entertainment | Garrity Defense, Cubby Blast, Platinum Bay, bars |
| Alien | Banu trading collectives, Xi'an cultural exchange |

---

### 3. News Flash
| Duration | Format | Variants |
|---|---|---|
| 20–40 sec | Single anchor | 6–8 per station |

Single headline + 1–2 sentences of context. Event already occurred or is ongoing. High frequency, cheap to generate.

---

### 4. News Segment
| Duration | Format | Variants |
|---|---|---|
| 60–90 sec | Single anchor OR 2-speaker | 5–6 per station |
| 2–3 min | Single OR anchor + field reporter | 5 per station |

Full story. Station bias shapes framing. Same event, different spin across stations.

**The same-event framing principle:**
> A Drake Cutlass destroyed near Cellin, crew unaccounted for.
- UEE PB: "Authorities investigating the loss of an unregistered vessel..."
- Pyro Free: "Another ship gone near Cellin. No official statement. No survivors found."
- Bounty Board FM: "Two active contracts linked to the vessel's crew were closed this cycle."
- The Exchange: "Cargo manifest unknown. Insurance claims filed with Llyod's of Stanton."

---

### 5. Host Banter (Solo)
| Duration | Format | Variants |
|---|---|---|
| 15–30 sec | Single host | 8 per station |
| 60–90 sec | Single host monologue | 6 per station |

Host in character. Reacts to music, comments on universe, brief anecdote. No news. Pure station voice.

---

### 6. Two-Host Banter
| Duration | Format | Variants |
|---|---|---|
| 60 sec | 2 recurring hosts | 5–6 per station |
| 2–3 min | 2 recurring hosts | 4 per station |

Conversation between two defined characters. Can be complementary or combative.

**Applicable stations:** Senate Floor, Galaxy Goss, Stanton Drift, Levski Underground, Murray Cup Live, Bounty Board FM, Stellar FM, microTech Pulse, Rough Cut, CrusaderCast, Pyro Free Radio, Dead Reckoning, Banu Bazaar, Spectrum Pirate, NavyWave.

Audio expression tags (Wingman-compatible): `[laughs]` `[sighs]` `[scoffs]` `[pause]`

---

### 7. Podcast Segment
| Duration | Format | Variants |
|---|---|---|
| 3–5 min | 2–3 speakers, topic-driven | 3–4 per station |

Structured conversation: intro → development → conclusion. Speakers have defined roles.

**Applicable stations:** Ark Hour, Levski Underground, Senate Floor, Dead Reckoning, Tevarin Remembrance, Bounty Board FM, The Exchange, Stanton Drift.

**Chunking:** Split scripts at natural dialogue breaks. Generate per-chunk, concatenate audio.

---

### 8. Listener Callin (Simulated)
| Duration | Format | Variants |
|---|---|---|
| 60–90 sec | Host + caller (2 voices) | 4–5 per station |

Caller voice gets comms/radio filter applied in post-processing (ffmpeg equalizer + aecho filter).

**Applicable stations:** Pyro Free Radio, Rough Cut, Spectrum Pirate, Bounty Board FM, Galaxy Goss.

---

### 9. Navigation / Traffic Report
| Duration | Format | Variants |
|---|---|---|
| 20–60 sec | Single traffic reporter voice | 6–8 per station |

System conditions as factual status. Not warnings. Not advisories.

**Topic pool:** Jump point transit times, quantum lane density observations, debris field extents, atmospheric conditions, infrastructure outages, patrol presence (factual only).

**Correct:** "The Stanton-Pyro jump point recorded 340 transits this cycle, a 22% increase over last week."  
**Wrong:** "Pilots are advised to plan alternate routes."

---

### 10. Trade / Market Report
| Duration | Format | Variants |
|---|---|---|
| 10–30 sec | Single market voice | 6–8 per station |
| 60–120 sec | Single or 2-speaker | 4 per station |

Commodity price movements and index changes as data. Never recommendations.

**Correct:** "Agricultural exports from ArcCorp recorded a 14% volume drop this quarter."  
**Wrong:** "Now is a great time to move your cargo."

**Applicable stations:** The Exchange, ArcCorp 24/7, Banu Bazaar Radio, UEE Public Broadcasting, microTech Pulse.

---

### 11. Security / Incident Report
| Duration | Format | Variants |
|---|---|---|
| 10–30 sec | Single voice flash | 6–8 per station |
| 30–90 sec | Single voice full | 5 per station |

Criminal activity, Advocacy operations, gang movements — reported as concluded or ongoing events. Never soliciting response.

**Station framing contrast (same event):**
| Station | Framing |
|---|---|
| UEE Public Broadcasting | "Advocacy forces concluded a two-day operation near Port Olisar, detaining fourteen individuals." |
| Pyro Free Radio | "Fourteen people were taken by the Advocacy near Olisar. No charges confirmed. Families not notified." |
| Bounty Board FM | "Fourteen contract subjects recovered in a coordinated operation near Olisar. Recovery rate: 93%." |
| Levski Underground | "The UEE arrested fourteen people near Olisar. Names withheld. As always." |

---

### 12. Station Promo
| Duration | Format | Variants |
|---|---|---|
| 15–30 sec | Single voice | 4–5 per station |

Promotes upcoming content on same station. Creates programming continuity illusion.

---

## Chatter Stack Architecture

Blocks assembled into **chatter stacks** between two songs. Runtime randomizer selects and assembles based on duration budget and station archetype.

**Example — deep content stack:**
```
[Song 5:00] → [Commercial 15sec] → [Commercial 30sec] → [News Segment 2min] 
→ [News Segment 90sec] → [Podcast Segment 3min] → [Commercial 10sec] → [Song 4:00]
```

**Stack duration targets:**

| Station type | Min | Max | Avg |
|---|---|---|---|
| Ambient (Nul Static, Xi'an, Vanduul) | 8 sec | 30 sec | 15 sec |
| Mainstream (UEE PB, CrusaderCast) | 60 sec | 4 min | 2.5 min |
| Talk-heavy (Senate Floor, Ark Hour) | 3 min | 8 min | 5 min |
| Outlaw/Frontier (Pyro Free, Rough Cut) | 30 sec | 3 min | 90 sec |
| Commerce (Exchange, ArcCorp 24/7) | 60 sec | 5 min | 3 min |
| Entertainment (Galaxy Goss, Murray Cup) | 2 min | 6 min | 3.5 min |

---

## Block Assignments Per Station

| Station | IDs | Comms | NFlash | NSeg | Banter1 | Banter2 | Pod | Callin | Nav | Trade | Security | Promo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| UEE Public Broadcasting | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | ✓ | — | ✓ | ✓ |
| Stellar FM | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | — | — | — | — | ✓ |
| Senate Floor | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | — | — | ✓ | ✓ |
| NavyWave | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | ✓ | — | ✓ | ✓ |
| CrusaderCast | ✓ | ✓ | — | — | ✓ | ✓ | — | — | — | — | — | ✓ |
| Hurston Heavy | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | ✓ | ✓ |
| microTech Pulse | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | — | — | ✓ | — | ✓ |
| The Exchange | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | ✓ | ✓ | — | ✓ |
| ArcCorp 24/7 | ✓ | ✓ | — | — | ✓ | — | — | — | — | ✓ | — | ✓ |
| Pyro Free Radio | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | — |
| Nul Static | ✓ | — | — | — | ✓ | — | — | — | — | — | — | — |
| The Rough Cut | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | ✓ |
| Levski Underground | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | ✓ | — |
| Dead Reckoning | ✓ | ✓ | — | — | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ |
| Banu Bazaar Radio | ✓ | ✓ | — | — | ✓ | ✓ | — | — | — | ✓ | — | ✓ |
| Xi'an Signal | ✓ | — | — | — | ✓ | — | — | — | — | — | — | — |
| Tevarin Remembrance | ✓ | — | — | — | ✓ | — | ✓ | — | — | — | — | — |
| Vanduul Frequency | ✓ | — | — | — | — | — | — | — | — | — | — | — |
| Murray Cup Live | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | — | — | — | ✓ |
| Bounty Board FM | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — | — | ✓ | ✓ |
| The Stanton Drift | ✓ | — | — | — | ✓ | ✓ | ✓ | — | — | — | — | ✓ |
| Galaxy Goss | ✓ | ✓ | ✓ | — | ✓ | ✓ | — | ✓ | — | — | — | ✓ |
| Spectrum Pirate | ✓ | — | ✓ | ✓ | ✓ | ✓ | — | ✓ | — | — | ✓ | — |
| The Ark Hour | ✓ | — | ✓ | ✓ | ✓ | — | ✓ | — | — | — | — | ✓ |
| Dead Air | ✓ | — | — | — | ✓ | — | — | — | — | — | — | — |

---

## Total Script Count Estimate

| Block type | Est. total scripts |
|---|---|
| Station IDs | ~175 |
| Commercials (all lengths) | ~264 |
| News Flash | ~96 |
| News Segments (both lengths) | ~130 |
| Host Banter (both lengths) | ~284 |
| Two-Host Banter (both lengths) | ~100 |
| Podcast Segments | ~32 |
| Listener Callins | ~27 |
| Nav / Traffic Reports | ~84 |
| Trade / Market Reports | ~50 |
| Security Reports (both lengths) | ~166 |
| Station Promos | ~90 |
| **TOTAL** | **~1,498 scripts** |

---

## Post-Processing Notes

- **Caller comms filter:** Apply to callin blocks after TTS generation. ffmpeg command:  
  `ffmpeg -i caller.wav -af "equalizer=f=300:width_type=o:width=2:g=-10,equalizer=f=3000:width_type=o:width=2:g=3,aecho=0.8:0.9:20:0.5" caller_filtered.wav`
- **Vanduul Frequency / Nul Static:** Apply heavy distortion and static overlay to all audio.
- **Spectrum Pirate:** Light distortion on host voice, heavier on caller tracks.
- **Content ID check:** Run all music through YouTube Studio checker before finalizing library.

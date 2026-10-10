# SC Radio — Station Master Reference
**Project:** Star Citizen GTA-Style Radio Station App  
**Author:** Mallachi  
**Version:** 2.0  
**Updated:** Architecture revised to fully local generation (no cloud APIs)

---

## Architecture Notes

- **Music generation:** Local models (YuE, Stable Audio Open, ACE-Step, DiffRhythm)
- **Chatter/TTS:** Wingman AI v2.1 local TTS
- **Scripts:** Claude-generated, pre-written, static
- **No ElevenLabs, no Suno, no Udio — zero ongoing cost**
- **Hardware:** NVIDIA RTX 4070 Ti (12GB VRAM)

---

## Music Model Assignment Key

| Model | Best for | Vocals |
|---|---|---|
| **YuE** | Full songs with vocals, most genres | Yes |
| **Stable Audio Open** | Ambient, atmospheric, instrumental | No |
| **ACE-Step** | Diverse genres, fast generation | Optional |
| **DiffRhythm** | Structured, high-fidelity instrumental | No |

---

## Station Profiles

### 1. UEE Public Broadcasting
| Property | Value |
|---|---|
| Tagline | "Authorized. Accurate. Always On." |
| Location | Terra Prime, UEE Core Systems |
| Music genre | Patriotic orchestral, military marches, classical anthems |
| Music model | Stable Audio Open / DiffRhythm |
| Music ratio | 50% |
| Chatter style | Formal news anchor, no personality, pro-UEE bias |
| Advertisers | RSI, UEE Advocacy, Crusader Industries, MedPen |
| Chatter types | News segments, nav reports, security reports, commercials, station IDs |
| Voices | 2 (male anchor, female field reporter) |
| Tone | Authoritative, measured, propaganda-adjacent |

### 2. Stellar FM
| Property | Value |
|---|---|
| Tagline | "Your Universe. Your Sound." |
| Location | ArcCorp, Area 18 |
| Music genre | Pop, synth-pop, upbeat electronic |
| Music model | YuE |
| Music ratio | 55% |
| Chatter style | Bubbly, celebrity-obsessed, shallow, enthusiastic |
| Advertisers | Fashion brands, nightclubs, RSI lifestyle |
| Chatter types | Host banter, two-host banter, news flash, commercials, promos |
| Voices | 2 (male + female co-hosts) |
| Tone | Upbeat, vacuous, entertainment-focused |

### 3. The Senate Floor
| Property | Value |
|---|---|
| Tagline | "Where Policy Meets the People." |
| Location | Terra, UEE Senate District |
| Music genre | Minimal classical, occasional jazz |
| Music model | Stable Audio Open |
| Music ratio | 25% |
| Chatter style | Political punditry, debate format |
| Advertisers | Law firms, political consulting |
| Chatter types | Podcast segments, two-host banter, news segments, news flash, security reports |
| Voices | 3 (moderator + two opposing pundits) |
| Tone | Serious, combative, intellectually pretentious |

### 4. NavyWave
| Property | Value |
|---|---|
| Tagline | "For Those Who Serve." |
| Location | UEEN Idris-class broadcast array |
| Music genre | Military march, heroic orchestral, patriotic rock |
| Music model | YuE / Stable Audio Open |
| Music ratio | 55% |
| Chatter style | Military cadence, hero worship, recruitment-adjacent |
| Advertisers | UEEN Recruitment, RSI military line, Behring Arms |
| Chatter types | News segments, host banter, commercials, nav reports, security reports |
| Voices | 2 (male military narrator, female news reader) |
| Tone | Proud, disciplined, jingoistic |

### 5. CrusaderCast
| Property | Value |
|---|---|
| Tagline | "Above the Clouds. Close to Home." |
| Location | Orison, Crusader, Stanton |
| Music genre | Soft jazz, ambient lounge, light classical, acoustic |
| Music model | Stable Audio Open / DiffRhythm |
| Music ratio | 65% |
| Chatter style | Friendly, community-focused, family-safe |
| Advertisers | Crusader Industries, Covalex, Stor-All |
| Chatter types | Host banter, two-host banter, commercials, station promos |
| Voices | 2 (warm female host, friendly male co-host) |
| Tone | Cozy, domestic, aspirational |

### 6. Hurston Heavy
| Property | Value |
|---|---|
| Tagline | "Work Hard. Broadcast Harder." |
| Location | Lorville, Hurston, Stanton |
| Music genre | Industrial rock, heavy metal, hard-driving electronic |
| Music model | YuE |
| Music ratio | 50% |
| Chatter style | Gruff, pro-corporate, safety-briefing delivery, dark humor |
| Advertisers | Hurston Dynamics, Shubin Interstellar, medical insurance |
| Chatter types | Host banter, news segments, commercials, security reports, station IDs |
| Voices | 2 (gruff male host, clipped female announcer) |
| Tone | Grim, sardonic, Hurston company-loyal |

### 7. microTech Pulse
| Property | Value |
|---|---|
| Tagline | "Think Forward." |
| Location | New Babbage, microTech, Stanton |
| Music genre | Synthwave, electronic, tech-house |
| Music model | YuE / ACE-Step |
| Music ratio | 55% |
| Chatter style | Startup culture, tech optimism, dry wit |
| Advertisers | microTech products, tech startups, computing hardware |
| Chatter types | Host banter, two-host banter, trade reports, news flash, commercials |
| Voices | 2 (cool male tech-bro host, sharp female analyst) |
| Tone | Sleek, optimistic, slightly smug |

### 8. The Exchange
| Property | Value |
|---|---|
| Tagline | "Know the Numbers." |
| Location | Port Tressler, Stanton |
| Music genre | Smooth jazz, light lounge, sophisticated ambient |
| Music model | Stable Audio Open / DiffRhythm |
| Music ratio | 40% |
| Chatter style | Market reporter cadence, dry financial humor |
| Advertisers | Trading firms, freight companies, insurance, Covalex |
| Chatter types | Trade reports, news segments, host banter, podcast segments, nav reports |
| Voices | 2 (market reporter, analyst guest) |
| Tone | Dry, precise, financially literate |

### 9. ArcCorp 24/7
| Property | Value |
|---|---|
| Tagline | "Commerce Never Sleeps." |
| Location | Area 18, ArcCorp, Stanton |
| Music genre | Relentless upbeat commercial electronic, high-energy pop, aggressive positivity |
| Music model | YuE / ACE-Step |
| Music ratio | 30% |
| Chatter style | Hyper-commercial, every segment is an ad |
| Advertisers | Everything. ArcCorp subsidiaries, consumer products |
| Chatter types | Commercials (dominant), station IDs, host banter, trade flash |
| Voices | 2 (overly cheerful male announcer, equally cheerful female) |
| Tone | Aggressively commercial, hollow positivity |

### 10. Pyro Free Radio
| Property | Value |
|---|---|
| Tagline | "They Can't Silence All of Us." |
| Location | Unknown. Somewhere in Pyro. |
| Music genre | Anarchist punk, industrial noise, hardcore, outlaw country |
| Music model | YuE |
| Music ratio | 50% |
| Chatter style | Anti-UEE, raw, unedited, genuine anger |
| Advertisers | Drake, GrimHEX vendors, unlicensed medical, illegal mods |
| Chatter types | Host banter, two-host banter, news flash, security reports (anti-Advocacy), callins |
| Voices | 2 (male anarchist host, female co-host) + caller voices |
| Tone | Angry, passionate, anti-establishment |

### 11. Nul Static
| Property | Value |
|---|---|
| Tagline | None |
| Location | Deep space. Unknown origin. |
| Music genre | Dark ambient, drone, cosmic horror soundscape |
| Music model | Stable Audio Open |
| Music ratio | 92% |
| Chatter style | Rare cryptic fragments, sounds like interception |
| Advertisers | None |
| Chatter types | Station IDs only (very sparse, unsettling) |
| Voices | 1 (distorted, genderless) |
| Tone | Unsettling, unknowable |

### 12. The Rough Cut
| Property | Value |
|---|---|
| Tagline | "Hard Work. Honest Sound." |
| Location | Clio system, mining outposts |
| Music genre | Space country, frontier folk, outlaw country, acoustic rock |
| Music model | YuE |
| Music ratio | 55% |
| Chatter style | Frontier charm, mining culture, old spacer stories |
| Advertisers | Drake, Argo, mining equipment, frontier supplies |
| Chatter types | Host banter, two-host banter, callins, nav reports, security reports, commercials |
| Voices | 2 (weathered male host, no-nonsense female co-host) |
| Tone | Honest, warm, frontier-tough |

### 13. Levski Underground
| Property | Value |
|---|---|
| Tagline | "The System Is the Crime." |
| Location | Levski, Delamar |
| Music genre | Protest music, underground punk, political hip-hop |
| Music model | YuE |
| Music ratio | 45% |
| Chatter style | Anti-corporate manifestos, political theory |
| Advertisers | None (explicitly refuses corporate advertising) |
| Chatter types | Host banter, two-host banter, podcast segments, news segments, security reports |
| Voices | 3 (rotating host collective) |
| Tone | Righteous, intellectual, anti-corporate |

### 14. Dead Reckoning
| Property | Value |
|---|---|
| Tagline | "For Those Who Know the Stars by Name." |
| Location | Broadcast origin unknown. Old navigation beacon format. |
| Music genre | Spacer folk, acoustic, shanty-adjacent, melancholic instrumental |
| Music model | YuE / DiffRhythm |
| Music ratio | 55% |
| Chatter style | Old spacer wisdom, navigation lore, quiet philosophy |
| Advertisers | Argo Astronautics, independent shipwrights |
| Chatter types | Host banter, two-host banter, podcast segments, nav reports |
| Voices | 2 (elderly male navigator, younger female apprentice) |
| Tone | Wise, nostalgic, spacer-culture reverent |

### 15. Banu Bazaar Radio
| Property | Value |
|---|---|
| Tagline | "Every Deal. Every System. Always Open." |
| Location | Banu Souli, multiple relay nodes |
| Music genre | Dense multilayered world fusion, exotic percussion, alien-influenced sincere folk, market energy |
| Music model | YuE / ACE-Step |
| Music ratio | 50% |
| Chatter style | Chaotic multilingual ads, rapid-fire trade gossip |
| Advertisers | Banu trading collectives, rare goods importers, exotic tech |
| Chatter types | Host banter, two-host banter, trade reports, commercials |
| Voices | 3 (Banu-accented male, human female translator, chaotic third) |
| Tone | Chaotic, enthusiastic, mercantile, alien-flavored |

### 16. Xi'an Signal
| Property | Value |
|---|---|
| Tagline | None in human language |
| Location | Xi'an space, exact origin classified |
| Music genre | Meditative electronic, mathematically structured, alien tonal systems |
| Music model | Stable Audio Open / DiffRhythm |
| Music ratio | 94% |
| Chatter style | Precise, structured, minimal |
| Advertisers | None recognizable |
| Chatter types | Station IDs (translated), rare host banter |
| Voices | 1 (synthetic-sounding, metered) |
| Tone | Alien, deliberate, unknowable but not threatening |

### 17. Tevarin Remembrance
| Property | Value |
|---|---|
| Tagline | "We Were. We Are. We Remember." |
| Location | Kesser, Croshaw system |
| Music genre | Haunting Tevarin cultural music, mournful instrumental, ritual chant |
| Music model | YuE / Stable Audio Open |
| Music ratio | 70% |
| Chatter style | Spoken word poetry, historical narration, lore-heavy cultural content |
| Advertisers | None |
| Chatter types | Host banter (monologue), podcast segments (oral history), station IDs |
| Voices | 2 (elder Tevarin male, young female cultural narrator) |
| Tone | Mournful, dignified, historically grounded |

### 18. The Vanduul Frequency
| Property | Value |
|---|---|
| Tagline | None |
| Location | Unknown. Beyond the frontier. |
| Music genre | Aggressive noise, percussive chaos, alien industrial |
| Music model | Stable Audio Open |
| Music ratio | 98% |
| Chatter style | Static. Fragments. Nothing coherent. |
| Advertisers | None |
| Chatter types | Station IDs only (static-heavy, distorted) |
| Voices | 0 (no intelligible voice) |
| Tone | Hostile, alien, atmospheric horror |

### 19. Murray Cup Live
| Property | Value |
|---|---|
| Tagline | "Speed. Glory. Carnage." |
| Location | Shubin Interstellar Event Broadcast, Stanton |
| Music genre | High-energy electronic, racing pump-up, adrenaline rock |
| Music model | YuE / ACE-Step |
| Music ratio | 40% |
| Chatter style | Sports commentary energy, race results, sponsor chaos |
| Advertisers | Racing sponsors, Drake, Anvil, performance mods |
| Chatter types | Host banter, two-host banter, news flash, news segment, commercials, promos |
| Voices | 2 (hyped male commentator, expert female analyst) |
| Tone | Manic, loud, sports-radio energy |

### 20. Bounty Board FM
| Property | Value |
|---|---|
| Tagline | "Know the Score." |
| Location | GrimHEX, Stanton |
| Music genre | Aggressive electronic, dark hip-hop, hunter culture |
| Music model | YuE / ACE-Step |
| Music ratio | 45% |
| Chatter style | Crime stats as sports results, bounty culture, matter-of-fact about violence |
| Advertisers | Garrity Defense, Cubby Blast, bounty tracking services |
| Chatter types | Host banter, two-host banter, podcast segments, news flash, security reports, callins |
| Voices | 3 (lead host, bounty analyst, rotating callin hunters) |
| Tone | Clinical, darkly humorous, hunter-coded |

### 21. The Stanton Drift
| Property | Value |
|---|---|
| Tagline | "Late Nights. Long Hauls. No Destination Required." |
| Location | Port Olisar orbit. Maybe. |
| Music genre | Late-night jazz, lo-fi, ambient electronic, slow soul |
| Music model | Stable Audio Open / DiffRhythm |
| Music ratio | 60% |
| Chatter style | Philosophical, unhurried, introspective |
| Advertisers | None (or very rare, ironic ones) |
| Chatter types | Host banter, two-host banter, podcast segments, station promos |
| Voices | 2 (quiet male night host, occasional female guest) |
| Tone | Contemplative, warm, slightly melancholy |

### 22. Galaxy Goss
| Property | Value |
|---|---|
| Tagline | "Everyone's Talking. We Just Say It Louder." |
| Location | Area 18, ArcCorp |
| Music genre | Celebrity pop, glam electronic, upbeat dance |
| Music model | YuE |
| Music ratio | 45% |
| Chatter style | Celebrity drama, socialite culture, fashion, gossip |
| Advertisers | Fashion, beauty, luxury goods, nightlife |
| Chatter types | Host banter, two-host banter, news flash, callins, commercials, promos |
| Voices | 2 (sharp female gossip host, catty male co-host) |
| Tone | Catty, theatrical, delighted by drama |

### 23. Spectrum Pirate
| Property | Value |
|---|---|
| Tagline | "You Didn't Hear This From Us." |
| Location | Unknown. Mobile. Untraceable. |
| Music genre | Cyberpunk dark electronic, glitchy industrial, fragmented signal aesthetic |
| Music model | YuE / ACE-Step |
| Music ratio | 45% |
| Chatter style | Stolen broadcast announcements, ransom humor, dark satire |
| Advertisers | Ironic fake ads, black market humor |
| Chatter types | Host banter, two-host banter, news flash, security reports, callins |
| Voices | 2 (distorted male pirate host, chaotic female sidekick) |
| Tone | Chaotic, darkly funny, anti-authority |

### 24. The Ark Hour
| Property | Value |
|---|---|
| Tagline | "History Doesn't Forget." |
| Location | The Ark, Davien system |
| Music genre | Understated classical, scholarly ambient |
| Music model | Stable Audio Open |
| Music ratio | 30% |
| Chatter style | Academic, lore-deep, measured intellectual discourse |
| Advertisers | None (public scholarly broadcast) |
| Chatter types | Host banter, news segments, podcast segments, station promos |
| Voices | 2 (scholarly male host, expert female guest) |
| Tone | Intellectual, careful, lore-reverent |
| Special | Scripts seeded from Galactapedia API |

### 25. Dead Air
| Property | Value |
|---|---|
| Tagline | "We'll Be Right Back." |
| Location | Unknown. Possibly abandoned. |
| Music genre | Generic minimal ambient, bland soft instrumental, forgettable background sound |
| Music model | Stable Audio Open |
| Music ratio | 40% |
| Chatter style | Technical difficulty announcements, apologies, long silences |
| Advertisers | None |
| Chatter types | Station IDs (apologetic), host banter (baffled) |
| Voices | 1 (confused, tired male engineer/host) |
| Tone | Deadpan, exhausted, meta |

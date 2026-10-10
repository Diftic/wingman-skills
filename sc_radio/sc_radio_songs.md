# SC Radio — Music Generation Prompts
**Project:** Star Citizen GTA-Style Radio Station App  
**Author:** Mallachi  
**Version:** 2.0  
**Updated:** Local model architecture

---

## Generation Notes

- **Target:** ~600 songs total (avg 24 per station, varying by music ratio)
- **Hardware:** RTX 4070 Ti, 12GB VRAM
- **Primary vocal model:** YuE (Apache 2.0, 8GB+ quantized)
- **Primary instrumental model:** Stable Audio Open (Apache 2.0)
- **Secondary models:** ACE-Step, DiffRhythm
- **Target duration:** 3–5 minutes per track
- **Output format:** WAV 44.1kHz, then convert to MP3 320kbps for distribution
- **Content ID check:** Required before finalizing any track

## Songs Per Station (based on music ratio × 270min per station)

| Station | Music % | Songs (est.) | Model |
|---|---|---|---|
| UEE Public Broadcasting | 50% | 32 | Stable Audio Open |
| Stellar FM | 55% | 35 | YuE |
| The Senate Floor | 25% | 16 | Stable Audio Open |
| NavyWave | 55% | 35 | YuE + Stable |
| CrusaderCast | 65% | 41 | Stable Audio Open |
| Hurston Heavy | 50% | 32 | YuE |
| microTech Pulse | 55% | 35 | YuE / ACE-Step |
| The Exchange | 40% | 26 | Stable / DiffRhythm |
| ArcCorp 24/7 | 30% | 19 | YuE / ACE-Step |
| Pyro Free Radio | 50% | 32 | YuE |
| Nul Static | 92% | 58 | Stable Audio Open |
| The Rough Cut | 55% | 35 | YuE |
| Levski Underground | 45% | 29 | YuE |
| Dead Reckoning | 55% | 35 | YuE / DiffRhythm |
| Banu Bazaar Radio | 50% | 32 | YuE / ACE-Step |
| Xi'an Signal | 94% | 60 | Stable / DiffRhythm |
| Tevarin Remembrance | 70% | 45 | YuE / Stable |
| The Vanduul Frequency | 98% | 62 | Stable Audio Open |
| Murray Cup Live | 40% | 26 | YuE / ACE-Step |
| Bounty Board FM | 45% | 29 | YuE / ACE-Step |
| The Stanton Drift | 60% | 38 | Stable / DiffRhythm |
| Galaxy Goss | 45% | 29 | YuE |
| Spectrum Pirate | 45% | 29 | YuE / ACE-Step |
| The Ark Hour | 30% | 19 | Stable Audio Open |
| Dead Air | 40% | 26 | Stable Audio Open |
| **TOTAL** | | **~819** | |

*Note: ~820 songs if generating full 4.5hr per station. Can reduce to ~600 by targeting 3.5hr effective music runtime.*

---

## Prompt Templates by Station

### UEE Public Broadcasting (Stable Audio Open — instrumental)
```
Patriotic orchestral anthem, sweeping strings, brass fanfare, military percussion,
triumphant and authoritative, UEE government broadcast aesthetic, cinematic and formal,
44.1kHz stereo, no vocals, 3-4 minutes
```

### Stellar FM (YuE — vocal)
```
Upbeat synthpop with catchy hooks, female lead vocals, bright electronic production,
danceable 120bpm, mainstream pop aesthetic, positive lyrics about city life and success,
radio-friendly, 3-4 minutes
```

### The Senate Floor (Stable Audio Open — instrumental)
```
Understated piano jazz, sophisticated and minimal, contemplative mood, quiet bass,
sparse percussion, background music for serious conversation, no vocals, 3-4 minutes
```

### NavyWave (YuE — vocal)
```
Heroic military rock anthem, powerful male vocals, driving guitar, military snare drums,
patriotic and proud, lyrics about service and honor, 130bpm, anthemic chorus, 3-4 minutes
```

### CrusaderCast (Stable Audio Open — instrumental)
```
Soft lounge jazz, warm acoustic guitar, gentle piano, brushed drums, smooth bass,
relaxing and elegant, floating above clouds aesthetic, no vocals, ambient mood, 4 minutes
```

### Hurston Heavy (YuE — vocal)
```
Heavy industrial rock, distorted guitar riffs, pounding drums, gritty male vocals,
dark lyrics about labor and grinding machinery, 140bpm, aggressive and relentless,
factory floor energy, 3-4 minutes
```

### microTech Pulse (YuE / ACE-Step — vocal or instrumental)
```
Clean synthwave, pulsing 808 bass, arpeggiated synths, crisp electronic production,
futuristic and optimistic, tech startup energy, 110bpm, sharp and modern, 3-4 minutes
```

### The Exchange (Stable Audio Open / DiffRhythm — instrumental)
```
Sophisticated smooth jazz, saxophone lead, walking bass, light brushed drums,
piano comping, upscale lounge atmosphere, intelligent and unhurried, no vocals, 4-5 minutes
```

### ArcCorp 24/7 (YuE — vocal)
```
Relentless upbeat commercial electronic, high-energy pop, driving 125bpm,
female vocalist, lyrics about lifestyle and aspiration, bright synth production,
polished and corporate, 2-3 minutes
```

### Pyro Free Radio (YuE — vocal)
```
Raw anarchist punk, distorted guitars, shouted male vocals, fast 160bpm drumming,
angry anti-establishment lyrics, lo-fi recording quality intentional, aggressive and urgent,
Pyro system outlaw aesthetic, 2-3 minutes
```

### Nul Static (Stable Audio Open — instrumental)
```
Dark deep space ambient drone, slowly evolving textures, distant cosmic resonance,
no rhythm, no melody, pure atmosphere, unsettling undertones, cold and vast,
deep space horror aesthetic, 5 minutes
```

### The Rough Cut (YuE — vocal)
```
Outlaw space country, acoustic guitar, fiddle, warm male vocals, frontier storytelling lyrics,
mining culture themes, 90bpm, honest and unpolished production, campfire warmth,
Clio system frontier aesthetic, 3-4 minutes
```

### Levski Underground (YuE — vocal)
```
Underground protest punk, political rap-rock hybrid, multiple vocalists,
anti-corporate lyrics, raw production, Delamar cave system energy,
urgent and defiant, 3-4 minutes
```

### Dead Reckoning (YuE / DiffRhythm — vocal or instrumental)
```
Spacer folk ballad, fingerpicked acoustic guitar, melancholic male vocals,
navigation and loss themes, slow 70bpm, intimate recording quality,
old spacer wisdom aesthetic, verses about the void and finding home, 4-5 minutes
```

### Banu Bazaar Radio (YuE / ACE-Step — vocal)
```
Chaotic alien market fusion, multiple scales and rhythmic patterns colliding,
multilingual lyrics fragments, exotic percussion, Banu trading post energy,
loud and colorful, 3-4 minutes
```

### Xi'an Signal (Stable Audio Open / DiffRhythm — instrumental)
```
Mathematically precise alien electronic, non-Western scales, structured harmonic patterns,
meditative and deliberate, no human emotional arc, alien intelligence aesthetic,
44.1kHz stereo, 4-5 minutes
```

### Tevarin Remembrance (YuE / Stable Audio Open — vocal or instrumental)
```
Haunting Tevarin cultural music, mournful modal scales, ritual chant elements,
sparse percussion, ancient and dignified, loss and remembrance themes,
cultural preservation aesthetic, slow and reverent, 4-5 minutes
```

### The Vanduul Frequency (Stable Audio Open — instrumental)
```
Aggressive alien noise, chaotic percussion, no melodic structure, hostile atmosphere,
industrial grinding textures, intercepted signal aesthetic, deeply unsettling,
alien incomprehensibility, 3-5 minutes
```

### Murray Cup Live (YuE / ACE-Step — vocal or instrumental)
```
High-energy racing electronic, adrenaline-pumping 150bpm, driving bassline,
intense crowd energy, stadium atmosphere, aggressive synth leads,
Murray Cup racing aesthetic, 3 minutes
```

### Bounty Board FM (YuE / ACE-Step — vocal)
```
Dark hip-hop, heavy 808s, menacing bass, cold male rapper vocals,
lyrics about contracts and targets (reported as past events), GrimHEX aesthetic,
hunter culture, 90bpm trap production, 3-4 minutes
```

### The Stanton Drift (Stable Audio Open / DiffRhythm — instrumental)
```
Late night lo-fi jazz, warm vinyl texture, slow 70bpm, Rhodes piano,
muted trumpet, lazy bass, contemplative and melancholy, Port Olisar orbit at 3am aesthetic,
no vocals, 4-5 minutes
```

### Galaxy Goss (YuE — vocal)
```
Glamorous pop electronic, glittery production, female vocalist, celebrity gossip energy,
upbeat but with dramatic flair, Area 18 socialite aesthetic, catchy hooks,
fashion week soundtrack, 115bpm, 3-4 minutes
```

### Spectrum Pirate (YuE / ACE-Step — vocal or instrumental)
```
Cyberpunk dark electronic, glitchy production, stolen broadcast aesthetic,
distorted synths, chaotic structure that occasionally resolves, pirate transmission energy,
anti-corporate undertones, 3-4 minutes
```

### The Ark Hour (Stable Audio Open — instrumental)
```
Understated scholarly classical, solo piano or small ensemble, thoughtful and unhurried,
intellectual atmosphere, Ark library aesthetic, no drama, background for serious discussion,
no vocals, 4-5 minutes
```

### Dead Air (Stable Audio Open — instrumental)
```
Generic minimal ambient, soft and textureless, slow-moving pads,
no rhythmic structure, forgettable and unobtrusive, bland background sound,
no emotional arc, 3-4 minutes
```

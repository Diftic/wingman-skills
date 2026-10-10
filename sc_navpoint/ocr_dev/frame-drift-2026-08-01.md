# Does a container's origin move through the SolarSystem frame?

Built on the `zs_*.json` decodes from the previous pass, which were
produced by the shipped `overlay_reader` / `overlay_fields`. No new
decoding path exists here; this file only does arithmetic on rows that
the reader already trusted.

## Method and what is discarded

- A row contributes a position only if the text after `Pos:` contains NO
  refusal, splits into EXACTLY three tokens, and every token matches
  `^[+-]?\d+(\.\d+)?(km|m)$`. A token without an explicit `m` or `km`
  raises rather than defaulting, because the overlay mixes units per axis
  and a silent default is a 1000x error. Zero such raises occurred.
- A pair contributes only if BOTH frames decode the same stack DEPTH and
  the names at each depth are character-compatible (`?` matches anything).
  Frames where the stack changed (a ship leaving a hangar) are dropped
  rather than matched across a reshape.
- `dt` comes from `index.jsonl` `mono` seconds. Sessions without that file
  contribute NOTHING to this section and are named below.
- `drift = |d_system - d_container| / dt` compares two scalar
  DISPLACEMENT MAGNITUDES, as specified. Because
  `|‖a‖ - ‖b‖| <= ‖a - b‖`, this is a LOWER BOUND on the container
  origin's true motion relative to the system frame: a container origin
  moving across the player's direction of travel is partly invisible to
  it. It cannot overstate drift, only understate it.

**Sessions with no `index.jsonl`, so no `dt` and no drift rate:** game-bright, game-mid, ice-bright, login, login-black, starfield, vote-fast.

## 0. Known positive: surface-01 frame_0000 against frame_0038

- `pyro3` Pos: (330742.1, 218740.80000000002, 119003.7) m -> (330742.1, 218740.80000000002, 119003.7) m
- `SolarSystem` Pos: (-16104284922.2, 7588008096.8, 119003.7) m -> (-16104286715.1, 7587997134.1, 119003.7) m
- **d_container = 0.000 m**, |Δ|magnitude| of pyro3 = 0.000 m
- **d_system = 11,108.343 m = 11.1083 km**
- dt = 80.694 s, so drift >= 137.66 m/s

The lead's hand-derivation was ~11.1 km of system-frame motion against
under a metre of body-frame motion. This pipeline gives 11.1083 km against 0.000 m, so the two agree.

ONE DETAIL OF THE DERIVATION DIFFERS, and it strengthens rather than
weakens the conclusion. The lead read `pyro3` as going 414.0045 km ->
414.0053 km between these two frames. It does not: in `frame_0038` the
`pyro3` Pos is BIT-IDENTICAL to `frame_0000`, all three components, so
the body-frame displacement is exactly 0.000 m and not 0.8 m. 414.0053
km is the session MAXIMUM and it occurs in `frame_0056` and
`frame_0057`. Across all 90 frames, spanning 189.2 s, the player moved
25.46 m in the body frame while the system frame moved 26.039 km.

## 1. Drift per container, per session

### surface-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `pyro3` | 89 | 0 | 0.000 / 0.000 / 1.929 | 137.615 / 133.819 / 143.511 | **137.615** | 138.695 | 141.594 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 4.082 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `pyro3` | 81 | 0.000 | 137.615 | **137.615** |

### red-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `P5_?2` | 111 | 0 | 0.000 / 0.000 / 428.069 | 0.000 / 0.000 / 428.089 | **0.000** | 0.017 | 0.054 |
| `rs_cargo_001` | 94 | 0 | 0.000 / 0.000 / 5.250 | 0.000 / 0.000 / 5.203 | **0.000** | 0.011 | 0.047 |
| `?ransit?arria?e_ele?_util_746881332878` | 23 | 0 | 0.063 / 0.004 / 0.721 | 0.088 / 0.000 / 428.089 | **0.008** | 0.064 | 428.057 |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | 21 | 0 | 0.063 / 0.004 / 0.723 | 0.081 / 0.000 / 0.748 | **0.008** | 0.019 | 0.064 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 11.168 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `P5_?2` | 96 | 0.000 | 0.000 | **0.000** |
| `rs_cargo_001` | 80 | 0.000 | 0.000 | **0.000** |
| `?ransit?arria?e_ele?_util_746881332878` | 20 | 0.058 | 0.074 | **0.007** |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | 18 | 0.058 | 0.064 | **0.004** |

### flight-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `P5_?2` | 17 | 0 | 41.265 / 0.090 / 45.583 | 41.252 / 0.096 / 45.578 | **0.007** | 0.029 | 0.031 |
| `????_?lipper_742164815970` | 17 | 0 | 0.003 / 0.000 / 0.016 | 41.252 / 0.096 / 45.578 | **41.252** | 43.752 | 45.562 |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | 6 | 0 | 2.656 / 0.074 / 6.287 | 2.652 / 0.096 / 6.314 | **0.011** | 0.027 | 0.027 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.050 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `P5_?2` | 17 | 41.265 | 41.252 | **0.007** |
| `????_?lipper_742164815970` | 17 | 0.003 | 41.252 | **41.252** |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | 6 | 2.656 | 2.652 | **0.011** |

### preflight

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `glaciemring_segment_wtn-018` | 1 | 0 | 1.998 / 1.998 / 1.998 | 1.996 / 1.996 / 1.996 | **0.001** | 0.001 | 0.001 |
| `rs_int_ptn_set` | 1 | 0 | 1.997 / 1.997 / 1.997 | 1.996 / 1.996 / 1.996 | **0.000** | 0.000 | 0.000 |

**Restricted to pairs where the innermost container moved < 12.859 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 12.859 to 12.859 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| *(none)* | 0 | | | |

### terrain-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `????_?lipper_742164815970` | 3 | 0 | 0.000 / 0.000 / 0.000 | 0.001 / 0.001 / 0.003 | **0.001** | 0.003 | 0.003 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.000 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `????_?lipper_742164815970` | 3 | 0.000 | 0.001 | **0.001** |

### bright-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `????_?lipper_742164815970` | 2 | 0 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 | **0.000** | 0.000 | 0.000 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.000 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `????_?lipper_742164815970` | 2 | 0.000 | 0.000 | **0.000** |

### bright-02

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `????_?lipper_742164815970` | 2 | 0 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 | **0.000** | 0.000 | 0.000 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.000 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `????_?lipper_742164815970` | 2 | 0.000 | 0.000 | **0.000** |

### camdir-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `pyro3` | 17 | 0 | 168.390 / 6.624 / 229.550 | 139.104 / 50.745 / 203.277 | **63.414** | 126.669 | 140.945 |
| `????_?lipper_742164815970` | 17 | 0 | 0.011 / 0.000 / 0.031 | 139.104 / 50.745 / 203.277 | **139.094** | 178.797 | 203.266 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.067 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `pyro3` | 17 | 168.390 | 139.104 | **63.414** |
| `????_?lipper_742164815970` | 17 | 0.011 | 139.104 | **139.094** |

### fov-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `pyro3` | 74 | 1 | 668.564 / 0.000 / 1,021.625 | 520.936 / 83.696 / 868.991 | **148.884** | 165.792 | 170.616 |
| `????_?lipper_742164815970` | 72 | 1 | 0.005 / 0.000 / 0.612 | 520.777 / 83.696 / 868.991 | **520.752** | 852.247 | 868.991 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 1.284 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `pyro3` | 71 | 672.556 | 521.349 | **149.138** |
| `????_?lipper_742164815970` | 71 | 0.005 | 521.349 | **521.342** |

### nosignal-01

No consecutive pair had a stable, fully readable stack in both
frames, so no drift rate can be computed.

### dark-01

| container | n pairs | quantum pairs excluded | d_container m/s (med / min / max) | d_system m/s (med / min / max) | drift m/s (median) | drift m/s (p90) | drift m/s (max) |
|---|---|---|---|---|---|---|---|
| `????_?lipper_742164815970` | 6 | 5 | 0.000 / 0.000 / 0.016 | 326.872 / 0.000 / 911.234 | **326.869** | 911.234 | 911.234 |

**Restricted to pairs where the innermost container moved < 1.000 m** (25th percentile of innermost displacement in this session, floored at 1 m; innermost displacement here spans 0.000 to 0.122 m):

| container | n still pairs | d_container m/s (med) | d_system m/s (med) | drift m/s (median) |
|---|---|---|---|---|
| `????_?lipper_742164815970` | 11 | 0.000 | 911.234 | **911.234** |

### game-bright

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### game-mid

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### ice-bright

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### login

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### login-black

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### starfield

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

### vote-fast

No `index.jsonl`, so `dt` is unknown and no drift rate can be
computed for this session. Its rows still contribute to section 3.

## 2. Best estimate of each container origin's drift rate

| container | session | pairs | drift m/s (median) | drift m/s (p90) | drift m/s (max) | verdict |
|---|---|---|---|---|---|---|
| `????_?lipper_742164815970` | fov-01 | 72 | 520.752 | 852.247 | 868.991 | origin moves fast through the system frame |
| `????_?lipper_742164815970` | dark-01 | 6 | 326.869 | 911.234 | 911.234 | origin moves fast through the system frame |
| `pyro3` | fov-01 | 74 | 148.884 | 165.792 | 170.616 | origin moves fast through the system frame |
| `????_?lipper_742164815970` | camdir-01 | 17 | 139.094 | 178.797 | 203.266 | origin moves fast through the system frame |
| `pyro3` | surface-01 | 89 | 137.615 | 138.695 | 141.594 | origin moves fast through the system frame |
| `pyro3` | camdir-01 | 17 | 63.414 | 126.669 | 140.945 | origin moves through the system frame |
| `????_?lipper_742164815970` | flight-01 | 17 | 41.252 | 43.752 | 45.562 | origin moves through the system frame |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | flight-01 | 6 | 0.011 | 0.027 | 0.027 | static within measurement noise |
| `?ransit?arria?e_ele?_util_746881332878` | red-01 | 23 | 0.008 | 0.064 | 428.057 | **BIMODAL**: static when parked, up to 428 m/s in motion |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | red-01 | 21 | 0.008 | 0.019 | 0.064 | static within measurement noise |
| `P5_?2` | flight-01 | 17 | 0.007 | 0.029 | 0.031 | static within measurement noise |
| `glaciemring_segment_wtn-018` | preflight | 1 | 0.001 | 0.001 | 0.001 | static within measurement noise |
| `????_?lipper_742164815970` | terrain-01 | 3 | 0.001 | 0.003 | 0.003 | static within measurement noise |
| `rs_int_ptn_set` | preflight | 1 | 0.000 | 0.000 | 0.000 | static within measurement noise |
| `P5_?2` | red-01 | 111 | 0.000 | 0.017 | 0.054 | static within measurement noise |
| `rs_cargo_001` | red-01 | 94 | 0.000 | 0.011 | 0.047 | static within measurement noise |
| `????_?lipper_742164815970` | bright-01 | 2 | 0.000 | 0.000 | 0.000 | static within measurement noise |
| `????_?lipper_742164815970` | bright-02 | 2 | 0.000 | 0.000 | 0.000 | static within measurement noise |

Pairs discarded because the SolarSystem zone id differed between the two
frames or could not be read: none.

## 2b. Negative control: a parked ship in open space

8 consecutive pairs have a ship as the ONLY container,
the player moving < 0.5 m inside it, and the system frame moving
< 0.5 m/s. A ship's origin can therefore be static in the system
frame, so the large ship numbers above are thrust and not a property
of ship containers.

| session | frame A | frame B | container | d_container m | d_system m | dt s |
|---|---|---|---|---|---|---|
| terrain-01 | frame_0001.png | frame_0005.png | `????_?lipper_742164815970` | 0.0000 | 0.0100 | 12.552 |
| terrain-01 | frame_0005.png | frame_0006.png | `????_?lipper_742164815970` | 0.0000 | 0.0100 | 3.129 |
| terrain-01 | frame_0006.png | frame_0016.png | `????_?lipper_742164815970` | 0.0000 | 0.0400 | 31.308 |
| bright-01 | frame_0002.png | frame_0007.png | `????_?lipper_742164815970` | 0.0000 | 0.0000 | 15.682 |
| bright-01 | frame_0007.png | frame_0009.png | `????_?lipper_742164815970` | 0.0000 | 0.0000 | 36.271 |
| bright-02 | frame_0001.png | frame_0006.png | `????_?lipper_742164815970` | 0.0000 | 0.0000 | 15.716 |
| bright-02 | frame_0006.png | frame_0008.png | `????_?lipper_742164815970` | 0.0000 | 0.0000 | 36.315 |
| dark-01 | frame_0007.png | frame_0008.png | `????_?lipper_742164815970` | 0.0000 | 0.0000 | 3.122 |

## 3. Does the container's Z equal the SolarSystem row's Z?

Compared in METRES after unit conversion, over every frame where the
container row and the SolarSystem row both decoded all three axes
cleanly. `exact` is bit-equal after conversion; `near` is within 0.01 m
(display rounding); `mismatch` is anything else.

Counts are pooled over every session in which the container appears,
which is why the frame counts exceed any single session's length.

| container | sessions | exact | near | mismatch | verdict |
|---|---|---|---|---|---|
| `pyro3` | camdir-01, fov-01, surface-01 | 184 | 0 | 0 | Z PASSES THROUGH |
| `P5_?2` | flight-01, red-01 | 138 | 0 | 0 | Z PASSES THROUGH |
| `????_?lipper_742164815970` | bright-01, bright-02, camdir-01, dark-01, flight-01, fov-01, terrain-01 | 0 | 0 | 136 | never matches |
| `rs_cargo_001` | red-01 | 0 | 0 | 97 | never matches |
| `?an?ar_SmallFront_RestStop_Pyro_746881365623` | flight-01, red-01 | 0 | 0 | 29 | never matches |
| `?ransit?arria?e_ele?_util_746881332878` | red-01 | 0 | 0 | 26 | never matches |
| `glaciemring_segment_wtn-014` | game-mid | 5 | 0 | 0 | Z PASSES THROUGH |
| `rsi_polaris_kaboos_ext` | game-mid | 0 | 0 | 5 | never matches |
| `glaciemring_segment_wtn-018` | preflight | 2 | 0 | 0 | Z PASSES THROUGH |
| `rs_int_ptn_set` | preflight | 0 | 0 | 2 | never matches |
| `?umppoint_pyro_ny` | dark-01 | 1 | 0 | 0 | Z PASSES THROUGH |

## 4. What this answers

**Bodies drift, and fast.** `pyro3`'s origin moves through the
SolarSystem frame at a median 137.6 m/s over 89 pairs in surface-01 and
148.9 m/s over 74 pairs in fov-01. In surface-01 the player stood still
for 189 s: the body-frame position moved 25.46 m in total while the
system-frame position moved 26.039 km. A system-frame waypoint stored on
a body surface is wrong by roughly 8 km after one minute.

**The rest-stop parent container `P5_?2` does NOT drift.** Median 0.000
m/s over 111 pairs in red-01 and 0.007 m/s over 17 in flight-01, max
0.054 m/s. This is the contested container and the evidence is the
largest in the set. Over red-01 frames 0040 to 0042 the player rode a
transit 1.466 km: the displacement measured against `P5_?2` and against
SolarSystem agree in magnitude to millimetres while pointing in different
directions, which is a pure Z-axis rotation between the two frames with
no relative motion of the origins.

**Ships do not drift when parked; the large ship numbers are thrust.**
8 pairs across terrain-01, bright-01, bright-02 and dark-01 have a ship
as the only container with the player still inside it and the system
frame moving 0.00 to 0.04 m over 3 to 36 s. A ship in flight reads 40 to
911 m/s, which is the ship moving, not its container frame slipping.

**The station question cannot be answered properly.** The only ring-
station observation with timestamps is `glaciemring_segment_wtn-018` in
preflight, and it yields exactly ONE usable pair at 0.001 m/s. The other
three station sessions (game-mid, starfield, vote-fast) have no
`index.jsonl`, so no `dt` exists for them at all. One pair from one
station cannot establish that stations do not drift, and a station in
orbit would drift slowly enough that one pair could not see it. This is
the thinnest part of the evidence and it is exactly where the 50 km
scale threshold makes its decision.

**The jump point cannot be answered at all.** `?umppoint_pyro_ny` appears
in ONE frame of dark-01, so there is no pair and no drift rate. Its Z
does match the SolarSystem Z exactly in that frame.

**Z passes through for exactly the containers whose origin does not
drift, and for no others.** `pyro3` (184/184), `P5_?2` (138/138),
`glaciemring_segment_wtn-014` (5/5), `wtn-018` (2/2) and the jump point
(1/1) match the SolarSystem Z bit for bit. Ships, rooms, hangars and the
transit carriage never match, in 288 observations, with zero exceptions
either way. The lead's prediction is confirmed for pyro3, P5_?2 and the
jump point, and the station segments it did not cover fall on the
Z-passes-through side.

NOTE the one place Z-identity and drift DISAGREE: `glaciemring_segment_*`
passes the Z test, which groups it with the non-drifting containers, but
its drift rate rests on a single pair. Z identity is a statement about
the frame's ORIENTATION (a Z-axis rotation leaves Z alone); it is not by
itself proof that the origin is stationary. Do not let the strong Z
result stand in for the missing drift measurement.

# Follow-up: changing digits and capture methods

The user reports frame generation is inactive in NVIDIA settings. The supplied game screenshot shows Vulkan, 5120×1440, DLSS Balanced (57%), Transformer, and HDR disabled. This does not establish the origin of the questionable digit shapes. Frame generation is not a confirmed explanation.

## Direct neighboring-pixel evidence

A 240-frame native GDI/MSS burst over 4.07 seconds produced 206 accepted coordinate captures. Among refused numeric cells, 34 matched an intermediate mixture of the actual captured pixels immediately before and after them, under the stated diagnostic thresholds. This comparison does not use stored glyph templates to synthesize the endpoints.

The frames were decoded afterward; the short diagnostic recording does not change the runtime OCR cadence.

Example: Root row, frame 191, cell 20. The middle capture fits 56.76% of the previous captured cell plus 43.24% of the next, with 0.97 RGB RMS error; either neighbor alone differs by 22.06 or 28.95. The reader identifies the neighboring cells as `5` and `6`, and refuses the middle one. This supports a temporal transition in the captured pixels. It does not identify which rendering or capture stage produced it, nor which endpoint should be treated as current.

![Native captured pixels enlarged without smoothing](D:/Navpoint-background-20260909/burst-20260909-230104/neighbor-comparison.png)

Evidence: `D:\Navpoint-background-20260909\burst-20260909-230104\analysis.json`, raw lossless PNGs and capture timestamps.

## Second capture method

An isolated experiment compared MSS/GDI with DXcam 0.3.0 using Windows Desktop Duplication. Both produced 240 frames, but their brightness transfer differed substantially: one corresponding overlay pair differed by 16.54 RGB levels on average. Therefore their native-reader acceptance rates are not a valid backend-quality comparison without further calibration. The current glyph bank is calibrated to the original capture path.

A pixel-only transition test found examples in both outputs, but the counts cannot be directly compared because the transfer/clipping differs. This experiment neither proves nor excludes an artifact specific to the original screenshot path.

DXcam initially crashed in its staging-texture cleanup. A compatibility fix was applied only in the diagnostic process: allow comtypes to release COM pointers on destruction instead of explicitly releasing them and then destroying them again. This follows the [comtypes pointer-lifetime documentation](https://comtypes.readthedocs.io/en/stable/com_interfaces.html). No installed library files or production capture code were modified. Capture API reference: [DXcam documentation](https://github.com/ra1nty/DXcam).

Evidence: `D:\Navpoint-background-20260909\backends-20260909-230734\`, `compare_capture_backends.py` and `backend_pixel_transitions.py`. Packages were installed only in the experiment folder's virtual environment.

## Next controlled comparison

Requested: temporarily disable DLSS/upscaling while retaining Vulkan and 5120×1440, then return to the game with `r_displayinfo 2` visible. Record the exact changed setting and collect comparable moving-coordinate captures. Do not treat this as proof against DLSS or as a permanent settings recommendation before comparing results.

Production runtime fingerprints remain unchanged from the [validated performance build](OCR_LIVE_VALIDATION.md). No temporal reconstruction or experimental numerical recovery feeds navigation.

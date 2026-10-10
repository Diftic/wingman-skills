# NavPoint Vision cleanup — 2026-09-17

## Result

Removed the unused Vision screenshot encoder, extraction prompt, model-message
builder and completion/JSON-response parser. NavPointScanner now validates
structured OCR payloads only. V8 FrameAwareReader remains the sole live reader.

Removed the retired prompt-example coordinate filters and their warning state.
These filters still reached V8 space readings and could reject valid positions
whose coordinates happened to match old prompt examples. Regression tests first
reproduced those rejections and now verify acceptance through the V8 payload path.

Shared coordinate-unit, frame-agreement, plausibility and non-gameplay origin
checks remain. No calibration, arrival or display thresholds changed.

Coordinate tests formerly wrapped in fake model completions now call the payload
validator directly. Tests exclusive to the deleted screenshot/prompt/canary code
were retired. Space facing-direction coverage now checks the returned reading.

The config instruction not to activate the separate VisionAI skill is retained
intentionally: it prevents unnecessary tool routing and is not a Vision reader
option. Historical documentation and offline decoder fixtures remain as evidence.

## Verification and installation

Current suite and package counts are recorded in
[the ledger](ledger/LEDGER.md#current-installed-build--2026-09-17).
Four files were copied from source into the release and installed NavPoint skill:
main.py, scanner.py, navigation.py and overlay_fields.py. All manifest hashes were
checked before and after copying. Python 3.11 syntax checks passed. The installed
V8 model loaded and parsed a space payload under the development Python 3.13.14.

This does not establish a successful live Wingman restart. Restart Wingman before
testing; the Levski live alignment checklist remains pending in the
[handover](HANDOVER_2026-09-15.md). No Wingman core files or waypoint data changed.

Backup and verification evidence:
`D:/Navpoint-background-20260909/vision-cleanup-20260917-224325/`.
This holds source/test backups, the previous release and installed versions of
the four files, the previous manifest, and vision-cleanup-verification.json.


# Published reading instructions

The stable public file is:
https://raw.githubusercontent.com/Diftic/wingman-ai/main/skills/sc_log_reader/updates/instructions.json

Current publication: revision **7**, version **0.3.3-update-test**. Its parsing rules
match revision 5, including Orbituary and Orbituary Clinic. The package rename in
0.5.0 does not change already published JSON bytes.

## Publishing

1. Edit the complete JSON, increment revision and update version/release_notes.
   Never change bytes while reusing a published revision.
2. Validate with `python -m sc_log_reader validate updates/instructions.json`,
   using the project source on PYTHONPATH. Test modified rules against logs and
   handler outcomes before declaring verified builds.
3. Publish this JSON to the path above. Do not include code or personal logs.

The historical wire identifier `sc_log_reader_2` stays in published files for
older clients. Engines 0.5.0+ additionally accept `sc_log_reader`. A future file
using that identifier must require minimum_reader_version 0.5.0 or higher.
Changing the identifier is unnecessary for routine parser updates.

Wingman downloads and stages valid updates automatically, activating at a later
process startup. Instruction Recovery schedules local rollback and blocks rejected
revisions. Manual CLI/review tools remain available for standalone use.

The bundled fallback is separate and preserves its original bytes. A future move
to ShipBit requires an explicit publisher URL change; repository movement alone
does not redirect installed users.

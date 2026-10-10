# Task Ledger: Resource-well resource identification

Last updated: 2026-08-16 Europe/Oslo
Status: delivered

## Intended outcome

- Literal request: Fix nitrogen extraction lookup.
- Desired end state: A nitrogen location request finds only nitrogen Resource Well Extractors in the active save and opens their map.
- Definition of done: Parser distinguishes nitrogen, water, and oil wells; live lookup returns 21 nitrogen matches; every command guides Apex toward short, everyday player language.
- Portability requirement: enabling the skill on any Wingman profile provides the full Satisfactory behavior without profile-specific instructions.

## Constraints and priorities

- Preserve the working map popup, save-driven audit, and bounded spoken responses.
- Derive resource identity from the save; do not classify wells by coordinates or aliases alone.
- Keep existing user configuration and terrain assets intact.
- Use everyday player language and avoid reading internal implementation terms aloud.

## Epistemic state

### Facts

- The latest request was transcribed and routed correctly as a nitrogen-extractor map request.
- The mirror flattened all resource-well references to `Persistent Level`, so matching returned nothing.
- Raw extractor output inventories contain the actual resource descriptor.
- The active save contains 21 nitrogen, 6 water, and 6 crude-oil Resource Well Extractors.
- The first full pipeline pilot recovered resources correctly but also matched six nitrogen packagers; extractor-intent filtering must exclude downstream manufacturing.

## Complete workflow

1. Parse output-inventory descriptors into extractor snapshots.
2. Add regression coverage for descriptor extraction and nitrogen matching.
3. Rebuild the active mirror and verify 21 nitrogen-only matches.
4. Run full verification, regenerate the release, and install it live.
5. Simplify tool guidance and common player-facing replies without changing calculations.
6. Move all required Satisfactory planning and routing behavior into the skill defaults so it works on any Wingman profile.

## Current checkpoint

- Current phase: tester handoff.
- What is complete: the skill is self-contained for any Wingman profile; 481 tests pass with one intentional platform skip; the Navpoint-style installer and generic tester guide are included; the ZIP contents and live installation are verified.
- Next action: testers extract the ZIP, run install.bat, restart Wingman, and enable Satisfactory Assistant on their chosen profile.
- Stop condition: any regression that changes non-resource-well machine classification or map behavior.

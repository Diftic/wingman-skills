# Project instructions

- A question is NEVER to trigger a workflow.
- This is SC Log Reader, developed in the user-approved folder `D:\PycharmProjects\wingman-ai\skills\sc_log_reader`. The temporary project name sc_log_reader_2 was retired for release 0.5.0.
- The user explicitly authorized edits inside this folder. Preserve all other Wingman files and the archived predecessor `skills/OLD_sc_log_reader` unchanged.
- User terminology: Reader = log assembly/JSON interpretation; Handler = normalized-event interpretation/state and persistence; Orchestrator = settings, Wingman integration and lifecycle.
- Keep implementation, generated data, environments and test output inside this project or task-specific temporary directories.
- Do not edit, move, install into, or remove anything from `D:\PycharmProjects\wingman-ai` or installed Wingman skills unless the user explicitly authorizes it.
- Treat `reference/current_skill` as a frozen snapshot. Develop the replacement under `src/`, not in the reference files.
- Do not create symlinks or junctions to the original skill, or tests that write into its directories. Do not launch the original skill or Wingman as a test side effect.
- The JSON in `docs/design` is a design draft, not an implemented or verified reader.
- Instruction updates download and stage automatically after validation, then activate at the next Wingman process startup. User-approved policy changed on 2026-09-20: recovery uses the Instruction Recovery dropdown, rejects reverted revisions and preserves previous/bundled fallbacks. Do not install into the live environment directly.
- Distinguish logged observations, inferred state, requests and confirmed outcomes. Missing or ambiguous fields must not become invented state or money.

# Plan: GitHub release version check + zip release pipeline

**Date:** 2026-07-11 (planned; implementation scheduled for the next session)
**Scope:** sc_log_reader (pilot) and sc_accountant; pattern reusable by any future skill.
**Tree:** 2.1.1 public/live tree conventions. Version-check ONLY, no auto-install.

## Goal

1. Each skill checks GitHub for a newer released version of itself and, when one exists, tells the user in chat with a download link.
2. Skill releases are published as GitHub Releases on `Diftic/wingman-ai` with the same predefined zip naming and versioning already used for the Discord zips.

## Grounding decisions (settled today with the user)

- Release host: existing repo `Diftic/wingman-ai` (public fork, skills development).
- No self-update in 2.1.1: prior investigation (2026-07-07, memory: skill-self-update) found in-place hot-swap breaks on the sys.modules sibling cache; staged self-update is a 3.1.2-only design currently on hold. This feature stops at notify + link.
- Zip naming stays `<skill_name>_v<version>.zip` with a single top-level `<skill_name>/` folder containing the full release_version payload (convention verified against sc_log_reader_v4.8.3.0.zip and reproduced today in v4.8.3.4 / accountant v4.8.3.1).
- Versioning stays the SC-patch mirror scheme (`4.8.3.4` = SC 4.8.3, skill revision 4).

## Design

### Release / tag convention (per skill, shared repo)

- Tag: `<skill_name>-v<version>`, e.g. `sc_log_reader-v4.8.3.4`
- Release title: `SC_LogReader v4.8.3.4 (SC 4.8.3)`
- Asset: `sc_log_reader_v4.8.3.4.zip`
- Release notes: current-version entry from the skill DEVLOG.

### Version check (client side, per skill)

- New leaf module `update_check.py` inside each skill (skills stay self-contained; duplicate the module like atomic_io.py rather than share imports).
- Query `GET https://api.github.com/repos/Diftic/wingman-ai/releases?per_page=30`, filter tags by prefix `<skill_name>-v`, parse versions as 4-int tuples, compare against the skill's `VERSION`.
  (`/releases/latest` is unusable: it is repo-global and tags are per skill.)
- On newer version: chat badge via `printr.print(LogType.WARNING)` (established missing-dep badge pattern), message like: `SC_LogReader v4.8.3.5 is available (installed: v4.8.3.4). Download: <release html_url>`. Link to the release PAGE (html_url), not the raw asset, so users see the notes.
- Failure posture: never block or delay skill init (run in a background thread after prepare), 3 s timeout, all network errors logged at debug level only, no badge on failure.
- Rate limits: unauthenticated API allows 60 req/h/IP; check once per core start with a 24 h cooldown cache at `generated_files/<Skill>/update_check.json` (last_checked_at, latest_seen_tag).
- MANDATORY (lesson, three prior incidents): add `update_check.py` to BOTH `skill_installer_config.json` AND `update_release.py` RELEASE_FILES in each skill.

### Release pipeline (publisher side)

- Keep `update_release.py` as the dev -> release_version sync.
- Add zip building + publish step (open question below on placement). Publish via `gh release create <tag> <zip> --title <title> --notes-file <tmp>` using gh CLI keyring auth.
- Flow per release: bump VERSION fields -> update_release.py -> build zip -> gh release create -> (optional) post the release link on Discord.

### Tests

- Unit: version tuple parse/compare (incl. unequal lengths, malformed tags ignored), tag-prefix filter, cooldown logic, badge emitted only on strictly-newer. Mock HTTP; no live calls in tests.
- Manual live test: publish the current zips as the first releases (sc_log_reader-v4.8.3.4, sc_accountant-v4.8.3.1), then temporarily lower VERSION in the dev env and confirm the badge + link appear once, and the cooldown suppresses a second check.

## Rollout order

1. sc_log_reader (pilot, has the plans/ + test harness precedent)
2. sc_accountant
3. Publish both current zips as the inaugural GitHub Releases (they exist and are verified as of today).

## Open questions for the implementation session

1. HTTP client in `update_check.py`: stdlib `urllib` (zero deps, works in both skills) vs `httpx` (already a log reader dependency; confirm availability in the accountant's runtime before choosing).
2. Zip build placement: fold into each `update_release.py` (single sync+build entry point) vs a separate `build_zip.py`. Leaning fold-in with a `--zip` flag.
3. `~/.secrets` `GITHUB_TOKEN` is stale (401 verified 2026-07-11); decide: refresh it, or standardize the pipeline on gh keyring auth and remove the env var dependency.
4. Whether the check should also fire when the SC_TARGET_VERSION lags the released tag family (probably out of scope; version compare only).
5. Discord message template pointing at the GitHub release (nice-to-have).

## Non-goals

- No auto-download, no auto-install, no staged updates in 2.1.1 (3.1.2 design exists separately, on hold).
- No marketplace/api_version gating work (upstream has none yet).
- No changes outside `skills/`.

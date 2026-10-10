# Phase 6: Release

## Pre-Release Checks
- [ ] All automated tests pass: `pytest tests/sc_log_reader/ -v`
- [ ] Linting clean: `ruff check --fix . && ruff format .`
- [ ] No critical or major issues from beta
- [ ] Version bumped in `main.py` (SC_LogReader.VERSION)

## Documentation
- [ ] Devlog.md updated with:
  - Changelog entry for this version
  - Bug fixes applied
  - New features or improvements
- [ ] TODO.md updated:
  - Testing items marked complete
  - Known issues from beta documented
  - Next version goals added

## Git Operations
- [ ] All changes committed to feature branch
- [ ] PR created with:
  - Summary of changes
  - Test results (367+ tests passing)
  - Bug fixes (channel_change_left, shallow copy, validate parameter)
- [ ] Code review approved
- [ ] Merge to main/develop branch
- [ ] Tag release: `git tag -a vX.Y.Z -m "SC_LogReader vX.Y.Z"`

## Build and Deploy
- [ ] Final build from merged branch
- [ ] Verify build passes Phase 3 + 4 checklists
- [ ] Deploy/publish release

## Post-Release
- [ ] Monitor for user reports in first 48 hours
- [ ] Prepare hotfix branch if critical issues emerge
- [ ] Archive beta tester Game.log files for future regression tests

## Pass Criteria
Clean merge, tagged release, and no critical post-release issues within 48 hours.

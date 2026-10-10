# Phase 5: Beta Test

## Preparation
- [ ] Build release candidate with `python build.py`
- [ ] Package with release notes listing:
  - New features since last version
  - Known limitations
  - Required configuration steps
- [ ] Create feedback form (Google Forms or similar) with:
  - Star Citizen install path
  - Operating system / GPU / RAM
  - SC version (LIVE/PTU/EPTU)
  - Events detected correctly (checklist)
  - Events missed or incorrect
  - Crashes or errors (with logs)
  - General feedback / suggestions

## Tester Selection
- [ ] Minimum 3 testers with different:
  - Install paths (C:, D:, custom)
  - Hardware configurations
  - Gameplay styles (combat, trading, mining, exploration)

## Distribution
- [ ] Send build package to testers
- [ ] Include installation instructions
- [ ] Include Phase 2 checklist as testing guide
- [ ] Request Game.log files for regression suite expansion

## Feedback Collection
- [ ] Collect responses within agreed timeframe (1-2 weeks)
- [ ] Triage issues by severity:
  - **Critical**: Crashes, data loss, blocks other skills
  - **Major**: Events missed, incorrect data, performance issues
  - **Minor**: Cosmetic, edge cases, nice-to-have improvements
- [ ] Add new Game.log files to `Test findings/Parsed logs/` for regression tests

## Resolution
- [ ] Fix all critical issues
- [ ] Fix major issues where feasible
- [ ] Document known minor issues in TODO.md
- [ ] Re-run full automated test suite after fixes
- [ ] Send fixed build to testers who reported critical/major issues

## Pass Criteria
No critical issues AND major issues resolved or documented with workarounds.

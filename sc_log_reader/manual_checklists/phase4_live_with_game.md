# Phase 4: Live Environment — Full Test (Game Running)

## Prerequisites
- [ ] Phase 3 passed
- [ ] Star Citizen LIVE build running
- [ ] Built WingmanAiCore.exe running

## Event Detection
Repeat all event detection checks from Phase 2:
- [ ] Session events (start, join PU)
- [ ] Location events (changes, names)
- [ ] Zone events (armistice, jurisdiction)
- [ ] Ship events (entry, exit, name cleanup)
- [ ] Contract events (accept, objective, complete, fail)
- [ ] Travel events (quantum, ATC)
- [ ] Health events (injury, med bed)
- [ ] Economy events (rewards)

## AI Tool Verification
- [ ] All 3 tools return correct data (same as Phase 2)

## Extended Session Test (1 hour minimum)
- [ ] Run for at least 1 hour of active gameplay
- [ ] No crashes or freezes during extended session
- [ ] Memory usage remains stable (no unbounded growth)
- [ ] Events continue to be detected after 30+ minutes
- [ ] Notification batching still works correctly

## Game Crash/Restart Resilience
- [ ] Force-quit Star Citizen while monitoring
- [ ] SC_LogReader does not crash
- [ ] Restart Star Citizen
- [ ] SC_LogReader resumes monitoring new Game.log
- [ ] Events detected correctly after game restart

## Performance
- [ ] No noticeable impact on game FPS
- [ ] AI response time not degraded by log monitoring
- [ ] CPU usage of WingmanAI reasonable during gameplay

## Pass Criteria
Same as Phase 2 PLUS extended session stability AND crash resilience.

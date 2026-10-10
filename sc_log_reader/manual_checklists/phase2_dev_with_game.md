# Phase 2: Dev Environment — Full Test (Game Running)

## Prerequisites
- [x] Phase 1 passed
- [x] Star Citizen LIVE build running
- [x] Game.log path configured in SC_LogReader settings

## Startup Verification
- [x] SC_LogReader detects Game.log automatically or via configured path
- [x] "Monitoring Game.log" message appears
- [x] No errors in console during initial log parsing

## Event Detection Checklist

### Session Events
- [ ] Session start detected (player name correct)
- [ ] Join PU detected (server/shard info)

### Location Events
- [ ] Location change detected when moving between areas
- [ ] Location names resolve correctly (not raw codes)

### Zone Events
- [ ] Entering armistice zone detected
- [ ] Leaving armistice zone detected
- [ ] Jurisdiction change detected

### Ship Events
- [ ] Ship entry detected (correct ship name)
- [ ] Ship exit detected
- [ ] Ship name cleaned (no manufacturer prefix, no player suffix)

### Contract Events
- [ ] Contract accepted detected (mission name + ID)
- [ ] Objective updates detected
- [ ] Contract completion detected
- [ ] Contract failure detected (if applicable)

### Travel Events
- [ ] Quantum route set detected
- [ ] ATC connection detected

### Health Events
- [ ] Injury detected (severity, body part, tier)
- [ ] Med bed heal detected (parts healed)

### Economy Events
- [ ] Reward earned detected (amount)

## AI Tool Verification
- [ ] `get_recent_game_events` returns actual events with timestamps
- [ ] `get_recent_game_events` with count parameter limits results
- [ ] `get_recent_game_events` with event_type filter works
- [ ] `get_current_game_state` returns player name, location, ship, etc.
- [ ] `get_active_missions` returns accepted contracts with objectives

## Notification System
- [ ] Proactive notifications appear for detected events
- [ ] Notification batching works (events within 4s grouped)
- [ ] Duplicate notifications suppressed within 10s cooldown
- [ ] Throttling pauses after 5 auto-messages without user input
- [ ] User message resets throttle counter
- [ ] Category toggles respected (disable contracts -> no contract notifications)
- [ ] Master toggle disables all notifications

## State Persistence
- [ ] State accumulates correctly over play session
- [ ] No memory leaks during extended monitoring (check with task manager)

## Pass Criteria
All event categories detected correctly AND AI tools return accurate data.

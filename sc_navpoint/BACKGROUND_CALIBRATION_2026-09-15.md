# Calibration before navigation

Activation starts one dedicated background thread. While no target is selected,
it requests a full-precision local capture and waits one second between attempts.
It uses the existing foreground gate, capture lock, V8 reader and its shared
PlanetRotationTracker. It pauses during navigation; navigation's faster captures
keep the same tracker current. Stopping/arriving/deleting the target lets idle
calibration resume. Unloading stops the background thread with a bounded join.

Idle captures do not publish a position or overwrite the navigation outcome/ring
status. They bypass the higher-level capture actions: no waypoint changes,
arrival logic, server-change cleanup or spoken warnings. Reader failure details
remain in local capture diagnostics. The old fixed-font reader is not polled
for calibration because it has no planet tracker.

The 20-sample/30-second observation requirement, 50-meter residual tolerance,
freshness checks and planet/session identity gates remain unchanged. A warm valid
model is reusable immediately, but initial activation, unreadable panels, frame
changes or a lost fit can still require a calibration wait.

Validation: 1,221 tests passed in 28.84 seconds. Thread lifetime/unload, idle
capture guards, shared state isolation and activation startup are covered.
A synthetic paired-coordinate sequence passes through the real FrameAwareReader
and PlanetRotationTracker without a target, then a target is selected and receives
valid rotation without resetting the accumulated samples.

Installed source and staged package updated. Restart Wingman and activate the
skill to start calibration. Actual live time-to-direction remains to be checked.

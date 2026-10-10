# Concise navigation speech

Observed at 18:57:06 in wingman-core.2026-09-15_18-47-16.log: the generated reply
reused the previous trip's 999-meter approach and arrival wording for a new
target still 4.2 kilometers away. Actual arrival was at 18:58:13. The installed
prompt also explicitly requested the obsolete manual-position-update reminder.

The skill now supplies a fixed instant response from execute_tool for
navigate_to: `Navigating to [confirmed target name].` The tool disables generated
summaries and waiting filler. Error results still speak their actual error and
hint. Other tools retain the normal dispatcher behavior. The installed Wingman
3.2.1 handler was checked read-only: an instant response returns before the
follow-up summarization call. No Wingman files were changed.

Automatic messages are `Slow down for final approach.`, `Approaching: [distance].`
and `Arrived.` They still use direct TTS, but no longer append assistant messages
to conversation history. Arrival thresholds and the two-reading confirmation
are unchanged. The skill prompt removes the manual-update reminder and forbids
repeating or predicting earlier trip announcements.

Validation: 1,215 tests passed in 29.51 seconds. New checks cover fixed success
replies, preserved failure instructions, unchanged dispatch for other tools,
disabled summaries/wait filler, short alerts and no alert history insertion.
Source, staged package and installed copy updated. Restart and a live navigation
command are required to confirm speech in the app.

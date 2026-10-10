# Spoken distances

User requested explicit decimal pronunciation and full unit names. Speech
guidance and approach announcements now use `format_spoken_distance`: for
example, `4.5 km` becomes `4 point 5 kilometers`, and `98 m` becomes `98 meters`.
Fractional digits are separated individually; whole values omit trailing zeros.
Display precision is preserved. The ring and HUD keep their compact formatting.

The skill prompt asks the conversation model to preserve the explicit word
`point` and full unit names. Direct skill announcements send this text to TTS;
model-generated replies can still deviate from instructions.

Validation: 65 focused speech/navigation/arrival tests passed in 0.88 seconds,
including the actual skill-to-TTS helper boundary with a recording collaborator.
This checks the submitted text, not the acoustic output of the selected voice.
Installed source and staged package updated; restart Wingman for a live listen.

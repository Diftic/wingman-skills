# Automatic startup and compact dashboard card — v4.9.0.25

Requested: start NavPoint with Wingman and match Accountant's startup card and QR
size, showing no separate phone/tablet HTTP address.

Changed auto_activate to true. Once NavPoint is enabled for a wingman, Wingman's
startup activation path prepares it without a voice request. The dashboard card
uses Accountant's threaded announcement and 15-second startup delay, so it does
not block preparation or arrive during the loading screen. An announcement is
discarded if its server was unloaded or replaced during the wait.

The card reads:

    NavPoint dashboard ready.
    Scan with your phone, or open:
    http://127.0.0.1:7869

The attached QR contains the LAN dashboard URL. The PNG uses Accountant's scale
of three pixels per module and four-module quiet border. With the reference URL
it is 99 by 99 pixels and matches Accountant's generator pixel for pixel. The
shorter text also removes the long line that widened the chat bubble. If LAN
discovery or QR generation fails, the card offers the computer link without a
scan instruction. No browser is opened automatically.

Verification: full suite 1,268 passed in 35.96 seconds, including QR decoding,
automatic-start metadata, delayed startup, unload/replacement and missing-QR
cases. The ZIP upgraded an isolated v4.9.0.24 installation, preserving saved data
and profile settings. Packaged Python syntax passed the Python 3.11 check.
Actual Wingman rendering and cold-start delivery still require a restarted UI.

Artifact: sc_navpoint_v4.9.0.25.zip, with its .zip.sha256 checksum.
Evidence: D:/Navpoint-background-20260909/startup-card-20260919/verification/.
Packaging initially left the user's actual installed skill unchanged. On the
follow-up startup report, the installed copy was found to still be v4.9.0.23 with
auto_activate false; the startup log showed only discoverable NavPoint. Updated
the actual installed skill to v4.9.0.25 and verified all runtime files against
the ZIP. Auto-activation is now true. Wingman was left running and requires a full
restart to load the update. Wingman core and profile settings were not changed.
Installation backup/manifest: D:/Navpoint-background-20260909/live-v211-v49025-20260919/.

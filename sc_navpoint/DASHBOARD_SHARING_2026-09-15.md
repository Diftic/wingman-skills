# Dashboard link and phone access

Activation posts a Wingman chat message using Accountant's `LogSource.WINGMAN`
and `additional_data.image_base64` format. It includes the loopback URL for this
computer and, when an outbound interface is available, the LAN URL and a QR code
for a phone/tablet on the same network. The server already listens on all local
interfaces; this change does not modify binding or firewall configuration.

Navigation no longer opens the browser. The native ring is independent of the
dashboard. An explicit `show_navpoint_hud` request can still open the browser.
Prompt and tool result wording describe this behavior.

QR generation uses a NavPoint-local copy of Accountant's vendored Project Nayuki
MIT-licensed qrcodegen.py, with the original license retained. Accountant is not
a runtime dependency. If LAN discovery fails, the computer link remains; the
skill does not present a loopback QR as usable from a phone.

Verification: 1,208 full-suite checks passed for the link/no-automatic-browser
change before adding QR support. After QR support, 85 focused checks passed in
2.69 seconds, including independent OpenCV decoding of the generated PNG,
startup chat payload, LAN lookup failure, explicit open and navigation behavior.
Actual phone connectivity and the installed chat rendering require a live test
after Wingman restart.

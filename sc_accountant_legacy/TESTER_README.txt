SC ACCOUNTANT
Personal Accounting for Star Citizen
Version 4.8.3.1 (qualified against Star Citizen 4.8.3)
Author: Mallachi


WHAT IT DOES

A full personal-accounting system for Star Citizen, built as a Wingman AI skill.
Tracks your aUEC, fleet, trade positions, hauls, and trade opportunities. Comes
with a web dashboard you can open in any browser, including your phone.


INSTALL

1. Make sure Wingman AI is closed.
2. Double-click install.bat in this folder. Click "Yes" if Windows asks for
   permission (this lets it copy files into your Wingman AI folder).
3. Start Wingman AI. The skill loads automatically and assigns to your wingman.

If Windows pops a UAC prompt the first time the dashboard starts, that is the
skill adding a one-time firewall rule so your phone can reach the dashboard.
Click "Yes". You will not be asked again.


USING IT

Talk to your wingman like normal. A few examples:

  "What's my balance?"
  "Record 500 aUEC for fuel."
  "Register my Prospector, purchased for 2.1 million."
  "What should I trade right now?"
  "When will my Prospector break even?"
  "Open the accounting dashboard."

When the skill loads, your wingman drops a QR code and a LAN URL into the chat.
Scan the QR with your phone to open the dashboard on your mobile, or open the
URL in any browser on your network.

The dashboard runs on localhost:7863 by default. Tabs include Balance Sheet,
Operations, Ledger, My Assets, Portfolio, Opportunities, and About.


SIBLING SKILLS

SC_LogReader (recommended): captures your trades and ship boardings from the
game log automatically. Without it, you can still enter everything by voice.

UEXCorp (recommended): provides live market prices, ship valuations, and
trade-route suggestions. Without it, market features are limited.

The About tab shows whether each sibling is loaded and on the right SC patch.


KNOWN LIMITATIONS

- Single-player. Each wingman has its own ledger; no cloud sync.
- The skill trusts what you tell it. There is no live link to your in-game
  account; balances are tracked locally.
- Auto-sync only captures commodity and item trades. Mission rewards, bounties,
  fuel, and fines must be recorded manually (or by voice).
- Market prices come from UEX (uexcorp.space) and may be up to 24h stale.


REPORTING ISSUES

When reporting a bug, please include:
  - Your SC patch version
  - The skill version shown in the About tab
  - What you said to the wingman, and what happened
  - A screenshot of the wingman log if there's an error

See RELEASE_NOTES_v4.7.2.txt for what's new in this build.

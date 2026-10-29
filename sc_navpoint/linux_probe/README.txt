NavPoint Linux probe
====================

Thanks for helping! This is a tiny test skill for Wingman AI. It checks whether
the NavPoint skill could see Star Citizen on your Linux machine. Nothing else
needs to be installed: it runs inside Wingman itself. It takes a few minutes.

It is READ-ONLY: it changes no settings and sends nothing anywhere. It saves a
picture of the small top-right corner of the game (the r_displayinfo position
panel), never a full screenshot. Process command lines are not stored, and your
home folder is shown as "~".

Install
-------
1. Fully close Wingman AI.
2. Copy the folder "navpoint_linux_probe" (the whole folder, not just its
   files) into Wingman's custom skills folder:

     Wingman installed natively on Linux:
       ~/.local/share/WingmanAI/custom_skills/

     Wingman running under Wine/Proton: inside that Wine prefix,
       drive_c/users/<your user>/AppData/Roaming/ShipBit/WingmanAI/custom_skills/

   Create the custom_skills folder if it does not exist yet.
3. Start Wingman AI and enable "NavPoint Linux Probe" in your wingman's skills.

Run the test
------------
1. Start Star Citizen and get into the game world (standing in a station or on
   a planet is fine).
2. Open the game console with the ~ key, type   r_displayinfo 2   and press
   Enter. Close the console. The position panel shows at the top right.
3. With the game focused, tell your wingman (voice or push-to-talk):
       "Run the NavPoint Linux probe."
   Keep the game focused for about 5 seconds.
4. Your wingman says the report is ready. It is in your home folder, named
   navpoint_probe_<date-time>.zip (under Wine: the Windows user folder inside
   the prefix, drive_c/users/<your user>/).
5. Send that ZIP back, and say how you start Star Citizen (Lutris, Steam/Proton,
   other) and how Wingman is installed (native Linux or under Wine).

If you can, run it twice: once with the game in fullscreen and once windowed.

Afterwards you can delete the navpoint_linux_probe folder from custom_skills.

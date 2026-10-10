@echo off
setlocal
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\youtube_video_player"

echo.
echo Installing YouTube Video Player skill...
echo Destination: %DEST%
echo.

robocopy "%~dp0." "%DEST%" /E /IS /IT /XF install.bat TESTER_README.md RELEASE_NOTES_v0.1.0.txt /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set RC=%errorlevel%

rem Robocopy: 0-7 = success ^(0=nothing to do, 1-3=copies happened, etc.^), 8+ = real error.
if %RC% leq 7 goto :success
goto :failure

:success
echo Done.
echo.
echo Next steps:
echo   1. If Wingman Player isn't installed yet, get it from:
echo      https://github.com/Diftic/Wingman-Player/releases/latest
echo      [download Wingman-Player-Setup.msi and run it]
echo   2. Restart Wingman AI
echo   3. Activate the YouTube Video Player skill in your wingman config
echo   4. Wingman will prompt for your YouTube Data API v3 key on first use
echo.
echo The skill auto-launches the player when needed, provided it's
echo installed at the default per-user MSI location.
goto :end

:failure
echo Could not install skill files.
echo Robocopy reported a real error ^(exit code %RC%, anything 8 or above^).
echo.
echo Try:
echo   - Run this installer as your normal user, not Administrator
echo   - Make sure %DEST% isn't read-only or held open by another program
echo   - Reboot and try again if a previous Wingman AI is still running
echo.
echo If it keeps failing, copy this whole window's text and send it to
echo the skill author so we can diagnose.
goto :end

:end
echo.
pause
endlocal

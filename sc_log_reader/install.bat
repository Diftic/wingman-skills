@echo off
setlocal
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\sc_log_reader"

echo.
echo Installing SC Log Reader skill...
echo Destination: %DEST%
echo.

robocopy "%~dp0." "%DEST%" /E /IS /IT /XF install.bat TESTER_README.md /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set RC=%errorlevel%

rem Robocopy: 0-7 = success ^(0=nothing to do, 1-3=copies happened, etc.^), 8+ = real error.
if %RC% leq 7 goto :success
goto :failure

:success
echo Done.
echo.
echo Next steps:
echo   1. Fully close Wingman AI ^(end the WingmanAiCore process via Task Manager
echo      if it stays resident in the system tray^)
echo   2. Relaunch Wingman AI
echo   3. Confirm the skill is enabled in your wingman's Skills settings
echo   4. SC_LogReader auto-detects the StarCitizen folder. Override only if
echo      needed via the "Star Citizen Path" custom property
echo   5. To contribute logs to improve parser coverage, say "donate logs"
echo      to your Wingman ^(opens a local preview page in your browser^)
goto :end

:failure
echo Could not install skill files.
echo Robocopy reported a real error ^(exit code %RC%, anything 8 or above^).
echo.
echo Try:
echo   - Run this installer as your normal user, not Administrator
echo   - Make sure %DEST% isn't read-only or held open by another program
echo   - Close Wingman AI completely ^(end WingmanAiCore in Task Manager if
echo     it stays running^) before re-running install.bat
echo.
echo If it keeps failing, copy this whole window's text and send it to
echo the skill author so we can diagnose.
goto :end

:end
echo.
pause
endlocal

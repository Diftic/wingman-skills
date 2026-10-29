@echo off
setlocal
set "RC=1"
if not defined AppData goto :no_appdata
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\sc_telemetry"

echo.
echo Installing Star Citizen Telemetry skill...
echo Destination: %DEST%
echo Close Wingman AI before installing. Run as your normal Windows user.
echo.

rem A ZIP must be fully extracted before this installer can be used.
for %%F in (__init__.py main.py default_config.yaml reaction_prompt.md dependencies\sc_telemetry_core\handler.py dependencies\sc_telemetry_core\schema.desc) do (
    if not exist "%~dp0%%F" goto :incomplete
)

robocopy "%~dp0." "%DEST%" /E /IS /IT /XF installer.bat README.md DESIGN.md TELEMETRY_REPORT.md DATA_SOURCES.md /XD __pycache__ tests tools .pytest_cache /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set "RC=%errorlevel%"
rem Robocopy 0-7 means success; 8 or above is a copy failure.
if %RC% geq 8 goto :failure
set "RC=0"
echo Install complete!
echo.
echo Next steps:
echo   1. Restart Wingman AI and enable Star Citizen Telemetry on your wingman.
echo   2. In the skill's settings, switch on "Enable Star Citizen telemetry".
echo   3. Quit the RSI Launcher completely (also from the tray) and start it again.
echo   4. Start Star Citizen and ask: "What's my ship status?"
echo.
echo Needs a Wingman AI version with gRPC support.
goto :end

:incomplete
echo ERROR: The installer package is incomplete.
echo Extract the entire ZIP to a folder, then run installer.bat there.
goto :end

:no_appdata
echo ERROR: The Windows AppData folder could not be determined.
echo Run this installer as your normal Windows user.
goto :end

:failure
echo ERROR: Could not install skill files. Robocopy exit code: %RC%
echo Close Wingman AI completely, then run installer.bat again.
echo Check that the destination folder is writable.
goto :end

:end
echo.
pause
endlocal & exit /b %RC%

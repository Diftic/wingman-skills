@echo off
setlocal
set "RC=1"
if not defined AppData goto :no_appdata
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\sc_distances"

echo.
echo Installing SC Distances skill...
echo Destination: %DEST%
echo Close Wingman AI before installing. Run as your normal Windows user.
echo.

rem A ZIP must be fully extracted before this installer can be used.
for %%F in (__init__.py main.py default_config.yaml dependencies\sc_data.py dependencies\sc_distance.py data\index.json) do (
    if not exist "%~dp0%%F" goto :incomplete
)

rem Refresh code and bundled data. Downloaded data updates live in Wingman's generated files and are kept.
robocopy "%~dp0." "%DEST%" /E /IS /IT /XF installer.bat README.md /XD __pycache__ /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set "RC=%errorlevel%"
rem Robocopy 0-7 means success; 8 or above is a copy failure.
if %RC% geq 8 goto :failure
set "RC=0"
echo Install complete!
echo.
echo Next steps:
echo   1. Restart Wingman AI.
echo   2. Enable SC Distances in your wingman's Skills settings.
echo   3. Ask for example: "How far is Lorville from Everus Harbor?"
echo.
echo The location data updates itself from GitHub after Star Citizen patches.
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

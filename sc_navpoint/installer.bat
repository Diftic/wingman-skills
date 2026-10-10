@echo off
setlocal
set "RC=1"
if not defined AppData goto :no_appdata
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\sc_navpoint"

echo.
echo Installing SC NavPoint skill...
echo Destination: %DEST%
echo Close Wingman AI before installing. Run as your normal Windows user.
echo.

rem A ZIP must be fully extracted before this installer can be used.
for %%F in (main.py default_config.yaml frame_reader.py scanner.py navpoint_location_names.py models\specialist_v8\model.onnx models\specialist_v8\characters.json _vendor\cv2\cv2.pyd) do (
    if not exist "%~dp0%%F" goto :incomplete
)

rem Refresh defaults and code. Profiles and waypoint data live elsewhere.
robocopy "%~dp0." "%DEST%" /E /IS /IT /XF installer.bat TESTER_README.md /XD __pycache__ /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set "RC=%errorlevel%"
rem Robocopy 0-7 means success; 8 or above is a copy failure.
if %RC% geq 8 goto :failure
rem Remove only NavPoint's retired module, which collides with SC Log Reader.
if exist "%DEST%\location_names.py" del /q "%DEST%\location_names.py"
if exist "%DEST%\location_names.py" goto :obsolete_module
set "RC=0"
echo Install complete!
echo.
echo Next steps:
echo   1. Restart Wingman AI.
echo   2. Enable Star Citizen NavPoint in your wingman's Skills settings.
echo   3. In Star Citizen, open the console and enter: r_displayinfo 2
echo   4. Keep the game focused and the position panel visible.
echo   5. Check the Display to capture setting if you use multiple monitors.
echo.
echo NavPoint reads the screen; it does not send input to the game.
goto :end

:obsolete_module
set "RC=1"
echo ERROR: Could not remove NavPoint's obsolete location_names.py.
echo Close Wingman AI completely and run installer.bat again.
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

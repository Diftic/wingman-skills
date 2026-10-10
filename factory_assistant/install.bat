@echo off
setlocal
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\factory_assistant"
set "PARSER_DIR=%DEST%\factory_games\satisfactory\reader\tools\save_parser"

echo.
echo Installing Factory Assistant skill...
echo Destination: %DEST%
echo.

robocopy "%~dp0." "%DEST%" /E /IS /IT /XF install.bat TESTER_README.md /XD __pycache__ .pytest_cache .ruff_cache tests node_modules /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set RC=%errorlevel%

rem Robocopy: 0-7 = success ^(0=nothing to do, 1-3=copies happened, etc.^), 8+ = real error.
if %RC% leq 7 goto :success
goto :failure

:success
echo Done.
call :ensure_parser_runtime
echo.
echo Next steps:
echo   1. Fully close Wingman AI ^(end WingmanAiCore in Task Manager if it
echo      stays open in the system tray^)
echo   2. Relaunch Wingman AI
echo   3. Enable Factory Assistant in any Wingman's Skills settings
echo   4. Load a save in your game ^(Satisfactory or Dyson Sphere Program^), then save once
goto :end

:ensure_parser_runtime
if not exist "%PARSER_DIR%\package.json" goto :eof
if exist "%PARSER_DIR%\node_modules\@etothepii\satisfactory-file-parser\package.json" (
    echo Save parser dependency already installed.
    goto :eof
)
where npm >nul 2>&1
if errorlevel 1 (
echo The skill was copied, but the save reader needs Node.js and npm.
echo Install Node.js, then run this installer again.
    goto :eof
)
echo Installing optional save parser dependency...
pushd "%PARSER_DIR%" >nul
if exist package-lock.json (
    call npm ci --omit=dev --ignore-scripts
) else (
    call npm install --omit=dev --ignore-scripts
)
set "NPM_RC=%errorlevel%"
popd >nul
if not "%NPM_RC%"=="0" (
    echo The skill was copied, but the save reader could not be installed.
    echo Check your internet connection, then run this installer again.
) else (
    echo Save parser dependency installed.
)
goto :eof

:failure
echo Could not install skill files.
echo Robocopy reported a real error ^(exit code %RC%, anything 8 or above^).
echo.
echo Try:
echo   - Run this installer as your normal user, not Administrator
echo   - Make sure %DEST% is not read-only or held open by another program
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

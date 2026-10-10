@echo off
setlocal
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\satisfactory_assistant"
set "SRC=%~dp0."
set "CONFIG_HINT=%AppData%\ShipBit\WingmanAI\3_1_1\configs\Satisfactory"
set "PARSER_DIR=%DEST%\tools\save_parser"

if exist "%~dp0release_version\main.py" set "SRC=%~dp0release_version"

echo.
echo Installing Satisfactory Assistant skill...
echo Source: %SRC%
echo Destination: %DEST%
echo.

robocopy "%SRC%" "%DEST%" /E /IS /IT /XF install.bat TESTER_README.md RELEASE_NOTES_v0.1.0.txt /XD __pycache__ .pytest_cache .ruff_cache tests node_modules /NJH /NJS /NFL /NDL /NC /NS /NP >nul 2>&1
set RC=%errorlevel%

rem Robocopy: 0-7 = success (0=nothing to do, 1-3=copies happened, etc.), 8+ = real error.
if %RC% leq 7 goto :success
goto :failure

:success
echo Done.
call :ensure_parser_runtime
echo.
echo Next steps:
echo   1. Fully close Wingman AI (end WingmanAiCore in Task Manager if needed)
echo   2. Relaunch Wingman AI
echo   3. Open your Satisfactory config:
echo      %CONFIG_HINT%
echo   4. Confirm your Satisfactory wingman has SatisfactoryAssistant enabled
echo   5. Start or load a Satisfactory save before asking for save-specific plans
echo   6. Leave "Satisfactory Saved Directory" blank for auto-detect, or set it
echo      to your FactoryGame Saved folder if auto-detect does not find it
goto :end

:ensure_parser_runtime
if not exist "%PARSER_DIR%\package.json" goto :eof
if exist "%PARSER_DIR%\node_modules\@etothepii\satisfactory-file-parser\package.json" (
    echo Save parser dependency already installed.
    goto :eof
)
where npm >nul 2>&1
if errorlevel 1 (
    echo Warning: npm was not found. Factory audit, actuals, and locate need the
    echo          optional save parser dependency. Install Node.js/npm, then run
    echo          npm ci --omit=dev --ignore-scripts in:
    echo          %PARSER_DIR%
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
    echo Warning: npm could not install the save parser dependency. Factory audit,
    echo          actuals, and locate will stay unavailable until it is installed
    echo          or Satisfactory Parser Runtime Directory points at node_modules.
) else (
    echo Save parser dependency installed.
)
goto :eof

:failure
echo Could not install skill files.
echo Robocopy reported a real error (exit code %RC%, anything 8 or above).
echo.
echo Try:
echo   - Run this installer as your normal user, not Administrator
echo   - Make sure %DEST% is not read-only or held open by another program
echo   - Close Wingman AI completely before re-running install.bat
echo.
echo If it keeps failing, copy this whole window's text and send it to the skill author.
goto :end

:end
echo.
pause
endlocal
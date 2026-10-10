@echo off
setlocal
set "DEST=%AppData%\ShipBit\WingmanAI\custom_skills\sc_accountant"
echo Installing SC Accountant to %DEST%...
robocopy "%~dp0." "%DEST%" /E /IS /IT /XF install.bat TESTER_README.md
if %errorlevel% leq 7 (
    echo.
    echo Install complete!
) else (
    echo.
    echo ERROR: Install failed with code %errorlevel%
)
pause

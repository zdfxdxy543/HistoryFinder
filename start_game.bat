@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "GAME_URL=http://127.0.0.1:8765/play/"
set "HEALTH_URL=http://127.0.0.1:8765/api/health"
set "PYTHON_CMD=python"

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo [HistoryFinder] Python was not found in PATH.
        echo Install Python 3 or add it to PATH, then run this file again.
        pause
        exit /b 1
    )
    set "PYTHON_CMD=py -3"
)

powershell.exe -NoProfile -Command "try { $r = Invoke-RestMethod -TimeoutSec 2 '%HEALTH_URL%'; if ($r.status -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
if not errorlevel 1 (
    echo [HistoryFinder] The game server is already running.
    start "" "%GAME_URL%"
    exit /b 0
)

if not exist "player\dist\index.html" (
    where npm.cmd >nul 2>nul
    if errorlevel 1 (
        echo [HistoryFinder] Frontend files are missing and npm.cmd was not found.
        echo Install Node.js, then run this file again.
        pause
        exit /b 1
    )
    echo [HistoryFinder] Building the player frontend...
    pushd "player"
    call npm.cmd run build
    if errorlevel 1 (
        popd
        echo [HistoryFinder] Frontend build failed.
        pause
        exit /b 1
    )
    popd
)

echo [HistoryFinder] Starting the game server...
start "HistoryFinder Server" cmd.exe /k "%PYTHON_CMD% -m viewer.server --host 127.0.0.1 --port 8765"

for /l %%I in (1,1,20) do (
    powershell.exe -NoProfile -Command "try { $r = Invoke-RestMethod -TimeoutSec 1 '%HEALTH_URL%'; if ($r.status -eq 'ok') { exit 0 } } catch {}; exit 1" >nul 2>nul
    if not errorlevel 1 goto :ready
    timeout /t 1 /nobreak >nul
)

echo [HistoryFinder] The server did not become ready in time.
echo Check the HistoryFinder Server window for an error message.
pause
exit /b 1

:ready
echo [HistoryFinder] Ready: %GAME_URL%
start "" "%GAME_URL%"
exit /b 0

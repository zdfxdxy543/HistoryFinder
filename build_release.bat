@echo off
setlocal EnableExtensions

cd /d "%~dp0"
set "RELEASE_VERSION=0.1.0"
set "RELEASE_NAME=HistoryFinder-v%RELEASE_VERSION%-windows-x64"
set "RELEASE_DIR=%CD%\release\%RELEASE_NAME%"
set "RELEASE_ZIP=%CD%\release\%RELEASE_NAME%.zip"

where python >nul 2>nul
if errorlevel 1 (
    echo [HistoryFinder] Python was not found in PATH.
    exit /b 1
)

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [HistoryFinder] PyInstaller is missing.
    echo Run: python -m pip install pyinstaller
    exit /b 1
)

where npm.cmd >nul 2>nul
if errorlevel 1 (
    echo [HistoryFinder] npm.cmd was not found. Install Node.js first.
    exit /b 1
)

echo [HistoryFinder] Building the player frontend...
pushd player
call npm.cmd run build
if errorlevel 1 (
    popd
    echo [HistoryFinder] Frontend build failed.
    exit /b 1
)
popd

echo [HistoryFinder] Building the Windows executable...
python -m PyInstaller --noconfirm --clean packaging\HistoryFinder.spec
if errorlevel 1 (
    echo [HistoryFinder] PyInstaller build failed.
    exit /b 1
)

echo [HistoryFinder] Creating release package...
powershell.exe -NoProfile -Command "$targets = @('%RELEASE_DIR%', '%RELEASE_ZIP%'); foreach ($target in $targets) { if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force } }; New-Item -ItemType Directory -Path '%RELEASE_DIR%' -Force | Out-Null; Copy-Item -Path '%CD%\dist\HistoryFinder\*' -Destination '%RELEASE_DIR%' -Recurse -Force; Copy-Item -LiteralPath '%CD%\README.md' -Destination '%RELEASE_DIR%\README.md' -Force; Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%RELEASE_ZIP%' -CompressionLevel Optimal"
if errorlevel 1 (
    echo [HistoryFinder] Release packaging failed.
    exit /b 1
)

echo [HistoryFinder] Release ready:
echo   %RELEASE_DIR%
echo   %RELEASE_ZIP%
exit /b 0

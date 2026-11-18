@echo off
REM Ein-Klick-Build des Standalone-Fotobuch-Executables unter Windows.
REM Legt eine isolierte Build-venv an, installiert Build-Deps und ruft PyInstaller.
setlocal
cd /d "%~dp0\.."

echo === Build-Umgebung vorbereiten ===
if not exist ".venv-build\Scripts\python.exe" (
  python -m venv .venv-build
  if errorlevel 1 (
    echo Python 3.11+ wurde nicht gefunden. Bitte von https://www.python.org/downloads/ installieren.
    pause
    exit /b 1
  )
)

echo === Abhaengigkeiten installieren (kann einige Minuten dauern) ===
".venv-build\Scripts\python.exe" -m pip install --upgrade pip
".venv-build\Scripts\python.exe" -m pip install -r packaging\requirements-build.txt
if errorlevel 1 (
  echo Installation fehlgeschlagen.
  pause
  exit /b 1
)

echo === Bundle bauen ===
".venv-build\Scripts\python.exe" packaging\build.py
if errorlevel 1 (
  echo Build fehlgeschlagen.
  pause
  exit /b 1
)

echo.
echo Fertig. Ergebnis liegt unter: dist\Fotobuch\Fotobuch.exe
echo (Ordner "dist\Fotobuch" komplett weitergeben oder als ZIP/Installer packen.)
pause
endlocal

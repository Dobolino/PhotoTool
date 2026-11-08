@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title PhotoTool - Quellcode aktualisieren
color 0F

echo.
echo ========================================
echo   PhotoTool - Quellcode aktualisieren
echo ========================================
echo.
echo Installiertes Programm: bitte "Updates" oder den Installer verwenden.
echo Quellcode: aktualisiert den aktuellen Branch von seinem Upstream.
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Git wurde nicht gefunden.
  echo.
  echo Ohne Git bitte so aktualisieren:
  echo   1. Gewuenschte Version auf GitHub Releases waehlen
  echo   2. Installer verwenden oder Source code ZIP herunterladen
  echo   3. Quellcode in einen neuen Programmordner entpacken
  echo.
  echo Git installieren: https://git-scm.com/download/win
  echo.
  pause
  exit /b 1
)

if not exist ".git" (
  echo FEHLER: Dieser Ordner ist kein Git-Clone.
  echo.
  echo Dann entweder:
  echo   - Projekt per git clone neu holen, oder
  echo   - ZIP von GitHub erneut herunterladen und entpacken.
  echo.
  pause
  exit /b 1
)

git symbolic-ref --quiet HEAD >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Kein aktiver Branch ^(z.B. ein Release-Tag^).
  echo Bitte den gewuenschten Quellstand bewusst waehlen. Siehe START.md.
  pause
  exit /b 1
)

echo Aktueller Branch:
git branch --show-current
echo Verfolgter Upstream:
git rev-parse --abbrev-ref --symbolic-full-name "@{upstream}"
if errorlevel 1 (
  echo FEHLER: Fuer diesen Branch ist kein Upstream eingerichtet.
  echo Bitte die Git-Konfiguration pruefen. Siehe START.md.
  pause
  exit /b 1
)

echo.
echo Lade Updates ^(git pull --ff-only^)...
git pull --ff-only
if errorlevel 1 (
  echo.
  echo FEHLER: git pull ist fehlgeschlagen.
  echo Bitte die Git-Meldung pruefen, lokale Aenderungen sichern
  echo und gegebenenfalls die Internetverbindung kontrollieren.
  echo.
  pause
  exit /b 1
)

if exist ".venv\Scripts\python.exe" (
  echo.
  echo Aktualisiere die Python-Pakete der vorhandenen Umgebung...
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo FEHLER: Quellcode aktualisiert, Paketinstallation fehlgeschlagen.
    echo Bitte den pip-Befehl aus START.md wiederholen.
    pause
    exit /b 1
  )
) else (
  echo Die Startdatei legt beim ersten Start eine neue Umgebung an.
)

echo.
echo ----------------------------------------
echo Update fertig.
echo.
echo Als Naechstes:
echo   Doppelklick auf "Fotobuch starten.bat"
echo.
echo Hinweise zu Start und Updates stehen in START.md.
echo ----------------------------------------
echo.
pause
endlocal
exit /b 0

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Fotobuch - Aktualisieren
color 0F

echo.
echo ========================================
echo   Fotobuch - Programm aktualisieren
echo ========================================
echo.
echo Holt den neuesten Stand vom Branch
echo   cursor/photobook-curator-c6d6
echo.

where git >nul 2>&1
if errorlevel 1 (
  echo FEHLER: Git wurde nicht gefunden.
  echo.
  echo Ohne Git bitte so aktualisieren:
  echo   1. Auf GitHub Branch cursor/photobook-curator-c6d6 waehlen
  echo   2. Code - Download ZIP
  echo   3. Alten Ordner ersetzen ^(Fotos/Ausgabe bleiben woanders^)
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

echo Wechsle auf den Update-Branch...
git checkout cursor/photobook-curator-c6d6
if errorlevel 1 (
  echo FEHLER: Branch konnte nicht gewechselt werden.
  pause
  exit /b 1
)

echo.
echo Lade Updates (git pull)...
git pull origin cursor/photobook-curator-c6d6
if errorlevel 1 (
  echo.
  echo FEHLER: git pull ist fehlgeschlagen.
  echo Oft hilft: Internet pruefen, oder lokal geaenderte Dateien sichern.
  echo.
  pause
  exit /b 1
)

echo.
echo ----------------------------------------
echo Update fertig.
echo.
echo Als Naechstes:
echo   Doppelklick auf "Fotobuch starten.bat"
echo.
echo Wenn Pakete geaendert wurden, repariert
echo das Start-Skript die Umgebung bei Bedarf.
echo ----------------------------------------
echo.
pause
endlocal
exit /b 0

@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Fotobuch-Auswahl
color 0F

echo.
echo ========================================
echo   Fotobuch-Auswahl - Start
echo ========================================
echo.
echo Dieses schwarze Fenster bleibt sichtbar,
echo damit du Fortschritt und Fehler siehst.
echo Das eigentliche Programm oeffnet sich
echo danach in einem eigenen Fenster.
echo.

rem --- Python finden (echter Installer, kein Store-Stub) ---
set "BOOTSTRAP_PY="

where py >nul 2>&1
if not errorlevel 1 (
  for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "BOOTSTRAP_PY=%%I"
)

if not defined BOOTSTRAP_PY (
  where python >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "BOOTSTRAP_PY=%%I"
  )
)

if not defined BOOTSTRAP_PY (
  echo FEHLER: Python wurde nicht gefunden.
  echo.
  echo Bitte Python 3.11 oder neuer installieren:
  echo   https://www.python.org/downloads/
  echo.
  echo Wichtig beim Setup:
  echo   [x] Add python.exe to PATH
  echo   [x] tcl/tk und IDLE ^(meist Standard^)
  echo Danach diesen PC neu starten und erneut doppelklicken.
  echo.
  pause
  exit /b 1
)

echo %BOOTSTRAP_PY% | find /i "WindowsApps" >nul
if not errorlevel 1 (
  echo FEHLER: Windows startet nur den Microsoft-Store-Platzhalter fuer Python.
  echo Dadurch oeffnet sich oft ein leeres Store-Fenster - nicht dieses Programm.
  echo.
  echo Loesung:
  echo   1. Python von https://www.python.org/downloads/ installieren
  echo   2. "Add python.exe to PATH" aktivieren
  echo   3. Einstellungen - Apps - Aliase fuer App-Ausfuehrung
  echo      - "App-Installationsalias" fuer python.exe / python3.exe AUS
  echo.
  pause
  exit /b 1
)

echo Python gefunden:
"%BOOTSTRAP_PY%" -c "import sys; print(' ', sys.version)"
if errorlevel 1 (
  echo FEHLER: Python antwortet nicht korrekt.
  pause
  exit /b 1
)

"%BOOTSTRAP_PY%" -c "import tkinter" 1>nul 2>nul
if errorlevel 1 (
  echo.
  echo FEHLER: tkinter fehlt - ohne diese Bibliothek gibt es kein Programmfenster.
  echo Bitte Python erneut von python.org installieren ^(Standard-Optionen^).
  echo.
  pause
  exit /b 1
)

rem --- Umgebung anlegen / reparieren ---
if not exist ".venv\Scripts\python.exe" goto CREATE_VENV

echo Pruefe vorhandene Umgebung...
".venv\Scripts\python.exe" -c "import PIL, cv2, numpy" 1>nul 2>nul
if errorlevel 1 (
  echo Vorhandene Umgebung ist unvollstaendig oder beschaedigt.
  echo Wird neu angelegt...
  rmdir /s /q ".venv" 2>nul
  goto CREATE_VENV
)
goto RUN

:CREATE_VENV
echo.
echo Erstelle Python-Umgebung .venv ...
"%BOOTSTRAP_PY%" -m venv .venv
if errorlevel 1 (
  echo FEHLER: virtuelle Umgebung konnte nicht erstellt werden.
  pause
  exit /b 1
)

echo.
echo Installiere Pakete (nur beim ersten Mal, oft 3-10 Minuten^)...
echo Bitte warten - Fenster nicht schliessen.
echo.
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
  echo FEHLER: pip-Upgrade fehlgeschlagen.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo FEHLER: Paket-Installation fehlgeschlagen.
  echo Oft hilft: Internetpruefung, VPN aus, erneut starten.
  echo.
  pause
  exit /b 1
)
echo.
echo Installation fertig.
echo.

:RUN
echo Starte Programmfenster...
echo Falls es einige Sekunden dauert: normal beim ersten Start.
echo Fehler werden auch in start_log.txt / fehler_beim_start.txt gespeichert.
echo.
".venv\Scripts\python.exe" -m photobook_curator.gui 2> "start_log.txt"
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo ----------------------------------------
  echo Das Programm ist mit Fehlercode %ERR% beendet.
  echo Siehe start_log.txt und ggf. fehler_beim_start.txt
  echo ----------------------------------------
) else (
  echo Programm beendet.
  echo Falls sich kein Fenster geoeffnet hat: start_log.txt / fehler_beim_start.txt
)
echo.
pause
endlocal
exit /b %ERR%

@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Erstelle Python-Umgebung...
  python -m venv .venv
  if errorlevel 1 (
    echo Python wurde nicht gefunden. Bitte Python 3.11+ installieren von https://www.python.org/downloads/
    echo Bei der Installation "Add python.exe to PATH" aktivieren.
    pause
    exit /b 1
  )
  echo Installiere Pakete (kann ein paar Minuten dauern)...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 (
    echo Installation fehlgeschlagen.
    pause
    exit /b 1
  )
)

echo Starte Fotobuch...
".venv\Scripts\python.exe" -m photobook_curator.gui 2> "start_log.txt"
echo.
echo Programm beendet. Falls sich kein Fenster geoeffnet hat, steht der Fehler
echo in der Datei "start_log.txt" (und ggf. "fehler_beim_start.txt") in diesem Ordner.
echo.
pause
endlocal

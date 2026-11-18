@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Fotobuch - Code zusammenfassen
color 0F

echo.
echo ========================================
echo   Code in gesamter_code.txt speichern
echo ========================================
echo.

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  where py >nul 2>&1 && for /f "delims=" %%I in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%I"
)
if not defined PY (
  where python >nul 2>&1 && for /f "delims=" %%I in ('python -c "import sys; print(sys.executable)" 2^>nul') do set "PY=%%I"
)

if not defined PY (
  echo FEHLER: Python nicht gefunden.
  echo Bitte zuerst "Fotobuch starten.bat" einmal ausfuehren
  echo ^(legt die Umgebung an^), oder Python installieren.
  echo.
  pause
  exit /b 1
)

"%PY%" "combine.py"
echo.
pause
endlocal
exit /b 0

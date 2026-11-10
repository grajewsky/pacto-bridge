@echo off
cd /d "%~dp0"
if not exist ".venv-win\Scripts\pythonw.exe" (
  echo Brak srodowiska .venv-win. Zainstaluj aplikacje zgodnie z README.md.
  pause
  exit /b 1
)
start "PactoBridge" ".venv-win\Scripts\pythonw.exe" -m pactobridge gui

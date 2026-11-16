@echo off
setlocal
cd /d "%~dp0"

echo [Baithak] Preparing the local app...
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>nul
    if errorlevel 1 (
        python -m venv .venv
    ) else (
        py -3 -m venv .venv
    )
    if errorlevel 1 goto :failed
)

".venv\Scripts\python.exe" -c "import django, qrcode" >nul 2>nul
if errorlevel 1 (
    echo [Baithak] Installing Python packages...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 goto :failed
)

echo [Baithak] Setting up the database and seats...
".venv\Scripts\python.exe" manage.py migrate
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" manage.py seed_seats
if errorlevel 1 goto :failed

echo [Baithak] Starting at http://127.0.0.1:8000/
echo Press Ctrl+C to stop the server.
".venv\Scripts\python.exe" manage.py run_local
if errorlevel 1 goto :failed
goto :eof

:failed
echo.
echo Baithak could not start. Check the message above, then try again.
pause

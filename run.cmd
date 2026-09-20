@echo off
cd /d "%~dp0"

if not exist .env (
    copy .env.example .env >nul
    notepad .env
    exit /b 0
)

if not exist .venv (
    py -3 -m venv .venv
    if errorlevel 1 exit /b 1
)

.venv\Scripts\pip install -r requirements.txt
if errorlevel 1 exit /b 1

for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8593 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique"`) do (
    echo Closing existing listener on port 8593 (PID %%P)...
    taskkill /PID %%P /F >nul 2>&1
    timeout /t 1 /nobreak >nul
)

.venv\Scripts\streamlit run app.py --server.port=8593

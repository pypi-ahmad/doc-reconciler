@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

if not exist .env (
    echo [.env missing] Copying .env.example to .env and opening notepad...
    copy .env.example .env >nul
    notepad .env
    exit /b 0
)

if not exist .venv (
    echo [.venv missing] Creating virtual environment with py -3...
    py -3 -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment with py -3.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

echo [Dependencies] Installing / verifying requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo [Starting] Launching Streamlit application...
streamlit run app.py

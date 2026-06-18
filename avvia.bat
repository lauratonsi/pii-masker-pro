@echo off
REM Double-click this file (Windows) to launch PII Masker Pro in your browser.
REM It runs entirely on your computer - no data is sent anywhere.

cd /d "%~dp0"

where conda >nul 2>nul
if %errorlevel%==0 (
    call conda activate pii-masker
    streamlit run app.py
) else (
    echo Conda non trovato. Apri un prompt ed esegui:
    echo     conda activate pii-masker ^&^& streamlit run app.py
    pause
)

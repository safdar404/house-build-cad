@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe py -3.12 -m venv .venv
if errorlevel 1 (echo Install 64-bit Python 3.12 first. & pause & exit /b 1)
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (echo Dependency installation failed. See README.md. & pause & exit /b 1)
.venv\Scripts\python.exe -m streamlit run app.py

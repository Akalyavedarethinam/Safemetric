@echo off
REM Windows: start the API and the frontend dev server in two windows.
REM Requires Python 3.10+, Node 18+ and Tesseract (https://github.com/UB-Mannheim/tesseract/wiki)
set ROOT=%~dp0..
if "%TESSERACT_CMD%"=="" set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
cd /d %ROOT%\backend
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r requirements.txt
start "SafeMetric API" cmd /k "cd /d %ROOT%\backend && .venv\Scripts\activate && uvicorn app.main:app --reload --port 8000"
cd /d %ROOT%\frontend
if not exist node_modules call npm install
npm run dev

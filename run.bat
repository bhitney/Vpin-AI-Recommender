@echo off
cd /d "%~dp0"
for /f "tokens=2 delims==" %%a in ('findstr GEMINI_API_KEY .env') do set GEMINI_API_KEY=%%a
call .venv\Scripts\activate.bat
python Vpin_Recommender.py

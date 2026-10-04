@echo off
cd /d "%~dp0"
REM Select AI backend: "azure" (default, keyless) or "gemini".
if "%AI_PROVIDER%"=="" set AI_PROVIDER=azure
REM Load all KEY=VALUE pairs from .env (service principal creds, GEMINI_API_KEY, etc.).
REM eol=# skips comment lines. .env is gitignored - never commit it.
if exist .env (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
)
call .venv\Scripts\activate.bat
python Vpin_Recommender.py

@echo off
cd /d "%~dp0"
REM Optional overrides (otherwise vpin_recommender_config.py is used):
REM   VPIN_EMU_IDS  - comma-separated emulator IDs, e.g. set VPIN_EMU_IDS=10
REM   first argument - number of history days, e.g. BuildHistoryReport.bat 180
REM set VPIN_EMU_IDS=10
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
python Vpin_HistoryReport.py %*
if "%CI%"=="" if exist HistoryReport.html start "" HistoryReport.html
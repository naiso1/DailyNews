@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d %~dp0
chcp 65001 > nul

set "ROOT=%~dp0.."
set "NEWS_JS=%ROOT%\news_data.js"
set "WORKFLOW=%ROOT%\image_flux2_klein_text_to_image (1).json"
set "LOG_DIR=%~dp0logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "TODAY=%%i"
set "LOG=%LOG_DIR%\run_search_and_update_%TODAY%.log"

echo ================================================== >> "%LOG%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd HH:mm:ss"') do set "START_TS=%%i"
echo [START] %START_TS% >> "%LOG%"

REM Determine target date range: (latest_date + 1) to yesterday
for /f "tokens=1,2 delims=|" %%a in ('
  python -c "import re,datetime,pathlib; p=pathlib.Path(r'%NEWS_JS%'); \
  t=p.read_text(encoding='utf-8', errors='ignore') if p.exists() else ''; \
  dates=re.findall(r'\\bdate:\\s*\\\"(\\d{4}-\\d{2}-\\d{2})\\\"', t); \
  latest=max(dates) if dates else None; \
  if latest: d=datetime.datetime.strptime(latest,'%Y-%m-%d').date()+datetime.timedelta(days=1); \
  else: d=datetime.date.today()-datetime.timedelta(days=1); \
  y=datetime.date.today()-datetime.timedelta(days=1); \
  print(d.strftime('%Y-%m-%d')+'|'+y.strftime('%Y-%m-%d'))"
') do (
  set "START_DATE=%%a"
  set "END_DATE=%%b"
)

echo [INFO] Target range: %START_DATE% to %END_DATE% >> "%LOG%"

REM If start date is after end date, skip
for /f %%i in ('
  python -c "import datetime; \
  s=datetime.datetime.strptime(r'%START_DATE%','%Y-%m-%d').date(); \
  e=datetime.datetime.strptime(r'%END_DATE%','%Y-%m-%d').date(); \
  print(1 if s>e else 0)"
') do set "SKIP=%%i"

if "%SKIP%"=="1" (
  echo [INFO] No new dates to process. >> "%LOG%"
) else (
  REM Run search collector for target dates
  python -u google_search_script.py --dates %START_DATE%,%END_DATE% >> "%LOG%" 2>&1

  REM Append to DailyNews and generate insights/ideas
  python -u "..\auto_update_daily_news.py" >> "%LOG%" 2>&1

  REM Generate idea images via ComfyUI (latest ideas only)
  if exist "%WORKFLOW%" (
    python -u "..\generate_idea_images_comfyui.py" --only-missing --workflow "%WORKFLOW%" >> "%LOG%" 2>&1
  ) else (
    echo [WARN] Workflow not found: %WORKFLOW% >> "%LOG%"
  )
)

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd HH:mm:ss"') do set "END_TS=%%i"
echo [END] %END_TS% >> "%LOG%"
echo ================================================== >> "%LOG%"

echo Done. Log: %LOG%
pause

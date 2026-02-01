@echo off
cd /d %~dp0
chcp 65001 > nul

REM ==========================================================
REM  Change points for other departments
REM  1) department_settings.json (rss_feeds / country_settings / keywords / prompt_path / synonym_groups)
REM  2) prompt file (see PROMPT_PATH in department_settings.json)
REM  3) api_keys.json (API keys)
REM  4) Environment vars (TARGET_DATES, USE_LLM, DEPARTMENT)
REM ==========================================================

echo Installing requirements...
pip install -r requirements.txt
echo.
echo Running collector...
python -u google_search_script.py

REM Example: python -u google_search_script.py --dept interior

echo.

@echo off
cd /d %~dp0
chcp 65001 > nul

python -u run_search_and_update.py

pause

@echo off
cd /d "%~dp0"
py -3.11 -m main
if errorlevel 1 pause

@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m pip install --upgrade pip
if errorlevel 1 goto :failed
py -3.11 -m pip install -r requirements.txt
if errorlevel 1 goto :failed
py -3.11 -m pytest -q
if errorlevel 1 goto :failed
py -3.11 -m PyInstaller --noconfirm --clean "AutoBeatVideoEditorAI.spec"
if errorlevel 1 goto :failed
echo.
echo EXE build completed. Expected path:
echo dist\KHIETTRAN Autobeat Cut\KHIETTRAN Autobeat Cut.exe
where ISCC.exe >nul 2>nul
if not errorlevel 1 (
  ISCC.exe "KHIETTRAN_Autobeat_Cut.iss"
  if errorlevel 1 goto :failed
  echo Installer created under installer_output\
) else (
  echo Inno Setup ISCC.exe was not found. Open KHIETTRAN_Autobeat_Cut.iss in Inno Setup Compiler to build installer.
)
echo If tools\ffmpeg.exe and tools\ffprobe.exe exist, they are bundled automatically.
echo Otherwise FFmpeg and FFprobe must be installed on the target PC and available on PATH.
pause
exit /b 0
:failed
echo BUILD OR TEST FAILED. Review the error output above.
pause
exit /b 1

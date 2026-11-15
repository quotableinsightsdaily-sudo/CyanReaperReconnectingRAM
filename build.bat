@echo off
REM Builds CyanReapersRAM.exe  (run from the folder that has cyanreaper_ram.py)
cd /d "%~dp0"
if not exist cyanreaper_ram.py (
  echo ERROR: cyanreaper_ram.py is not in this folder: %cd%
  pause & exit /b 1
)
python -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto fail
set ICO=
if exist icon.ico set ICO=--icon icon.ico
python -m PyInstaller --onefile --noconsole %ICO% --name CyanReapersRAM --collect-all webview --hidden-import websocket cyanreaper_ram.py
if errorlevel 1 goto fail
if not exist "dist\CyanReapersRAM.exe" goto missing
echo.
echo SUCCESS - your app is here: %cd%\dist\CyanReapersRAM.exe
explorer dist
pause & exit /b 0

:missing
echo.
echo The build finished but the .exe is gone. Windows Defender most likely removed it.
echo Open Windows Security ^> Virus ^& threat protection ^> Protection history and restore it,
echo or add this folder as an exclusion and run build.bat again.
pause & exit /b 1

:fail
echo.
echo BUILD FAILED - scroll up and read the error above this message.
pause & exit /b 1

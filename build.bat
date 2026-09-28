@echo off
setlocal
cd /d "%~dp0"
echo === Step 1/3: install packaging tools (pyinstaller, pywebview) ===
python -m pip install --user --upgrade pyinstaller pywebview
if errorlevel 1 goto :piperr
echo.
echo === Step 2/3: build PokerTracker.exe ===
python -m PyInstaller --noconfirm --onefile --noconsole --name PokerTracker --distpath .. --workpath build --specpath build --add-data "%~dp0index.html;." --hidden-import webview --hidden-import clr main.py
if errorlevel 1 goto :builderr
echo.
echo === Step 3/3: done ===
echo The program is here: %~dp0..\PokerTracker.exe
echo Double-click it to run. hands folder and tracker\tracker.db stay where they are.
echo.
pause
exit /b 0

:piperr
echo.
echo pip install failed. Check that Python is installed and the network is available.
echo.
pause
exit /b 1

:builderr
echo.
echo Build failed. Please screenshot the messages above and send them to Claude.
echo.
pause
exit /b 1

@echo off
echo Building Windows Executable...
REM Install PyInstaller if not present
REM pip install pyinstaller

pyinstaller --noconfirm --onefile --windowed ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --name "FuzzyMatcher_Windows" ^
  app.py

echo Build complete! Check the dist\ directory for FuzzyMatcher_Windows.exe
pause

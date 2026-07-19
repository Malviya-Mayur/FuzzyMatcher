@echo off
echo Building Windows Executable...

REM Installing PyInstaller just in case it's missing (without REM it will run)
pip install pyinstaller

python -m pyinstaller --noconfirm --onefile --windowed ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --name "FuzzyMatcher_Windows" ^
  app.py

echo Build complete! Check the dist\ directory for FuzzyMatcher_Windows.exe
pause
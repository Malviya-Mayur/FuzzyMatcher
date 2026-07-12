#!/bin/bash
# Install PyInstaller if not present
# pip3 install pyinstaller

echo "Building Linux Executable..."
pyinstaller --noconfirm --onefile --windowed \
  --add-data "templates:templates" \
  --add-data "static:static" \
  --name "FuzzyMatcher_Linux" \
  app.py

echo "Build complete! Check the dist/ directory for FuzzyMatcher_Linux."

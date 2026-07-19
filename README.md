# FuzzyMatcher Studio 🚀

FuzzyMatcher Studio is a sleek, modern desktop-like web application designed for offline fuzzy text matching between columns across CSV or Excel files. It is powered by a high-performance Python backend (using `rapidfuzz` and `pandas`) and serves a beautiful, glassmorphic frontend UI via a local production-ready Flask server.

---

## Features ✨

- **Modern Glassmorphic UI**: Beautiful dark mode interface with interactive micro-animations.
- **Drag & Drop Upload**: Easily upload Target and Source files (CSV, XLSX, XLS).
- **Flexible CSV Parsing**: Explicit dropdown selectors for custom CSV delimiters (Comma, Semicolon, Tab) and Text Qualifiers/Quotes (Double, Single, None).
- **Dynamic Column Mapping**: Dropdowns automatically populate with headers parsed directly from your uploaded data.
- **Advanced Match Algorithms**: 
  - **Smart (Ensemble)**: A weighted ensemble of 5 scorers (Ratio, Partial Ratio, Token Sort, Token Set, WRatio) for the most balanced matching.
  - Individual scorers: Ratio, Partial Ratio, Token Sort Ratio, Token Set Ratio, WRatio.
- **Preprocessing Control**: Clean scoring inputs on-the-fly (lowercase, trim whitespace, strip punctuation, remove stopwords, stem words) without altering original display values in the output.
- **Multi-Format Export**: Download results directly in **Excel (.xlsx)** or **CSV (.csv)** format.
- **Production Server (Waitress)**: Runs on a secure, warning-free WSGI server and automatically launches your browser on startup.

---

## Download Releases ⬇️

Ready-to-use executable files are available in the [Releases](../../releases) section for both Windows and Linux. You don't need Python installed to run these!

- **Windows**: Download `FuzzyMatcher_Windows.exe` and simply double-click to run.
- **Linux**: Download `FuzzyMatcher_Linux`, grant it execution permissions (`chmod +x FuzzyMatcher_Linux`), and run it from your terminal (`./FuzzyMatcher_Linux`).

---

## Installation & Setup 📦

Ensure you have Python 3.8+ installed.

### 1. Install Dependencies
Open your terminal in the project directory and run:

```bash
pip install flask waitress werkzeug pandas openpyxl rapidfuzz
```

*Note (Optional): If you wish to use the word stemming option, ensure `nltk` is installed:*
```bash
pip install nltk
```

---

## How to Run Locally 💻

Start the server using:

```bash
python app.py
```

- Waitress will automatically open your default browser to `http://127.0.0.1:5000`.
- Drag and drop your files, specify column names and matching configurations, then click **Run Match**.

---

## How to Build Standalone Executables 🛠️

You can bundle FuzzyMatcher Studio into a single executable file that can run on systems *without* Python installed.

Ensure `pyinstaller` is installed:
```bash
pip install pyinstaller
```

### 1. For Arch Linux (or other Linux distros)
1. Grant execute permissions to the build script:
   ```bash
   chmod +x build_linux.sh
   ```
2. Run the script:
   ```bash
   ./build_linux.sh
   ```
3. Locate the single-file executable in the `dist/` directory as `FuzzyMatcher_Linux`.

### 2. For Windows
*Note: Because PyInstaller does not support cross-compilation, you must run this step on a Windows machine.*
1. Copy this project folder to a Windows environment.
2. Ensure Python, PyInstaller, and Waitress are installed.
3. Double-click the `build_windows.bat` script.
4. Locate the single-file executable in `dist\` as `FuzzyMatcher_Windows.exe`.

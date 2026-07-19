import os
from flask import Flask, request, jsonify, render_template, send_from_directory
from werkzeug.utils import secure_filename
import pandas as pd
from FuzzyMatcher import fuzzy_match

import sys

if getattr(sys, 'frozen', False):
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
else:
    app = Flask(__name__)

import tempfile
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'FuzzyMatcher_uploads')
OUTPUT_FOLDER = os.path.join(tempfile.gettempdir(), 'FuzzyMatcher_Outputs')
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_columns(filepath, csv_separator=',', csv_quotechar='"'):
    try:
        if filepath.endswith('.csv'):
            if csv_quotechar == '':
                df = pd.read_csv(filepath, sep=csv_separator, nrows=0, quoting=3)
            else:
                df = pd.read_csv(filepath, sep=csv_separator, quotechar=csv_quotechar, nrows=0)
        else:
            df = pd.read_excel(filepath, engine='openpyxl', nrows=0)
        return list(df.columns)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return []

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        csv_separator = request.form.get('csv_separator', ',')
        csv_quotechar = request.form.get('csv_quotechar', '"')
        
        columns = get_columns(filepath, csv_separator, csv_quotechar)
        return jsonify({'filename': filename, 'columns': columns})
    return jsonify({'error': 'File not allowed'}), 400

@app.route('/api/match', methods=['POST'])
def match():
    data = request.json
    try:
        target_file = os.path.join(app.config['UPLOAD_FOLDER'], data['target_file'])
        source_file = os.path.join(app.config['UPLOAD_FOLDER'], data['source_file'])
        
        target_col = data['target_col']
        source_col = data['source_col']
        scorer = data.get('scorer', 'smart')
        threshold = float(data.get('threshold', 80.0))
        
        preprocess_options = data.get('preprocess_options', {})
        export_format = data.get('export_format', 'xlsx')
        csv_separator = data.get('csv_separator', ',')
        csv_quotechar = data.get('csv_quotechar', '"')
        
        target_name = os.path.splitext(data['target_file'])[0]
        source_name = os.path.splitext(data['source_file'])[0]
        output_filename = f"matched_{target_name}_{source_name}.{export_format}"
        output_filepath = os.path.join(OUTPUT_FOLDER, output_filename)
        
        fuzzy_match(
            target_file=target_file,
            source_file=source_file,
            target_col=target_col,
            source_col=source_col,
            scorer=scorer,
            threshold=threshold,
            preprocess_options=preprocess_options,
            output_file=output_filepath,
            csv_separator=csv_separator,
            csv_quotechar=csv_quotechar
        )
        
        return jsonify({'success': True, 'output_file': output_filename})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/download/<filename>')
def download_file(filename):
    return send_from_directory(OUTPUT_FOLDER, filename, as_attachment=True)

if __name__ == '__main__':
    try:
        from waitress import serve
        import webbrowser
        import threading
        import urllib.request

        URL = "http://127.0.0.1:5000"

        def _open_browser_when_ready():
            """Poll the server until it responds, then open the browser."""
            import time
            for _ in range(60):          # try for up to 30 seconds
                try:
                    urllib.request.urlopen(URL, timeout=1)
                    webbrowser.open(URL)  # server is up — open browser now
                    return
                except Exception:
                    time.sleep(0.5)

        # Launch browser-opener as a daemon thread so it doesn't block startup
        t = threading.Thread(target=_open_browser_when_ready, daemon=True)
        t.start()

        print(f"Starting production server on {URL}...")
        serve(app, host='127.0.0.1', port=5000)
    except ImportError:
        print("Waitress not installed. Falling back to development server...")
        app.run(debug=False, port=5000)

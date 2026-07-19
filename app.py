import os
import sys

# -------------------------------------------------------------------------
# Redirect stdout/stderr to a log file so errors are always visible.
# In --windowed mode sys.stdout and sys.stderr are None and crash uvicorn.
# -------------------------------------------------------------------------
_log_path = os.path.join(os.path.expanduser("~"), "FuzzyMatcher_log.txt")
try:
    _logfile = open(_log_path, 'w', encoding='utf-8', buffering=1)
    if sys.stdout is None:
        sys.stdout = _logfile
    if sys.stderr is None:
        sys.stderr = _logfile
except Exception:
    pass

import uuid
import time
import socket
import tempfile
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

import jinja2
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
import pandas as pd
from werkzeug.utils import secure_filename

from FuzzyMatcher import fuzzy_match, load_plugin_scorers, get_all_scorer_names

# -------------------------------------------------------------------------
# App bootstrap: resolve template/static paths for both dev and frozen exe
# -------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    _base = sys._MEIPASS
else:
    _base = os.path.dirname(os.path.abspath(__file__))

# Use raw Jinja2 Environment — Starlette's Jinja2Templates wrapper has a
# broken LRU cache (uses dict as key) that raises TypeError in some versions.
_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(_base, "templates")),
    autoescape=True,
)

app = FastAPI(title="FuzzyMatcher Studio")
app.mount("/static", StaticFiles(directory=os.path.join(_base, "static")), name="static")

# -------------------------------------------------------------------------
# Storage directories
# -------------------------------------------------------------------------
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'FuzzyMatcher_uploads')
OUTPUT_FOLDER = os.path.join(tempfile.gettempdir(), 'FuzzyMatcher_Outputs')
ALLOWED_EXTENSIONS = {'csv', 'xls', 'xlsx'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# -------------------------------------------------------------------------
# Async job registry
# -------------------------------------------------------------------------
_jobs: dict = {}
_executor = ThreadPoolExecutor(max_workers=4)

# -------------------------------------------------------------------------
# Startup: load plugin scorers
# -------------------------------------------------------------------------
_scorers_dir = os.path.join(_base, "scorers")
_plugin_names = load_plugin_scorers(_scorers_dir)

# -------------------------------------------------------------------------
# Heartbeat monitor (auto-shutdown)
# -------------------------------------------------------------------------
_last_heartbeat = time.time()
_monitor_started = False

def _heartbeat_monitor():
    while True:
        time.sleep(2)
        if time.time() - _last_heartbeat > 5:
            print("Heartbeat lost. Shutting down...")
            os._exit(0)


def _allowed(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_columns(filepath: str, csv_separator: str = ',', csv_quotechar: str = '"'):
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


# -------------------------------------------------------------------------
# Routes
# -------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    # Build the static URL prefix so the template can reference /static/...
    template = _jinja_env.get_template("index.html")
    html = template.render()
    return HTMLResponse(content=html)


@app.get("/api/scorers")
async def list_scorers():
    return get_all_scorer_names()


@app.post("/api/heartbeat")
async def heartbeat():
    global _last_heartbeat, _monitor_started
    _last_heartbeat = time.time()
    if not _monitor_started:
        _monitor_started = True
        threading.Thread(target=_heartbeat_monitor, daemon=True).start()
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    csv_separator: str = Form(','),
    csv_quotechar: str = Form('"'),
):
    if not _allowed(file.filename):
        raise HTTPException(status_code=400, detail="File type not allowed")
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    content = await file.read()
    with open(filepath, 'wb') as f:
        f.write(content)
    columns = _get_columns(filepath, csv_separator, csv_quotechar)
    return {"filename": filename, "columns": columns}


@app.post("/api/jobs")
async def create_job(payload: dict):
    job_id = str(uuid.uuid4())
    _jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "total": 0,
        "output_file": None,
        "error": None,
        "created_at": time.time(),
    }

    def _run():
        try:
            _jobs[job_id]["status"] = "running"
            target_file = os.path.join(UPLOAD_FOLDER, payload['target_file'])
            source_file = os.path.join(UPLOAD_FOLDER, payload['source_file'])

            target_name = os.path.splitext(payload['target_file'])[0]
            source_name = os.path.splitext(payload['source_file'])[0]
            export_format = payload.get('export_format', 'xlsx')
            output_filename = f"matched_{target_name}_{source_name}.{export_format}"
            output_filepath = os.path.join(OUTPUT_FOLDER, output_filename)

            def _progress(completed: int, total: int):
                _jobs[job_id]["progress"] = completed
                _jobs[job_id]["total"] = total

            fuzzy_match(
                target_file=target_file,
                source_file=source_file,
                target_col=payload['target_col'],
                source_col=payload['source_col'],
                scorer=payload.get('scorer', 'smart'),
                threshold=float(payload.get('threshold', 80.0)),
                preprocess_options=payload.get('preprocess_options', {}),
                output_file=output_filepath,
                csv_separator=payload.get('csv_separator', ','),
                csv_quotechar=payload.get('csv_quotechar', '"'),
                progress_callback=_progress,
            )

            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["output_file"] = output_filename
        except Exception as e:
            import traceback
            traceback.print_exc()
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)

    _executor.submit(_run)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id":      job_id,
        "status":      job["status"],
        "progress":    job["progress"],
        "total":       job["total"],
        "output_file": job["output_file"],
        "error":       job["error"],
    }


@app.get("/api/download/{filename}")
async def download_file(filename: str):
    filepath = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(filepath, filename=filename,
                        media_type='application/octet-stream')


# -------------------------------------------------------------------------
# Port helpers
# -------------------------------------------------------------------------
def _find_free_port(start: int = 5000, end: int = 5100) -> int:
    """Find a free TCP port in the range [start, end)."""
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range 5000-5100")


# -------------------------------------------------------------------------
# Entry point
# -------------------------------------------------------------------------
if __name__ == '__main__':
    import webbrowser
    import uvicorn

    port = _find_free_port()
    URL = f"http://127.0.0.1:{port}"

    def _open_browser_when_ready():
        import urllib.request
        for _ in range(120):
            try:
                urllib.request.urlopen(URL, timeout=1)
                webbrowser.open(URL)
                return
            except Exception:
                time.sleep(0.5)

    t = threading.Thread(target=_open_browser_when_ready, daemon=True)
    t.start()

    print(f"Starting FuzzyMatcher Studio on {URL} ...")
    print(f"Log file: {_log_path}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
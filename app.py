import os
import sys
import uuid
import time
import tempfile
import threading
from typing import Optional
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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

templates = Jinja2Templates(directory=os.path.join(_base, "templates"))

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
_jobs: dict = {}           # job_id -> job dict
_executor = ThreadPoolExecutor(max_workers=4)

# File-level preprocessed source cache: {(filepath, mtime): (orig_list, proc_list)}
_file_cache: dict = {}

# -------------------------------------------------------------------------
# Startup: load plugin scorers
# -------------------------------------------------------------------------
_scorers_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scorers")
_plugin_names = load_plugin_scorers(_scorers_dir)


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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/scorers")
async def list_scorers():
    return get_all_scorer_names()


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
    """Start a match job asynchronously. Returns job_id immediately."""
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
# Entry point
# -------------------------------------------------------------------------
if __name__ == '__main__':
    import uvicorn
    import webbrowser

    URL = "http://127.0.0.1:5000"

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
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="warning")
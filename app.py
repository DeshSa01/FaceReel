"""Web app: find every appearance of a person in a YouTube video and stitch the clips."""

import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import archive
import pipeline

BASE_DIR = os.path.dirname(__file__)
JOBS_DIR = os.path.join(BASE_DIR, "storage", "jobs")


def clean_jobs_dir(path=JOBS_DIR):
    """Delete every previous job's scratch directory. Job state is in-memory,
    so anything still on disk at startup is orphaned. Returns the count."""
    os.makedirs(path, exist_ok=True)
    removed = 0
    for name in os.listdir(path):
        target = os.path.join(path, name)
        if os.path.isdir(target):
            shutil.rmtree(target, ignore_errors=True)
            removed += 1
    return removed


@asynccontextmanager
async def lifespan(_app):
    # deliberately not at module scope: importing this module must not delete
    # anything, or a test run would wipe the user's outputs
    removed = clean_jobs_dir()
    print(f"Cleared {removed} orphaned job folder(s) from {JOBS_DIR}")
    archive.ensure_archive_dir()
    yield


app = FastAPI(title="FaceReel", lifespan=lifespan)

jobs = {}
jobs_lock = threading.Lock()


def _worker(job_id, url, screenshot_path, job_dir, tuning):
    job = jobs[job_id]

    def progress(stage, pct, message):
        job.update(stage=stage, progress=round(min(pct, 99), 1), message=message)

    try:
        result = pipeline.process_job(url, screenshot_path, job_dir, progress, tuning)
    except pipeline.PipelineError as e:
        job.update(status="error", message=str(e))
        return
    except Exception as e:
        job.update(status="error", message=f"Unexpected error: {e}")
        return

    try:
        entry_path = archive.archive_job(job_id, url, result, tuning, screenshot_path)
    except Exception as e:
        # The reel generated correctly but did not persist -- report failure
        # rather than success, since the atomic rename guarantees there is no
        # half-saved reel to explain (research D8).
        job.update(status="error", message=f"Reel was generated but could not be saved: {e}")
        return

    # Repoint at the archived file so /api/jobs/{id}/output keeps serving the
    # result card unchanged (FR-027, research D4) -- the job dir it came from
    # is wiped at the next restart.
    job.update(status="done", stage="done", progress=100,
               message="Done!", result={k: v for k, v in result.items() if k != "output"},
               output_path=os.path.join(entry_path, "output.mp4"))


@app.post("/api/jobs")
async def create_job(
    url: str = Form(...),
    screenshot: UploadFile = File(...),
    lead_in: float | None = Form(None),
    boundary_reach: float | None = Form(None),
    clip_gap: float | None = Form(None),
    zoom: bool = Form(False),
    hi_res: bool = Form(False),
):
    tuning = pipeline.Tuning.clamped(lead_in, boundary_reach, clip_gap, zoom, hi_res)
    with jobs_lock:
        if any(j["status"] == "processing" for j in jobs.values()):
            raise HTTPException(409, "A video is already being processed. Try again when it finishes.")
        job_id = uuid.uuid4().hex[:12]
        jobs[job_id] = {
            "id": job_id, "status": "processing", "stage": "start",
            "progress": 0, "message": "Starting...", "result": None,
            # echoed back on poll so a run can be tied to the values that made it
            "tuning": asdict(tuning),
        }

    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    screenshot_path = os.path.join(job_dir, "screenshot" + os.path.splitext(screenshot.filename or "")[1])
    with open(screenshot_path, "wb") as f:
        shutil.copyfileobj(screenshot.file, f)

    threading.Thread(target=_worker,
                     args=(job_id, url, screenshot_path, job_dir, tuning),
                     daemon=True).start()
    return {"id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found.")
    return {k: v for k, v in job.items() if k != "output_path"}


@app.get("/api/jobs/{job_id}/output")
def get_output(job_id: str):
    job = jobs.get(job_id)
    if not job or job["status"] != "done":
        raise HTTPException(404, "Output not available.")
    name = (job.get("result") or {}).get("filename") or "facereel.mp4"
    return FileResponse(job["output_path"], media_type="video/mp4",
                        filename=name, content_disposition_type="inline")


@app.get("/")
def index():
    # FileResponse sends no Cache-Control, so browsers heuristically cache the
    # page and keep serving a stale copy across restarts; force revalidation
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"),
                        headers={"Cache-Control": "no-cache"})


def _require_valid_id(reel_id):
    # A malformed id is 400, never 404, so a traversal attempt is
    # distinguishable in the logs from a genuine miss (research D5). The
    # routes below capture reel_id with the :path converter specifically so
    # that an encoded "/" still reaches this check instead of being 404'd by
    # the router before validation ever runs.
    if not archive.valid_id(reel_id):
        raise HTTPException(400, "Malformed reel id.")


@app.get("/archive")
def archive_page():
    return FileResponse(os.path.join(BASE_DIR, "static", "archive.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/api/archive")
def list_archive():
    total_bytes, entries = archive.list_entries()
    return {"total_bytes": total_bytes, "entries": entries}


@app.get("/api/archive/{reel_id:path}/video")
def get_archive_video(reel_id: str):
    _require_valid_id(reel_id)
    entry = archive.read_entry(reel_id)
    if entry is None:
        raise HTTPException(404, "Archived reel not found.")
    path = os.path.join(archive.entry_dir(reel_id), entry["video"])
    if not os.path.exists(path):
        raise HTTPException(404, "Archived reel not found.")
    return FileResponse(path, media_type="video/mp4",
                        filename=entry["filename"], content_disposition_type="inline")


@app.get("/api/archive/{reel_id:path}/thumb")
def get_archive_thumb(reel_id: str):
    _require_valid_id(reel_id)
    entry = archive.read_entry(reel_id)
    if entry is None or not entry.get("thumb"):
        raise HTTPException(404, "No thumbnail for this reel.")
    path = os.path.join(archive.entry_dir(reel_id), entry["thumb"])
    if not os.path.exists(path):
        raise HTTPException(404, "No thumbnail for this reel.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/archive/{reel_id:path}/screenshot")
def get_archive_screenshot(reel_id: str):
    _require_valid_id(reel_id)
    entry = archive.read_entry(reel_id)
    if entry is None or not entry.get("screenshot"):
        raise HTTPException(404, "No screenshot for this reel.")
    path = os.path.join(archive.entry_dir(reel_id), entry["screenshot"])
    if not os.path.exists(path):
        raise HTTPException(404, "No screenshot for this reel.")
    return FileResponse(path)


@app.delete("/api/archive/{reel_id:path}")
def delete_archive_entry(reel_id: str):
    _require_valid_id(reel_id)
    freed = archive.delete_entry(reel_id)
    if freed is None:
        raise HTTPException(404, "Archived reel not found.")
    return {"deleted": reel_id, "freed_bytes": freed}

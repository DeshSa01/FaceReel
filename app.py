"""Web app: find every appearance of a person in a YouTube video and stitch the clips."""

import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

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
        job.update(status="done", stage="done", progress=100,
                   message="Done!", result={k: v for k, v in result.items() if k != "output"},
                   output_path=result["output"])
    except pipeline.PipelineError as e:
        job.update(status="error", message=str(e))
    except Exception as e:
        job.update(status="error", message=f"Unexpected error: {e}")


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

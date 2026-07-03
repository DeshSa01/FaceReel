"""Web app: find every appearance of a person in a YouTube video and stitch the clips."""

import os
import shutil
import threading
import uuid

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import pipeline

BASE_DIR = os.path.dirname(__file__)
JOBS_DIR = os.path.join(BASE_DIR, "storage", "jobs")

app = FastAPI(title="FaceReel")

jobs = {}
jobs_lock = threading.Lock()


def _worker(job_id, url, screenshot_path, job_dir):
    job = jobs[job_id]

    def progress(stage, pct, message):
        job.update(stage=stage, progress=round(min(pct, 99), 1), message=message)

    try:
        result = pipeline.process_job(url, screenshot_path, job_dir, progress)
        job.update(status="done", stage="done", progress=100,
                   message="Done!", result={k: v for k, v in result.items() if k != "output"},
                   output_path=result["output"])
    except pipeline.PipelineError as e:
        job.update(status="error", message=str(e))
    except Exception as e:
        job.update(status="error", message=f"Unexpected error: {e}")


@app.post("/api/jobs")
async def create_job(url: str = Form(...), screenshot: UploadFile = File(...)):
    with jobs_lock:
        if any(j["status"] == "processing" for j in jobs.values()):
            raise HTTPException(409, "A video is already being processed. Try again when it finishes.")
        job_id = uuid.uuid4().hex[:12]
        jobs[job_id] = {
            "id": job_id, "status": "processing", "stage": "start",
            "progress": 0, "message": "Starting...", "result": None,
        }

    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)
    screenshot_path = os.path.join(job_dir, "screenshot" + os.path.splitext(screenshot.filename or "")[1])
    with open(screenshot_path, "wb") as f:
        shutil.copyfileobj(screenshot.file, f)

    threading.Thread(target=_worker, args=(job_id, url, screenshot_path, job_dir),
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
    return FileResponse(job["output_path"], media_type="video/mp4",
                        filename="facereel.mp4", content_disposition_type="inline")


@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))

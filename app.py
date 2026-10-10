"""Web app: find every appearance of a person in a YouTube video and stitch the clips."""

import os
import shutil
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

import archive
import pipeline
import sessions
from runner import Runner

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


# Module scope, but inert: constructing these touches no disk and starts no
# thread. Everything with side effects happens in lifespan().
store = sessions.SessionStore()
runner = Runner(store, JOBS_DIR)


@asynccontextmanager
async def lifespan(_app):
    # deliberately not at module scope: importing this module must not delete
    # anything, or a test run would wipe the user's outputs
    removed = clean_jobs_dir()
    print(f"Cleared {removed} orphaned job folder(s) from {JOBS_DIR}")
    archive.ensure_archive_dir()
    sessions.ensure_sessions_dir()
    store.load()
    # Order matters: recovery reconciles interrupted work against the archive
    # (research D3) and must finish before the runner can pick anything.
    store.recover()
    runner.start()
    yield


app = FastAPI(title="FaceReel", lifespan=lifespan)


def _require_id(value, what="id"):
    # A malformed id is 400, never 404, so a traversal attempt is
    # distinguishable in the logs from a genuine miss (001 research D5). Runs
    # before any path is built from the value (FR-023, Principle V).
    if not archive.valid_id(value):
        raise HTTPException(400, f"Malformed {what}.")


def _session_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except sessions.SessionError as e:
        raise HTTPException(e.status, e.message)


@app.get("/api/jobs/active")
def get_active_job():
    # What the shared progress bar polls. Before sessions this sat above
    # GET /api/jobs/{job_id} for route-order reasons; that route is gone
    # along with the rest of the single-job API, because a second way to
    # start work would bypass the line (research D10).
    return {"job": store.active()}


@app.get("/api/sessions")
def list_sessions():
    return {"sessions": store.list_open()}


@app.post("/api/sessions", status_code=201)
def create_session():
    return {"id": store.create_session()}


@app.get("/api/sessions/{sid}")
def get_session(sid: str):
    _require_id(sid, "session id")
    return _session_call(store.snapshot, sid)


@app.delete("/api/sessions/{sid}")
def discard_session(sid: str):
    _require_id(sid, "session id")
    _session_call(store.discard_session, sid)
    return {"deleted": sid}


@app.post("/api/sessions/{sid}/videos", status_code=201)
async def add_video(
    sid: str,
    url: str = Form(...),
    screenshot: UploadFile | None = File(None),
    screenshot_from: str | None = Form(None),
    lead_in: float | None = Form(None),
    boundary_reach: float | None = Form(None),
    clip_gap: float | None = Form(None),
    zoom: bool = Form(False),
    hi_res: bool = Form(False),
):
    _require_id(sid, "session id")
    tuning = pipeline.Tuning.clamped(lead_in, boundary_reach, clip_gap, zoom, hi_res)
    # a file input left empty can still arrive as a nameless part
    upload = (screenshot.filename, screenshot.file) if screenshot and screenshot.filename else None
    return _session_call(store.add_video, sid, url.strip(), asdict(tuning),
                         upload=upload, screenshot_from=screenshot_from or None)


@app.post("/api/sessions/{sid}/retry")
def retry_failed(sid: str):
    _require_id(sid, "session id")
    return {"retried": _session_call(store.retry_failed, sid)}


@app.delete("/api/sessions/{sid}/videos/{vid}")
def remove_video(sid: str, vid: str):
    _require_id(sid, "session id")
    _require_id(vid, "video id")
    _session_call(store.remove_video, sid, vid)
    return {"removed": vid}


@app.get("/api/sessions/{sid}/videos/{vid}/screenshot")
def get_video_screenshot(sid: str, vid: str):
    _require_id(sid, "session id")
    _require_id(vid, "video id")
    return FileResponse(_session_call(store.screenshot_path, sid, vid))


@app.get("/api/sessions/{sid}/output")
def get_session_output(sid: str):
    _require_id(sid, "session id")
    session = _session_call(store.snapshot, sid)
    entry = archive.read_entry(sid)
    # both checks: the user may have deleted the joined reel from the archive
    if session["state"] != sessions.FINISHED or entry is None:
        raise HTTPException(404, "No joined reel for this session.")
    path = os.path.join(archive.entry_dir(sid), entry["video"])
    if not os.path.exists(path):
        raise HTTPException(404, "No joined reel for this session.")
    return FileResponse(path, media_type="video/mp4",
                        filename=entry["filename"], content_disposition_type="inline")


@app.get("/")
def index():
    # FileResponse sends no Cache-Control, so browsers heuristically cache the
    # page and keep serving a stale copy across restarts; force revalidation
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/session/{sid}")
def session_page(sid: str):
    # Validated but not looked up: an unknown session still gets the page,
    # which renders "Session not found" from the API (contract "Pages").
    _require_id(sid, "session id")
    return FileResponse(os.path.join(BASE_DIR, "static", "session.html"),
                        headers={"Cache-Control": "no-cache"})


@app.get("/static/progress.js")
def progress_js():
    # Same staleness hazard as index()/archive_page(), and more exposed: a
    # stale copy of this file against a current app.py produces a bar that
    # silently stops working after a redeploy, with nothing else looking wrong.
    return FileResponse(os.path.join(BASE_DIR, "static", "progress.js"),
                        media_type="application/javascript",
                        headers={"Cache-Control": "no-cache"})


def _require_valid_id(reel_id):
    # The archive routes below capture reel_id with the :path converter
    # specifically so that an encoded "/" still reaches this check instead of
    # being 404'd by the router before validation ever runs.
    _require_id(reel_id, "reel id")


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

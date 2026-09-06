"""Owns storage/archive/: durable, browsable reels that survive a restart.

Placed as a sibling of storage/jobs/ rather than inside it so that app.py's
clean_jobs_dir() -- which wipes every subdirectory of storage/jobs/ because
job state lives only in memory -- never needs to know the archive exists.
Correctness by placement, not by teaching a destructive routine to spare
some of what it finds (research D1).
"""

import json
import os
import re
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
ARCHIVE_DIR = os.path.join(BASE_DIR, "storage", "archive")
SIDECAR_NAME = "reel.json"
# Entries are assembled under this prefix and only revealed by an atomic
# rename (research D3); the lister skips anything starting with a dot.
TMP_PREFIX = ".tmp-"

_ID_RE = re.compile(r"^[0-9a-f]{12}$")

# Arbitrary presentation choices (Constitution Principle II note in plan.md):
# neither affects the reel itself, only its preview image, so no measurement
# was warranted. Seek a short way in rather than frame zero, since the first
# frames of a cut can be a transition or a dark frame.
THUMB_SEEK_SECONDS = 1.0
THUMB_WIDTH = 320


def ensure_archive_dir():
    os.makedirs(ARCHIVE_DIR, exist_ok=True)


def valid_id(reel_id):
    return bool(_ID_RE.match(reel_id))


def entry_dir(reel_id):
    """Validate before joining to ARCHIVE_DIR. This is the only barrier
    between a URL path segment and shutil.rmtree (research D5) -- every
    archive endpoint and every function below reaches the filesystem through
    this call."""
    if not valid_id(reel_id):
        raise ValueError(f"Invalid reel id: {reel_id!r}")
    return os.path.join(ARCHIVE_DIR, reel_id)


def read_entry(reel_id):
    """Load one entry's sidecar. Returns None for a missing or unparseable
    sidecar, or an invalid id, rather than raising -- so one bad entry can't
    break a listing (FR-018)."""
    try:
        path = entry_dir(reel_id)
    except ValueError:
        return None
    try:
        with open(os.path.join(path, SIDECAR_NAME)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _dir_size(path):
    total = 0
    for de in os.scandir(path):
        if de.is_file():
            total += de.stat().st_size
    return total


def _make_thumbnail(video_path, dest):
    """One ffmpeg frame grab, scaled down to a listing-sized JPEG. Returns a
    success flag rather than raising -- thumbnail failure is non-fatal and
    leaves thumb: null (research D6)."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-ss", str(THUMB_SEEK_SECONDS), "-i", video_path,
             "-frames:v", "1", "-vf", f"scale={THUMB_WIDTH}:-2", dest],
            capture_output=True, text=True,
        )
    except OSError:
        return False
    return result.returncode == 0 and os.path.exists(dest)


def archive_job(job_id, url, result, tuning, screenshot_path):
    """Move a finished job's outputs into the archive as one atomic unit.

    Assembles everything under a .tmp-<id> staging directory and writes
    reel.json last, then os.rename()s the staging directory into place --
    the rename is what makes a half-written entry impossible, since it is
    atomic on one filesystem and both directories live under ARCHIVE_DIR
    (research D3). On any failure the staging directory is removed and the
    exception re-raised, so the caller reports this job as failed rather
    than as a success for a reel that did not actually persist (research D8).
    """
    ensure_archive_dir()
    staging = os.path.join(ARCHIVE_DIR, TMP_PREFIX + job_id)
    final = entry_dir(job_id)
    try:
        os.makedirs(staging)

        video_dest = os.path.join(staging, "output.mp4")
        shutil.move(result["output"], video_dest)

        screenshot_name = "screenshot" + os.path.splitext(screenshot_path)[1]
        shutil.move(screenshot_path, os.path.join(staging, screenshot_name))

        thumb_ok = _make_thumbnail(video_dest, os.path.join(staging, "thumb.jpg"))

        sidecar = {
            "id": job_id,
            # with UTC offset so a reel's time is unambiguous across a TZ change
            "created_at": datetime.now().astimezone().replace(microsecond=0).isoformat(),
            "url": url,
            "title": result["title"],
            "filename": result["filename"],
            "video": "output.mp4",
            "thumb": "thumb.jpg" if thumb_ok else None,
            "screenshot": screenshot_name,
            "clip_count": result["clip_count"],
            "source_duration": result["source_duration"],
            "output_duration": result["output_duration"],
            "resolution": result["resolution"],
            "zoomed_clips": result["zoomed_clips"],
            "tuning": asdict(tuning),
        }
        with open(os.path.join(staging, SIDECAR_NAME), "w") as f:
            json.dump(sidecar, f, indent=2)

        os.rename(staging, final)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return final


def list_entries():
    """Every valid entry, newest first, plus the archive's total measured
    size (FR-014, FR-016). Entries with a missing or unparseable sidecar are
    omitted rather than breaking the listing (FR-018, SC-006)."""
    ensure_archive_dir()
    total_bytes = 0
    entries = []
    for de in os.scandir(ARCHIVE_DIR):
        if not de.is_dir() or de.name.startswith("."):
            continue
        entry = read_entry(de.name)
        if entry is None:
            continue
        size = _dir_size(de.path)
        total_bytes += size
        thumb, screenshot, video = entry.get("thumb"), entry.get("screenshot"), entry.get("video")
        entries.append({
            **{k: v for k, v in entry.items() if k not in ("video", "thumb", "screenshot")},
            "size_bytes": size,
            "has_thumb": bool(thumb) and os.path.exists(os.path.join(de.path, thumb)),
            "has_screenshot": bool(screenshot) and os.path.exists(os.path.join(de.path, screenshot)),
            "available": bool(video) and os.path.exists(os.path.join(de.path, video)),
        })
    entries.sort(key=lambda e: e.get("created_at", ""), reverse=True)
    return total_bytes, entries


def delete_entry(reel_id):
    """Remove an entry recursively after measuring its size, so the freed
    amount can be reported. Returns the freed bytes, or None when the entry
    does not exist (FR-024)."""
    path = entry_dir(reel_id)
    if not os.path.isdir(path):
        return None
    freed = _dir_size(path)
    shutil.rmtree(path)
    return freed

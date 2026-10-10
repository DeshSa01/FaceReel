"""Owns storage/sessions/: the durable queue of sessions and their videos.

Placed as a sibling of storage/jobs/ and storage/archive/, never inside
jobs/, because clean_jobs_dir() wipes every subdirectory of jobs/ at start-up
and a session's queue has to outlive exactly that restart (FR-020, research
D1). Like the archive, it stays safe by placement rather than by teaching a
destructive routine to spare some of what it finds.

One SessionStore holds every session in memory behind one lock, and writes a
session's whole record to disk on every state transition. Progress ticks are
the exception -- see SessionStore.__init__.
"""

import copy
import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime

import archive
from pipeline import friendly_error

BASE_DIR = os.path.dirname(__file__)
SESSIONS_DIR = os.path.join(BASE_DIR, "storage", "sessions")
SESSION_FILE = "session.json"
SCREENSHOTS = "screenshots"

# A product rule set by the user when the feature was specified, not a tuned
# value -- there is nothing to measure (constitution Principle II). Counts the
# session's videos that have not been removed, so failures count and removals
# free their slot (spec Assumptions).
MAX_VIDEOS_PER_SESSION = 10

# Waits, in seconds, before each retry of a video that failed only because
# YouTube couldn't be reached (pipeline.is_network_error). Chosen, not
# measured -- there is no record of how long outages here last (constitution
# Principle II). Doubling from 30s rides out a router or Wi-Fi blip quickly
# without hammering a network that is down. The 10-minute cap and the limit
# of eight retries (~45 minutes in all) mean an error wrongly classed as a
# network one blocks the queue for under an hour, not forever.
NETWORK_RETRY_DELAYS = (30, 60, 120, 240, 480, 600, 600, 600)

# session states (data-model.md)
OPEN, JOINING = "open", "joining"
FINISHED, NOTHING_TO_JOIN, JOIN_FAILED = "finished", "nothing_to_join", "join_failed"
ENDED = (FINISHED, NOTHING_TO_JOIN, JOIN_FAILED)

# video states
WAITING, PROCESSING, DONE, FAILED, REMOVED = "waiting", "processing", "done", "failed", "removed"


class SessionError(Exception):
    """A refusal with the HTTP status the caller should report."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def ensure_sessions_dir():
    os.makedirs(SESSIONS_DIR, exist_ok=True)


def session_dir(sid):
    """Validate before joining to SESSIONS_DIR. Every path in this module is
    built through here or screenshots_dir(), so a URL segment can never
    reach the filesystem unchecked (FR-023, constitution Principle V)."""
    if not archive.valid_id(sid):
        raise ValueError(f"Invalid session id: {sid!r}")
    return os.path.join(SESSIONS_DIR, sid)


def screenshots_dir(sid):
    return os.path.join(session_dir(sid), SCREENSHOTS)


def _now():
    # same format as archive sidecars: with UTC offset, so it is unambiguous
    # across a timezone change
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def _write_session(record):
    """Write via a temp file and os.replace: the rename is atomic on one
    filesystem, so a crash mid-write leaves either the old session.json or
    the new one, never a torn file that would lose the queue (research D1)."""
    path = os.path.join(session_dir(record["id"]), SESSION_FILE)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp, path)


def _read_session(path):
    """None for an unreadable file, which is logged and left in place --
    never deleted, since it may be the only record of someone's queue
    (research D3, constitution Principle V)."""
    try:
        with open(path) as f:
            record = json.load(f)
        if not isinstance(record, dict) or not archive.valid_id(record.get("id", "")):
            raise ValueError("not a session record")
        return record
    except (OSError, ValueError) as e:
        print(f"Skipping unreadable session file {path}: {e}")
        return None


def _friendly_result(result):
    """The per-video summary in a session's result carries each failure's
    reason; show it the same way a failed queue row does."""
    if not result or not result.get("videos"):
        return result
    return {**result, "videos": [{**v, "reason": friendly_error(v.get("reason"))}
                                 for v in result["videos"]]}


class SessionStore:
    def __init__(self):
        self._lock = threading.Lock()
        # the runner parks on this; anything that creates work notifies it
        self.changed = threading.Condition(self._lock)
        self._sessions = {}
        # Per-tick progress (stage/progress/message), keyed by video id or by
        # session id for a join. Memory only: ticks arrive several times a
        # second and a restart starts the video over anyway (FR-020), so
        # writing them would add disk I/O to an encode-bound host for nothing
        # (research D1).
        self._runtime = {}
        self._running_join = None
        # Set while the runner is paused after a network failure:
        # {sid, vid, until (monotonic), retry}. Memory only -- after a restart
        # the video is simply retried at once, which is what a restart is for.
        self._backoff = None
        self._next_seq = 1

    # ---- start-up -------------------------------------------------------

    def load(self):
        ensure_sessions_dir()
        with self._lock:
            self._sessions.clear()
            for name in os.listdir(SESSIONS_DIR):
                if not archive.valid_id(name):
                    continue
                record = _read_session(os.path.join(SESSIONS_DIR, name, SESSION_FILE))
                if record is not None and record["id"] == name:
                    self._sessions[name] = record
            seqs = [v["seq"] for s in self._sessions.values() for v in s["videos"]]
            self._next_seq = max(seqs, default=0) + 1
            return len(self._sessions)

    def recover(self):
        """Repair what a restart interrupted, using the archive as the
        tiebreaker (research D3). Runs before the runner starts, so nothing
        else is in flight."""
        removed_tmp = 0
        # Second crash window: inside archive_job/archive_session, between
        # makedirs(staging) and the final rename. A stale .tmp-<id> would make
        # the retry's makedirs raise FileExistsError and fail a video that FR-020
        # says must not fail. Only names with a valid id are touched, and only
        # under ARCHIVE_DIR (Principle V; documented in the README).
        if os.path.isdir(archive.ARCHIVE_DIR):
            for name in os.listdir(archive.ARCHIVE_DIR):
                if name.startswith(archive.TMP_PREFIX) and \
                        archive.valid_id(name[len(archive.TMP_PREFIX):]):
                    shutil.rmtree(os.path.join(archive.ARCHIVE_DIR, name), ignore_errors=True)
                    removed_tmp += 1

        requeued = recovered = 0
        with self._lock:
            for s in self._sessions.values():
                changed = False
                for v in s["videos"]:
                    if v["state"] != PROCESSING:
                        continue
                    # First crash window: archive_job's rename landed but the
                    # session write after it did not. Re-running would fail on
                    # the existing archive dir, so trust the archive instead.
                    entry = archive.read_entry(v["id"])
                    if entry is not None:
                        self._apply_done(v, entry.get("title"), {
                            k: entry.get(k) for k in ("clip_count", "output_duration",
                                                      "source_duration", "resolution",
                                                      "zoomed_clips", "filename")})
                        recovered += 1
                    else:
                        # keeps its seq, so it stays first in line; never
                        # marked failed for being interrupted (FR-020)
                        v["state"] = WAITING
                        requeued += 1
                    changed = True
                if s["state"] == JOINING and archive.read_entry(s["id"]) is not None:
                    entry = archive.read_entry(s["id"])
                    s["state"] = FINISHED
                    s["result"] = self._result_from_entry(s, entry)
                    changed = True
                if self._maybe_complete(s):
                    changed = True
                if changed:
                    _write_session(s)
        print(f"Sessions: {len(self._sessions)} loaded, {requeued} video(s) re-queued, "
              f"{recovered} recovered from the archive, {removed_tmp} stale staging folder(s) removed")

    # ---- ids ------------------------------------------------------------

    def _id_taken(self, candidate):
        if candidate in self._sessions or os.path.exists(os.path.join(SESSIONS_DIR, candidate)):
            return True
        if os.path.exists(os.path.join(archive.ARCHIVE_DIR, candidate)):
            return True
        return any(v["id"] == candidate for s in self._sessions.values() for v in s["videos"])

    def _new_id(self):
        # Video ids become archive entry ids and session ids key the joined
        # reel's entry, so both must be unique against the archive too
        # (research D6). A 48-bit collision is unlikely; checking is cheap.
        while True:
            candidate = uuid.uuid4().hex[:12]
            if not self._id_taken(candidate):
                return candidate

    # ---- sessions -------------------------------------------------------

    def create_session(self):
        ensure_sessions_dir()
        with self._lock:
            sid = self._new_id()
            os.makedirs(screenshots_dir(sid))
            record = {"id": sid, "created_at": _now(), "state": OPEN, "videos": [],
                      "completed_at": None, "result": None, "error": None}
            _write_session(record)
            self._sessions[sid] = record
            return sid

    def discard_session(self, sid):
        """Only a session that never had a video (FR-024). The record stays
        authoritative for anything that had work, so it is never deleted
        here; removed videos stay in the list, which is why this checks for
        an empty list and not for zero active videos."""
        with self._lock:
            s = self._get(sid)
            if s["videos"]:
                raise SessionError(409, "Only a session with no videos can be discarded.")
            del self._sessions[sid]
            # session_dir() validated sid; confined to storage/sessions/<sid>
            # (constitution Principle V)
            shutil.rmtree(session_dir(sid))

    def _get(self, sid):
        s = self._sessions.get(sid)
        if s is None:
            raise SessionError(404, "Session not found.")
        return s

    # ---- videos ---------------------------------------------------------

    def add_video(self, sid, url, tuning, upload=None, screenshot_from=None):
        """upload is (filename, fileobj); exactly one of it and
        screenshot_from must be given (contract POST .../videos)."""
        if (upload is None) == (screenshot_from is None):
            raise SessionError(400, "Provide a screenshot, or choose to reuse an earlier one.")
        if screenshot_from is not None and not archive.valid_id(screenshot_from):
            raise SessionError(400, "Malformed id.")
        with self._lock:
            s = self._get(sid)
            # Checked under the same lock that completion runs under, so a
            # video added in the instant the last one finishes either lands
            # before completion or is refused after it -- never lost
            # (research D4).
            if s["state"] != OPEN:
                raise SessionError(409, "This session has completed. Start a new session to add more videos.")
            if self._total(s) >= MAX_VIDEOS_PER_SESSION:
                raise SessionError(409, f"A session holds at most {MAX_VIDEOS_PER_SESSION} videos.")

            vid = self._new_id()
            shots = screenshots_dir(sid)
            os.makedirs(shots, exist_ok=True)
            if upload is not None:
                filename, fileobj = upload
                ext = os.path.splitext(filename or "")[1].lower()
                # The extension only ever lands after a validated id, and
                # splitext cannot return a separator; restrict it anyway.
                if not ext[1:].isalnum() or len(ext) > 6:
                    ext = ""
                shot = vid + ext
                with open(os.path.join(shots, shot), "wb") as f:
                    shutil.copyfileobj(fileobj, f)
            else:
                src = next((v for v in s["videos"] if v["id"] == screenshot_from), None)
                if src is None:
                    raise SessionError(400, "That screenshot is not from this session.")
                shot = vid + os.path.splitext(src["screenshot"])[1]
                shutil.copy2(os.path.join(shots, src["screenshot"]), os.path.join(shots, shot))

            video = {
                "id": vid, "seq": self._next_seq, "index": len(s["videos"]) + 1,
                "url": url, "screenshot": shot, "tuning": tuning, "state": WAITING,
                "added_at": _now(), "finished_at": None, "title": None,
                "result": None, "error": None,
            }
            self._next_seq += 1
            s["videos"].append(video)
            _write_session(s)
            self.changed.notify_all()
            return {"id": vid, "index": self._display_index(s, video),
                    "line_position": self._line_position(video, sid)}

    def remove_video(self, sid, vid):
        with self._lock:
            s = self._get(sid)
            v = next((v for v in s["videos"] if v["id"] == vid), None)
            if v is None:
                raise SessionError(404, "Video not found.")
            if v["state"] != WAITING:
                raise SessionError(409, "Only a waiting video can be removed.")
            v["state"] = REMOVED
            # removing the last waiting video can be what empties the queue
            # (spec edge case), so completion is checked here too
            if self._maybe_complete(s):
                self.changed.notify_all()
            _write_session(s)

    def screenshot_path(self, sid, vid):
        with self._lock:
            s = self._get(sid)
            v = next((v for v in s["videos"] if v["id"] == vid), None)
            if v is None:
                raise SessionError(404, "Video not found.")
            path = os.path.join(screenshots_dir(sid), v["screenshot"])
        if not os.path.exists(path):
            raise SessionError(404, "Screenshot not found.")
        return path

    # ---- runner interface (all called by runner.Runner) ----------------

    @staticmethod
    def _priority(s, v):
        """Queue order (FR-010, revised 2026-10-10): sessions in the order they
        were created, and within a session the order videos were added. A
        session started first finishes first, even if a later session's
        videos were added earlier. created_at is parsed rather than compared
        as text, since its UTC offset changes across DST."""
        return (datetime.fromisoformat(s["created_at"]), s["id"], v["seq"])

    def pick_next(self):
        """Caller holds self.changed. Joins first, then the first waiting
        video in queue order (_priority). Joins jump the line
        because their inputs are all ready, their user is waiting on exactly
        that output, and a join usually costs seconds -- behind ten later
        videos it would wait for an hour (research D2)."""
        joining = [s for s in self._sessions.values() if s["state"] == JOINING]
        if joining:
            s = min(joining, key=lambda s: (s["completed_at"] or "", s["id"]))
            self._running_join = s["id"]
            self._runtime[s["id"]] = {"stage": "join", "progress": 0, "message": "Preparing to join..."}
            return ("join", s["id"], None)
        waiting = [(self._priority(s, v), s, v) for s in self._sessions.values()
                   for v in s["videos"] if v["state"] == WAITING]
        if not waiting:
            return None
        _, s, v = min(waiting, key=lambda t: t[0])
        self._backoff = None
        v["state"] = PROCESSING
        _write_session(s)
        self._runtime[v["id"]] = {"stage": "start", "progress": 0, "message": "Starting..."}
        return ("video", s["id"], copy.deepcopy(v))

    def defer_for_network(self, sid, vid):
        """Put a video that couldn't reach YouTube back in line, in its
        original place, and pause the runner for the next backoff delay.
        Returns the delay, or None once the retries are used up -- the caller
        then fails the video. Back in "waiting", the video keeps its session
        open: a network blip must not complete a session as "nothing to join"
        (the 2026-10-10 outage that prompted this)."""
        with self._lock:
            s = self._sessions[sid]
            v = next(v for v in s["videos"] if v["id"] == vid)
            done = v.get("network_retries", 0)
            if done >= len(NETWORK_RETRY_DELAYS):
                return None
            delay = NETWORK_RETRY_DELAYS[done]
            v.update(state=WAITING, network_retries=done + 1)
            self._runtime.pop(vid, None)
            self._backoff = {"sid": sid, "vid": vid, "retry": done + 1,
                             "until": time.monotonic() + delay}
            _write_session(s)
            return delay

    def backoff_remaining(self):
        """Seconds the runner should still wait. Caller holds the lock."""
        if self._backoff is None:
            return 0
        return max(0.0, self._backoff["until"] - time.monotonic())

    def _backoff_message(self):
        b = self._backoff
        secs = int(self.backoff_remaining() + 0.999)
        when = f"{secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{secs}s"
        return (f"Couldn't reach YouTube. Retrying in {when} "
                f"(retry {b['retry']} of {len(NETWORK_RETRY_DELAYS)}).")

    def set_progress(self, key, stage, pct, message):
        with self._lock:
            self._runtime[key] = {"stage": stage, "progress": pct, "message": message}

    def mark_done(self, sid, vid, title, result):
        with self._lock:
            s = self._sessions[sid]
            v = next(v for v in s["videos"] if v["id"] == vid)
            self._apply_done(v, title, result)
            self._runtime.pop(vid, None)
            self._maybe_complete(s)
            _write_session(s)

    def mark_failed(self, sid, vid, error):
        with self._lock:
            s = self._sessions[sid]
            v = next(v for v in s["videos"] if v["id"] == vid)
            v.update(state=FAILED, error=error, finished_at=_now())
            self._runtime.pop(vid, None)
            self._maybe_complete(s)
            _write_session(s)

    def join_plan(self, sid):
        """The session's non-removed videos, in order, for the runner to join."""
        with self._lock:
            return copy.deepcopy([v for v in self._sessions[sid]["videos"]
                                  if v["state"] != REMOVED])

    def mark_join_result(self, sid, state, result=None, error=None):
        with self._lock:
            s = self._sessions[sid]
            s.update(state=state, result=result, error=error)
            self._runtime.pop(sid, None)
            self._running_join = None
            _write_session(s)

    def _apply_done(self, v, title, result):
        v.update(state=DONE, title=title, result=result, error=None, finished_at=_now())

    def _maybe_complete(self, s):
        """FR-011: complete the moment the session holds at least one video
        and none is waiting or processing. An empty session is never complete
        (spec edge case). Caller holds the lock and persists; returns whether
        the session changed."""
        if s["state"] != OPEN or not s["videos"]:
            return False
        if any(v["state"] in (WAITING, PROCESSING) for v in s["videos"]):
            return False
        s["state"] = JOINING
        s["completed_at"] = _now()
        self.changed.notify_all()
        return True

    def _result_from_entry(self, s, entry):
        return {"archive_id": s["id"], "output_duration": entry.get("output_duration"),
                "resolution": entry.get("resolution"), "clip_count": entry.get("clip_count"),
                "joined_count": sum(1 for v in entry.get("videos") or [] if v.get("state") == "joined"),
                "videos": entry.get("videos") or []}

    # ---- read side ------------------------------------------------------
    # Everything below returns deep copies built under the lock, never live
    # references: 002 research D6 found a real "dictionary changed size during
    # iteration" from a handler reading a record the worker was mutating, and
    # this store has more writers and more pollers than that did (research D12).

    @staticmethod
    def _total(s):
        return sum(1 for v in s["videos"] if v["state"] != REMOVED)

    @staticmethod
    def _display_index(s, video):
        """Rank among non-removed videos, so it pairs with _total() and a
        display never reads "video 6 of 5" (data-model display_index)."""
        if video["state"] == REMOVED:
            return None
        rank = 0
        for v in s["videos"]:
            if v["state"] != REMOVED:
                rank += 1
            if v is video:
                return rank
        return None

    def _wait_breakdown(self, video, own_sid):
        """What a waiting video is queued behind, split by whether it belongs
        to the same session. Joins count as other work: they run first."""
        own = other = 0
        mine = self._priority(self._sessions[own_sid], video)
        for s in self._sessions.values():
            for v in s["videos"]:
                ahead = v["state"] == PROCESSING or (
                    v["state"] == WAITING and self._priority(s, v) < mine)
                if ahead:
                    if s["id"] == own_sid:
                        own += 1
                    else:
                        other += 1
            if s["state"] == JOINING:
                other += 1
        return own, other

    def _line_position(self, video, own_sid):
        """The real wait across every session (spec edge case): everything
        waiting ahead of it, plus joins (which run first), plus whatever is
        running now."""
        own, other = self._wait_breakdown(video, own_sid)
        return 1 + own + other

    def _summary(self, s):
        counts = {k: 0 for k in (WAITING, PROCESSING, DONE, FAILED, REMOVED)}
        for v in s["videos"]:
            counts[v["state"]] += 1
        first = next((v for v in s["videos"] if v["state"] != REMOVED), None)
        return {"id": s["id"], "created_at": s["created_at"], "state": s["state"],
                "title": first["title"] if first else None,
                # the title is only known once a video finishes; until then
                # the link is what the user will recognise (FR-003)
                "first_url": first["url"] if first else None,
                "counts": counts, "total": self._total(s)}

    def _public_video(self, s, v):
        out = {k: v[k] for k in ("id", "index", "url", "tuning", "state", "added_at",
                                 "finished_at", "title", "result")}
        # the stored error stays raw for debugging; people get one sentence
        out["error"] = friendly_error(v["error"])
        if v["error"] and out["error"] != v["error"]:
            out["error_detail"] = v["error"]
        out["display_index"] = self._display_index(s, v)
        if v["state"] == PROCESSING:
            out.update(self._runtime.get(v["id"], {"stage": "start", "progress": 0, "message": ""}))
        if v["state"] == WAITING and self._backoff and self._backoff["vid"] == v["id"] \
                and self.backoff_remaining() > 0:
            out["network_wait"] = self._backoff_message()
        if v["state"] == WAITING:
            # Split out work from other sessions: without it, a video queued
            # behind someone else's earlier-added video looks stuck, because
            # nothing in its own session is moving (FR-010 serves by add time,
            # not by session).
            own, other = self._wait_breakdown(v, s["id"])
            out.update(line_position=1 + own + other, ahead_own=own, ahead_other=other)
        return out

    def snapshot(self, sid):
        with self._lock:
            s = self._get(sid)
            live = [v for v in s["videos"] if v["state"] != REMOVED]
            own_processing = any(v["state"] == PROCESSING for v in s["videos"])
            own_waiting = any(v["state"] == WAITING for v in s["videos"])
            last = live[-1] if live else None
            out = self._summary(s)
            out.update({
                "completed_at": s["completed_at"],
                "limit": MAX_VIDEOS_PER_SESSION,
                # contract: only this session's own videos count (FR-011a)
                "will_complete_after_current": s["state"] == OPEN and own_processing and not own_waiting,
                "prefill": {"from_video": last["id"], "tuning": last["tuning"]} if last else None,
                "videos": [self._public_video(s, v) for v in s["videos"]],
                "join": (dict(self._runtime[sid]) if s["state"] == JOINING and sid in self._runtime
                         else None),
                "result": _friendly_result(s["result"]),
                "error": friendly_error(s["error"]),
            })
            return copy.deepcopy(out)

    def list_open(self):
        with self._lock:
            open_ = [self._summary(s) for s in self._sessions.values()
                     if s["state"] in (OPEN, JOINING)]
        open_.sort(key=lambda s: s["created_at"])
        return copy.deepcopy(open_)

    def active(self):
        """What the shared progress bar shows (contract GET /api/jobs/active)."""
        with self._lock:
            for s in self._sessions.values():
                for v in s["videos"]:
                    if v["state"] == PROCESSING:
                        rt = self._runtime.get(v["id"], {"stage": "start", "progress": 0, "message": ""})
                        return {"id": v["id"], "kind": "video", "session_id": s["id"],
                                "index": self._display_index(s, v), "total": self._total(s),
                                "status": "processing", **rt}
            if self._backoff and self.backoff_remaining() > 0:
                b = self._backoff
                s = self._sessions[b["sid"]]
                v = next(v for v in s["videos"] if v["id"] == b["vid"])
                return {"id": v["id"], "kind": "video", "session_id": s["id"],
                        "index": self._display_index(s, v), "total": self._total(s),
                        "status": "processing", "stage": "network", "progress": 0,
                        "message": self._backoff_message()}
            if self._running_join is not None:
                sid = self._running_join
                rt = self._runtime.get(sid, {"stage": "join", "progress": 0, "message": ""})
                return {"id": sid, "kind": "join", "session_id": sid, "index": None,
                        "total": None, "status": "processing", **rt}
            ended = [s for s in self._sessions.values() if s["state"] in ENDED]
            if not ended:
                return None
            s = max(ended, key=lambda s: (s["completed_at"] or "", s["id"]))
            if s["state"] == FINISHED:
                n = (s["result"] or {}).get("joined_count") or 0
                status, message = "done", f"Joined {n} video(s) into one reel."
            elif s["state"] == NOTHING_TO_JOIN:
                status, message = "done", "No video produced footage, so there was nothing to join."
            else:
                status, message = "error", s["error"] or "Joining failed."
            return {"id": s["id"], "kind": "session", "session_id": s["id"],
                    "state": s["state"], "status": status, "message": message}

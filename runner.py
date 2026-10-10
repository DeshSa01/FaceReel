"""The single consumer of the application-wide line.

Before sessions, every submission got its own thread and a 409 refused a
second one while the first ran. That *enforced* one-video-at-a-time. A queue
accepts every submission, so something else has to decide when each one
runs. Here that is one long-lived thread, and with only one consumer FR-010
holds by construction rather than by a check that could be bypassed
(research D2).

The pipeline and ffmpeg run outside the store lock; only state transitions
take it.
"""

import os
import shutil
import threading
import traceback

import archive
import pipeline
import sessions


class Runner:
    def __init__(self, store, jobs_dir):
        self.store = store
        self.jobs_dir = jobs_dir
        self._thread = None

    def start(self):
        # Started from app.lifespan, not at import, for the same reason
        # clean_jobs_dir() isn't at module scope: importing must have no side
        # effects.
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="facereel-runner", daemon=True)
            self._thread.start()

    def _loop(self):
        while True:
            with self.store.changed:
                item = self.store.pick_next()
                while item is None:
                    self.store.changed.wait()
                    item = self.store.pick_next()
            kind, sid, video = item
            # A bug escaping here would kill the only consumer and silently
            # stop every session's queue, so nothing is allowed out.
            try:
                if kind == "join":
                    self._run_join(sid)
                else:
                    self._run_video(sid, video)
            except Exception:
                traceback.print_exc()

    def _run_video(self, sid, video):
        job_dir = os.path.join(self.jobs_dir, video["id"])
        try:
            self._process(sid, video, job_dir)
        finally:
            # A failed video leaves its downloaded source here, and a queue
            # can fail several in a row -- gigabytes that would otherwise wait
            # for the next restart. Scratch only (the reel and screenshot have
            # already been moved into the archive), inside the clean_jobs_dir()
            # bound, and vid is store-generated.
            shutil.rmtree(job_dir, ignore_errors=True)

    def _process(self, sid, video, job_dir):
        vid = video["id"]
        try:
            os.makedirs(job_dir, exist_ok=True)
            # Copy, never pass the session's own screenshot through.
            # archive_job *moves* its screenshot into the archive, so handing
            # it the session copy would take it out of storage/sessions/. A
            # restart after that leaves a waiting video with no screenshot,
            # and a later video can no longer be prefilled from it
            # (research D3).
            src = os.path.join(sessions.screenshots_dir(sid), video["screenshot"])
            shot = os.path.join(job_dir, "screenshot" + os.path.splitext(video["screenshot"])[1])
            shutil.copy2(src, shot)
            tuning = pipeline.Tuning(**video["tuning"])
        except Exception as e:
            self.store.mark_failed(sid, vid, f"Unexpected error: {e}")
            return

        def progress(stage, pct, message):
            self.store.set_progress(vid, stage, round(min(pct, 99), 1), message)

        try:
            result = pipeline.process_job(video["url"], shot, job_dir, progress, tuning)
        except pipeline.PipelineError as e:
            self.store.mark_failed(sid, vid, str(e))
            return
        except Exception as e:
            self.store.mark_failed(sid, vid, f"Unexpected error: {e}")
            return

        try:
            archive.archive_job(vid, video["url"], result, tuning, shot, session_id=sid)
        except Exception as e:
            # The reel generated correctly but did not persist -- report failure
            # rather than success; the atomic rename guarantees there is no
            # half-saved reel to explain (001 research D8).
            self.store.mark_failed(sid, vid, f"Reel was generated but could not be saved: {e}")
            return

        self.store.mark_done(sid, vid, result["title"],
                             {k: v for k, v in result.items() if k not in ("output", "title")})

    def _run_join(self, sid):
        videos = self.store.join_plan(sid)
        inputs, summary, clip_count = [], [], 0
        for v in videos:
            item = {"vid": v["id"], "title": v["title"], "url": v["url"]}
            if v["state"] == sessions.DONE:
                entry = archive.read_entry(v["id"])
                path = os.path.join(archive.entry_dir(v["id"]), entry["video"]) if entry else None
                if path and os.path.exists(path):
                    inputs.append(path)
                    clip_count += (v["result"] or {}).get("clip_count") or 0
                    summary.append({**item, "state": "joined"})
                else:
                    # deleting a single reel doesn't touch the session, so the
                    # join skips it and says so (research D6)
                    summary.append({**item, "state": "skipped",
                                    "reason": "Its reel was deleted from the archive before the join."})
            else:
                summary.append({**item, "state": "failed", "reason": v["error"]})

        if not inputs:
            self.store.mark_join_result(sid, sessions.NOTHING_TO_JOIN,
                                        result={"joined_count": 0, "videos": summary})
            return

        work_dir = os.path.join(self.jobs_dir, f"join-{sid}")

        def progress(stage, pct, message):
            self.store.set_progress(sid, stage, round(min(pct, 99), 1), message)

        try:
            joined = pipeline.join_reels(inputs, work_dir, progress)
            archive.archive_session(sid, joined["output"], {
                "clip_count": clip_count, "output_duration": joined["output_duration"],
                "resolution": joined["resolution"], "videos": summary,
            })
            self.store.mark_join_result(sid, sessions.FINISHED, result={
                "archive_id": sid, "output_duration": joined["output_duration"],
                "resolution": joined["resolution"], "clip_count": clip_count,
                "joined_count": len(inputs), "videos": summary,
            })
        except Exception as e:
            # individual reels are untouched by a failed join (FR-022)
            self.store.mark_join_result(sid, sessions.JOIN_FAILED,
                                        result={"joined_count": 0, "videos": summary},
                                        error=str(e) or e.__class__.__name__)
        finally:
            # Up to ten re-encoded reels would otherwise sit here until the
            # next restart. Inside the clean_jobs_dir() bound; sid came from
            # the store, which only ever holds validated ids.
            shutil.rmtree(work_dir, ignore_errors=True)

# Phase 1 Quickstart: Verifying the Session Video Queue

Three things here cannot be settled by reading code, and they decide whether the feature works:

- **Step 6**, a restart mid-queue.
- **Step 8**, a mixed-resolution join that must decode cleanly.
- **Step 12**, the same restart done as a real container redeploy.

Use short source videos (1–3 minutes) so a session of several videos finishes in reasonable time. Keep a terminal open on `storage/sessions/`, because several assertions are about what is on disk.

Contracts referenced below: [sessions-api.md](./contracts/sessions-api.md). States and fields: [data-model.md](./data-model.md).

## Local (fast loop, macOS)

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

### 1. The chooser with nothing running (FR-001)

```bash
curl -s localhost:8765/api/sessions | python3 -m json.tool   # {"sessions": []}
curl -s localhost:8765/api/jobs/active                         # {"job": null}
```

Open `/`. Only **Create session** is offered. There is no list and no progress bar.

### 2. Create a session and queue three videos (US1, FR-006, FR-009)

Create a session from the UI. The browser lands on `/session/<sid>`, and `storage/sessions/<sid>/session.json` exists with `"state": "open"` and `"videos": []`.

Add video 1 with a screenshot. It starts processing at once (US1 scenario 2), and the bottom bar reads "Session <sid…> · video 1 of 1 · …" (FR-016).

While it runs, add videos 2 and 3. Check that:

- The form came back with video 1's screenshot preview and tuning already set, and an empty link field (FR-007, US1 scenario 8). Adding needs only a new link.
- Each new video shows as **waiting** with a `line_position` (FR-015).
- In `session.json`, `seq` increases in the order the videos were added.

### 3. Hand-off and order (FR-009, SC-002)

```bash
watch -n1 'curl -s localhost:8765/api/jobs/active | python3 -c "
import json,sys; j=json.load(sys.stdin)[\"job\"]; print(j and (j[\"kind\"], j[\"index\"], j[\"status\"], j[\"stage\"], j[\"progress\"]))"'
```

When video 1 finishes, video 2 must be `processing` within 5 seconds. The order must be 1 → 2 → 3, never anything else.

### 4. The completion warning and auto-completion (FR-011, FR-011a)

While video 3 (the last) is processing and nothing else is waiting, the session page shows the warning that the session will complete when this video finishes. `will_complete_after_current` is `true`.

When video 3 finishes, the session moves to `joining`, then to `finished`. Then:

- Try to add a fourth video from the open page. It is refused with the "session has completed" message, and the page offers a new session.
- `curl -s -o /dev/null -D - localhost:8765/api/sessions/<sid>/output` returns `200` with `video/mp4`. Use a GET: FastAPI GET routes answer `HEAD` with 405, as the archive routes already do.
- Check the join:

```bash
for f in storage/archive/<vid1>/output.mp4 storage/archive/<vid2>/output.mp4 storage/archive/<vid3>/output.mp4 storage/archive/<sid>/output.mp4; do
  ffprobe -v error -show_entries format=duration -of csv=p=0 "$f"; done
```

The last duration equals the sum of the first three to within 1 second (SC-003).

- `/archive` lists the joined reel marked as a session reel, plus the three single reels (FR-019, FR-021).
- The bottom bar shows the session-finished notice, which links to `/session/<sid>` (research D9).

### 5. The limit and removal (FR-008, FR-012, FR-013)

Create a new session and add 10 videos quickly. Use the same short link 10 times; duplicates are allowed. Then:

- An 11th add returns 409 with the limit message, and `session.json` is unchanged (SC-006).
- Remove a waiting video. It shows as `removed`, and an 11th add now succeeds, because removed videos do not count.
- The processing video offers no remove control, and `DELETE` on it returns 409.
- Remove every remaining waiting video. Once the processing one finishes, the session completes and joins only what finished.

### 6. Restart mid-queue (FR-020, SC-007): **decisive**

Create a session with three videos. While video 2 is in the `scan` stage, stop uvicorn with Ctrl-C and start it again. Then:

- `session.json` shows video 2 back in `waiting` with its original `seq`, never `failed`.
- Within a few seconds video 2 is `processing` again, restarting from the beginning. The bar's percentage drops back. That is expected and honest (research D9).
- Video 3 follows it, and the session joins normally.
- `storage/jobs/` held video 2's partial scratch before the restart. It is empty after start-up, and nothing under `storage/sessions/` was removed.

**Crash-window variant (research D3)**: add a temporary `time.sleep(10)` between `archive_job` and the session write. Kill the process inside that window and restart. The video must come back as `done`, not re-run and not `failed`. Remove the sleep afterwards.

**Second window (research D3)**: move the sleep to just after `os.makedirs(staging)` in `archive_job`. Kill the process inside it and restart. The start-up log reports one removed staging folder, `storage/archive/.tmp-<vid>` is gone, and the video re-runs to `done`, never `failed`. Remove the sleep afterwards.

### 7. Two sessions share one line (FR-005, FR-010)

Create session A and add 2 videos. In a **second browser**, create session B and add 1 video. Then add a third video to A. Then:

- `GET /api/sessions` lists both (US3 scenario 1).
- A's third video, added last, still goes ahead of B's video: the older session finishes first (FR-010).
- B's video shows a `line_position` that counts all of A's remaining videos, and the page says it is waiting on another session.
- Only one video is ever `processing` application-wide.
- Join A from the second browser. Its queue matches the first browser's within 2 seconds (US3 scenario 3).

### 8. Mixed-resolution join (FR-018): **decisive**

Make one session with video 1 at default settings and video 2 with **Download the source in 4K** ticked, using a source that has a 4K rendition. When it finishes, decode the whole joined reel:

```bash
ffmpeg -v error -i storage/archive/<sid>/output.mp4 -f null - && echo CLEAN
```

This must print `CLEAN` with no error lines above it. Also play it in Safari and in Chrome through the transition between the two videos. It must play with no freeze or garbled frames.

### 9. Failure inside a session (FR-014, US2 scenario 3/4)

Add three videos where the middle one has a screenshot of someone who does not appear in it. That video ends `failed` with the "not found" reason, video 3 still runs, and the joined reel contains videos 1 and 3. The joined reel's sidecar `videos` names video 2 and its reason.

Repeat with every video failing. The session ends `nothing_to_join`, no `storage/archive/<sid>` is created, and the bar's notice says there was nothing to join.

### 10. Discarding an empty session (FR-024)

Create a session and do not add anything. It appears in the chooser. `DELETE /api/sessions/<sid>` removes `storage/sessions/<sid>` and nothing else. On a session that has videos, the same call returns 409.

Malformed ids return 400:

```bash
curl -s -o /dev/null -w '%{http_code}\n' localhost:8765/api/sessions/..%2F..%2Fapp.py   # 404: the router decodes %2F and matches no route, so no handler or path is ever reached
curl -s -o /dev/null -w '%{http_code}\n' -X DELETE localhost:8765/api/sessions/ZZZ          # 400
```

### 11. Retired routes (research D10)

`curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8765/api/jobs` must return 404 or 405, never 200.

## Container (the environment that ships)

### 12. Redeploy mid-session: **decisive**

On the nucbox, with the published image, queue three videos. While video 2 is processing, redeploy the stack from Portainer (or run `docker compose up -d --force-recreate`). After the container is back:

- The session resumes exactly as in step 6.
- `storage/sessions/` is on the host bind mount, so `/opt/facereel/storage/sessions/<sid>/session.json` exists on the **host**.

### 13. Mixed-resolution join in the container

Repeat step 8 inside the container. The container's ffmpeg build is not the Homebrew one (constitution Principle III), so `ffmpeg -v error … -f null -` must be run with `docker exec` against the container's file.

### 14. Join timing (research D5, Principle II)

On the nucbox, record the wall-clock join time for:

- (a) A three-reel copy-path session.
- (b) A three-reel mixed 1080p/4K session, under the mode-canvas policy.
- (c) The same session under a max-canvas policy, toggled temporarily.

Write the figures into the comment on the canvas rule in `pipeline.join_reels`.

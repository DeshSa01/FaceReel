# Phase 1 Quickstart: Verifying the Reel Archive

The verification that matters is the restart test — the whole feature exists because restarting currently destroys everything. Do it against the container, not just locally, because that is where the bind mount and the wipe interact.

## Local (fast loop)

```bash
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

### 1. Archive on completion (Story 1, FR-001)

Generate a reel through the UI as normal, then:

```bash
ls storage/archive/                 # one directory, 12 hex characters
ls storage/archive/*/               # output.mp4, thumb.jpg, screenshot.*, reel.json
cat storage/archive/*/reel.json | python3 -m json.tool
```

Confirm the sidecar carries the title, url, created_at, the stats, and all five tuning values (FR-006 to FR-010).

### 2. The restart test (SC-001 — the point of the feature)

```bash
# stop the server (Ctrl-C), then start it again
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8765
```

The start-up log must still say `Cleared N orphaned job folder(s)`, and:

```bash
ls storage/jobs/                    # empty — working files cleared as before (FR-005)
ls storage/archive/                 # entry still present (FR-003, FR-004)
curl -s localhost:8765/api/archive | python3 -m json.tool
```

**This is the assertion that matters.** Before this feature the reel was gone; it must now be listed and playable.

### 3. Listing and ordering (FR-014, FR-016)

Generate a second reel, then:

```bash
curl -s localhost:8765/api/archive | python3 -c "
import json,sys
d=json.load(sys.stdin)
print('total_bytes:', d['total_bytes'])
for e in d['entries']:
    print(e['created_at'], e['id'], e['title'][:40])"
```

Newest must be first. `total_bytes` must be non-zero and roughly `du -sb storage/archive`.

### 4. Playback and seeking (FR-019, FR-020)

```bash
ID=$(curl -s localhost:8765/api/archive | python3 -c "import json,sys;print(json.load(sys.stdin)['entries'][0]['id'])")
curl -s -o /dev/null -w "full: %{http_code} %{size_download} bytes\n" localhost:8765/api/archive/$ID/video
curl -s -o /dev/null -w "range: %{http_code}\n" -H "Range: bytes=0-1023" localhost:8765/api/archive/$ID/video
```

The ranged request must return **206**, not 200 — without it the player cannot seek.

### 5. Path traversal is rejected (the security note in research D5)

```bash
curl -s -o /dev/null -w "%{http_code}\n" "localhost:8765/api/archive/..%2F..%2Fetc/video"      # expect 400
curl -s -o /dev/null -w "%{http_code}\n" -X DELETE "localhost:8765/api/archive/../../jobs"      # expect 400
curl -s -o /dev/null -w "%{http_code}\n" localhost:8765/api/archive/ZZZZZZZZZZZZ/video          # expect 400
```

All three must be **400**, and `storage/` must be untouched afterwards. Run this before trusting the delete endpoint with anything.

### 6. Deletion (Story 3, FR-022 to FR-025)

```bash
du -sh storage/archive/
curl -s -X DELETE localhost:8765/api/archive/$ID
ls storage/archive/$ID 2>&1          # must be "No such file or directory"
du -sh storage/archive/              # smaller by that reel's size (SC-003)
curl -s -X DELETE localhost:8765/api/archive/$ID   # second delete -> 404, not a silent success
```

Then restart once more and confirm the deleted reel does not come back (FR-025).

### 7. Damaged entries do not break the page (FR-018, SC-006)

```bash
mkdir -p storage/archive/deadbeef0001 && echo 'not json' > storage/archive/deadbeef0001/reel.json
mkdir -p storage/archive/deadbeef0002                      # no sidecar at all
curl -s localhost:8765/api/archive | python3 -m json.tool  # must still list the good entries, no 500
```

Then delete a good entry's `output.mp4` by hand and confirm it reports `available: false` rather than 500 or vanishing.

Clean up the fixtures afterwards.

### 8. The generation flow is unchanged (FR-027, SC-007)

Run a normal job start to finish. The progress bar, the result card, its stats line, in-page playback and the download button must all behave exactly as before — the only difference being that the reel is afterwards present in the archive. Confirm the download filename still matches the `<title-slug>-<timestamp>.mp4` scheme.

Also confirm a second submission while one is running still returns **409** (FR-028).

## Container (the deployment that matters)

After the image is rebuilt and the stack redeployed:

```bash
# on the host
ls -la /opt/facereel/storage/archive/
docker compose logs facereel | grep "orphaned job folder"
```

Then:

1. Generate a reel through `http://<host>:8765`.
2. Confirm it appears in the archive page.
3. **Restart the container** (`docker compose restart facereel`, or Portainer's restart).
4. Reload the archive page — the reel must still be listed and must still play.
5. Confirm on the host that `/opt/facereel/storage/archive/<id>/` exists, proving it landed on the bind mount rather than the container's writable layer (FR-004).
6. **Redeploy** (`docker compose pull && up -d`) and confirm the archive survives a container replacement, not just a restart.

Step 6 is the one that proves durability against redeployment rather than merely against a restart, and it is the scenario that actually happens whenever a new image ships.

## Ownership check

If archiving fails in the container with a permission error, the bind mount is not writable by uid 1000:

```bash
sudo chown -R 1000:1000 /opt/facereel/storage
```

The archive directory is created by the app at start-up, so it inherits the mount's ownership — the same failure mode the README already documents for `storage/jobs/`.

# Phase 0 Research: Reel Archive

No `NEEDS CLARIFICATION` markers reached this phase. The three questions that would have produced them — retention policy, how the listing presents a reel, and which fields are recorded — were put to the user before the spec was written and are settled in the spec's Assumptions. What follows is the design reasoning and the alternatives rejected.

## D1. Where archived reels live

**Decision**: A sibling directory, `storage/archive/`, alongside the existing `storage/jobs/`.

**Rationale**: `app.py`'s `clean_jobs_dir()` iterates `storage/jobs/` and removes every subdirectory it finds. Its contract — "anything still on disk at startup is orphaned" — is true precisely because job records are in memory. That reasoning does not apply to archived reels, which carry their own on-disk record. Putting the archive outside `jobs/` means the existing wipe needs no modification at all, so FR-003 and FR-005 are satisfied by placement rather than by adding a rule that a future reader could get wrong.

**Alternatives rejected**:
- *Keep reels in `storage/jobs/` and teach the wipe to spare archived ones.* Makes a destructive routine conditional on metadata it would have to parse. One parsing bug deletes the user's whole archive.
- *A directory outside `storage/`.* Only `storage/` is bind-mounted; anything else lives in the container's writable layer and dies with the container.

## D2. One JSON sidecar per reel vs. a central index

**Decision**: `storage/archive/<id>/reel.json`, one file per reel, self-contained beside its media.

**Rationale**:
- Deletion is a single directory removal. There is no second place to update, so a partial delete cannot leave a dangling index row.
- A corrupt or truncated sidecar can only affect its own entry, which is what FR-018 and SC-006 require. A corrupt central index takes out the entire archive.
- No read-modify-write cycle, so no risk of concurrent writes clobbering each other, and no need to hold a lock across a write.
- The archive stays comprehensible from a shell. Copying a directory out, or deleting one by hand, does the obvious thing.

**Cost accepted**: listing reads N small files instead of one. At the stated scale — hundreds of reels — this is a few milliseconds of `os.scandir` plus small reads, and it is only done when the archive page is opened.

**Alternatives rejected**:
- *Single `archive/index.json`.* One fsync-torn write loses every record. Rejected on blast radius, not performance.
- *SQLite.* Genuinely appropriate for querying at scale, and it would give atomic deletes. Rejected because there is no querying beyond "list all, newest first", it adds a schema and migration burden to a two-file app, and it makes the archive opaque to inspection. Reconsider if the archive ever needs search or filtering.

## D3. Preventing half-written entries

**Decision**: Assemble each entry in `storage/archive/.tmp-<id>/` and `os.rename` the finished directory to `storage/archive/<id>`. The lister ignores names beginning with a dot.

**Rationale**: `rename` within one filesystem is atomic — the entry either exists complete or does not exist. This is what makes the disk-full edge case safe: a job that runs out of space during archiving leaves a `.tmp-` directory to be cleaned, never a visible entry with a playable-looking but truncated video. Both directories are under `storage/archive/`, guaranteeing the same filesystem, which a `/tmp` staging area would not.

**Also decided**: write `reel.json` last, after the media files are in place, so its presence means the entry is complete.

**Alternatives rejected**:
- *Write in place and hope.* An interrupted archive leaves an entry that lists but will not play.
- *Write a `.complete` marker file.* Equivalent guarantee but adds a second thing to check on every read, and leaves entries that must be garbage-collected.

## D4. Move the reel, or copy it

**Decision**: Move `output.mp4` out of the job directory into the archive entry, then repoint the in-memory job's `output_path` at its new location.

**Rationale**: A copy doubles peak disk use for a file that can be hundreds of megabytes on a small home server, and the job-directory copy is deleted at the next restart anyway. Moving means one copy exists at all times. Repointing `output_path` in the same step keeps `GET /api/jobs/{id}/output` — which the result card uses for both the player and the download link — working with no change to that endpoint, satisfying FR-027.

**Alternatives rejected**:
- *Copy and leave the original.* Wasteful, and creates a window where two files disagree.
- *Change the result card to use the archive endpoint immediately.* More frontend churn for no gain, and it would touch the generation flow that FR-027 protects.

## D5. Identity of an entry

**Decision**: Reuse the existing 12-hex-character job id as the archive id.

**Rationale**: Already generated per job (`uuid4().hex[:12]`), already unique, already the identifier the user saw during generation, and it makes an archived reel traceable back to its job in the logs. Collision risk at 48 bits over hundreds of entries is negligible, and the archive write can assert the directory does not already exist.

**Consequence**: the id appears in URLs and is used to build filesystem paths, so it **must** be validated against `^[0-9a-f]{12}$` before any path construction. This is the single most important security note in the design: without it, `../` in a path segment reaches outside the archive, and deletion is destructive. Validation lives in `archive.py` so no caller can forget it.

**Alternatives rejected**:
- *Sequential integers.* Requires a counter, which is shared mutable state — the thing the sidecar design avoids.
- *The download filename* (e.g. `ricka-20260727-151225`). Derived from the video title, so not guaranteed unique or filesystem-safe.

## D6. The still image

**Decision**: Extract one frame from the finished reel with the ffmpeg already in the image, at archive time, scaled down and saved as `thumb.jpg`.

**Rationale**: The user chose a thumbnail grid because a title alone does not identify *which person* a reel is of. A frame from the reel shows the actual content. Extracting a single frame is a sub-second operation against a job that already took minutes, so doing it at archive time — rather than lazily on first view — keeps the listing endpoint free of subprocess calls and means a missing thumbnail is a permanent, visible fact rather than a repeated failed attempt.

**Detail**: seek a short way into the reel rather than taking frame zero, since the first frames of a cut can be a transition or a dark frame.

**Failure handling**: thumbnail extraction is **non-fatal**. If it fails, the entry is still written and the reel still plays; the listing shows a placeholder. This is required by the spec's edge case and means the thumbnail step must not be able to fail the archive write.

**Alternatives rejected**:
- *Use the uploaded reference face image as the thumbnail.* Shows who, but not what — every reel of the same person would look identical. The screenshot is retained as a recorded field regardless (FR-009), so both are available.
- *Generate thumbnails lazily on first request.* Puts a subprocess call in a page load and re-attempts on every view when it fails.

## D7. Ordering and the total size

**Decision**: Sort by the recorded `created_at` timestamp from the sidecar, descending. Total size is summed from actual file sizes at list time.

**Rationale**: Sorting on recorded data rather than filesystem mtime survives a `cp -r`, a restore, or a volume migration, any of which rewrites mtimes and would silently scramble the order. Summing real file sizes rather than a stored number means the figure cannot drift from reality, and `os.scandir` makes it cheap.

## D8. Archive failure and job outcome

**Decision**: If archiving raises, the job is reported as failed, with the reason surfaced to the user.

**Rationale**: The spec's edge case requires a disk-full at archive time to be "reported against that job". Reporting success while the reel silently failed to persist would be the worst outcome: the user believes it is saved, restarts, and loses it. Because the rename is atomic, a failed archive leaves nothing visible behind, so reporting failure is truthful — there is no half-saved reel to explain.

**Consequence accepted**: a reel that generated correctly but failed to archive is lost. Given the failure mode is essentially always "disk full", the alternative — keeping it in a job directory that the next restart wipes — is a false promise.

## D9. Testing approach

**Decision**: Manual end-to-end verification via `quickstart.md`. No test framework added.

**Rationale**: The repository has no test suite, no test dependency, and no CI test step; introducing pytest is a separate decision the user has not asked for. The verification that actually matters for this feature — that reels survive a restart — is inherently an integration test against a running container, which `quickstart.md` scripts explicitly.

**Mitigation**: `archive.py` is written so its logic is testable without a server — id validation, sidecar round-tripping, listing, and deletion all operate on a directory path passed in or module-level constant, so a future suite can point them at a scratch directory. This is a structural choice made now to keep that option cheap.

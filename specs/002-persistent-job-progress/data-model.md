# Phase 1 Data Model: Persistent Job Progress

This feature introduces **no persistent storage**. Nothing is written to disk, no schema changes, no new files under `storage/`. What follows describes the shape of an existing in-memory record (with one addition), the response derived from it, and two disposable per-browser values.

## 1. Job record — existing, one field seeded

Lives in `app.py`'s module-level `jobs` dict, keyed by job id. Created by `create_job`, mutated by `_worker`. Lost when the process stops — which is the fact FR-012 exists to report.

| Field | Type | Set by | Notes |
|---|---|---|---|
| `id` | string | `create_job` | `uuid4().hex[:12]`, so always `^[0-9a-f]{12}$` |
| `status` | `processing` \| `done` \| `error` | both | The only field that drives indicator state |
| `stage` | string | `_worker` | `start`, `reference`, `download`, `scan`, `refine`, `track`, `stitch`, `done` — named to the user so slow is distinguishable from stalled (FR-018) |
| `progress` | number 0–100 | `_worker` | Capped at 99 until completion by the existing `progress()` callback |
| `message` | string | both | Human-readable; carries the failure reason when `status` is `error` |
| `result` | object \| null | `_worker` | Reel stats; `null` until completion |
| `tuning` | object | `create_job` | The five values the reel was started with |
| `output_path` | string \| **null** | `create_job` (seeded), `_worker` (set) | **The change.** Seeded to `null` at creation so the record's key set is fixed for its lifetime — see below |

### Why `output_path` is seeded

`_worker` currently *adds* this key on completion. `get_job` builds its response by iterating `job.items()`. A dict that gains a key mid-iteration raises `RuntimeError: dictionary changed size during iteration`.

Today that window is microseconds, once per reel, and requires a poll to land exactly at completion. This feature polls from every page continuously, including at that moment. Seeding the key at creation makes the record's shape constant, so a concurrent `update()` can only replace values — safe to read under the GIL with no locking. Locking would not have helped: `_worker` does not hold `jobs_lock` when it updates a job.

The seeded `null` is never read. It needs a comment saying so and saying why, or it will be deleted as dead code.

### State transitions

```text
                    ┌──────────────► done   (reel archived; output_path set)
processing ─────────┤
                    └──────────────► error  (message carries the reason)

(process stops) ───► record ceases to exist  ──► reported by the client as
                                                 "interrupted" (FR-012)
```

Terminal states are final: a record never leaves `done` or `error`. The third outcome is not a state but an absence, which is why it can only be detected client-side (research D4).

## 2. Active-reel response — new, derived

Returned by `GET /api/jobs/active`. Not stored; computed per request. Full shape in [contracts/active-job-api.md](./contracts/active-job-api.md).

Selection rule, in order:

1. The record with `status == "processing"`, if one exists. At most one can, because `POST /api/jobs` refuses a second.
2. Otherwise the most recently created record, whatever its terminal state — this is what makes FR-008 and FR-009 reachable after the reel has finished.
3. Otherwise `null`.

"Most recently created" is the last-inserted key: `jobs` is a plain dict, and insertion order is a language guarantee, not an implementation detail. No timestamp field is added.

`output_path` is excluded from the response, as `get_job` already excludes it — it is a server filesystem path and no client has any use for it.

## 3. Per-browser display state — new, disposable

Two `localStorage` keys. Neither is ever used to *find* a reel; discovery is always the server's answer. Both are safe to lose — the worst case is one repeated completion notice.

| Key | Holds | Purpose | If missing |
|---|---|---|---|
| `facereel.watching` | job id, or absent | The reel this browser is currently displaying as in progress. Compared against the server's answer to detect that a reel has **vanished** — the only way an interrupted reel is detectable at all (FR-012). Cleared when the reel reaches a terminal state or is reported interrupted. | No interruption can be reported for a reel this browser never saw start. Correct: it has nothing to report. |
| `facereel.acknowledged` | job id, or absent | The last terminal reel the user dismissed. A terminal reel whose id matches is not shown (FR-010). | A completion notice the user already dismissed appears once more. |

Deliberately **not** stored: progress, stage, or message. Caching those would let a stale figure be rendered before the first poll returns, which is exactly what FR-007 forbids.

## 4. Indicator state — derived, not stored

The bar is in exactly one of five states, computed on each poll from the response plus the two keys above.

| State | Condition | Shown |
|---|---|---|
| **absent** | response is `null`; or the reel is terminal and acknowledged | nothing; body padding released (FR-011) |
| **processing** | `status == "processing"` | stage name, percentage, message |
| **stale** | 2+ consecutive failed requests while processing | last known figure, explicitly marked not live (FR-015) |
| **completed** | `status == "done"`, unacknowledged | completion, link to `/archive#<id>`, dismiss |
| **failed** | `status == "error"`, unacknowledged | the reason from `message`, dismiss |
| **interrupted** | `facereel.watching` set, that reel was processing, response no longer contains it | "did not finish", dismiss (FR-012) |

`stale` is a presentation overlay on `processing`, not a server state — the server has no idea the client cannot reach it.

## Entity mapping to the spec

| Spec entity | Realised as |
|---|---|
| Active reel job | §1, the existing `jobs` record, surfaced by §2 |
| Progress indicator | §4, derived per poll in `progress.js` |
| Acknowledgement | §3, `facereel.acknowledged` |

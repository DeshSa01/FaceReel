<!--
SYNC IMPACT REPORT
==================
Version change: none → 1.0.0 (initial ratification)

Rationale: First ratified constitution. The file previously contained only the
unmodified spec-kit scaffold with [PRINCIPLE_N_NAME] placeholders, so no prior
version existed to amend. MAJOR is not applicable to a first adoption; 1.0.0 is
the initial baseline.

Principles defined (all new):
  I.   Explain Why, Not What
  II.  Measure Before Tuning
  III. Verify In The Environment That Ships
  IV.  Earn Every Dependency
  V.   Destructive Operations Are Explicit And Bounded

Sections added:
  - Runtime & Deployment Constraints (replaces [SECTION_2_NAME])
  - Development Workflow (replaces [SECTION_3_NAME])
  - Governance

Removed sections: none.

Derivation: principles were extracted from conventions already observable in the
repository rather than imported wholesale. Each cites its evidence so a future
reader can check whether the rule still reflects practice. Notably, no test-first
principle was adopted, because the repository has no test suite and inventing an
unmet gate would make the constitution a document to route around.

Follow-up TODOs: none. No placeholder tokens remain.
-->

# FaceReel Constitution

FaceReel finds every appearance of a person in a YouTube video and stitches those
clips into one reel. It is a single-user application, run by its author on a home
server. This constitution records the conventions the codebase already follows, so
that they survive being handed to a new contributor or a fresh agent session.

## Core Principles

### I. Explain Why, Not What

Every non-obvious constant, guard and ordering decision MUST carry a comment
explaining the reasoning that produced it, not a restatement of the code.

Code that reads plainly needs no comment. Code that encodes a hard-won fact needs
one, because the fact is invisible and will otherwise be undone by the next person
who finds the line surprising.

*Evidence*: `pipeline.py` documents why the concat demuxer needs absolute paths,
why `clean_jobs_dir()` is deliberately not at module scope, and why the `_ydl`
retry exists. Each of those comments prevents a specific regression.

*Test*: a reviewer can answer "what breaks if I change this?" from the comment
alone, without archaeology.

### II. Measure Before Tuning

A threshold, cap, or default that affects output quality MUST be justified by a
measurement recorded alongside it. Guessed numbers are not acceptable where a
measurement is possible.

*Evidence*: `ZOOM_TRIGGER_FACE_HEIGHT` cites 1334 real detections with median and
decile values. The tuning defaults cite 100% footage recall at 0.15/0.6/0.6 against
79.8% at 0/0/0, and that recall flattens at 0.6.

*Test*: for any tunable value, the comment or README states what was measured and
what the alternative cost.

### III. Verify In The Environment That Ships

A change MUST be verified in the environment it will run in, not only where it was
written. When the two environments differ, the difference itself MUST be recorded.

This is the most expensively learned principle here. The macOS development machine
and the Linux container have repeatedly diverged in ways that pass locally and fail
in production: a JavaScript runtime present via Homebrew but absent from the image;
an OpenCV build that decodes AV1 in software on macOS but only in hardware on Linux.
Both produced clean local runs and hard failures on the server.

Rules:

- Behaviour that depends on a system binary, a bundled library, or a codec MUST be
  probed at runtime rather than assumed from a local result.
- The container is the source of truth for whether a feature works.
- A verification that cannot be run locally MUST be written down as a step to run
  against the deployment.

*Test*: the change's verification steps name the environment each step runs in.

### IV. Earn Every Dependency

A new runtime dependency MUST be justified against the cost of not having it, and
the justification recorded. Dependency versions MUST be pinned as a complete
closure, so that a rebuild produces the environment that was tested.

*Evidence*: OpenCV's bundled YuNet and SFace were chosen over InsightFace and dlib
specifically to avoid native build pain, and that reasoning is recorded in
`HANDOFF.md`. `requirements.txt` pins transitive packages, not just direct ones,
after an unpinned resolve produced a starlette major-version jump under a pinned
FastAPI.

*Test*: every entry in the requirements files is pinned, and any addition is
explained in the commit that introduces it.

### V. Destructive Operations Are Explicit And Bounded

Any operation that deletes user data MUST be scoped to a location it cannot escape,
MUST validate any externally supplied identifier before building a path from it, and
MUST NOT run as a side effect of an unrelated action.

Data loss is the one failure this application cannot apologise its way out of: a
generated reel represents minutes of irreplaceable compute and a user's intent.

Rules:

- An identifier that reaches a filesystem path MUST be validated against an explicit
  pattern before use, never sanitised after.
- Deletion MUST be confined to a known subtree.
- Automatic deletion MUST be documented in the README where a user will see it.

*Evidence*: `clean_jobs_dir()` only ever walks `storage/jobs/`, and its docstring
states why anything found there is safe to remove.

*Test*: for each destructive call site, name the input that could redirect it and the
check that prevents that.

## Runtime & Deployment Constraints

These are properties of the deployment, not preferences. Violating them breaks the
running application.

- **Single instance, single worker.** Job state is a module-level dict in `app.py`
  and the one-video-at-a-time rule is enforced in-process. The app MUST NOT be run
  with multiple uvicorn workers, replicas, or scaled instances. Any feature
  introducing shared state MUST state how it behaves under this constraint.
- **Durable data lives under `storage/`.** Only that directory is bind-mounted;
  anything written elsewhere dies with the container. `storage/jobs/` is cleared at
  every start-up and MUST NOT be used for anything meant to persist.
- **The image is built by CI, not by hand.** Pushes to `main` build and publish
  `ghcr.io/deshsa01/facereel`. Every `sha-` tag is a rollback target.
- **The host is modest.** An Intel N95 with four efficiency cores. Work added to the
  request path or the job pipeline MUST account for encoding already being the
  bottleneck.
- **yt-dlp rots.** It is pinned in its own file and installed as the image's last
  layer specifically so it can be bumped cheaply. A YouTube download failure is
  presumed to be staleness until shown otherwise.

## Development Workflow

- **Plan before non-trivial changes.** Features are specified before they are built.
  Spec-driven artifacts live under `specs/<NNN>-<name>/`.
- **Documentation MUST NOT outlive its truth.** A change that invalidates a statement
  in `README.md` or `HANDOFF.md` MUST correct that statement in the same change. A
  confidently wrong document is worse than a missing one.
- **Commits explain the reasoning.** The commit message carries the why; where a
  decision was reached by elimination, the alternatives tried and rejected belong in
  the message.
- **Report outcomes honestly.** A partially working change is described as such. A
  step that was skipped is named.
- **Tests are not currently mandated.** The repository has no test suite, and this
  constitution does not invent one as an unmet gate. Where logic is cheaply testable
  in isolation, it SHOULD be structured to keep that option open. Adding a test
  framework is a decision to be taken explicitly, not smuggled in with a feature.

## Governance

This constitution records how this project is actually built. It supersedes habit and
convenience, and it yields to evidence.

**Amendment procedure**: Amendments are made by updating this file with a Sync Impact
Report at its head recording the version change and what moved. A principle contradicted
by practice MUST be either enforced or amended — never left standing as decoration.

**Versioning policy**: Semantic versioning.

- **MAJOR** — a principle is removed or redefined in a way that invalidates prior work.
- **MINOR** — a principle or section is added, or guidance is materially expanded.
- **PATCH** — clarification and wording that does not change meaning.

**Compliance review**: Implementation plans carry a Constitution Check. Where a plan
conflicts with a principle, the conflict is justified in that plan's Complexity Tracking
table or the plan changes. An unfilled or inapplicable check MUST be recorded as such
rather than marked passed.

**Scope**: This is a personal, single-user project on a trusted network. Principles are
written for correctness and maintainability, not for multi-tenant security or team
process. Should the deployment ever become multi-user or internet-facing, this document
requires a MAJOR revision before that happens.

**Version**: 1.0.0 | **Ratified**: 2026-09-05 | **Last Amended**: 2026-09-05

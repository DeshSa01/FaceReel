# yt-dlp's YouTube extractor needs a JavaScript runtime to solve the player
# challenges; without one every download fails with a hard 403. deno is the
# only runtime yt-dlp enables by default, so shipping it means pipeline.py
# needs no --js-runtimes flag. Pinned to the version the Mac runs.
FROM denoland/deno:bin-2.9.5 AS deno

# Otherwise single stage: every Python dependency ships as a prebuilt wheel,
# so there is nothing to compile and a builder stage would save nothing.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ffmpeg + ffprobe, both shelled out to by pipeline.py. Debian's build carries
# libx264 and the native AAC encoder, which is all cut_and_stitch() asks for.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

COPY --from=deno /deno /usr/local/bin/deno
# fail the build here rather than at the first download attempt
RUN deno --version

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

# Its own later layer: bumped often, independently of everything above.
COPY requirements-ytdlp.txt .
RUN pip install -r requirements-ytdlp.txt

# 37 MB of ONNX that almost never changes -- cached above the app code so a
# code edit doesn't re-copy it.
COPY models/ models/
COPY static/ static/
COPY app.py pipeline.py archive.py ./

# uid 1000 matches the usual first non-root user on the host, so the
# bind-mounted storage/ stays writable without a fight.
RUN useradd --uid 1000 --create-home app \
 && mkdir -p storage/jobs storage/archive \
 && chown -R app:app storage
USER app
# Docker does not reliably derive HOME from the USER instruction, and deno
# caches under $HOME/.cache -- left as /root it would be unwritable
ENV HOME=/home/app

EXPOSE 8765

# stdlib urllib rather than curl, which isn't installed
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/', timeout=4)"

# 0.0.0.0, not the dev 127.0.0.1, or the published port is unreachable.
# No --workers: app.py holds job state in a module-level dict and enforces
# one-video-at-a-time in-process, so a second worker would break both.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8765"]

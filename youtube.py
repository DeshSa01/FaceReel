"""YouTube link previews: video-id extraction and a title lookup via oEmbed.

The add-video form shows a pasted link's thumbnail and title before it is
submitted (004 FR-025). The thumbnail needs nothing from the server; the title
comes from YouTube's oEmbed endpoint, fetched here because whether that
endpoint sends CORS headers is not something to build a feature on
(004 research D7).

The server never fetches the URL the user typed. It extracts an 11-character
id, validates it against an explicit pattern, and builds the oEmbed URL from
that id alone, so this cannot be used to make the server request arbitrary
addresses (constitution Principle V: validate, never sanitise).

Stdlib only (constitution Principle IV). yt-dlp would also give a title, but
takes seconds and competes with the running job on a four-core box.
"""

import json
import threading
import time
import urllib.parse
import urllib.request
from collections import OrderedDict

_ID_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-")
_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}
_PATH_PREFIXES = ("/shorts/", "/live/", "/embed/", "/v/")

# All chosen, not measured (constitution Principle II): no measurement applies.
# 4 s: long enough for a slow oEmbed reply, short enough that a hung request
#   doesn't hold a threadpool worker while the user waits on a preview.
# 256 entries: far more distinct videos than one person previews in a run.
# 60 s for failures: a brief YouTube outage shouldn't stick in the cache.
TIMEOUT_SECONDS = 4
CACHE_SIZE = 256
FAILURE_TTL_SECONDS = 60

# Per process, which is correct under the single-instance constraint.
_cache = OrderedDict()
_lock = threading.Lock()


def _valid_id(candidate):
    return candidate is not None and len(candidate) == 11 and set(candidate) <= _ID_CHARS


def video_id(url):
    """The 11-character id of a YouTube video link, or None. Recognises
    watch?v=, youtu.be/, /shorts/, /live/, /embed/ and /v/ on youtube.com and
    its www., m. and music. hosts. Mirrors youtubeId() in static/js/shell.js."""
    try:
        u = urllib.parse.urlsplit((url or "").strip())
    except ValueError:
        return None
    if u.scheme not in ("http", "https"):
        return None
    host = (u.hostname or "").lower()
    candidate = None
    if host == "youtu.be":
        candidate = u.path.lstrip("/").split("/")[0]
    elif host in _HOSTS:
        if u.path == "/watch":
            candidate = (urllib.parse.parse_qs(u.query).get("v") or [None])[0]
        else:
            for prefix in _PATH_PREFIXES:
                if u.path.startswith(prefix):
                    candidate = u.path[len(prefix):].split("/")[0]
                    break
    return candidate if _valid_id(candidate) else None


def _fetch(vid):
    watch = f"https://www.youtube.com/watch?v={vid}"
    oembed = "https://www.youtube.com/oembed?" + urllib.parse.urlencode({"format": "json", "url": watch})
    req = urllib.request.Request(oembed, headers={"User-Agent": "Supercut/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        if resp.status != 200:
            return None
        data = json.loads(resp.read(256 * 1024))
    return data.get("title"), data.get("author_name")


def preview(vid):
    """{id, title, author, thumbnail} for a validated id. title and author are
    None when YouTube can't be reached, times out, or the video is private;
    the caller still gets the thumbnail URL."""
    if not _valid_id(vid):
        raise ValueError(f"Invalid video id: {vid!r}")
    now = time.monotonic()
    with _lock:
        hit = _cache.get(vid)
        if hit and (hit["expires"] is None or hit["expires"] > now):
            _cache.move_to_end(vid)
            return dict(hit["value"])
    try:
        got = _fetch(vid)
    except Exception:  # network, HTTP error, bad JSON: all mean "no title"
        got = None
    title, author = got if got else (None, None)
    value = {"id": vid, "title": title, "author": author,
             "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"}
    with _lock:
        _cache[vid] = {"value": value, "expires": None if got else now + FAILURE_TTL_SECONDS}
        _cache.move_to_end(vid)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return dict(value)

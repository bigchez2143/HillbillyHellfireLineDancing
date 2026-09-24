"""Song card: a Spotify share link, plus an optional local audio file.

The link is for opening and sharing. Rehearsal, BPM, and teaching use the
local file when one is attached, and the metronome when it is not. This
module does not call Spotify and does not store a client id.
"""
from copy import deepcopy
import re
from urllib.parse import unquote, urlsplit

_TYPES = {"track", "album", "playlist", "episode", "artist", "show"}
_ID = re.compile(r"^[0-9A-Za-z]{22}$")
_SHORT = re.compile(r"^[0-9A-Za-z_-]{2,80}$")
_SECRET_QUERY = re.compile(
    r"^(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|passwd|key|client[_-]?id|client[_-]?secret|code)$",
    re.IGNORECASE,
)
_SHARE_HOSTS = {"open.spotify.com", "www.open.spotify.com", "play.spotify.com", "www.play.spotify.com"}
_SHORT_HOSTS = {"spotify.link", "www.spotify.link"}

PASTE = "Paste a Spotify song, album, or playlist link."
CONNECT = "Paste the share link from Spotify. This app does not connect to Spotify."
KEY = "That link includes a key. Paste the normal share link."


def normalize_spotify_url(value):
    """Return a canonical https share link, or '' when the field is empty."""
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(PASTE)
    raw = value.strip()
    if not raw:
        return ""
    if len(raw) > 2048 or any(ord(char) < 32 for char in raw):
        raise ValueError(PASTE)
    if raw.lower().startswith("spotify:"):
        parts = raw.split(":")
        if len(parts) == 3 and parts[1].lower() in _TYPES and _ID.fullmatch(parts[2]):
            return f"https://open.spotify.com/{parts[1].lower()}/{parts[2]}"
        raise ValueError(PASTE)
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as error:
        raise ValueError(PASTE) from error
    if port not in (None, 443):
        raise ValueError(PASTE)
    if parsed.scheme.lower() != "https" or parsed.username or parsed.password:
        raise ValueError(PASTE)
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError(PASTE)
    if host not in _SHARE_HOSTS | _SHORT_HOSTS and (host.endswith(".spotify.com") or host == "spotify.com"):
        raise ValueError(CONNECT)
    for key, _item in _query_pairs(parsed.query):
        if _SECRET_QUERY.fullmatch(key):
            raise ValueError(KEY)
    if host in _SHORT_HOSTS:
        segment = parsed.path.strip("/")
        if "/" in segment or not _SHORT.fullmatch(segment):
            raise ValueError(PASTE)
        return f"https://spotify.link/{segment}"
    if host not in _SHARE_HOSTS:
        raise ValueError(PASTE)
    segments = [part for part in parsed.path.split("/") if part]
    while segments and (segments[0].lower() == "embed" or segments[0].lower().startswith("intl-")):
        segments.pop(0)
    if len(segments) != 2 or segments[0].lower() not in _TYPES or not _ID.fullmatch(segments[1]):
        raise ValueError(PASTE)
    return f"https://open.spotify.com/{segments[0].lower()}/{segments[1]}"


def _query_pairs(query):
    if not query:
        return
    for piece in query.split("&"):
        key, _sep, value = piece.partition("=")
        key = unquote(key)
        if key:
            yield key, value


def apply_spotify_url(meta):
    """Copy sheet details and keep only a validated Spotify link."""
    if not isinstance(meta, dict):
        raise ValueError("Sheet details must be an object.")
    result = deepcopy(meta)
    if "spotify_url" in result:
        result["spotify_url"] = normalize_spotify_url(result.get("spotify_url"))
    return result


def local_media_path(song):
    """A local recording path. Web and Spotify addresses are not media files."""
    if not isinstance(song, dict):
        return ""
    path = song.get("path")
    if not isinstance(path, str):
        return ""
    path = path.strip().strip('"')
    if not path:
        return ""
    lowered = path.lower()
    if lowered.startswith(("http://", "https://", "spotify:", "file:")):
        return ""
    return path


def rehearsal_source(song, spotify_url=""):
    """Rehearsal plays the local file, or the metronome. Never the Spotify link."""
    path = local_media_path(song)
    link = ""
    try:
        link = normalize_spotify_url(spotify_url)
    except ValueError:
        link = ""
    if path:
        return {
            "kind": "local",
            "path": path,
            "open_url": link,
            "plays_spotify": False,
            "note": "Rehearsal plays your local audio file. The Spotify link is only for sharing and opening the song.",
        }
    return {
        "kind": "metronome",
        "path": "",
        "open_url": link,
        "plays_spotify": False,
        "note": "Rehearsal uses the metronome. The Spotify link is only for sharing and opening the song.",
    }

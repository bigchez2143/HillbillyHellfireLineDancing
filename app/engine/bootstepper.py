"""Read-only BootStepper Public API search for a personal key.

The key is supplied by the caller and sent only as a request header. This module
does not write to BootStepper, page through a catalog, or store results.
"""
from __future__ import annotations

import json
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


API_ORIGIN = "https://api.bootstepper.com"
SITE_ORIGIN = "https://bootstepper.com"
PAGE_LIMIT = 10
MAX_QUERY = 80
MAX_RESPONSE_BYTES = 524288
TIMEOUT_SECONDS = 20
ID_RE = re.compile(r"^[A-Za-z0-9]{6,64}$")
SEARCH_PATHS = {
    "dances": "/dances/search",
    "songs": "/songs/search",
    "choreographers": "/choreographers/search",
}
PAGE_PATHS = {
    "dances": "/dances/",
    "songs": "/songs/",
    "choreographers": "/choreographers/",
}
DIFFICULTY = {
    "absolute_beginner": "Absolute beginner",
    "beginner": "Beginner",
    "improver": "Improver",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
    "unknown": "Unspecified",
}
ATTRIBUTION = (
    "These results are from BootStepper for this search only. "
    "They are not saved into your dance, and this app does not keep a copy of their catalog."
)


class BootStepperError(RuntimeError):
    def __init__(self, message, code="BOOTSTEPPER_ERROR"):
        self.code = code
        super().__init__(message)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def urlopen(request, timeout):
    """Keep the personal key on the documented BootStepper host only."""
    return build_opener(_NoRedirect()).open(request, timeout=timeout)


def _text(value, limit=160):
    if not isinstance(value, str):
        return ""
    cleaned = "".join(char for char in value if ord(char) >= 32 and ord(char) != 127)
    return cleaned.strip()[:limit]


def _whole(value, upper):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    number = int(value)
    if 0 <= number <= upper:
        return number
    return None


def _page(kind, identifier):
    if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier):
        return ""
    return SITE_ORIGIN + PAGE_PATHS[kind] + identifier


def _people(row):
    names = []
    rows = row.get("danceChoreographers")
    if not isinstance(rows, list):
        return names
    for item in rows[:8]:
        person = item.get("choreographer") if isinstance(item, dict) else None
        name = _text(person.get("name") if isinstance(person, dict) else "")
        if name and name not in names:
            names.append(name)
    return names


def _song_labels(row):
    labels = []
    rows = row.get("danceSongs")
    if not isinstance(rows, list):
        return labels
    for item in rows[:8]:
        song = item.get("song") if isinstance(item, dict) else None
        if not isinstance(song, dict):
            continue
        title = _text(song.get("title"))
        artist = _text(song.get("artist"))
        if title and artist:
            label = f"{title} — {artist}"
        else:
            label = title or artist
        if label and label not in labels:
            labels.append(label)
    return labels


def _dance(row):
    title = _text(row.get("title"), 200)
    if not title:
        return None
    item = {
        "title": title,
        "difficulty": DIFFICULTY.get(row.get("difficultyLevel"), ""),
        "counts": _whole(row.get("counts"), 256),
        "walls": _whole(row.get("walls"), 16),
        "choreographers": _people(row),
        "songs": _song_labels(row),
        "url": _page("dances", row.get("id")),
    }
    return {key: value for key, value in item.items() if value not in ("", None, [])}


def _song(row):
    title = _text(row.get("title"), 200)
    if not title:
        return None
    item = {
        "title": title,
        "artist": _text(row.get("artist"), 200),
        "dance_count": _whole(row.get("danceCount"), 100000),
        "url": _page("songs", row.get("id")),
    }
    return {key: value for key, value in item.items() if value not in ("", None)}


def _choreographer(row):
    name = _text(row.get("name"), 200)
    if not name:
        return None
    item = {
        "name": name,
        "country": _text(row.get("country"), 80),
        "dance_count": _whole(row.get("danceCount"), 100000),
        "url": _page("choreographers", row.get("id")),
    }
    return {key: value for key, value in item.items() if value not in ("", None)}


_PRESENTERS = {"dances": _dance, "songs": _song, "choreographers": _choreographer}


def _search_url(kind, query):
    return API_ORIGIN + SEARCH_PATHS[kind] + "?" + urlencode({"query": query, "limit": PAGE_LIMIT})


def _read_json(request):
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status = exc.code
        exc.close()
        if 300 <= status < 400:
            raise BootStepperError(
                "BootStepper redirected the search. The personal key was not forwarded.",
                "REDIRECT_BLOCKED",
            ) from None
        guidance = {
            400: ("REQUEST_REJECTED", "BootStepper could not run that search. Try a shorter name."),
            401: ("AUTH_FAILED", "BootStepper did not accept this personal key. Check the key in your BootStepper account."),
            403: ("ACCESS_DENIED", "This BootStepper key cannot run that search. Check the key in your account."),
            404: ("NOT_FOUND", "BootStepper could not find that search. Try again later."),
            429: ("RATE_LIMITED", "BootStepper asked for a pause. Wait a moment, then search again."),
        }
        code, message = guidance.get(status, ("SERVICE_ERROR", f"BootStepper returned HTTP {status}. Try again later."))
        raise BootStepperError(message, code) from None
    except (URLError, TimeoutError, OSError) as exc:
        if isinstance(exc, (TimeoutError, socket.timeout)) or isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
            raise BootStepperError("BootStepper took too long to answer. Try again.", "TIMEOUT") from None
        raise BootStepperError("Could not reach BootStepper. Check your connection and try again.", "NETWORK_ERROR") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise BootStepperError("BootStepper returned more than this search can show. Try a narrower name.", "RESPONSE_TOO_LARGE")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise BootStepperError("BootStepper returned an unexpected response.", "INVALID_RESPONSE") from None
    if not isinstance(value, dict) or not isinstance(value.get("items"), list):
        raise BootStepperError("BootStepper returned an unexpected response.", "INVALID_RESPONSE")
    return value


def search(kind, query, api_key):
    """Search dances, songs, or choreographers. Read only; nothing is stored."""
    if kind not in SEARCH_PATHS:
        raise BootStepperError("Choose dances, songs, or choreographers.", "INVALID_SEARCH")
    if not isinstance(query, str):
        raise BootStepperError("Enter a name to search for.", "INVALID_SEARCH")
    query = query.strip()
    if not query or len(query) > MAX_QUERY or any(ord(char) < 32 or ord(char) == 127 for char in query):
        raise BootStepperError("Enter a name to search for, up to 80 characters.", "INVALID_SEARCH")
    if not isinstance(api_key, str) or not api_key or any(char.isspace() or ord(char) < 32 for char in api_key):
        raise BootStepperError("Add your personal BootStepper key in Advanced before searching.", "KEY_REQUIRED")
    request = Request(
        _search_url(kind, query),
        headers={
            "Accept": "application/json",
            "User-Agent": "HillbillyHellfireLineDanceCreator",
            "X-BootStepper-API-Key": api_key,
        },
        method="GET",
    )
    payload = _read_json(request)
    present = _PRESENTERS[kind]
    items = []
    for row in payload["items"][:PAGE_LIMIT]:
        if not isinstance(row, dict):
            continue
        item = present(row)
        if item:
            items.append(item)
    return {
        "kind": kind,
        "query": query,
        "read_only": True,
        "stored": False,
        "attribution": ATTRIBUTION,
        "source": SITE_ORIGIN + "/",
        "terms": SITE_ORIGIN + "/terms",
        "items": items,
    }

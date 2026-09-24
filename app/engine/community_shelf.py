"""Basic community links stored in local settings.

These are websites the instructor opens. They are not accounts, uploads, or
keys. Starter links ship with the app; edits stay in settings.json, which is
not part of the source tree.
"""
import re
from urllib.parse import unquote, urlsplit

from .creator_exports import ExportError, safe_url
from . import settings

LINK_ID = re.compile(r"^[a-z0-9-]{1,40}$")


BOOTSTEPPER_URL = "https://bootstepper.com/"
BOOTSTEPPER_CREATE_URL = "https://bootstepper.com/dances/create"
COPPERKNOB_URL = "https://www.copperknob.co.uk/"
COPPERKNOB_SUBMIT_URL = "https://www.copperknob.co.uk/contactus"
LINEDANCE_URL = "https://www.linedance.com/"
# Member submit page. Signed-out visitors are asked to sign in on that page.
LINEDANCE_SUBMIT_URL = "https://www.linedance.com/submit"
HILLBILLY_HELLFIRE_URL = "https://hillbillyhellfire.com"
HILLBILLY_HELLFIRE_YOUTUBE_URL = "https://www.youtube.com/@HillbillyHellfire"

MAX_LINKS = 40
_SECRET_QUERY = {
    "api_key", "apikey", "api-key", "access_token", "refresh_token", "token",
    "secret", "password", "passwd", "key", "client_secret", "client-secret",
}


class CommunityError(ValueError):
    pass


STARTER_LINKS = (
    {"id": "bootstepper", "name": "BootStepper", "url": BOOTSTEPPER_URL, "note": "Dances, songs, and events"},
    {"id": "copperknob", "name": "CopperKnob", "url": COPPERKNOB_URL, "note": "Step sheets and choreographers"},
    {"id": "linedance", "name": "LineDance.com", "url": LINEDANCE_URL, "note": "Dance lists, sheets, and videos"},
    {"id": "bootstepper-create", "name": "Add a dance on BootStepper", "url": BOOTSTEPPER_CREATE_URL, "note": "Their page for adding a dance"},
    {"id": "hillbilly-hellfire", "name": "Hillbilly Hellfire", "url": HILLBILLY_HELLFIRE_URL, "note": "Hillbilly Hellfire website"},
    {"id": "hillbilly-hellfire-youtube", "name": "Hillbilly Hellfire on YouTube", "url": HILLBILLY_HELLFIRE_YOUTUBE_URL, "note": "Hillbilly Hellfire videos"},
)


def starter_links():
    return [dict(item) for item in STARTER_LINKS]


def _plain(value, limit, label, required):
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise CommunityError("Enter the " + label + " as plain text.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise CommunityError("The " + label + " cannot include line breaks or odd characters.")
    value = value.strip()
    if required and not value:
        raise CommunityError("Enter a " + label + ".")
    if len(value) > limit:
        raise CommunityError("The " + label + " is too long.")
    return value


def _website(value):
    try:
        url = safe_url(value)
    except ExportError as exc:
        raise CommunityError("Use a shorter website address.") from exc
    if not url:
        raise CommunityError("Use a complete website address, starting with https://.")
    query = urlsplit(url).query
    for pair in query.split("&"):
        if not pair:
            continue
        name = unquote(pair.split("=", 1)[0]).replace("-", "_").lower()
        if name in _SECRET_QUERY or name.replace("_", "") in {"apikey", "accesstoken", "clientsecret"}:
            raise CommunityError("That link includes a key. Use the normal website address.")
    return url


def normalize_link(row, fallback_id):
    if not isinstance(row, dict):
        raise CommunityError("Each link needs a name and a website.")
    name = _plain(row.get("name"), 80, "name", True)
    url = _website(row.get("url"))
    note = _plain(row.get("note", ""), 160, "note", False)
    link_id = row.get("id")
    if not isinstance(link_id, str) or not LINK_ID.fullmatch(link_id):
        link_id = fallback_id
    if not LINK_ID.fullmatch(link_id):
        raise CommunityError("A link could not be saved. Try it again.")
    return {"id": link_id, "name": name, "url": url, "note": note}


def normalize_links(rows):
    if not isinstance(rows, list):
        raise CommunityError("The link list could not be read.")
    if len(rows) > MAX_LINKS:
        raise CommunityError("Keep 40 links or fewer.")
    clean, seen_urls, seen_ids = [], set(), set()
    for index, row in enumerate(rows):
        item = normalize_link(row, "link-" + str(index + 1))
        if item["url"] in seen_urls:
            raise CommunityError("That website is already in your list.")
        if item["id"] in seen_ids:
            suffix = "-" + str(index + 1)
            item = dict(item, id=(item["id"][:40 - len(suffix)] + suffix))
            if item["id"] in seen_ids or not LINK_ID.fullmatch(item["id"]):
                raise CommunityError("Two links got mixed up. Try saving again.")
        seen_urls.add(item["url"])
        seen_ids.add(item["id"])
        clean.append(item)
    return clean


def links_for_backup(raw):
    """Sanitized links for a private backup, or None when the shelf was never saved."""
    if not isinstance(raw, dict) or "community" not in raw:
        return None
    community = raw.get("community")
    rows = community.get("links") if isinstance(community, dict) else None
    if not isinstance(rows, list):
        return []
    clean, seen = [], set()
    for index, row in enumerate(rows):
        if len(clean) >= MAX_LINKS:
            break
        try:
            item = normalize_link(row, "link-" + str(index + 1))
        except CommunityError:
            continue
        if item["url"] in seen or item["id"] in {kept["id"] for kept in clean}:
            continue
        seen.add(item["url"])
        clean.append(item)
    return clean


def _stored_links(raw):
    community = raw.get("community") if isinstance(raw, dict) else None
    if not isinstance(community, dict) or "links" not in community:
        return None
    return community.get("links")


def load_shelf():
    stored = _stored_links(settings.read_lenient())
    if stored is None:
        return {"saved": False, "links": starter_links()}
    try:
        links = normalize_links(stored)
    except CommunityError:
        return {"saved": False, "links": starter_links(),
                "warning": "Saved links could not be read. Starter links are shown until you save the list again."}
    return {"saved": True, "links": links}


def save_shelf(rows):
    links = normalize_links(rows)

    def mutate(raw):
        raw["community"] = {"links": links}

    settings.update_settings(mutate)
    return {"saved": True, "links": links}


def reset_shelf():
    def mutate(raw):
        raw.pop("community", None)

    settings.update_settings(mutate)
    return {"saved": False, "links": starter_links()}

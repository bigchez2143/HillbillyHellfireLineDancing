"""Starter dance copied into an empty projects folder.

The Corn Maze Dance in this file is an original beginner sequence written
for this app from its own move catalog. It is not a transcription of a
published step sheet, and it does not include a recording. A projects
folder that already contains a dance is left unchanged.
"""
import os
import time

from .choreography import compile_choreography
from .steps import MOVE_BY_ID
from . import project as store


SAMPLE_ID = "the-corn-maze-dance"
SAMPLE_NAME = "The Corn Maze Dance"
FREEWARE_LINE = "Freeware from Hillbilly Hellfire"
SITE_URL = "https://hillbillyhellfire.com"
SAMPLE_NOTE = (
    "Starter sample included with this app. These 32 counts were written here "
    "from the app's own moves. They are not a copy of a published step sheet, "
    "and no song file is included. Add a recording you have permission to use, "
    "then practice with the count. 112 BPM is a practice tempo, not a measured song."
)

# Right-lead start. Each pair is (catalog move id, lead). Counts: 32.
# One quarter turn, so the sequence is four walls when it is repeated.
_SEQUENCE = (
    ("vine_touch", "R"),
    ("vine_touch", "L"),
    ("rocking_chair", "R"),
    ("jazz_box", "R"),
    ("walk_fwd", "R"),
    ("walk_fwd", "R"),
    ("pivot_quarter", "R"),
    ("walk_fwd", "R"),
    ("charleston", "R"),
    ("step_touch", "R"),
    ("step_touch", "L"),
)


def sample_moves():
    moves = []
    for index, (move_id, lead) in enumerate(_SEQUENCE, start=1):
        definition = MOVE_BY_ID[move_id]
        item = definition.variant(lead)
        item["id"] = f"corn-{index}"
        moves.append(item)
    return moves


def sample_choreography():
    return {
        "schema_version": 1,
        "start": {"free_foot": "R", "support": "L", "facing_deg": "0"},
        "meter": {"beats": 4, "unit": 4, "group_counts": 8},
        "repeat": True,
        "parts": [{
            "id": "A",
            "name": "Part A",
            "kind": "part",
            "moves": sample_moves(),
        }],
        "routine": [{"id": "run-a", "part_id": "A", "repeat": 1}],
    }


def sample_document():
    song = {"title": SAMPLE_NAME, "artist": "", "path": None, "filename": None}
    sheet = {
        "dance_title": SAMPLE_NAME,
        "choreographer": "Hillbilly Hellfire",
        "level_label": "Beginner",
        "description": SAMPLE_NOTE,
        "youtube_url": "",
        "sheet_url": "",
        "spotify_url": "",
    }
    music_map = {"bpm": 112, "first_count": 0, "meter": 4, "key": ""}
    return {
        "id": SAMPLE_ID,
        "name": SAMPLE_NAME,
        "sample": True,
        "created": time.time(),
        "song": song,
        "analysis": None,
        "lyrics_raw": "",
        "lyric_sections": [],
        "alignment": None,
        "sections": [],
        "phrase": None,
        "lyric_move_draft": None,
        "dance": {},
        "tutorial": None,
        "sheet_meta": sheet,
        "draft": {
            "choreography": sample_choreography(),
            "music_map": music_map,
            "sheet_meta": sheet,
            "song": dict(song),
            "lyrics_raw": "",
        },
    }


def _has_projects():
    store.ensure_dirs()
    try:
        names = os.listdir(store.PROJECTS_DIR)
    except OSError:
        return False
    for name in names:
        if not store.PROJECT_ID_RE.fullmatch(name):
            continue
        if os.path.isdir(os.path.join(store.PROJECTS_DIR, name)):
            return True
    return False


def ensure_sample_project():
    """Install the starter only when the projects folder has no dances yet."""
    if _has_projects():
        return None
    try:
        return store.save_project(SAMPLE_ID, sample_document())
    except store.RevisionConflict:
        return None


def compiled_sample():
    return compile_choreography(sample_choreography())

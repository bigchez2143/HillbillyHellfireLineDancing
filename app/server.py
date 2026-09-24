"""Line Dance Creator — local GUI server.

Run:  python server.py        (opens http://127.0.0.1:8766 in the browser)
"""
import copy
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import traceback

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, StrictInt

from engine import (alignment as alignment_engine, audio as audio_engine,
                    database as step_database, repair as repair_engine)
from engine import (ai_assistant, lyric_moves as lyric_moves_engine, move_import,
                    phrasing, project as store, settings as app_settings,
                    tutorial as tutorial_engine)
from engine.assembler import assemble, validate_sequence, AssemblyError
from engine.emitter import (build_sheet, render_txt, render_html, render_pdf,
                            build_challenge_kit, build_publish_kit)
from engine.steps import (library_json, delete_custom_move, get_move,
                          list_custom_move_records, save_custom_move)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="Line Dance Creator")
from workspace_api import router as workspace_router
from creator_api import router as creator_router
from export_api import router as creator_export_router
from library_api import router as creator_library_router
from instructor_api import router as instructor_router
from media_api import router as recording_media_router
app.include_router(workspace_router)
app.include_router(creator_router)
app.include_router(creator_export_router)
app.include_router(creator_library_router)
app.include_router(instructor_router)
app.include_router(recording_media_router)
from move_browser_api import router as move_browser_router
from phrase_api import router as phrase_router
from backup_api import router as backup_router
from ai_connection_api import router as ai_connection_router
app.include_router(move_browser_router)
app.include_router(phrase_router)
app.include_router(backup_router)
app.include_router(ai_connection_router)


@app.middleware('http')
async def local_request_boundary(request, call_next):
    origin=request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        return JSONResponse(status_code=403, content={'detail':'Open the local application to perform this action.'})
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='no-referrer'
    return response


@app.exception_handler(store.RevisionConflict)
async def revision_conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={'detail': {'code':'REVISION_CONFLICT',
                        'message':str(exc), 'current_revision':exc.current_revision}})

# In-memory job state.  Both jobs are deliberately separate: analyzing beats
# and aligning vocal words can run independently, but either becomes stale
# when the song or lyric sheet changes.
_jobs = {}
_alignment_jobs = {}
_repair_jobs = {}
_jobs_lock = threading.Lock()


def _file_signature(path):
    """Return the identity relevant to a long-running local audio job.

    Comparing the path alone is insufficient: an editor or downloader can
    replace a song in place while WhisperX is still working.  Size and the
    nanosecond modification time let us discard that now-stale transcript.
    """
    resolved = os.path.normcase(os.path.realpath(path))
    stat = os.stat(resolved)
    return {
        "path": resolved,
        "size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
    }


def _analysis_signature(analysis):
    """Fingerprint the exact beat/downbeat analysis used by lyric scanning."""
    if not analysis:
        return None
    encoded = json.dumps(
        analysis, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mark_lyric_move_draft_stale(project, reason):
    """Invalidate a saved review draft without touching the chosen dance."""
    draft = project.get("lyric_move_draft")
    if not isinstance(draft, dict):
        return False
    stale = copy.deepcopy(draft)
    previous_status = stale.get("status")
    stale["status"] = "STALE"
    stale["stale_reason"] = reason
    if previous_status and previous_status != "STALE":
        stale["previous_status"] = previous_status
    project["lyric_move_draft"] = stale
    return True


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class NewProject(BaseModel):
    name: str
    title: str | None = None
    artist: str | None = None


class SongPath(BaseModel):
    path: str


class LyricsBody(BaseModel):
    text: str
    expected_revision: StrictInt | None = Field(default=None, ge=0)


class SectionsBody(BaseModel):
    sections: list  # [{label, start, end}]
    pattern_len: int | None = 32
    expected_revision: StrictInt | None = Field(default=None, ge=0)


class GenerateBody(BaseModel):
    level: str = "AB"
    wall: str = "2"
    turn_dir: str = "L"
    counts: int = 32
    seed: int = 0
    k: int = 3
    allow_sync: bool = False
    experimental_mode: bool = False
    publication_mode: bool = True
    include_custom_moves: bool = False


class LyricMoveDraftBody(GenerateBody):
    passage_id: str | None = None
    fill_gaps: bool = True


class DanceBody(BaseModel):
    source: str            # "generated" | "custom"
    chosen: int | None = None
    moves: list | None = None   # for custom: [{move_id, lead}]
    counts: int = 32
    wall: str = "2"
    turn_dir: str = "L"


class MetaBody(BaseModel):
    expected_revision: StrictInt | None = Field(default=None, ge=0)
    dance_title: str | None = None
    choreographer: str | None = None
    country: str | None = None
    contact: str | None = None
    level_label: str | None = None
    description: str | None = None
    signature_note: str | None = None
    ending_note: str | None = None
    youtube_url: str | None = None
    sheet_url: str | None = None
    title: str | None = None
    artist: str | None = None


class ValidateBody(BaseModel):
    moves: list            # [{move_id, lead}]
    counts: int = 32
    wall: str = "2"
    turn_dir: str = "L"
    bpm: float | None = None


class RepairRenderBody(BaseModel):
    stem: str
    source_start: float
    source_end: float
    target_start: float
    target_end: float
    fade_ms: int = 120
    gain_db: float = -2.0


class AISettingsBody(BaseModel):
    """Optional connection details. The key is write-only and never returned."""
    enabled: bool = False
    provider: str = "openai_compatible"
    base_url: str = ""
    model: str = ""
    timeout_seconds: int = 60
    api_key: str | None = None


class AIChatBody(BaseModel):
    prompt: str
    project_id: str | None = None
    include_project: bool = True
    history: list[dict] = []


class CustomMoveBody(BaseModel):
    name: str
    counts: int
    start: str
    end: str
    rotation: int = 0
    level: str = "I"
    travel: str = ""
    instructions: str
    header: str | None = None
    family: str | None = None
    sync: bool = False
    ab_safe: bool = False
    in_generator: bool = False


class TutorialBuildBody(BaseModel):
    callout_lead_counts: int = Field(default=2, ge=0, le=8)
    voice_name: str = Field(default="Georgia Belle", min_length=1, max_length=80)
    tempo_grid_confirmed: bool = False
    count_in: str = Field(default=tutorial_engine.DEFAULT_COUNT_IN,
                          min_length=1, max_length=160)
    count_in_counts: int = Field(default=4, ge=1, le=8)
    anchor_seconds: float | None = Field(default=None, ge=0)
    voice_notes: str = Field(default="", max_length=4000)
    producer_notes: str = Field(default="", max_length=4000)


class TutorialSegmentEdit(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    callout: str | None = Field(default=None, max_length=120)
    camera: str | None = Field(default=None, max_length=40)
    confirmed: bool | None = None
    review_note: str | None = Field(default=None, max_length=240)


class TutorialUpdateBody(BaseModel):
    expected_revision: StrictInt | None = Field(default=None, ge=0)
    segments: list[TutorialSegmentEdit] = Field(default_factory=list)
    count_in: str | None = Field(default=None, max_length=160)
    voice_notes: str | None = Field(default=None, max_length=4000)
    producer_notes: str | None = Field(default=None, max_length=4000)
    tempo_grid_confirmed: bool | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load(pid):
    try:
        return store.load_project(pid)
    except (FileNotFoundError, ValueError):
        raise HTTPException(404, f"No project '{pid}'")


def _require_expected_revision(project, expected):
    if expected is not None and expected != project['document_revision']:
        raise store.RevisionConflict(expected, project['document_revision'])


STEM_DISPLAY = {
    "drums": {"name": "Drums", "detail": "Kick, snare, cymbals and percussion"},
    "bass": {"name": "Bass", "detail": "Low-end bass instruments"},
    "vocals": {"name": "Vocals", "detail": "Lead and backing vocals together"},
    "guitar": {"name": "Guitar", "detail": "Electric and acoustic guitar when detected"},
    "piano": {"name": "Piano / keys", "detail": "Piano and keyboard content when detected"},
    "other": {"name": "Other instruments", "detail": "Fiddle, banjo, bagpipes and remaining accompaniment"},
}
SAFE_STEM_RE = re.compile(r"^[a-z0-9_-]+$")


def _repair_root(pid):
    return os.path.realpath(os.path.join(store.project_dir(pid), "repair"))


def _inside_repair_root(pid, path):
    root = _repair_root(pid)
    return os.path.commonpath([root, os.path.realpath(path)]) == root


def _clear_repair(p):
    """Invalidate derived stems/repairs whenever the source recording changes."""
    p["repair"] = {}


def _repair_info(p):
    repair = p.get("repair") or {}
    separation = repair.get("separation") or {}
    stems = separation.get("stems") or {}
    return {
        "separation": {
            "status": separation.get("status", "idle"),
            "model": separation.get("model"),
            "stems": [
                {"id": key, **STEM_DISPLAY.get(key, {"name": key.title(), "detail": "Separated component"})}
                for key in stems if os.path.isfile(stems[key]) and _inside_repair_root(p["id"], stems[key])
            ],
        },
        "last_output": bool(repair.get("last_output") and
                            os.path.isfile(repair["last_output"]) and
                            _inside_repair_root(p["id"], repair["last_output"])),
        "last_render": repair.get("last_render"),
        "model_limits": "The model can separate drums, bass, vocals, guitar, piano/keys and other accompaniment. It cannot reliably isolate banjo, fiddle, bagpipes, or backing vocals from every finished stereo song; those remain in Other or Vocals.",
    }


def _expand_moves(items, start_foot="R"):
    """[{move_id, lead}] -> full variant dicts (validating ids).

    Free-foot fillers (start == 'F': hold, scuff, hitch, point...) are
    resolved to whichever foot is actually free at that point in the walk, so
    the emitted sheet text names the right foot ("Scuff L" after a vine R,
    not a hardcoded "Scuff R").
    """
    out = []
    foot = start_foot
    for it in items:
        m = get_move(it.get("move_id"))
        if not m:
            raise HTTPException(400, f"Unknown move id: {it.get('move_id')}")
        lead = it.get("lead", "R")
        if lead not in ("R", "L"):
            raise HTTPException(400, f"Bad lead: {lead}")
        if m.start == "F":
            lead = foot
        v = m.variant(lead)
        out.append(v)
        if v["end"] != "SAME":
            foot = v["end"]
        # end == "SAME" -> the free foot is unchanged; nothing to update
    return out


def _current_dance(p):
    """Resolve the project's active dance into emitter form."""
    from engine.project_media import recording_review_needed
    if recording_review_needed(p):
        raise HTTPException(409, 'The dance is preserved, but this recording and timing map need review in Music before using the older production tools.')
    d = p.get("dance") or {}
    if d.get('source') == 'structured':
        raise HTTPException(422, 'This dance uses the complete choreography format. Use Practice and Export in the main workspace; this older production tool requires a flat legacy dance.')
    if d.get("source") == "custom" and d.get("custom"):
        moves = store.resolve_move_variants(p, d['custom'], start_foot=d.get('start_foot', 'R'))
    elif d.get("candidates"):
        idx = d.get("chosen") or 0
        idx = max(0, min(idx, len(d["candidates"]) - 1))
        moves = d["candidates"][idx]["moves"]
    else:
        return None
    tempo = d.get("tempo") or {}
    # Custom dances may not have been generated in this session, so use the
    # current recording's measured BPM when no candidate snapshot exists.
    measured_bpm = tempo.get("bpm", (p.get("analysis") or {}).get("bpm"))
    if p.get('recording_review'):
        # The accepted dance retains its original tempo snapshot. Explicitly
        # reviewed replacement music supplies this recording's timing instead.
        measured_bpm = (p.get('draft', {}).get('music_map') or p.get('music_map') or {}).get('bpm')
    rep = validate_sequence(moves, d.get("counts", 32), d.get("wall", "2"),
                            d.get("turn_dir", "L"), bpm=measured_bpm, start_foot=d.get('start_foot', 'R'))
    return {"moves": moves, "total_counts": rep["counts"],
            "wall": d.get("wall", "2"), "walls": rep["walls"],
            "turn_dir": d.get("turn_dir", "L"),
            "net_rot": rep["net_rot"], "validation": rep,
            "tempo": rep.get("tempo")}


def _ai_project_context(p):
    """A compact, deliberately lyric-free project snapshot for Ask AI."""
    analysis = p.get("analysis") or {}
    context = {
        "song": {
            "title": p.get("song", {}).get("title"),
            "artist": p.get("song", {}).get("artist"),
            "bpm": analysis.get("bpm"),
            "key": analysis.get("key"),
            "duration_seconds": analysis.get("duration"),
        },
        "manual_music_map": [
            {"label": section.get("label"), "start": section.get("start"),
             "end": section.get("end")}
            for section in (p.get("sections") or [])[:60]
        ],
    }
    phrase = p.get("phrase") or {}
    if phrase.get("dance_fit"):
        context["dance_fit"] = phrase["dance_fit"]
    dance = _current_dance(p)
    if dance:
        context["current_dance"] = {
            "counts": dance["total_counts"], "walls": dance["walls"],
            "net_rotation": dance["net_rot"],
            "moves": [
                {"name": move.get("name"), "counts": move.get("counts"),
                 "turn_degrees": move.get("rot")}
                for move in dance["moves"]
            ],
        }
    return context


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"ok": True}


# ---------------------------------------------------------------------------
# Optional AI connection settings
# ---------------------------------------------------------------------------
@app.get("/api/settings/ai")
def get_ai_settings():
    """Connection preferences only — never return a key to the browser."""
    return app_settings.load_ai_settings()


@app.put("/api/settings/ai")
def save_ai_settings(body: AISettingsBody):
    try:
        return app_settings.save_ai_settings(body.model_dump())
    except app_settings.SettingsError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/settings/ai/key")
def forget_ai_key():
    return app_settings.clear_ai_key()


@app.post("/api/ai/chat")
def ask_optional_ai(body: AIChatBody):
    """User-triggered AI chat. It returns an idea only; it never saves edits."""
    project_context = None
    if body.include_project and body.project_id:
        project_context = _ai_project_context(_load(body.project_id))
    try:
        connection = app_settings.load_ai_connection()
        result = ai_assistant.ask(connection, body.prompt, body.history, project_context)
    except app_settings.SettingsError as exc:
        raise HTTPException(400, str(exc))
    except ai_assistant.AssistantError as exc:
        raise HTTPException(502, str(exc))
    result["project_context_included"] = bool(project_context)
    return result


@app.get("/api/database")
def database_status():
    """Inventory of the local, queryable step catalog."""
    return step_database.initialize_database()


# ---------------------------------------------------------------------------
# Move library: vetted built-ins, a reference glossary, and dancer-owned moves
# ---------------------------------------------------------------------------
@app.get("/api/moves/summary")
def move_library_summary():
    entries = library_json()
    built_in = {row["move_id"] for row in entries if not row["move_id"].startswith("custom-")}
    custom = list_custom_move_records()
    glossary = step_database.initialize_database()
    return {
        "buildable_moves": len({row["move_id"] for row in entries}),
        "built_in_moves": len(built_in), "custom_moves": len(custom),
        "reference_glossary": glossary.get("steps", 0),
        "note": ("The reference glossary is broader vocabulary. Only moves with verified "
                 "counts, feet, rotation, and instructions are offered to the builder."),
    }


@app.get("/api/moves/custom")
def custom_moves():
    return list_custom_move_records()


@app.get("/api/moves/template")
def custom_move_template():
    return move_import.template()


@app.post("/api/moves/custom")
def add_custom_move(body: CustomMoveBody):
    try:
        return save_custom_move(body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.delete("/api/moves/custom/{move_id}")
def remove_custom_move(move_id: str):
    try:
        delete_custom_move(move_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True}


@app.post("/api/moves/import")
async def import_custom_moves(file: UploadFile = File(...)):
    filename = os.path.basename(file.filename or "moves")
    payload = await file.read()
    try:
        return move_import.import_moves(filename, payload)
    except move_import.MoveImportError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/projects")
def projects():
    return store.list_projects()


@app.post("/api/projects")
def create_project(body: NewProject):
    return store.create_project(body.name, body.title, body.artist)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    p = _load(pid)
    return p


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    _load(pid)  # validates the id before the recursive project-folder delete
    store.delete_project(pid)
    return {"ok": True}


# ---------------------------------------------------------------------------
# Song / audio
# ---------------------------------------------------------------------------
@app.post("/api/projects/{pid}/song-path")
def set_song_path(pid: str, body: SongPath):
    from engine.project_media import switch_recording
    p = _load(pid)
    path = body.path.strip().strip('"')
    if not os.path.isfile(path):
        raise HTTPException(400, f"File not found: {path}")
    try:
        if switch_recording(p, path, os.path.basename(path)):
            _clear_repair(p)
        store.save_project(pid, p)
    except OSError as exc:
        raise HTTPException(503, 'The recording or project could not be read or saved. Your last saved project is retained.') from exc
    _supersede_job(pid)
    return p["song"]


@app.post("/api/projects/{pid}/song-upload")
async def upload_song(pid: str, file: UploadFile = File(...)):
    """Use immutable project-local recordings; repeated names never overwrite."""
    import uuid
    from engine.project_media import switch_recording
    p = _load(pid)
    name = os.path.basename((file.filename or "").replace("\\", "/"))
    if not name or name in (".", ".."):
        await file.close()
        raise HTTPException(400, "Invalid upload filename")
    extension = os.path.splitext(name)[1].lower()
    if extension not in (".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac"):
        await file.close()
        raise HTTPException(400, "Upload must be an audio file "
                                 "(.mp3 .wav .m4a .flac .ogg .aac)")
    pdir = os.path.realpath(store.project_dir(pid))
    recording_dir = os.path.realpath(os.path.join(pdir, 'recordings'))
    if os.path.dirname(recording_dir) != pdir:
        await file.close()
        raise HTTPException(400, "The recording directory leaves the project folder.")
    dest = os.path.join(recording_dir, 'audio-' + uuid.uuid4().hex + extension)
    temporary = dest + '.uploading'
    committed = False
    try:
        os.makedirs(recording_dir, exist_ok=True)
        digest, size = hashlib.sha256(), 0
        with open(temporary, 'xb') as handle:
            while True:
                block = await file.read(1024 * 1024)
                if not block:
                    break
                size += len(block)
                if size > 512 * 1024 * 1024:
                    raise HTTPException(413, 'Audio uploads must be at most 512 MiB.')
                digest.update(block)
                handle.write(block)
            if not size:
                raise HTTPException(400, 'The audio file is empty.')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, dest)
        signature = {'sha256': digest.hexdigest(), 'bytes': size}
        if switch_recording(p, dest, name, signature):
            _clear_repair(p)
        store.save_project(pid, p)
        committed = True
    except OSError as exc:
        raise HTTPException(503, 'The upload could not be saved. Your prior recording and saved dance are retained.') from exc
    finally:
        await file.close()
        if not committed:
            for candidate in (temporary, dest):
                if os.path.isfile(candidate):
                    os.unlink(candidate)
    _supersede_job(pid)
    return p["song"]


@app.get("/api/projects/{pid}/audio")
def get_audio(pid: str):
    p = _load(pid)
    path = p["song"].get("path")
    if not path or not os.path.isfile(path):
        raise HTTPException(404, "No audio file set")
    media = "audio/mpeg" if path.lower().endswith(".mp3") else \
            "audio/wav" if path.lower().endswith(".wav") else \
            "application/octet-stream"
    return FileResponse(path, media_type=media, filename=os.path.basename(path))


# ---------------------------------------------------------------------------
# Analysis (background thread + polling)
# ---------------------------------------------------------------------------
def _supersede_job(pid):
    """Invalidate any in-flight work for a project whose song changed.

    Without this, a long analysis of song A finishes AFTER the user switches
    to song B and writes A's BPM and beat grid into B's project — the exact
    silently-wrong-sheet failure the app exists to prevent.
    """
    with _jobs_lock:
        job = _jobs.get(pid)
        if job and job.get("status") == "running":
            job.update(
                generation=job.get("generation", 0) + 1,
                superseded=True,
                status="stale",
                message="Song changed; the previous analysis was discarded. "
                        "Run Analyze again.",
            )
        alignment_job = _alignment_jobs.get(pid)
        if alignment_job and alignment_job.get("status") == "running":
            alignment_job.update(
                generation=alignment_job.get("generation", 0) + 1,
                superseded=True,
                status="stale",
                message="Song changed; the lyric result was discarded.",
            )


def _supersede_alignment_job(pid):
    """Discard an alignment when its lyric sheet has been edited."""
    with _jobs_lock:
        job = _alignment_jobs.get(pid)
        if job and job.get("status") == "running":
            job.update(
                generation=job.get("generation", 0) + 1,
                superseded=True,
                status="stale",
                message="Lyrics changed; the in-progress lyric result was discarded.",
            )


def _supersede_scan_for_section_edit(pid):
    """Make a manual section save win over an in-progress automatic draft."""
    with _jobs_lock:
        job = _alignment_jobs.get(pid)
        if (job and job.get("status") == "running" and
                job.get("mode") == "scan"):
            job.update(
                generation=job.get("generation", 0) + 1,
                superseded=True,
                status="stale",
                message="Section markers were edited; your markers were kept and the scan draft was discarded.",
            )


def _run_analysis(pid, path, generation):
    def current():
        job = _jobs.get(pid)
        return bool(job) and job.get("generation") == generation

    def progress(msg):
        with _jobs_lock:
            if current():
                _jobs[pid].update(status="running", message=msg)
    try:
        result = audio_engine.analyze(path, progress=progress)
        with _jobs_lock:
            if not current():
                # the song changed underneath us — throw this result away
                return
        p = store.load_project(pid)
        if p["song"].get("path") != path:
            with _jobs_lock:
                _jobs[pid] = {"status": "stale", "generation": generation,
                              "message": "Song changed during analysis; "
                                         "result discarded. Re-run Analyze."}
            return
        result["source_path"] = path
        result["source_filename"] = os.path.basename(path)
        if _analysis_signature(p.get("analysis")) != _analysis_signature(result):
            _mark_lyric_move_draft_stale(
                p, "Audio analysis changed after this draft was built.",
            )
        p["analysis"] = result
        p["phrase"] = None
        store.save_project(pid, p)
        with _jobs_lock:
            if current():
                _jobs[pid] = {"status": "done", "generation": generation,
                              "message": "Analysis complete."}
    except Exception as e:
        traceback.print_exc()
        with _jobs_lock:
            if current():
                _jobs[pid] = {"status": "error", "generation": generation,
                              "message": str(e)}


@app.post("/api/projects/{pid}/analyze")
def analyze(pid: str):
    p = _load(pid)
    path = p["song"].get("path")
    if not path or not os.path.isfile(path):
        raise HTTPException(400, "Set a song file first")
    with _jobs_lock:
        job = _jobs.get(pid)
        if (job and job.get("status") == "running" and
                not job.get("superseded") and job.get("path") == path):
            # already analysing THIS file — join the existing run
            return {"status": "running", "message": job.get("message", "")}
        generation = (job.get("generation", 0) + 1) if job else 1
        _jobs[pid] = {"status": "running", "generation": generation,
                      "path": path, "message": "Starting analysis...",
                      "superseded": False}
    t = threading.Thread(target=_run_analysis, args=(pid, path, generation),
                         daemon=True)
    t.start()
    return {"status": "running", "message": "Starting analysis..."}


@app.get("/api/projects/{pid}/analysis-status")
def analysis_status(pid: str):
    with _jobs_lock:
        job = _jobs.get(pid)
    if not job:
        p = _load(pid)
        if p.get("analysis"):
            return {"status": "done", "message": "Analysis loaded."}
        return {"status": "idle", "message": ""}
    return job


# ---------------------------------------------------------------------------
# Lyrics / sections / phrasing
# ---------------------------------------------------------------------------
@app.put("/api/projects/{pid}/lyrics")
def set_lyrics(pid: str, body: LyricsBody):
    p = _load(pid)
    _require_expected_revision(p, body.expected_revision)
    _supersede_alignment_job(pid)
    parsed = phrasing.parse_tagged_lyrics(body.text)
    source_changed = (
        p.get("lyrics_raw", "") != body.text or
        p.get("lyric_sections", []) != parsed or
        p.get("alignment") is not None
    )
    p["lyrics_raw"] = body.text
    p["lyric_sections"] = parsed
    # Timings belong to the exact lyric copy that was aligned.  Never leave
    # an old timestamp table visible after the user has corrected a word.
    p["alignment"] = None
    if source_changed:
        _mark_lyric_move_draft_stale(
            p, "Lyrics or timed alignment changed after this draft was built.",
        )
    store.save_project(pid, p)
    return {"sections": p["lyric_sections"]}


def _validated_scan_sections(result):
    """Normalize scan proposals before any project state is changed."""
    raw = result.get("suggested_sections") or []
    if not isinstance(raw, list):
        raise alignment_engine.AlignmentError(
            "The lyric scan returned an invalid section draft. Your project was not changed."
        )
    sections = []
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise alignment_engine.AlignmentError(
                "The lyric scan returned an invalid section draft. Your project was not changed."
            )
        try:
            start = float(row["start"])
            end = float(row["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise alignment_engine.AlignmentError(
                "The lyric scan returned an invalid section time. Your project was not changed."
            ) from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise alignment_engine.AlignmentError(
                "The lyric scan returned an invalid section time. Your project was not changed."
            )
        sections.append({
            "label": str(row.get("label") or f"Section {index}").strip() or f"Section {index}",
            "start": round(start, 3),
            "end": round(end, 3),
        })
    sections.sort(key=lambda section: section["start"])
    for previous, current in zip(sections, sections[1:]):
        if current["start"] < previous["end"] - 0.001:
            raise alignment_engine.AlignmentError(
                "The lyric scan returned overlapping section times. Your project was not changed."
            )
    return sections


def _scan_failure_message(result):
    issues = result.get("issues") or []
    for issue in issues:
        if isinstance(issue, str) and issue.strip():
            return issue.strip()
        if isinstance(issue, dict):
            message = issue.get("message")
            if message:
                return str(message)
    return "The song could not be scanned for lyrics. Your project was not changed."


def _run_lyric_scan(pid, path, analysis, generation, file_signature,
                    analysis_signature, pre_scan_lyrics,
                    replace_generated_lyrics=False,
                    replace_generated_sections=False):
    """Transcribe unknown lyrics and save one reviewable draft atomically."""
    def current():
        job = _alignment_jobs.get(pid)
        return (bool(job) and job.get("generation") == generation and
                job.get("mode") == "scan")

    def progress(message):
        with _jobs_lock:
            if current():
                _alignment_jobs[pid].update(status="running", message=message)

    try:
        result = alignment_engine.scan(path, analysis, progress=progress)
        if not isinstance(result, dict):
            raise alignment_engine.AlignmentError(
                "The lyric scan did not return a usable draft. Your project was not changed."
            )
        if str(result.get("status", "")).lower() in {"blocked", "error", "failed"}:
            raise alignment_engine.AlignmentError(_scan_failure_message(result))
        transcript = str(result.get("lyrics_text") or "").strip()
        if not transcript:
            raise alignment_engine.AlignmentError(
                "No clear sung lyrics were detected. Your project was not changed."
            )
        proposed_sections = _validated_scan_sections(result)

        # Serialize the final optimistic check with every route that can
        # supersede a lyric job. This closes the last-millisecond window where
        # a manual marker save could otherwise be overwritten by the draft.
        with _jobs_lock:
            if not current():
                return
            p = store.load_project(pid)
            current_path = (p.get("song") or {}).get("path")
            try:
                current_file_signature = _file_signature(current_path) if current_path else None
            except OSError:
                current_file_signature = None
            stale_message = None
            if current_file_signature != file_signature:
                stale_message = (
                    "The song file changed during the scan; the draft was discarded. Scan again."
                )
            elif _analysis_signature(p.get("analysis")) != analysis_signature:
                stale_message = (
                    "The song analysis changed during the scan; the draft was discarded. Scan again."
                )
            elif p.get("lyrics_raw", "") != pre_scan_lyrics:
                stale_message = (
                    "Lyrics were edited during the scan; your edit was kept and the draft was discarded."
                )
            if stale_message:
                _alignment_jobs[pid] = {
                    "status": "stale", "mode": "scan", "generation": generation,
                    "message": stale_message,
                }
                return

            # Work on a copy and persist only once, after every stale/shape
            # check. save_project uses a temporary file + os.replace, making
            # the transcript, alignment and optional markers one update.
            updated = copy.deepcopy(p)
            # A repeat scan may safely replace the app's own prior draft when
            # it is still byte-for-byte unchanged.  Hand-entered or edited
            # lyrics and markers continue to win.
            lyrics_applied = (not pre_scan_lyrics.strip() or
                              replace_generated_lyrics)
            if lyrics_applied:
                updated["lyrics_raw"] = transcript
                updated["lyric_sections"] = phrasing.parse_tagged_lyrics(transcript)

            sections_applied = bool(proposed_sections) and (
                not (updated.get("sections") or []) or replace_generated_sections
            )
            if sections_applied:
                updated["sections"] = proposed_sections
                updated["phrase"] = None
                updated["tutorial"] = None

            alignment = copy.deepcopy(result)
            alignment.update({
                "mode": "scan",
                "source_path": path,
                "source_filename": os.path.basename(path),
                "source_file_signature": file_signature,
                "source_analysis_signature": analysis_signature,
                "lyrics_applied": lyrics_applied,
                "sections_applied": sections_applied,
                "accepted": sections_applied,
                "manual_decision": ("auto_assigned_scan" if sections_applied
                                    else "preserved_existing_work"),
            })
            updated["alignment"] = alignment
            if (updated.get("lyrics_raw") != p.get("lyrics_raw") or
                    updated.get("lyric_sections") != p.get("lyric_sections") or
                    updated.get("alignment") != p.get("alignment")):
                _mark_lyric_move_draft_stale(
                    updated,
                    "Lyrics or timed alignment changed after this draft was built.",
                )
            store.save_project(pid, updated)

            if sections_applied:
                message = "Draft lyrics and section markers are ready to review."
            elif lyrics_applied:
                message = (
                    "Draft lyrics are ready to review; your existing section markers were preserved."
                )
            else:
                message = (
                    "Draft scan is ready to review; your existing lyrics and section markers were preserved."
                )
            _alignment_jobs[pid] = {
                "status": "done", "mode": "scan", "generation": generation,
                "message": message,
                "lyrics_applied": lyrics_applied,
                "sections_applied": sections_applied,
            }
    except alignment_engine.AlignmentError as exc:
        with _jobs_lock:
            if current():
                _alignment_jobs[pid] = {
                    "status": "error", "mode": "scan", "generation": generation,
                    "message": str(exc),
                }
    except Exception as exc:
        traceback.print_exc()
        with _jobs_lock:
            if current():
                _alignment_jobs[pid] = {
                    "status": "error", "mode": "scan", "generation": generation,
                    "message": f"Lyric scan failed: {exc}",
                }


@app.post("/api/projects/{pid}/scan-lyrics")
def scan_lyrics(pid: str):
    """Start a local transcription-first draft without overwriting user work."""
    p = _load(pid)
    path = (p.get("song") or {}).get("path")
    if not path or not os.path.isfile(path):
        raise HTTPException(400, "Set a song file first")

    with _jobs_lock:
        analysis_job = _jobs.get(pid)
    if analysis_job and analysis_job.get("status") == "running":
        raise HTTPException(
            409, "Song analysis is still running. Wait for Analyze to finish, then scan lyrics."
        )
    if analysis_job and analysis_job.get("status") in {"error", "stale"}:
        raise HTTPException(
            409, "The latest song analysis did not finish cleanly. Run Analyze again, then scan lyrics."
        )
    analysis = copy.deepcopy(p.get("analysis") or {})
    if not analysis:
        raise HTTPException(
            409, "Analyze the song first so lyric sections can snap to the beat grid."
        )
    analysis_path = analysis.get("source_path")
    if (analysis_path and
            os.path.normcase(os.path.realpath(analysis_path)) !=
            os.path.normcase(os.path.realpath(path))):
        raise HTTPException(
            409, "The saved song analysis belongs to another file. Run Analyze again, then scan lyrics."
        )
    try:
        file_signature = _file_signature(path)
    except OSError as exc:
        raise HTTPException(
            409, "The song file changed or became unavailable. Select it again before scanning lyrics."
        ) from exc
    analysis_signature = _analysis_signature(analysis)
    pre_scan_lyrics = p.get("lyrics_raw", "")
    previous_alignment = p.get("alignment") or {}
    previous_scan_lyrics = str(previous_alignment.get("lyrics_text") or "")
    replace_generated_lyrics = bool(
        previous_alignment.get("mode") == "scan" and
        pre_scan_lyrics.strip() and
        pre_scan_lyrics == previous_scan_lyrics
    )
    current_sections = p.get("sections") or []
    previous_suggestions = previous_alignment.get("suggested_sections") or []
    try:
        previous_sections = [
            {
                "label": str(row.get("label") or f"Section {index}").strip()
                         or f"Section {index}",
                "start": round(float(row["start"]), 3),
                "end": round(float(row["end"]), 3),
            }
            for index, row in enumerate(previous_suggestions, start=1)
        ]
    except (AttributeError, KeyError, TypeError, ValueError):
        previous_sections = []
    replace_generated_sections = bool(
        previous_alignment.get("mode") == "scan" and
        current_sections and
        _sections_key(current_sections) == _sections_key(previous_sections)
    )

    with _jobs_lock:
        job = _alignment_jobs.get(pid)
        if (job and job.get("status") == "running" and
                job.get("mode") == "scan" and
                job.get("file_signature") == file_signature and
                job.get("analysis_signature") == analysis_signature and
                job.get("pre_scan_lyrics") == pre_scan_lyrics):
            return {"status": "running", "mode": "scan",
                    "message": job.get("message", "")}
        generation = (job.get("generation", 0) + 1) if job else 1
        _alignment_jobs[pid] = {
            "status": "running", "mode": "scan", "generation": generation,
            "path": path, "file_signature": file_signature,
            "analysis_signature": analysis_signature,
            "pre_scan_lyrics": pre_scan_lyrics,
            "message": "Scanning the song for lyrics and section changes...",
        }
    thread = threading.Thread(
        target=_run_lyric_scan,
        args=(pid, path, analysis, generation, file_signature,
              analysis_signature, pre_scan_lyrics,
              replace_generated_lyrics, replace_generated_sections),
        daemon=True,
    )
    thread.start()
    return {"status": "running", "mode": "scan",
            "message": "Scanning the song for lyrics and section changes..."}


def _run_alignment(pid, path, lyrics_text, analysis, generation):
    """Run slow local transcription without blocking the browser request."""
    def current():
        job = _alignment_jobs.get(pid)
        return (bool(job) and job.get("generation") == generation and
                job.get("mode", "align") == "align")

    def progress(message):
        with _jobs_lock:
            if current():
                _alignment_jobs[pid].update(status="running", message=message)

    try:
        result = alignment_engine.align(path, lyrics_text, analysis,
                                        progress=progress)
        with _jobs_lock:
            if not current():
                return
        p = store.load_project(pid)
        # A result is meaningful only for the exact song and lyric text it
        # started with.  This protects a manual edit made while transcription
        # was running.
        if (p["song"].get("path") != path or
                p.get("lyrics_raw", "") != lyrics_text):
            with _jobs_lock:
                _alignment_jobs[pid] = {
                    "status": "stale", "mode": "align", "generation": generation,
                    "message": "Song or lyrics changed; timed lyrics were discarded.",
                }
            return
        result["source_path"] = path
        result["source_filename"] = os.path.basename(path)
        alignment_changed = p.get("alignment") != result
        p["alignment"] = result
        if alignment_changed:
            _mark_lyric_move_draft_stale(
                p, "Timed lyric alignment changed after this draft was built.",
            )
        store.save_project(pid, p)
        with _jobs_lock:
            if current():
                _alignment_jobs[pid] = {
                    "status": "done", "mode": "align", "generation": generation,
                    "message": "Timed lyrics are ready to review.",
                }
    except alignment_engine.AlignmentError as exc:
        with _jobs_lock:
            if current():
                _alignment_jobs[pid] = {
                    "status": "error", "mode": "align", "generation": generation,
                    "message": str(exc),
                }
    except Exception as exc:
        traceback.print_exc()
        with _jobs_lock:
            if current():
                _alignment_jobs[pid] = {
                    "status": "error", "mode": "align", "generation": generation,
                    "message": f"Lyric alignment failed: {exc}",
                }


@app.post("/api/projects/{pid}/align-lyrics")
def align_lyrics(pid: str):
    """Begin a local, review-only word-timestamp pass for the current song."""
    p = _load(pid)
    path = p["song"].get("path")
    lyrics_text = p.get("lyrics_raw", "")
    if not path or not os.path.isfile(path):
        raise HTTPException(400, "Set a song file first")
    if not lyrics_text.strip():
        raise HTTPException(400, "Paste the song lyrics first")
    with _jobs_lock:
        job = _alignment_jobs.get(pid)
        if (job and job.get("status") == "running" and
                job.get("path") == path and job.get("lyrics") == lyrics_text):
            return {"status": "running", "message": job.get("message", "")}
        generation = (job.get("generation", 0) + 1) if job else 1
        _alignment_jobs[pid] = {
            "status": "running", "mode": "align", "generation": generation, "path": path,
            "lyrics": lyrics_text, "message": "Starting lyric alignment...",
        }
    analysis = p.get("analysis") or {}
    thread = threading.Thread(target=_run_alignment,
                              args=(pid, path, lyrics_text, analysis, generation),
                              daemon=True)
    thread.start()
    return {"status": "running", "message": "Starting lyric alignment..."}


@app.get("/api/projects/{pid}/alignment-status")
def alignment_status(pid: str):
    with _jobs_lock:
        job = _alignment_jobs.get(pid)
    if job:
        # Source fingerprints and lyric text are implementation details, not
        # useful UI state to echo back on every poll.
        private = {"lyrics", "pre_scan_lyrics", "file_signature", "analysis_signature"}
        return {key: value for key, value in job.items() if key not in private}
    p = _load(pid)
    if p.get("alignment"):
        if p["alignment"].get("mode") == "scan":
            return {"status": "done", "mode": "scan",
                    "message": "Draft lyrics and sections are ready to review."}
        return {"status": "done", "mode": "align",
                "message": "Timed lyrics are ready to review."}
    return {"status": "idle", "message": ""}


@app.post("/api/projects/{pid}/alignment/accept")
def accept_alignment(pid: str):
    """Copy reviewed suggestions into the editable waveform section table."""
    p = _load(pid)
    alignment = p.get("alignment") or {}
    suggestions = alignment.get("suggested_sections") or []
    if not suggestions:
        raise HTTPException(422, "No dependable section suggestions are available")
    sections = [{"label": row["label"], "start": row["start"], "end": row["end"]}
                for row in suggestions]
    p["sections"] = sections
    p["phrase"] = None
    alignment_changed = (alignment.get("accepted") is not True or
                         alignment.get("manual_decision") != "accepted_suggestions")
    alignment["accepted"] = True
    alignment["manual_decision"] = "accepted_suggestions"
    p["alignment"] = alignment
    if alignment_changed:
        _mark_lyric_move_draft_stale(
            p, "Timed lyric alignment changed after this draft was built.",
        )
    store.save_project(pid, p)
    return {"sections": sections, "alignment": alignment}


@app.post("/api/projects/{pid}/alignment/keep-manual")
def keep_manual_sections(pid: str):
    """Record that the dancer kept their own waveform markers unchanged."""
    p = _load(pid)
    alignment = p.get("alignment")
    if not alignment:
        raise HTTPException(404, "No timed lyrics are available yet")
    alignment_changed = (alignment.get("accepted") is not False or
                         alignment.get("manual_decision") != "kept_manual_markers")
    alignment["accepted"] = False
    alignment["manual_decision"] = "kept_manual_markers"
    p["alignment"] = alignment
    if alignment_changed:
        _mark_lyric_move_draft_stale(
            p, "Timed lyric alignment changed after this draft was built.",
        )
    store.save_project(pid, p)
    return {"alignment": alignment, "sections": p.get("sections") or []}


def _sections_key(secs):
    return [(s.get("label"), round(float(s["start"]), 3), round(float(s["end"]), 3))
            for s in secs]


@app.put("/api/projects/{pid}/sections")
def set_sections(pid: str, body: SectionsBody):
    p = _load(pid)
    _require_expected_revision(p, body.expected_revision)
    _supersede_scan_for_section_edit(pid)
    secs = sorted(body.sections, key=lambda s: s["start"])
    # Only invalidate the phrasing report when the boundaries actually moved.
    # A plain re-save must not silently discard a completed double-check.
    if _sections_key(secs) != _sections_key(p.get("sections") or []):
        p["phrase"] = None
    p["sections"] = secs
    store.save_project(pid, p)
    return {"sections": secs, "phrase_kept": p.get("phrase") is not None}


@app.post("/api/projects/{pid}/phrase-check")
def phrase_check(pid: str, body: SectionsBody):
    _supersede_scan_for_section_edit(pid)
    p = _load(pid)
    if not p.get("analysis"):
        raise HTTPException(400, "Run analysis first")
    secs = sorted(body.sections, key=lambda s: s["start"]) if body.sections \
        else p.get("sections", [])
    p["sections"] = secs
    result = phrasing.phrase_check(secs, p["analysis"],
                                   pattern_len=body.pattern_len or 32)
    p["phrase"] = result
    store.save_project(pid, p)
    return result


# ---------------------------------------------------------------------------
# Steps / generation / validation
# ---------------------------------------------------------------------------
@app.get("/api/steps")
def steps():
    return library_json()


@app.post("/api/projects/{pid}/lyric-moves/draft")
def draft_lyric_moves(pid: str, body: LyricMoveDraftBody):
    """Build and save a review-only proposal without changing the dance."""
    p = _load(pid)
    settings = body.model_dump(exclude={"passage_id", "fill_gaps"})
    try:
        draft = lyric_moves_engine.build_draft(
            copy.deepcopy(p), settings,
            passage_id=body.passage_id, fill_gaps=body.fill_gaps,
        )
    except AssemblyError as exc:
        return Response(content=json.dumps(exc.to_dict()), status_code=422,
                        media_type="application/json")
    p["lyric_move_draft"] = draft
    store.save_project(pid, p)
    return draft


@app.post("/api/projects/{pid}/generate")
def generate(pid: str, body: GenerateBody):
    p = _load(pid)
    analysis = p.get("analysis") or {}
    bpm = analysis.get("bpm")
    try:
        result = assemble(total_counts=body.counts, wall=body.wall,
                           turn_dir=body.turn_dir, level=body.level,
                           allow_sync=body.allow_sync, seed=body.seed,
                           k=body.k, bpm=bpm,
                           experimental_mode=body.experimental_mode,
                           publication_mode=body.publication_mode,
                           include_custom_moves=body.include_custom_moves)
    except AssemblyError as e:
        return Response(content=__import__("json").dumps(e.to_dict()),
                        status_code=422, media_type="application/json")
    old = p.get("dance") or {}
    p["dance"] = {
        "source": "generated",
        "counts": body.counts, "wall": body.wall, "turn_dir": body.turn_dir,
        "level": body.level, "seed": body.seed, "allow_sync": body.allow_sync,
        "experimental_mode": body.experimental_mode,
        "publication_mode": body.publication_mode,
        "include_custom_moves": body.include_custom_moves, "tempo": result["tempo"],
        # snapshot so re-choosing a candidate can restore these even after a
        # custom save overwrote the shared counts/wall/turn_dir
        "gen_params": {"counts": body.counts, "wall": body.wall,
                       "turn_dir": body.turn_dir, "level": body.level,
                       "tempo": result["tempo"]},
        "candidates": result["candidates"], "chosen": 0,
        "custom": old.get("custom"),
    }
    store.save_project(pid, p)
    return result


@app.post("/api/validate")
def validate(body: ValidateBody):
    moves = _expand_moves(body.moves)
    return validate_sequence(moves, body.counts, body.wall, body.turn_dir,
                             bpm=body.bpm)


@app.put("/api/projects/{pid}/dance")
def set_dance(pid: str, body: DanceBody):
    p = _load(pid)
    d = p.get("dance") or {}
    if body.source == "custom":
        if not body.moves:
            raise HTTPException(400, "Custom dance needs moves")
        _expand_moves(body.moves)  # validate ids
        d.update({"source": "custom", "custom": body.moves,
                  "counts": body.counts, "wall": body.wall,
                  "turn_dir": body.turn_dir})
    else:
        d["source"] = "generated"
        if body.chosen is not None:
            d["chosen"] = body.chosen
        # restore generation-time params — a custom save may have overwritten
        # the shared counts/wall, which would validate the candidate against
        # the wrong pattern and falsely fail it
        gp = d.get("gen_params")
        if gp:
            d.update({"counts": gp["counts"], "wall": gp["wall"],
                       "turn_dir": gp["turn_dir"], "level": gp.get("level",
                                                                   d.get("level")),
                      "tempo": gp.get("tempo", d.get("tempo"))})
    p["dance"] = d
    store.save_project(pid, p)
    dance = _current_dance(p)
    return {"ok": True, "validation": dance["validation"] if dance else None}


@app.put("/api/projects/{pid}/meta")
def set_meta(pid: str, body: MetaBody):
    p = _load(pid)
    _require_expected_revision(p, body.expected_revision)
    meta = p.get("sheet_meta") or {}
    for k, v in body.model_dump(exclude_none=True, exclude={'expected_revision'}).items():
        if k in ("title", "artist"):
            p["song"][k] = v
        else:
            meta[k] = v
    p["sheet_meta"] = meta
    store.save_project(pid, p)
    return meta


# ---------------------------------------------------------------------------
# Tutorial Blueprint: one count-locked source for feet, calls, and cameras
# ---------------------------------------------------------------------------
def _current_tutorial(p):
    plan = p.get("tutorial")
    if not plan:
        return None
    current = copy.deepcopy(plan)
    dance = _current_dance(p) or {}
    report = tutorial_engine.validate_tutorial_plan(
        current, dance, p.get("analysis") or {}, p.get("phrase") or {},
    )
    current["validation"] = report
    current["status"] = report["status"]
    return current


@app.get("/api/projects/{pid}/tutorial")
def get_tutorial(pid: str):
    p = _load(pid)
    return {"tutorial": _current_tutorial(p)}


@app.post("/api/projects/{pid}/tutorial/build")
def build_tutorial(pid: str, body: TutorialBuildBody):
    p = _load(pid)
    dance = _current_dance(p)
    if not dance:
        raise HTTPException(400, "Save or choose a dance before building its tutorial blueprint.")
    plan = tutorial_engine.build_tutorial_plan(
        dance, p.get("analysis") or {}, p.get("phrase") or {},
        callout_lead_counts=body.callout_lead_counts,
        tempo_grid_confirmed=body.tempo_grid_confirmed,
        voice_name=body.voice_name,
        count_in=body.count_in,
        count_in_counts=body.count_in_counts,
        anchor_seconds=body.anchor_seconds,
        voice_notes=body.voice_notes,
        producer_notes=body.producer_notes,
    )
    plan["project"] = {
        "id": p.get("id"), "name": p.get("name"),
        "song_title": (p.get("song") or {}).get("title"),
        "artist": (p.get("song") or {}).get("artist"),
    }
    p["tutorial"] = plan
    store.save_project(pid, p)
    return {"tutorial": plan}


@app.put("/api/projects/{pid}/tutorial")
def update_tutorial(pid: str, body: TutorialUpdateBody):
    p = _load(pid)
    _require_expected_revision(p, body.expected_revision)
    if not p.get("tutorial"):
        raise HTTPException(400, "Build the tutorial blueprint before editing its cues.")
    try:
        plan = tutorial_engine.update_tutorial_plan(
            p["tutorial"],
            [item.model_dump(exclude_none=True) for item in body.segments],
            count_in=body.count_in,
            voice_notes=body.voice_notes,
            producer_notes=body.producer_notes,
            tempo_grid_confirmed=body.tempo_grid_confirmed,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    dance = _current_dance(p) or {}
    report = tutorial_engine.validate_tutorial_plan(
        plan, dance, p.get("analysis") or {}, p.get("phrase") or {},
    )
    plan["validation"] = report
    plan["status"] = report["status"]
    p["tutorial"] = plan
    store.save_project(pid, p)
    return {"tutorial": plan}


@app.post("/api/projects/{pid}/tutorial/validate")
def validate_tutorial(pid: str):
    p = _load(pid)
    plan = _current_tutorial(p)
    if not plan:
        raise HTTPException(400, "No tutorial blueprint has been built yet.")
    return plan["validation"]


def _tutorial_export(pid):
    p = _load(pid)
    plan = _current_tutorial(p)
    if not plan:
        raise HTTPException(400, "No tutorial blueprint has been built yet.")
    return plan


@app.get("/api/projects/{pid}/tutorial.txt")
def tutorial_txt(pid: str):
    plan = _tutorial_export(pid)
    return PlainTextResponse(tutorial_engine.render_tutorial_txt(plan))


@app.get("/api/projects/{pid}/tutorial.csv")
def tutorial_csv(pid: str):
    plan = _tutorial_export(pid)
    return Response(content=tutorial_engine.render_tutorial_csv(plan),
                    media_type="text/csv; charset=utf-8")


@app.get("/api/projects/{pid}/tutorial.json")
def tutorial_json(pid: str):
    plan = _tutorial_export(pid)
    return Response(content=tutorial_engine.render_tutorial_json(plan),
                    media_type="application/json")


# ---------------------------------------------------------------------------
# Sound Repair Studio: separation, phrase-copy repair, and download
# ---------------------------------------------------------------------------
def _set_repair_job(pid, **changes):
    with _jobs_lock:
        job = _repair_jobs.setdefault(pid, {"status": "idle", "message": ""})
        job.update(changes)


def _run_separation(pid, source_path, generation):
    """Run Demucs without blocking the FastAPI worker.

    Demucs intentionally runs as a separate process: its Torch runtime can be
    large and may download the selected model on its first use.  We keep all
    outputs underneath the project and only expose files found there.
    """
    try:
        root = _repair_root(pid)
        separation_root = os.path.join(root, "separation")
        os.makedirs(separation_root, exist_ok=True)
        _set_repair_job(pid, status="running", generation=generation,
                        kind="separation", message="Loading the separation model…")
        command = [sys.executable, "-m", "demucs.separate", "-n", "htdemucs_6s",
                   "-o", separation_root, source_path]
        process = subprocess.Popen(command, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", errors="replace")
        latest = "Separating stems…"
        if process.stdout:
            for line in process.stdout:
                line = line.strip()
                if line:
                    latest = line[-220:]
                    _set_repair_job(pid, status="running", generation=generation,
                                    kind="separation", message=latest)
        code = process.wait()
        if code:
            raise RuntimeError(
                "Stem separation could not start. Make sure the optional Demucs "
                "audio component is installed, then try again.")
        with _jobs_lock:
            current = _repair_jobs.get(pid, {})
            if current.get("generation") != generation:
                return
        # Demucs writes model/song-name/stem.wav. Find the newest result rather
        # than trusting the input filename, which may contain Unicode or dots.
        stem_paths = {}
        for folder, _, files in os.walk(separation_root):
            for filename in files:
                stem = os.path.splitext(filename)[0].lower()
                path = os.path.realpath(os.path.join(folder, filename))
                if (stem in STEM_DISPLAY and filename.lower().endswith(".wav") and
                        _inside_repair_root(pid, path)):
                    previous = stem_paths.get(stem)
                    if not previous or os.path.getmtime(path) > os.path.getmtime(previous):
                        stem_paths[stem] = path
        if not stem_paths:
            raise RuntimeError("The separation model finished but did not create any usable stems.")
        p = store.load_project(pid)
        if p.get("song", {}).get("path") != source_path:
            _set_repair_job(pid, status="stale", generation=generation,
                            kind="separation", message="Song changed; discarded the old stems.")
            return
        p["repair"] = p.get("repair") or {}
        p["repair"]["separation"] = {
            "status": "done", "model": "htdemucs_6s", "stems": stem_paths,
            "created": time.time(),
        }
        p["repair"].pop("last_output", None)
        p["repair"].pop("last_render", None)
        store.save_project(pid, p)
        _set_repair_job(pid, status="done", generation=generation, kind="separation",
                        message=f"Ready: {len(stem_paths)} editable stems.")
    except Exception as exc:
        traceback.print_exc()
        _set_repair_job(pid, status="error", generation=generation, kind="separation",
                        message=str(exc))


@app.get("/api/projects/{pid}/repair")
def repair_info(pid: str):
    return _repair_info(_load(pid))


@app.post("/api/projects/{pid}/repair/separate")
def separate_stems(pid: str):
    p = _load(pid)
    source_path = p.get("song", {}).get("path")
    if not source_path or not os.path.isfile(source_path):
        raise HTTPException(400, "Upload or choose a song before separating it.")
    with _jobs_lock:
        previous = _repair_jobs.get(pid, {})
        if (previous.get("status") == "running" and previous.get("kind") == "separation" and
                previous.get("source_path") == source_path):
            return {"status": "running", "message": previous.get("message", "Separating stems…")}
        generation = int(previous.get("generation", 0)) + 1
        _repair_jobs[pid] = {"status": "running", "kind": "separation", "generation": generation,
                             "source_path": source_path, "message": "Starting stem separation…"}
    thread = threading.Thread(target=_run_separation, args=(pid, source_path, generation), daemon=True)
    thread.start()
    return {"status": "running", "message": "Starting stem separation…"}


@app.get("/api/projects/{pid}/repair/status")
def repair_status(pid: str):
    _load(pid)
    with _jobs_lock:
        job = dict(_repair_jobs.get(pid, {"status": "idle", "message": ""}))
    return {key: value for key, value in job.items() if key != "source_path"}


@app.get("/api/projects/{pid}/repair/stems/{stem}")
def download_stem(pid: str, stem: str):
    if not SAFE_STEM_RE.fullmatch(stem):
        raise HTTPException(404, "No such stem")
    p = _load(pid)
    path = ((p.get("repair") or {}).get("separation") or {}).get("stems", {}).get(stem)
    if not path or not os.path.isfile(path) or not _inside_repair_root(pid, path):
        raise HTTPException(404, "That stem is not available for this project.")
    title = p.get("song", {}).get("title") or "song"
    return FileResponse(path, media_type="audio/wav",
                        filename=f"{title} - {stem} stem.wav")


def _run_repair_render(pid, source_path, stem_path, body, generation):
    try:
        _set_repair_job(pid, status="running", generation=generation, kind="render",
                        message="Blending the selected phrase into a new mix…")
        root = _repair_root(pid)
        rendered_dir = os.path.join(root, "renders")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        output_path = os.path.realpath(os.path.join(rendered_dir, f"repair-{stamp}.wav"))
        if not _inside_repair_root(pid, output_path):  # defense in depth
            raise RuntimeError("Unsafe repair output location.")
        summary = repair_engine.render_overlay(
            source_path, stem_path, output_path,
            source_start=body.source_start, source_end=body.source_end,
            target_start=body.target_start, target_end=body.target_end,
            fade_ms=body.fade_ms, gain_db=body.gain_db,
        )
        with _jobs_lock:
            current = _repair_jobs.get(pid, {})
            if current.get("generation") != generation:
                return
        p = store.load_project(pid)
        if p.get("song", {}).get("path") != source_path:
            _set_repair_job(pid, status="stale", generation=generation, kind="render",
                            message="Song changed; discarded the old repair.")
            return
        p["repair"] = p.get("repair") or {}
        p["repair"]["last_output"] = output_path
        p["repair"]["last_render"] = {
            "stem": body.stem, "created": time.time(), "source_start": body.source_start,
            "source_end": body.source_end, "target_start": body.target_start,
            "target_end": body.target_end, **summary,
        }
        store.save_project(pid, p)
        _set_repair_job(pid, status="done", generation=generation, kind="render",
                        message="Your repaired mix is ready to audition.")
    except Exception as exc:
        traceback.print_exc()
        _set_repair_job(pid, status="error", generation=generation, kind="render",
                        message=str(exc))


@app.post("/api/projects/{pid}/repair/render")
def render_repair(pid: str, body: RepairRenderBody):
    p = _load(pid)
    if body.stem not in STEM_DISPLAY:
        raise HTTPException(400, "Choose one of the separated stems.")
    source_path = p.get("song", {}).get("path")
    stem_path = ((p.get("repair") or {}).get("separation") or {}).get("stems", {}).get(body.stem)
    if not source_path or not os.path.isfile(source_path):
        raise HTTPException(400, "The original song is unavailable.")
    if not stem_path or not os.path.isfile(stem_path) or not _inside_repair_root(pid, stem_path):
        raise HTTPException(400, "Separate this song first, then choose an available stem.")
    try:
        repair_engine.validate_selection(
            float((p.get("analysis") or {}).get("duration") or 1e12),
            body.source_start, body.source_end, body.target_start, body.target_end,
        )
    except repair_engine.RepairError as exc:
        raise HTTPException(400, str(exc))
    with _jobs_lock:
        previous = _repair_jobs.get(pid, {})
        if previous.get("status") == "running":
            raise HTTPException(409, "Another separation or repair is still running.")
        generation = int(previous.get("generation", 0)) + 1
        _repair_jobs[pid] = {"status": "running", "kind": "render", "generation": generation,
                             "source_path": source_path, "message": "Starting repair…"}
    thread = threading.Thread(target=_run_repair_render,
                              args=(pid, source_path, stem_path, body, generation), daemon=True)
    thread.start()
    return {"status": "running", "message": "Starting repair…"}


@app.get("/api/projects/{pid}/repair/output")
def repaired_output(pid: str):
    p = _load(pid)
    path = (p.get("repair") or {}).get("last_output")
    if not path or not os.path.isfile(path) or not _inside_repair_root(pid, path):
        raise HTTPException(404, "No repaired mix is available yet.")
    title = p.get("song", {}).get("title") or "song"
    return FileResponse(path, media_type="audio/wav", filename=f"{title} - repaired mix.wav")


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
LEVEL_LABELS = {"AB": "Absolute Beginner", "B": "Beginner", "I": "Improver",
                "INT": "Intermediate", "A": "Advanced"}


def _sheet_for(p):
    dance = _current_dance(p)
    if not dance:
        raise HTTPException(400, "No dance yet — generate or build one first")
    meta = dict(p.get("sheet_meta") or {})
    # A dance may share a title with its song, but it does not have to.  Keep
    # those two publishing fields distinct from the very first draft.
    meta["title"] = meta.get("dance_title") or p["song"].get("title")
    meta["song_title"] = p["song"].get("title")
    meta.setdefault("artist", p["song"].get("artist"))
    # The sheet's Level header must reflect the level the dance was actually
    # generated at (a user-typed label still wins) — a Beginner dance stamped
    # "Absolute Beginner" is a community-trust failure.
    lvl = (p.get("dance") or {}).get("level")
    if lvl:
        meta.setdefault("level_label", LEVEL_LABELS.get(lvl, lvl))
    return build_sheet(meta, dance, p.get("analysis"), p.get("phrase")), meta, dance


@app.get("/api/projects/{pid}/sheet.json")
def sheet_json(pid: str):
    p = _load(pid)
    sheet, meta, dance = _sheet_for(p)
    return {"sheet": sheet, "validation": dance["validation"]}


@app.get("/api/projects/{pid}/sheet.txt")
def sheet_txt(pid: str):
    p = _load(pid)
    sheet, _, _ = _sheet_for(p)
    return PlainTextResponse(render_txt(sheet))


@app.get("/api/projects/{pid}/sheet.html")
def sheet_html(pid: str):
    p = _load(pid)
    sheet, _, _ = _sheet_for(p)
    return HTMLResponse(render_html(sheet))


@app.get("/api/projects/{pid}/sheet.pdf")
def sheet_pdf(pid: str):
    p = _load(pid)
    sheet, _, _ = _sheet_for(p)
    path = os.path.join(store.project_dir(pid), "sheet.pdf")
    render_pdf(sheet, path)
    return FileResponse(path, media_type="application/pdf",
                        filename=f"{sheet['title']} - step sheet.pdf")


@app.get("/api/projects/{pid}/challenge")
def challenge(pid: str):
    """Legacy route kept for old browser tabs; use /publish-kit in new UI."""
    p = _load(pid)
    sheet, meta, _ = _sheet_for(p)
    return build_challenge_kit(sheet, meta, p.get("analysis"), p.get("phrase"))


@app.get("/api/projects/{pid}/publish-kit")
def publish_kit(pid: str):
    p = _load(pid)
    sheet, meta, _ = _sheet_for(p)
    return build_publish_kit(sheet, meta, p.get("analysis"), p.get("phrase"))


@app.post("/api/projects/{pid}/export-files")
def export_files(pid: str):
    """Write every deliverable to disk in one click:
    exports/<project>/ next to the app folder — step sheet TXT/HTML/PDF,
    challenge kit, and a full project backup."""
    import json as _json
    import re as _re
    p = _load(pid)
    sheet, meta, dance = _sheet_for(p)
    base = _re.sub(r"[^\w\- ]+", "", sheet["title"]).strip() or pid
    exp_dir = os.path.join(os.path.dirname(APP_DIR), "exports", base)
    os.makedirs(exp_dir, exist_ok=True)
    written = []

    def w(name, content):
        path = os.path.join(exp_dir, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        written.append(name)

    w(f"{base} - step sheet.txt", render_txt(sheet))
    w(f"{base} - step sheet.html", render_html(sheet))
    render_pdf(sheet, os.path.join(exp_dir, f"{base} - step sheet.pdf"))
    written.append(f"{base} - step sheet.pdf")
    kit = build_publish_kit(sheet, meta, p.get("analysis"), p.get("phrase"))
    w(f"{base} - publisher kit.txt",
      f"YOUTUBE TITLE\n{kit['youtube_title']}\n\n"
      f"YOUTUBE DESCRIPTION ADD-ON\n{kit['youtube_add_on']}\n\n"
      f"HASHTAGS\n{kit['hashtags']}\n\n"
      f"COPPERKNOB COMMENTS\n{kit['copperknob_comments']}\n\n"
      f"COPPERKNOB CHECKLIST\n" + "\n".join(
          f"- {item}" for item in kit["copperknob_checklist"]) + "\n\n"
      f"BOOTSTEPPER CHECKLIST\n" + "\n".join(
          f"- {item}" for item in kit["bootstepper_checklist"]) + "\n")
    tutorial = _current_tutorial(p)
    if tutorial:
        w(f"{base} - tutorial call and shot list.txt",
          tutorial_engine.render_tutorial_txt(tutorial))
        w(f"{base} - tutorial timeline.csv",
          tutorial_engine.render_tutorial_csv(tutorial))
        w(f"{base} - tutorial blueprint.json",
          tutorial_engine.render_tutorial_json(tutorial))
        if not (tutorial.get("validation") or {}).get("ready"):
            issues = ((tutorial.get("validation") or {}).get("errors") or [])
            pending = (tutorial.get("validation") or {}).get("confirmation_pending", 0)
            w("WARNING - tutorial blueprint not ready.txt",
              "This tutorial blueprint is a review draft, not a final production plan.\n"
              + (f"{pending} movement cue(s) still need human confirmation.\n" if pending else "")
              + "\n".join(f"- {item.get('message')}" for item in issues))
    w(f"{base} - project backup.json", _json.dumps(p, indent=1))
    if dance.get("validation") and not dance["validation"]["valid"]:
        w("WARNING - dance does not validate.txt",
          "\n".join(pr["message"] for pr in dance["validation"]["problems"]))
    return {"folder": exp_dir, "files": written}


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
@app.get("/style.css")
def root_stylesheet():
    """Keeps the UI assets usable from the root app page and as a local preview."""
    return FileResponse(os.path.join(APP_DIR, "static", "style.css"),
                        media_type="text/css")


@app.get("/app.js")
def root_script():
    return FileResponse(os.path.join(APP_DIR, "static", "app.js"),
                        media_type="application/javascript")


app.mount("/static", StaticFiles(directory=os.path.join(APP_DIR, "static")),
          name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(APP_DIR, "static", "creator.html"))


@app.get("/dance")
def dance_creator():
    return FileResponse(os.path.join(APP_DIR, "static", "creator.html"))


@app.get('/legacy')
def legacy_creator():
    return FileResponse(os.path.join(APP_DIR, "static", "index.html"))


@app.get('/repair')
def repair_studio():
    return FileResponse(os.path.join(APP_DIR, 'static', 'repair.html'))


if __name__ == "__main__":
    import uvicorn
    import webbrowser
    store.ensure_dirs()
    step_database.initialize_database()
    threading.Timer(1.2, lambda: webbrowser.open("http://127.0.0.1:8766/dance")).start()
    uvicorn.run(app, host="127.0.0.1", port=8766)

"""Bounded creator sheet export, portable import, and local publish-pack routes."""
from urllib.parse import quote

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict

from engine import project as store
from engine.creator_exports import (ExportError, MAX_INPUT_BYTES, export_project,
                                   preview_project_package, restore_project_package)
from engine.publish_pack import PublishError, build_publish_pack, reveal_folder


router = APIRouter(prefix="/api/creator")


@router.get("/projects/{pid}/export/{format}")
def creator_export(pid: str, format: str, paper: str = "letter",
                   large_print: bool = Query(False), print_qr: bool = Query(False),
                   include_lyrics: bool = Query(False)):
    try:
        project = store.load_project(pid)
        payload, mime, filename = export_project(project, format, paper, large_print, print_qr, include_lyrics)
        return Response(payload, media_type=mime,
                        headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
                                 "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
    except FileNotFoundError as exc:
        raise HTTPException(404, "Project not found.") from exc
    except (ExportError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(503, "This export component is missing. Repair the application installation.") from exc


async def _read_upload(file):
    payload = await file.read(MAX_INPUT_BYTES + 1)
    if len(payload) > MAX_INPUT_BYTES:
        raise HTTPException(413, "Project packages must be no larger than 16 MB.")
    return payload


@router.post("/import/preview")
async def creator_import_preview(file: UploadFile = File(...)):
    payload = await _read_upload(file)
    try:
        return preview_project_package(payload, file.filename or "project.zip")
    except (ExportError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/import")
async def creator_import(file: UploadFile = File(...)):
    payload = await _read_upload(file)
    try:
        return restore_project_package(payload, file.filename or "project.zip")
    except (ExportError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    paper: str = "letter"
    large_print: bool = False
    print_qr: bool = False
    include_lyrics: bool = False


class OpenFolderBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    folder: str = ""


@router.post("/projects/{pid}/publish-pack")
def create_publish_pack(pid: str, body: PublishBody):
    """Write the step sheet and portable draft, then describe where to open them."""
    try:
        project = store.load_project(pid)
        return build_publish_pack(project, body.paper, body.large_print, body.print_qr, body.include_lyrics)
    except FileNotFoundError as exc:
        raise HTTPException(404, "That dance could not be found.") from exc
    except (ExportError, PublishError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/projects/{pid}/publish-pack/open")
def open_publish_folder(pid: str, body: OpenFolderBody):
    try:
        store.load_project(pid)
        return reveal_folder(pid, body.folder)
    except FileNotFoundError as exc:
        raise HTTPException(404, "That dance could not be found.") from exc
    except (PublishError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc

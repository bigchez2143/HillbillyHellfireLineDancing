"""S04 local library routes. Mount this router on the application.

All paths are under /api/creator/library. Snapshot dictionaries embed concrete
events for the one choreography compiler; they do not mutate the live catalog.
Uploads are user supplied only. Import previews never add moves automatically.
"""
import json
import sqlite3
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.routing import APIRoute
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from engine import library_store as store

class BoundedRoute(APIRoute):
    """Enforce a limit before multipart parsing can spool an unbounded upload."""
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def bounded(request):
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                limit = (store.MAX_VIDEO_BYTES if request.url.path.endswith('/attachments') else store.MAX_IMPORT_BYTES) + 65536
                length = request.headers.get('content-length')
                if length is not None:
                    try:
                        parsed_length = int(length)
                        if parsed_length < 0:
                            raise ValueError()
                    except ValueError as exc:
                        raise HTTPException(400, detail='Invalid request content length.') from exc
                    if parsed_length > limit:
                        raise HTTPException(413, detail='Request exceeds the upload size limit.')
                receive, received = request._receive, 0
                async def limited_receive():
                    nonlocal received
                    message = await receive()
                    received += len(message.get('body', b''))
                    if received > limit:
                        raise HTTPException(413, detail='Request exceeds the upload size limit.')
                    return message
                request._receive = limited_receive
            return await handler(request)
        return bounded


router = APIRouter(prefix='/api/creator/library', tags=['library'], route_class=BoundedRoute)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except store.Conflict as exc:
        raise HTTPException(409, detail={'code': 'LIBRARY_CONFLICT', 'message': str(exc)}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, detail='Local library storage is unavailable. Check storage and try again.') from exc


class FieldsBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    fields: dict


class VersionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)


class EditBody(VersionBody):
    fields: dict


class ConfirmBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed: StrictBool = False


class ReviewBody(VersionBody):
    reviewer: str
    notes: str = ''
    confirmed: StrictBool = False


class CommitBody(ConfirmBody):
    digest: str
    decisions: list[dict]


async def _read_upload(file, limit):
    try:
        # Read bounded chunks so unsupported content never grows without a limit.
        output = bytearray()
        while len(output) <= limit:
            chunk = await file.read(min(1024 * 1024, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
        if len(output) > limit:
            raise HTTPException(413, detail='File exceeds the upload size limit.')
        return bytes(output)
    finally:
        await file.close()


@router.get('')
def library(include_deleted: bool = False):
    return _call(store.get_library, include_deleted)


@router.post('/records', status_code=201)
def create(body: FieldsBody):
    return _call(store.create_record, body.fields)


@router.get('/records/{record_id}')
def record(record_id: str):
    return _call(store.get_record, record_id)


@router.patch('/records/{record_id}')
def edit(record_id: str, body: EditBody):
    return _call(store.update_record, record_id, body.expected_version, body.fields)


@router.delete('/records/{record_id}')
def delete(record_id: str, body: VersionBody):
    return _call(store.delete_record, record_id, body.expected_version)


@router.post('/records/{record_id}/restore')
def restore(record_id: str, body: VersionBody):
    return _call(store.restore_record, record_id, body.expected_version)


@router.get('/reference/{reference_id}/snapshot')
def reference_snapshot(reference_id: str, duration_counts: str | None = None):
    return _call(store.reference_snapshot, reference_id, duration_counts)


@router.get('/records/{record_id}/versions/{version}')
def version(record_id: str, version: int):
    return _call(store.get_record, record_id, version)


@router.get('/records/{record_id}/snapshot')
def snapshot(record_id: str, version: int | None = None):
    return _call(store.snapshot, record_id, version)


@router.post('/records/{record_id}/review')
def review(record_id: str, body: ReviewBody):
    return _call(store.review_record, record_id, body.expected_version, body.reviewer, body.notes, body.confirmed)


@router.post('/imports/preview')
async def preview(file: UploadFile = File(...), field_mapping: str = Form('{}'), origin_kind: str = Form('file')):
    try:
        mapping = json.loads(field_mapping)
    except ValueError as exc:
        await file.close()
        raise HTTPException(422, detail='Field mapping must be a JSON object.') from exc
    filename = file.filename or ''
    payload = await _read_upload(file, store.MAX_IMPORT_BYTES)
    return _call(store.preview_import, filename, payload, mapping, origin_kind)


@router.post('/imports/{token}/commit')
def commit(token: str, body: CommitBody):
    return _call(store.commit_import, token, body.digest, body.decisions, body.confirmed)


@router.post('/imports/batches/{batch_id}/rollback')
def rollback(batch_id: str, body: ConfirmBody):
    return _call(store.rollback_batch, batch_id, body.confirmed)


@router.get('/templates/{format_name}')
def template(format_name: str):
    payload, mime = _call(store.template, format_name)
    return Response(payload, media_type=mime, headers={'Content-Disposition': 'attachment; filename="move-template.' + format_name + '"',
                                                     'X-Content-Type-Options': 'nosniff'})


@router.post('/records/{record_id}/attachments', status_code=201)
async def attach(record_id: str, file: UploadFile = File(...), expected_version: int = Form(...),
                 caption: str = Form(''), orientation: str = Form('unspecified'),
                 start_seconds: str | None = Form(None), end_seconds: str | None = Form(None)):
    filename = file.filename or ''
    image_extensions = ('.png', '.jpg', '.jpeg', '.webp', '.gif')
    limit = store.MAX_IMAGE_BYTES if filename.casefold().endswith(image_extensions) else store.MAX_VIDEO_BYTES
    payload = await _read_upload(file, limit)
    return _call(store.attach_media, record_id, expected_version, filename, payload,
                 caption, orientation, start_seconds, end_seconds)


@router.get('/attachments/{media_id}/content')
def content(media_id: str):
    path, metadata = _call(store.media_content, media_id)
    return FileResponse(path, media_type=metadata['mime'], filename=metadata['original_filename'],
                        content_disposition_type='inline', headers={'X-Content-Type-Options': 'nosniff'})

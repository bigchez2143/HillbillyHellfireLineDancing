"""Bounded private-backup previews and explicit non-destructive restore."""
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, StrictBool
import sqlite3

from engine import full_backup as store


class BoundedRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def bounded(request):
            if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
                limit = store.MAX_ARCHIVE_BYTES + 65536 if request.url.path.endswith('/imports/preview') else store.MAX_JSON_BYTES
                length = request.headers.get('content-length')
                if length is not None:
                    try:
                        number = int(length)
                        if number < 0: raise ValueError()
                    except ValueError as exc:
                        raise HTTPException(400, 'Invalid content length.') from exc
                    if number > limit: raise HTTPException(413, 'The request exceeds the private-backup size limit.')
                receive, total = request._receive, 0
                async def limited():
                    nonlocal total
                    message = await receive(); total += len(message.get('body', b''))
                    if total > limit: raise HTTPException(413, 'The request exceeds the private-backup size limit.')
                    return message
                request._receive = limited
            return await handler(request)
        return bounded


router = APIRouter(prefix='/api/creator/backup', tags=['private-backup'], route_class=BoundedRoute)


class MediaOptions(BaseModel):
    model_config = ConfigDict(extra='forbid')
    include_music: StrictBool = False
    include_photos: StrictBool = False
    include_videos: StrictBool = False


class ExportBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    options: MediaOptions = Field(default_factory=MediaOptions)
    browser_preferences: dict = Field(default_factory=dict)


class RestoreBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    manifest_digest: str = Field(pattern=r'^[a-f0-9]{64}$')
    confirmed: StrictBool = False


def call(function, *args):
    try:
        return function(*args)
    except store.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, 'Backup preview or restored profile file was not found.') from exc
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, 'Private backup storage is unavailable. Check free space and retry. Current data has not been replaced.') from exc


@router.get('/profile')
def profile():
    return call(store.profile_context)


@router.post('/exports/preview')
def export_preview(body: ExportBody):
    return call(store.create_export, body.options.model_dump(), body.browser_preferences)


@router.get('/exports/{token}/download')
def download(token: str, manifest_digest: str, confirmed: bool = False):
    path = call(store.download_export, token, manifest_digest, confirmed)
    return FileResponse(path, media_type='application/zip', filename='PRIVATE-line-dance-complete-backup.zip',
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.post('/imports/preview')
async def import_preview(file: UploadFile = File(...)):
    token = None
    try:
        token, folder = call(store.new_import)
        total = 0
        with (folder / 'backup.zip').open('xb') as stream:
            while True:
                chunk = await file.read(1024**2)
                if not chunk: break
                total += len(chunk)
                if total > store.MAX_ARCHIVE_BYTES: raise HTTPException(413, 'Private backups must be at most 2 GiB.')
                stream.write(chunk)
        return call(store.finish_import, token)
    except BaseException:
        if token:
            try: store.discard(token)
            except FileNotFoundError: pass
        raise
    finally:
        await file.close()


@router.post('/imports/{token}/restore')
def restore(token: str, body: RestoreBody):
    return call(store.restore, token, body.manifest_digest, body.confirmed)


@router.delete('/previews/{token}')
def discard(token: str):
    call(store.discard, token)
    return {'discarded': True}


@router.get('/restored/{profile_id}/launcher')
def launcher(profile_id: str):
    return FileResponse(call(store.restored_file, profile_id, 'Open restored Line Dance Creator.cmd'),
                        filename='Open restored Line Dance Creator.cmd', media_type='application/octet-stream',
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})


@router.get('/restored/{profile_id}/report')
def report(profile_id: str):
    return FileResponse(call(store.restored_file, profile_id, 'restore-report.json'),
                        filename='private-restore-report.json', media_type='application/json',
                        headers={'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

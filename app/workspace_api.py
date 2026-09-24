"""S01 draft/history router; mount on the existing FastAPI application.

All mutations require expected_revision. Draft fields are extensible: omitted
fields survive older clients, while a supplied field replaces that whole field.
Song metadata merges while media identity remains owned by upload/relink APIs.
Draft save and history restore never replace the accepted dance.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from engine import project as store

router = APIRouter()


class RevisionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)


class DraftBody(RevisionBody):
    draft: dict


class VersionBody(RevisionBody):
    label: str = Field(min_length=1, max_length=120)


def _call(function, *args):
    try:
        return function(*args)
    except store.RevisionConflict as exc:
        raise HTTPException(409, detail={'code': 'REVISION_CONFLICT', 'message': str(exc),
                                        'current_revision': exc.current_revision}) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, detail='Project or saved version was not found') from exc
    except store.UnsupportedSchema as exc:
        raise HTTPException(409, detail={'code': 'UNSUPPORTED_SCHEMA', 'message': str(exc)}) from exc
    except store.ProjectCorrupt as exc:
        raise HTTPException(409, detail={'code': 'RECOVERY_REQUIRED', 'message': str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, detail='The project could not be saved or read. Your last successful save is retained; check storage and try again.') from exc


@router.get('/api/projects/{pid}/workspace')
def workspace(pid: str):
    return _call(store.get_workspace, pid)


@router.put('/api/projects/{pid}/workspace')
def save_workspace(pid: str, body: DraftBody):
    return _call(store.save_workspace, pid, body.draft, body.expected_revision)


@router.get('/api/projects/{pid}/versions')
def versions(pid: str):
    return _call(store.list_versions, pid)


@router.post('/api/projects/{pid}/versions')
def create_version(pid: str, body: VersionBody):
    return _call(store.create_version, pid, body.label, body.expected_revision)


@router.get('/api/projects/{pid}/versions/{version_id}')
def version_preview(pid: str, version_id: str):
    return _call(store.get_version, pid, version_id)


@router.post('/api/projects/{pid}/versions/{version_id}/restore')
def restore_version(pid: str, version_id: str, body: RevisionBody):
    return _call(store.restore_version, pid, version_id, body.expected_revision)

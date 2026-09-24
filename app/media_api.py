"""Explicit local review of a recording and its saved music map."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, Field
from engine import project_media

router = APIRouter(prefix='/api/creator/projects')


class ReviewBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    confirmed: StrictBool = False


@router.get('/{pid}/recording/status')
def status(pid: str):
    try:
        project = project_media.store.load_project(pid)
        needed = project_media.recording_review_needed(project)
        path = (project.get('song') or {}).get('path')
        has_audio = bool(path and Path(path).is_file())
        marker = project.get('recording_review') or {}
        state = 'REVIEW_REQUIRED' if needed else 'REVIEWED' if marker.get('status') == 'REVIEWED' else 'NOT_REVIEWED' if has_audio else 'NO_RECORDING'
        return {'review_needed': needed, 'status': state, 'has_audio': has_audio}
    except FileNotFoundError as exc:
        raise HTTPException(404, 'Project not found.') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, 'The recording or project could not be read. Check storage and try again.') from exc


@router.post('/{pid}/recording/review')
def review(pid: str, body: ReviewBody):
    try:
        return project_media.review_recording(pid, body.expected_revision, body.confirmed)
    except project_media.store.RevisionConflict:
        raise  # the app's global conflict handler supplies the current revision
    except FileNotFoundError as exc:
        raise HTTPException(404, 'Project or recording not found.') from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, 'The recording or project could not be read or saved. Check storage and try again.') from exc

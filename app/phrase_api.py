"""Local phrase endpoints. All choreography snapshots travel as frozen data."""
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt
from engine import phrase_store as store
from library_api import BoundedRoute

router = APIRouter(prefix='/api/creator/phrases', tags=['phrases'], route_class=BoundedRoute)


def _call(function, *args):
    try:
        return function(*args)
    except store.Conflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    except (OSError, sqlite3.Error) as exc:
        raise HTTPException(503, detail='Phrase storage is unavailable. Check local storage and try again.') from exc


class CreateBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=200)
    moves: list[dict] = Field(min_length=1, max_length=256)
    notes: str = Field(default='', max_length=3000)


class VersionBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: StrictInt = Field(ge=1)


class EditBody(VersionBody):
    fields: dict


class InsertBody(VersionBody):
    mirrored: StrictBool = False


@router.get('')
def phrases(include_archived: bool = False):
    return _call(store.list_phrases, include_archived)


@router.post('', status_code=201)
def create(body: CreateBody):
    return _call(store.create, body.name, body.moves, body.notes)


@router.get('/{phrase_id}')
def get(phrase_id: str, version: int | None = None):
    return _call(store.get, phrase_id, version)


@router.patch('/{phrase_id}')
def edit(phrase_id: str, body: EditBody):
    return _call(store.update, phrase_id, body.expected_version, body.fields)


@router.post('/{phrase_id}/insertion')
def insertion(phrase_id: str, body: InsertBody):
    return _call(store.insertion, phrase_id, body.expected_version, body.mirrored)

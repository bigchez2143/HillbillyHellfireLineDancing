"""Local instructor tools; no hosted publishing or external requests."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError
from engine import instructor_tools as store

router = APIRouter(prefix='/api/creator/tools')


class SaveBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    state: dict


class ImportBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_revision: StrictInt = Field(ge=0)
    ics: str = Field(max_length=5_000_000)
    apply: bool = False
    preview_token: str = ''


def call(function, *args):
    try:
        return function(*args)
    except store.Conflict as error:
        raise HTTPException(409, detail={'code':'REVISION_CONFLICT','current_revision':error.revision,'message':str(error)}) from error
    except store.Corrupt as error:
        raise HTTPException(409, detail={'code':'RECOVERY_REQUIRED','message':str(error)}) from error
    except FileNotFoundError as error:
        raise HTTPException(404, detail=str(error)) from error
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, detail=str(error)) from error
    except OSError as error:
        raise HTTPException(503, detail='Local instructor storage could not be read or saved. The last successful save is retained.') from error


@router.get('')
def state():
    return call(store.get_state)


@router.put('')
def save(body: SaveBody):
    return call(store.save_state, body.state, body.expected_revision)


@router.get('/setlists/{setlist_id}/guide.html', response_class=HTMLResponse)
def guide_html(setlist_id: str, include_private: bool = False):
    return call(store.class_guide, setlist_id, include_private, True)


@router.get('/setlists/{setlist_id}/guide.txt', response_class=PlainTextResponse)
def guide_txt(setlist_id: str, include_private: bool = False):
    return call(store.class_guide, setlist_id, include_private, False)


@router.get('/events.ics')
def events(include_private: bool = False):
    return Response(call(store.export_ics, include_private), media_type='text/calendar',
                    headers={'Content-Disposition':'attachment; filename="line-dance-events.ics"'})


@router.post('/events/import')
def import_events(body: ImportBody):
    return call(store.import_ics, body.ics, body.expected_revision, body.apply, body.preview_token)

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool
from engine import browser_preferences

router = APIRouter(prefix='/api/creator/move-browser')

class FavoriteBody(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str
    favorite: StrictBool

@router.get('/preferences')
def preferences():
    return browser_preferences.get_preferences()

@router.put('/favorites')
def favorite(body: FavoriteBody):
    try:
        return browser_preferences.set_favorite(body.key, body.favorite)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

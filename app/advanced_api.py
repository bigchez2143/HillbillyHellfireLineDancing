"""Advanced drawer routes. Personal keys stay on this computer.

Search reads BootStepper with the saved personal key. There is no write route,
and Spotify is reported as not enabled.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from engine import bootstepper, settings


router = APIRouter(prefix="/api/settings/advanced", tags=["advanced"])


class KeyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: str | None = None


class SearchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = Field(pattern=r"^(dances|songs|choreographers)$")
    query: str = Field(min_length=1, max_length=80)


@router.get("")
def advanced_status():
    return settings.public_advanced()


@router.put("/bootstepper")
def save_bootstepper_key(body: KeyBody):
    try:
        return settings.save_bootstepper_key(body.api_key)
    except settings.SettingsError as exc:
        raise HTTPException(400, str(exc)) from None


@router.delete("/bootstepper/key")
def forget_bootstepper_key():
    return settings.clear_bootstepper_key()


@router.post("/bootstepper/search")
def search_bootstepper(body: SearchBody):
    try:
        api_key = settings.load_bootstepper_key()
        return bootstepper.search(body.kind, body.query, api_key)
    except settings.SettingsError as exc:
        raise HTTPException(422, detail={"code": "KEY_REQUIRED", "message": str(exc)}) from None
    except bootstepper.BootStepperError as exc:
        status = 422 if exc.code in {"INVALID_SEARCH", "KEY_REQUIRED"} else 502
        raise HTTPException(status, detail={"code": exc.code, "message": str(exc)}) from None

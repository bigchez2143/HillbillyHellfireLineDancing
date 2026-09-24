"""Local community links. Websites only; no keys and no uploads."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.community_shelf import CommunityError, MAX_LINKS, load_shelf, reset_shelf, save_shelf
from engine.settings import SettingsError


router = APIRouter(prefix="/api/settings")


class CommunityLink(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = ""
    name: str = ""
    url: str = ""
    note: str = ""


class CommunityBody(BaseModel):
    model_config = ConfigDict(extra="ignore")
    links: list[CommunityLink] = Field(default_factory=list, max_length=MAX_LINKS)


def _call(function, *args):
    try:
        return function(*args)
    except (CommunityError, SettingsError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(400, "Check the link name and website, then try again.") from exc


@router.get("/community")
def community_links():
    return load_shelf()


@router.put("/community")
def replace_community_links(body: CommunityBody):
    return _call(save_shelf, [item.model_dump() for item in body.links])


@router.post("/community/reset")
def restore_starter_links():
    return _call(reset_shelf)

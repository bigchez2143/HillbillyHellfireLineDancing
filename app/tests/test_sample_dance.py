"""Starter Corn Maze sample and the Hillbilly Hellfire freeware line."""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import server
from engine import project as store
from engine.choreography import compile_choreography
from engine.publish_pack import build_publish_pack
from engine.sample_dance import (
    FREEWARE_LINE, SAMPLE_ID, SAMPLE_NAME, SITE_URL, _SEQUENCE,
    ensure_sample_project, sample_choreography, sample_document,
)
from engine.steps import MOVE_BY_ID


ROOT = Path(__file__).resolve().parents[2]
PAGES = (
    ROOT / "app" / "static" / "creator.html",
    ROOT / "app" / "static" / "index.html",
    ROOT / "app" / "static" / "repair.html",
)


@pytest.fixture
def projects(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    monkeypatch.setattr(store, "PROJECTS_DIR", str(root))
    return root


def test_sample_is_a_valid_beginner_dance_with_no_audio():
    document = sample_document()
    compiled = compile_choreography(sample_choreography())
    assert compiled["status"] == "VALID"
    assert compiled["valid"] is True
    assert compiled["total_counts"] == "32"
    assert document["name"] == SAMPLE_NAME
    assert document["song"]["path"] is None
    assert document["song"]["filename"] is None
    assert document["draft"]["sheet_meta"]["spotify_url"] == ""
    assert "published step sheet" in document["draft"]["sheet_meta"]["description"]
    move_ids = {move_id for move_id, _lead in _SEQUENCE}
    assert move_ids <= set(MOVE_BY_ID)
    assert "api_key" not in document
    blob = str(document).lower()
    assert ".mp3" not in blob and ".wav" not in blob and ".m4a" not in blob


def test_fresh_install_lists_the_sample_and_leaves_an_edited_copy_alone(projects):
    client = TestClient(server.app)
    listed = client.get("/api/projects")
    assert listed.status_code == 200
    body = listed.json()
    assert [item["id"] for item in body] == [SAMPLE_ID]
    assert body[0]["name"] == SAMPLE_NAME
    assert body[0]["sample"] is True
    assert body[0]["has_audio"] is False
    assert body[0]["has_draft"] is True
    saved = store.load_project(SAMPLE_ID)
    assert saved["song"]["path"] is None
    assert compile_choreography(saved["draft"]["choreography"])["status"] == "VALID"
    again = client.get("/api/projects").json()
    assert [item["id"] for item in again] == [SAMPLE_ID]
    saved["name"] = "Kept local edit"
    store.save_project(SAMPLE_ID, saved)
    ensure_sample_project()
    assert store.load_project(SAMPLE_ID)["name"] == "Kept local edit"
    assert client.get("/api/projects").json()[0]["name"] == "Kept local edit"


def test_an_existing_dance_is_not_replaced_or_joined_by_the_sample(projects):
    created = store.create_project("Evening practice")
    ensure_sample_project()
    listed = store.list_projects()
    assert [item["id"] for item in listed] == [created["id"]]
    assert not (projects / SAMPLE_ID).exists()


def test_sample_publish_pack_stays_local_and_keyless(projects, tmp_path):
    ensure_sample_project()
    project = store.load_project(SAMPLE_ID)
    pack = build_publish_pack(project, root=tmp_path)
    assert pack["files"][0]["label"] == "Step sheet"
    assert pack["files"][1]["label"] == "Portable draft"
    assert "api" not in pack["note"].lower()
    folder = Path(pack["folder"])
    blob = b"".join(path.read_bytes() for path in folder.iterdir() if path.is_file())
    assert b"api_key" not in blob
    assert b".mp3" not in blob.lower() and b".wav" not in blob.lower()
    text = (folder / "Read me.txt").read_text(encoding="utf-8")
    assert "Nothing was sent to a website" in text


def test_about_and_footers_show_the_freeware_line_and_site():
    creator = (ROOT / "app" / "static" / "creator.html").read_text(encoding="utf-8")
    about = creator.split('id="aboutCard"', 1)[1].split("</section>", 1)[0]
    footer = creator.split('<footer class="publisher">', 1)[1].split("</footer>", 1)[0]
    for page in PAGES:
        html = page.read_text(encoding="utf-8")
        assert FREEWARE_LINE in html
        assert SITE_URL in html
        assert 'href="https://hillbillyhellfire.com"' in html
    assert FREEWARE_LINE in about
    assert SITE_URL in about
    assert FREEWARE_LINE in footer
    assert "The Corn Maze Dance is included as a starter." in creator
    script = (ROOT / "app" / "static" / "creator.js").read_text(encoding="utf-8")
    assert "STARTER SAMPLE" in script

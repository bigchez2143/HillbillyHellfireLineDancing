"""Publish pack writes a local PDF and portable draft, then names the websites to open."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pypdf import PdfReader

from engine.creator_exports import read_project_package
from engine.publish_pack import (DESTINATIONS, PublishError, build_publish_pack, reveal_folder)
from export_api import router
import export_api


def fixture_project():
    def movement(identifier, duration, before, after, rotation="0"):
        return {"id": identifier, "name": identifier, "duration_counts": duration,
                "events": [{"id": "action", "duration_counts": duration, "text": identifier + ": step with care.",
                            "support_before": before, "support_after": after, "rotation_deg": rotation}]}
    return {"id": "existing", "name": "Evening Practice", "document_revision": 7,
            "song": {"title": "Synthetic Practice Track", "artist": "Example Musicians", "path": r"C:\Private\unreleased.wav"},
            "api_key": "DO-NOT-EXPORT-TOP-SECRET",
            "draft": {"choreography": {"schema_version": 1,
                        "parts": [{"id": "A", "name": "Basic part", "moves": [movement("Right step", "1", "L", "R"), movement("Left step", "1", "R", "L")]}]},
                      "music_map": {"bpm": 120, "first_count": 2, "meter": 4},
                      "sheet_meta": {"dance_title": "Evening Practice", "choreographer": "Alex Example", "level_label": "Beginner",
                                     "description": "Read carefully.", "youtube_url": "https://example.org/demo",
                                     "api_key": "DO-NOT-EXPORT-META-SECRET"},
                      "lyrics_raw": "PRIVATE LYRICS OMITTED"}}


def _pack(tmp_path, **changes):
    project = fixture_project()
    project.update(changes)
    return project, build_publish_pack(project, root=tmp_path)


def test_pack_contains_pdf_and_portable_draft_without_private_material(tmp_path):
    project, pack = _pack(tmp_path)
    folder = tmp_path / "Evening Practice"
    pdf_path = folder / "Evening Practice - step sheet.pdf"
    draft_path = folder / "Evening Practice - portable draft.zip"
    assert pack["folder"] == str(folder)
    assert pdf_path.is_file() and draft_path.is_file()
    assert [item["role"] for item in pack["files"]] == ["pdf", "portable"]
    pdf = PdfReader(str(pdf_path))
    text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    assert "Evening Practice" in text and "Alex Example" in text
    document = read_project_package(draft_path.read_bytes(), draft_path.name)
    assert document["name"] == "Evening Practice"
    blob = pdf_path.read_bytes() + draft_path.read_bytes() + (folder / "Read me.txt").read_bytes()
    for secret in (b"DO-NOT-EXPORT", b"PRIVATE LYRICS", b"unreleased.wav", b"foot-demo.mp4"):
        assert secret not in blob
    assert "Nothing was sent to a website" in pack["note"]
    assert "api" not in pack["note"].lower()
    assert [(item["name"], item["url"]) for item in pack["destinations"]] == [(item["name"], item["url"]) for item in DESTINATIONS]
    assert pack["destinations"][0]["url"] == "https://bootstepper.com/dances/create"
    assert pack["destinations"][1]["url"] == "https://www.copperknob.co.uk/contactus"
    assert pack["destinations"][2]["url"] == "https://www.linedance.com/submit"
    assert (folder / ".pack").read_text(encoding="utf-8").strip() == project["id"]


def test_republish_reuses_the_folder_and_a_second_dance_gets_its_own(tmp_path):
    project, first = _pack(tmp_path)
    second = build_publish_pack(project, root=tmp_path)
    assert second["folder"] == first["folder"]
    assert len(list((tmp_path / "Evening Practice").glob("*.pdf"))) == 1
    other = fixture_project()
    other["id"] = "another-dance"
    other["draft"]["sheet_meta"]["dance_title"] = "Evening Practice"
    again = build_publish_pack(other, root=tmp_path)
    assert again["folder"] != first["folder"]
    assert again["folder"].endswith("Evening Practice (2)")
    assert (tmp_path / "Evening Practice" / ".pack").read_text(encoding="utf-8").strip() == project["id"]


def test_reveal_opens_only_the_pack_folder(tmp_path):
    project, pack = _pack(tmp_path)
    opened = []
    assert reveal_folder(project["id"], pack["folder"], root=tmp_path, opener=opened.append)["opened"] is True
    assert opened == [tmp_path / "Evening Practice"]
    outside = tmp_path.parent / "elsewhere"
    outside.mkdir()
    (outside / ".pack").write_text(project["id"], encoding="utf-8")
    other = tmp_path / "other-dance"
    other.mkdir()
    (other / ".pack").write_text("someone-else", encoding="utf-8")
    for folder in (outside, other, tmp_path):
        with pytest.raises(PublishError):
            reveal_folder(project["id"], str(folder), root=tmp_path, opener=opened.append)
    assert opened == [tmp_path / "Evening Practice"]


def test_publish_routes_build_and_open_without_uploading(tmp_path, monkeypatch):
    project = fixture_project()
    def load_project(pid):
        if pid != project["id"]:
            raise FileNotFoundError(pid)
        return project
    monkeypatch.setattr(export_api.store, "load_project", load_project)
    monkeypatch.setattr("engine.publish_pack.publish_root", lambda: tmp_path)
    opened = []
    monkeypatch.setattr("engine.publish_pack._open_in_file_manager", opened.append)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    created = client.post("/api/creator/projects/existing/publish-pack", json={"paper": "letter", "api_key": "DO-NOT-KEEP"})
    assert created.status_code == 200
    body = created.json()
    assert body["files"][0]["label"] == "Step sheet"
    assert body["files"][1]["label"] == "Portable draft"
    assert "DO-NOT-KEEP" not in created.text
    shown = client.post("/api/creator/projects/existing/publish-pack/open", json={"folder": body["folder"]})
    assert shown.status_code == 200
    assert opened and str(opened[0]) == body["folder"]
    refused = client.post("/api/creator/projects/existing/publish-pack/open", json={"folder": str(tmp_path.parent)})
    assert refused.status_code == 400
    missing = client.post("/api/creator/projects/missing/publish-pack", json={})
    assert missing.status_code == 404

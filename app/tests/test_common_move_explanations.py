"""Guard the independent explanation overlay's identity and review boundaries."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_explanations_cover_every_existing_identity_in_order():
    catalog = read_data("step-database.json")["steps"]
    entries = read_data("common-move-explanations.json")["entries"]
    assert len(catalog) == len(entries)
    assert len(catalog) >= 173
    assert [(e["index"], e["name"]) for e in entries] == [
        (index, move["name"]) for index, move in enumerate(catalog)
    ]
    assert [e["category"] for e in entries] == [move["category"] for move in catalog]


def test_every_explanation_has_text_and_explicit_draft_authorship():
    overlay = read_data("common-move-explanations.json")
    assert overlay["review_status"] == "draft_needs_instructor_review"
    for entry in overlay["entries"]:
        assert isinstance(entry["explanation"], str)
        assert len(entry["explanation"].strip()) >= 20
        assert entry["review_status"] == "draft_needs_instructor_review"
        assert "New explanation draft" in entry["authorship_note"]
        assert "not a copyright certification" in entry["authorship_note"]
        assert isinstance(entry["review_notes"], list)


def test_explanation_overlay_cannot_override_structural_mechanics():
    allowed = {"index", "name", "category", "explanation", "review_status", "authorship_note", "review_notes"}
    for entry in read_data("common-move-explanations.json")["entries"]:
        assert set(entry) == allowed

"""The class one-pager is a one-page PDF built from markdown in release/."""
import importlib.util
from io import BytesIO
from pathlib import Path
import re

import pytest
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
PHRASES = (
    "Freeware from Hillbilly Hellfire",
    "Launch Line Dance Creator",
    "app\\run.bat",
    "The Corn Maze Dance",
    "starter sample",
    "Start without music",
    "Create dance",
    "Create / Edit",
    "a plus",
    "Preview",
    "Saved locally",
    "Practice",
    "Count-in",
    "None",
    "Play",
    "Pause",
    "metronome",
    "Song card",
    "Spotify",
    "Local audio file",
    "Export",
    "PDF sheet",
    "Dance title",
    "Publish",
    "step sheet",
    "portable draft",
    "BootStepper",
    "CopperKnob",
    "LineDance.com",
    "Copy folder",
    "Show folder",
    "does not ask for a key",
    "Line Dance Tools",
    "Community",
    "Restore starter links",
    "hillbillyhellfire.com",
    "Workspace view on Basic",
)


def _load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _text(payload):
    if isinstance(payload, Path):
        payload = payload.read_bytes()
    pages = PdfReader(BytesIO(payload)).pages
    return re.sub(r"\s+", " ", "\n".join(page.extract_text() or "" for page in pages)).strip()


@pytest.fixture(scope="module")
def guide():
    return _load("render_instructor_one_pager")


def test_source_and_pdf_ship_in_release(guide):
    assert guide.source_path() == ROOT / "release" / "instructor-one-pager.md"
    assert guide.pdf_path() == ROOT / "release" / "Instructor one-pager.pdf"
    assert guide.source_path().is_file()
    payload = guide.pdf_path().read_bytes()
    assert payload.startswith(b"%PDF")
    reader = PdfReader(guide.pdf_path().open("rb"))
    assert len(reader.pages) == 1
    text = _text(payload)
    for phrase in PHRASES:
        assert phrase in text
    assert "personal key" not in text.lower()
    assert "api key" not in text.lower()


def test_committed_pdf_matches_the_markdown_source(guide):
    fresh = guide.render_pdf(guide.source_path().read_text(encoding="utf-8"))
    assert _text(fresh) == _text(guide.pdf_path())
    assert len(PdfReader(__import__("io").BytesIO(fresh)).pages) == 1


def test_a_guide_that_spills_past_one_page_is_refused(guide):
    extra = "\n\n## Extra\n\n" + ("This line is only for the length check. " * 120)
    with pytest.raises(RuntimeError, match="one page"):
        guide.render_pdf(guide.source_path().read_text(encoding="utf-8") + extra)


def test_portable_folder_gets_the_pdf_at_the_top(tmp_path, guide):
    copied = guide.copy_into_portable(tmp_path)
    assert copied == tmp_path / "Instructor one-pager.pdf"
    assert copied.read_bytes().startswith(b"%PDF")
    builder = _load("build_portable")
    placed = builder.copy_instructor_guide(tmp_path / "portable")
    assert placed.name == "Instructor one-pager.pdf"
    assert placed.parent == tmp_path / "portable"
    assert "copy_instructor_guide(destination)" in (ROOT / "scripts" / "build_portable.py").read_text(encoding="utf-8")
    status = (ROOT / "scripts" / "build_portable.py").read_text(encoding="utf-8")
    assert "Instructor one-pager.pdf" in status


def test_source_manifest_includes_the_guide_and_not_a_random_file():
    manifest = _load("source_release_manifest").manifest()
    paths = {item["path"] for item in manifest["candidates"]}
    assert "release/instructor-one-pager.md" in paths
    assert "release/Instructor one-pager.pdf" in paths
    assert "release/not-a-guide.txt" not in paths

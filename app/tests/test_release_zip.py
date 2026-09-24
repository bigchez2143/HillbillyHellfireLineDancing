"""Operative freeware LICENSE and the Linux-built Windows portable zip."""
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ZIP_ROOT = "HillbillyHellfire-LineDanceCreator"


def _load(name):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hh_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_license_is_operative_freeware_and_named_in_the_readme():
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Lee Burnette" in text
    assert "Hillbilly Hellfire" in text
    assert "Version 1.0" in text
    assert "paid classes" in text
    assert "You may not sell" in text
    assert "original choreography" in text
    assert "Third-party software" in text
    assert "as is" in text
    assert "bring your own credentials" in text
    assert "not an Open Source Initiative (OSI) open source license" in text
    lowered = text.lower()
    assert "draft" not in lowered
    assert "not adopted" not in lowered
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "[LICENSE](LICENSE)" in readme
    assert "confirm that rights-holder line before a public release" in readme
    assert "build_release_zip.py" in readme
    assert "No account is required" in readme
    assert "not an OSI open source license" in readme
    historical = (ROOT / "LICENSE-DRAFT.md").read_text(encoding="utf-8")
    assert historical.startswith("# Historical draft — not the license")
    assert "Superseded" in historical.split("---", 1)[0]


def test_download_page_draft_covers_the_public_path():
    page = (ROOT / "docs" / "download-page-draft.md").read_text(encoding="utf-8")
    assert "## What it is" in page
    assert "## Download" in page
    assert "## No account required" in page
    assert "zero-cost" in page
    assert "bring your own" in page.lower()
    assert "Launch Line Dance Creator.bat" in page
    assert "run.bat" in page
    assert "no Setup.exe" in page
    assert "Wendy" in page
    assert "Lee Burnette" in page
    notes = (ROOT / "docs" / "windows-portable-zip.md").read_text(encoding="utf-8")
    assert "python scripts/build_release_zip.py" in notes
    assert "build_portable.py --output build\\portable-candidate --zip" in notes
    assert "no desktop icon" in notes.lower()


def test_release_zip_contains_the_portable_layout(tmp_path):
    builder = _load("build_release_zip")
    folder = tmp_path / "portable"
    archive = tmp_path / "LineDanceCreator-windows.zip"
    builder.assemble(folder)
    path, digest = builder.make_zip(folder, archive)
    assert path.is_file()
    assert len(digest) == 64
    with zipfile.ZipFile(path) as packed:
        names = set(packed.namelist())
    prefix = ZIP_ROOT + "/"
    expected = {
        "LICENSE",
        "START-HERE.txt",
        "RELEASE-NOTES.md",
        "Launch Line Dance Creator.bat",
        "run.bat",
        "app/run.bat",
        "app/server.py",
        "Instructor one-pager.pdf",
        "sample/the-corn-maze-dance/steps.txt",
        "sample/the-corn-maze-dance/sample-dance.json",
        "requirements/core-win-py312.lock.txt",
        "SHA256SUMS.txt",
        "PRIVACY.md",
    }
    for name in expected:
        assert prefix + name in names
    joined = "\n".join(names).lower()
    assert "license-draft.md" not in joined
    assert "setup.exe" not in joined
    assert ".lnk" not in joined
    assert ".msi" not in joined
    assert not any(name.lower().endswith(".exe") for name in names)
    with zipfile.ZipFile(path) as packed:
        start = packed.read(prefix + "START-HERE.txt").decode("utf-8")
        launch = packed.read(prefix + "Launch Line Dance Creator.bat").decode("ascii")
        steps = packed.read(prefix + "sample/the-corn-maze-dance/steps.txt").decode("utf-8")
        sample = json.loads(packed.read(prefix + "sample/the-corn-maze-dance/sample-dance.json"))
        pdf = packed.read(prefix + "Instructor one-pager.pdf")
        license_text = packed.read(prefix + "LICENSE").decode("utf-8")
    assert "No account is required" in start
    assert "Bring your own credentials" in start
    assert "Launch Line Dance Creator.bat" in start
    assert "no desktop icon" in start.lower()
    assert "runtime\\python.exe" in launch
    assert "app\\run.bat" in launch
    assert "The Corn Maze Dance" in steps
    assert "Total counts: 32" in steps
    assert sample["id"] == "the-corn-maze-dance"
    assert sample["song"]["path"] is None
    assert "Lee Burnette" in license_text
    assert pdf.startswith(b"%PDF")
    with pytest.raises(RuntimeError, match="existing files are never deleted"):
        builder.assemble(folder)


def test_windows_builder_uses_the_same_shared_files_and_manifest_lists_them():
    source = (ROOT / "scripts" / "build_portable.py").read_text(encoding="utf-8")
    assert "add_shared_files(destination)" in source
    assert "copy_instructor_guide(destination)" in source
    assert "There is no Setup installer and no desktop icon." in source
    manifest = _load("source_release_manifest").manifest()
    paths = {item["path"] for item in manifest["candidates"]}
    assert manifest["final_license_present"] is True
    assert manifest["ready_to_publish"] is False
    for path in (
        "LICENSE",
        "release/START-HERE.txt",
        "release/RELEASE-NOTES.md",
        "docs/download-page-draft.md",
        "docs/windows-portable-zip.md",
        "scripts/build_release_zip.py",
        "scripts/release_bundle.py",
    ):
        assert path in paths

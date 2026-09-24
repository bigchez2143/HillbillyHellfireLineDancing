"""Shared files for the Windows portable folder and the Linux-built release zip.

No downloads, no account access, and no installer. Launchers are batch files.
A desktop shortcut is never written.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIP_ROOT_NAME = "HillbillyHellfire-LineDanceCreator"

# Repo path, path inside the portable folder.
SHARED_COPIES = (
    ("release/START-HERE.txt", "START-HERE.txt"),
    ("release/RELEASE-NOTES.md", "RELEASE-NOTES.md"),
    ("THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
    ("requirements/core.txt", "requirements/core.txt"),
    ("requirements/core-win-py312.lock.txt", "requirements/core-win-py312.lock.txt"),
    ("app/run.bat", "app/run.bat"),
    ("release/Instructor one-pager.pdf", "Instructor one-pager.pdf"),
)

LAUNCH_BAT = (
    "@echo off\r\n"
    "cd /d \"%~dp0\"\r\n"
    "if exist \"%~dp0runtime\\python.exe\" (\r\n"
    "  \"%~dp0runtime\\python.exe\" -I -B \"%~dp0launch.py\"\r\n"
    "  if errorlevel 1 pause\r\n"
    "  exit /b\r\n"
    ")\r\n"
    "call \"%~dp0app\\run.bat\" %*\r\n"
)

RUN_BAT = (
    "@echo off\r\n"
    "cd /d \"%~dp0\"\r\n"
    "call \"%~dp0Launch Line Dance Creator.bat\" %*\r\n"
)

BANNED_NAMES = {"setup.exe", "setup.msi"}
BANNED_SUFFIXES = {".lnk", ".msi"}


def _copy_from_repo(relative: str, destination: Path):
    source = (ROOT / relative).resolve()
    root = ROOT.resolve()
    if not source.is_file() or not source.is_relative_to(root):
        raise RuntimeError(f"Required release file is missing: {relative}")
    data = source.read_bytes()
    if source.suffix.lower() == ".pdf" and not data.startswith(b"%PDF"):
        raise RuntimeError(f"{relative} is not a PDF.")
    target = destination / destination_name(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def destination_name(relative: str) -> str:
    for source, placed in SHARED_COPIES:
        if source == relative:
            return placed
    raise RuntimeError(f"No portable path for {relative}")


def write_sample(destination: Path):
    """Readable Corn Maze copy. The app still seeds its own project on first open."""
    app = str(ROOT / "app")
    inserted = app not in sys.path
    if inserted:
        sys.path.insert(0, app)
    try:
        from engine.sample_dance import (
            SAMPLE_ID, SAMPLE_NAME, SAMPLE_NOTE, compiled_sample, sample_document, sample_moves,
        )
        compiled = compiled_sample()
    finally:
        if inserted and app in sys.path:
            sys.path.remove(app)
    if compiled.get("status") != "VALID" or compiled.get("total_counts") != "32":
        raise RuntimeError("Corn Maze sample did not compile to 32 valid counts.")
    folder = destination / "sample" / SAMPLE_ID
    folder.mkdir(parents=True, exist_ok=True)
    document = sample_document()
    document["created"] = 0
    document["portable_copy"] = True
    blob = json.dumps(document, indent=2) + "\n"
    lowered = blob.lower()
    if ".mp3" in lowered or ".wav" in lowered or ".m4a" in lowered:
        raise RuntimeError("Sample dance materials must not name an audio file.")
    (folder / "sample-dance.json").write_text(blob, encoding="utf-8")
    lines = [
        SAMPLE_NAME,
        "",
        SAMPLE_NOTE,
        "",
        "No song file is included. 112 BPM is a practice tempo, not a measured song.",
        "This is a readable copy. The app also adds this dance when My Dances is empty.",
        "",
        "Counts  Move",
    ]
    count = 1
    for move in sample_moves():
        span = int(move["counts"])
        end = count + span - 1
        label = str(count) if span == 1 else f"{count}-{end}"
        lines.append(f"{label:>6}  {move['name']}")
        count = end + 1
    lines.append("")
    lines.append(f"Total counts: {count - 1}")
    (folder / "steps.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return folder


def write_launchers(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    launch = destination / "Launch Line Dance Creator.bat"
    launch.write_bytes(LAUNCH_BAT.encode("ascii"))
    run = destination / "run.bat"
    run.write_bytes(RUN_BAT.encode("ascii"))
    return launch, run


def add_shared_files(destination: Path):
    """Copy launchers, the class PDF, the sample dance, and the dancer notes."""
    destination = Path(destination)
    if not (ROOT / "LICENSE").is_file():
        raise RuntimeError("Adopted LICENSE is missing.")
    for relative, _placed in SHARED_COPIES:
        _copy_from_repo(relative, destination)
    write_launchers(destination)
    write_sample(destination)
    return destination


def layout_problems(destination: Path):
    """Installer and desktop-shortcut names do not belong in this folder."""
    found = []
    for path in destination.rglob("*"):
        if not path.is_file():
            continue
        if path.name.lower() in BANNED_NAMES or path.suffix.lower() in BANNED_SUFFIXES:
            found.append(path.relative_to(destination).as_posix())
    return sorted(found)


def write_checksums(destination: Path):
    lines = []
    for path in sorted(destination.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt" and "__pycache__" not in path.parts:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path.relative_to(destination).as_posix()}")
    (destination / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

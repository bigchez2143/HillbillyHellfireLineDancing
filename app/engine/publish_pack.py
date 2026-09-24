"""One local publish pack: a step-sheet PDF plus a portable draft.

The pack is written on this computer. Destination buttons only open the
site's own page. This module does not upload a dance or store a site login.
"""
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from .community_shelf import (BOOTSTEPPER_CREATE_URL, COPPERKNOB_SUBMIT_URL, LINEDANCE_SUBMIT_URL)
from .creator_exports import ExportError, export_project
from .paths import runtime_path
from . import settings


class PublishError(ValueError):
    pass


_RESERVED = re.compile(r"^(con|prn|aux|nul|com[1-9]|lpt[1-9])$", re.IGNORECASE)
PUBLISH_NOTE = (
    "Your step sheet and portable draft are in a folder on this computer. "
    "Nothing was sent to a website. Open a site when you want to add the dance yourself, then upload the step sheet."
)
DESTINATIONS = (
    {"id": "bootstepper", "name": "BootStepper", "detail": "Opens their add-a-dance page. You upload the step sheet there yourself.", "url": BOOTSTEPPER_CREATE_URL},
    {"id": "copperknob", "name": "CopperKnob", "detail": "Opens their contact page. You attach the step sheet there yourself.", "url": COPPERKNOB_SUBMIT_URL},
    {"id": "linedance", "name": "LineDance.com", "detail": "Opens Submit a Dance. Sign in there if they ask, then upload the step sheet.", "url": LINEDANCE_SUBMIT_URL},
)


def publish_root():
    legacy = os.path.join(os.path.dirname(settings.APP_DIR), "exports", "publish-packs")
    return Path(runtime_path("publish-packs", legacy))


def _title(project):
    draft = project.get("draft") if isinstance(project, dict) else None
    meta = draft.get("sheet_meta") if isinstance(draft, dict) else None
    title = ""
    if isinstance(meta, dict) and isinstance(meta.get("dance_title"), str):
        title = meta["dance_title"]
    if not title and isinstance(project, dict) and isinstance(project.get("name"), str):
        title = project["name"]
    title = re.sub(r"[\x00-\x1f]", " ", title).strip()
    return title or "Dance"


def _stem(title):
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", title).strip(" .")
    cleaned = re.sub(r"\s+", " ", cleaned)[:60].strip(" .") or "Dance"
    if _RESERVED.match(cleaned):
        cleaned = cleaned + " dance"
    return cleaned


def _marker_matches(folder, project_id):
    marker = folder / ".pack"
    if not folder.is_dir() or not marker.is_file():
        return False
    try:
        return marker.read_text(encoding="utf-8").strip() == project_id
    except OSError:
        return False


def _assign_folder(root, project_id, stem):
    root.mkdir(parents=True, exist_ok=True)
    candidates = [root / stem] + [root / f"{stem} ({number})" for number in range(2, 100)]
    for folder in candidates:
        if _marker_matches(folder, project_id) or not folder.exists():
            return folder
    raise PublishError("Too many folders already use this dance name. Rename the dance and publish again.")


def _write_bytes(path, payload):
    fd, temporary = tempfile.mkstemp(prefix=".pack-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _write_text(path, text):
    _write_bytes(path, text.encode("utf-8"))


def _owned_folder(project_id, folder, root):
    if not isinstance(folder, str) or not folder.strip():
        raise PublishError("Publish the dance first, then open its folder.")
    root = Path(root).resolve()
    try:
        path = Path(folder).resolve()
    except OSError as exc:
        raise PublishError("That folder could not be opened. Publish the dance again.") from exc
    if path.parent != root or not _marker_matches(path, project_id):
        raise PublishError("That folder is not the publish pack for this dance. Publish again to make a new one.")
    return path


def build_publish_pack(project, paper="letter", large_print=False, print_qr=False, include_lyrics=False, root=None):
    if not isinstance(project, dict) or not isinstance(project.get("id"), str):
        raise PublishError("Open a dance before publishing.")
    project_id = project["id"]
    try:
        pdf, _, _ = export_project(project, "pdf", paper, large_print, print_qr, include_lyrics)
        package, _, _ = export_project(project, "zip", paper, large_print, print_qr, include_lyrics)
    except ExportError:
        raise
    if not pdf.startswith(b"%PDF") or not package.startswith(b"PK"):
        raise PublishError("The step sheet or portable draft could not be prepared. Try again.")
    stem = _stem(_title(project))
    folder = _assign_folder(Path(root) if root is not None else publish_root(), project_id, stem)
    folder.mkdir(parents=True, exist_ok=True)
    _write_text(folder / ".pack", project_id + "\n")
    for child in folder.iterdir():
        if child.is_file() and child.suffix.lower() in {".pdf", ".zip"}:
            child.unlink()
    pdf_name = stem + " - step sheet.pdf"
    package_name = stem + " - portable draft.zip"
    _write_bytes(folder / pdf_name, pdf)
    _write_bytes(folder / package_name, package)
    readme = (
        _title(project) + "\n\n"
        "This folder has the files made by Publish:\n"
        "- " + pdf_name + " — the printable step sheet. Upload this file on a website.\n"
        "- " + package_name + " — a portable draft you can open in Line Dance Creator on another computer.\n\n"
        "Nothing was sent to a website. Open BootStepper, CopperKnob, or LineDance.com from Publish, then upload the step sheet yourself.\n"
    )
    _write_text(folder / "Read me.txt", readme)
    return {
        "folder": str(folder),
        "note": PUBLISH_NOTE,
        "files": [
            {"role": "pdf", "name": pdf_name, "label": "Step sheet"},
            {"role": "portable", "name": package_name, "label": "Portable draft"},
        ],
        "destinations": [dict(item) for item in DESTINATIONS],
        "copy_label": "Copy folder",
    }


def reveal_folder(project_id, folder, root=None, opener=None):
    path = _owned_folder(project_id, folder, Path(root) if root is not None else publish_root())
    if opener is None:
        opener = _open_in_file_manager
    try:
        opener(path)
    except OSError as exc:
        raise PublishError("This computer could not show the folder. Copy the folder path instead.") from exc
    return {"opened": True, "folder": str(path)}


def _open_in_file_manager(path):
    if os.name == "nt":
        os.startfile(path)  # noqa: S606 - local folder the user asked to see
        return
    command = ["open", str(path)] if sys.platform == "darwin" else ["xdg-open", str(path)]
    subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

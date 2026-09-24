"""Build the Windows portable zip that Linux CI can assemble.

The zip contains the application, Launch Line Dance Creator.bat, run.bat,
the instructor PDF, the Corn Maze sample, and LICENSE. It does not embed
Windows CPython. On Windows x64, scripts/build_portable.py --zip adds that
private runtime to the same launchers. No installer and no desktop icon.

Run from the repository with a Python that can import the packaging package
(the Windows builder already uses it).
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "build" / "HillbillyHellfire-LineDanceCreator"


def _load(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"hh_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assemble(destination: Path):
    destination = destination.resolve()
    if destination.exists():
        raise RuntimeError("Output must be a new directory; existing files are never deleted.")
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise RuntimeError("Output cannot contain the source tree.")
    if not (ROOT / "LICENSE").is_file():
        raise RuntimeError("Adopted LICENSE is missing.")
    portable = _load("build_portable")
    bundle = _load("release_bundle")
    destination.mkdir(parents=True)
    portable.copy_application(destination)
    portable.copy_instructor_guide(destination)
    bundle.add_shared_files(destination)
    problems = bundle.layout_problems(destination)
    if problems:
        raise RuntimeError("Release folder rejected: " + "; ".join(problems))
    bundle.write_checksums(destination)
    return destination


def make_zip(destination: Path, archive_path: Path):
    bundle = _load("release_bundle")
    archive_path = archive_path.resolve()
    if archive_path.exists():
        raise RuntimeError("Archive already exists; choose a new output path.")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as packed:
        for path in sorted(destination.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            inside = Path(bundle.ZIP_ROOT_NAME) / path.relative_to(destination)
            packed.write(path, inside.as_posix())
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    return archive_path, digest


def main(output: Path, archive_path: Path):
    folder = assemble(output)
    archive, digest = make_zip(folder, archive_path)
    print(json.dumps({
        "output": str(folder),
        "archive": str(archive),
        "sha256": digest,
        "installer": False,
        "desktop_icon": False,
        "windows_runtime_included": False,
    }))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="New folder for the unzipped portable layout")
    parser.add_argument("--zip", type=Path, default=None,
                        help="Zip path. Default: <output>-windows.zip beside the folder")
    args = parser.parse_args()
    archive = args.zip
    if archive is None:
        archive = args.output.parent / (args.output.name + "-windows.zip")
    main(args.output, archive)

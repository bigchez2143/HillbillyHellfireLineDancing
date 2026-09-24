"""Build an internal Windows portable candidate from an installed core environment.

Run with the tested .venv Python. No downloads or account access occur. This copies
a private CPython runtime, never a venv with a machine-specific pyvenv.cfg.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "requirements" / "core.txt"


def core_distributions():
    """Resolve installed runtime dependencies, respecting markers and extras."""
    queue = [Requirement(line.strip()) for line in CORE.read_text().splitlines()
             if line.strip() and not line.lstrip().startswith("#")]
    found, seen = {}, set()
    while queue:
        req = queue.pop()
        name = canonicalize_name(req.name)
        key = (name, tuple(sorted(req.extras)))
        dist = metadata.distribution(req.name)
        if req.specifier and not req.specifier.contains(dist.version, prereleases=True):
            raise RuntimeError(f"Installed {name}=={dist.version} does not satisfy {req}")
        found[name] = dist
        if key in seen:
            continue
        seen.add(key)
        for text in dist.requires or []:
            child = Requirement(text)
            if child.marker is None or any(child.marker.evaluate({"extra": extra})
                                           for extra in {"", *req.extras}):
                queue.append(child)
    return dict(sorted(found.items()))


def write_inventory(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    core = core_distributions()
    full = sorted((canonicalize_name(d.metadata["Name"]), d.version)
                  for d in metadata.distributions())
    (directory / "installed-development-environment.txt").write_text(
        "# Observed Windows x64, CPython " + platform.python_version() + "\n" +
        "\n".join(f"{name}=={version}" for name, version in full) + "\n", encoding="utf-8")
    (ROOT / "requirements" / "dev-win-py312.lock.txt").write_text(
        "# Installed development environment; Windows x64 / CPython " + platform.python_version() +
        "\n# Version snapshot, not a hashed wheel lock.\n" +
        "\n".join(f"{name}=={version}" for name, version in full) + "\n", encoding="utf-8")
    lock = ROOT / "requirements" / "core-win-py312.lock.txt"
    lock.write_text("# Installed core closure; Windows x64 / CPython " +
                    platform.python_version() + "\n# Version snapshot, not a hashed wheel lock.\n" +
                    "\n".join(f"{name}=={d.version}" for name, d in core.items()) + "\n",
                    encoding="utf-8")
    return core


def copy_inside(source: Path, destination: Path, allowed: Path):
    source = source.resolve()
    if not source.is_relative_to(allowed.resolve()):
        raise RuntimeError(f"Package file resolves outside its permitted source: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_runtime(destination: Path):
    base = Path(sys.base_prefix).resolve()
    if not (base / "python.exe").is_file() or not (base / "Lib" / "os.py").is_file():
        raise RuntimeError("A complete Windows CPython base runtime is required.")
    destination.mkdir()
    for item in base.iterdir():
        if item.is_file() and (item.name in {"python.exe", "pythonw.exe", "LICENSE.txt"}
                               or item.suffix.lower() == ".dll"):
            copy_inside(item, destination / item.name, base)
    for name in ("Lib", "DLLs", "tcl"):
        source_dir = base / name
        if not source_dir.exists():
            continue
        for item in source_dir.rglob("*"):
            rel = item.relative_to(base)
            if "site-packages" in rel.parts or "__pycache__" in rel.parts:
                continue
            if rel.parts[:2] == ("Lib", "test") or item.suffix == ".pyc":
                continue
            if item.is_file():
                copy_inside(item, destination / rel, base)


def copy_dependencies(core, destination: Path):
    site = Path(sysconfig.get_paths()["purelib"]).resolve()
    rows = []
    for name, dist in core.items():
        licences, copied = [], 0
        if not dist.files:
            raise RuntimeError(f"{name} has no installed file manifest; rebuild from a wheel.")
        for recorded in dist.files:
            item = Path(dist.locate_file(recorded)).resolve()
            # Wheel console entry points outside site-packages are not needed.
            if not item.is_relative_to(site):
                if "Scripts" in Path(str(recorded)).parts:
                    continue
                raise RuntimeError(f"Unexpected file outside site-packages for {name}: {recorded}")
            rel = item.relative_to(site)
            if item.suffix == ".pyc" or "__pycache__" in rel.parts:
                continue
            if not item.is_file():
                raise RuntimeError(f"Missing installed file for {name}: {recorded}")
            copy_inside(item, destination / rel, site)
            copied += 1
            if any("license" in part.lower() or "copying" in part.lower()
                   or "notice" in part.lower() for part in rel.parts):
                licences.append((Path("runtime/Lib/site-packages") / rel).as_posix())
        label = dist.metadata.get("License-Expression") or dist.metadata.get("License", "Unspecified")
        if len(label) > 180 or "\n" in label:
            label = "See retained distribution licence files and METADATA"
        rows.append({"name": name, "version": dist.version, "license_metadata": label,
                     "license_files": sorted(licences), "copied_file_count": copied})
    return rows


def copy_application(destination: Path):
    # Public source allowlist: no projects, keys, cached media, private research,
    # database sidecars, tests, or arbitrary top-level files enter the package.
    app = ROOT / "app"
    for item in [*sorted(app.glob("*.py")), *sorted((app / "engine").rglob("*.py"))]:
        copy_inside(item, destination / "app" / item.relative_to(app), app)
    for item in sorted((app / "static").rglob("*")):
        if item.is_file() and item.suffix.lower() in {
                ".html", ".js", ".css", ".svg", ".png", ".jpg", ".ico", ".woff2"}:
            copy_inside(item, destination / "app" / item.relative_to(app), app)
    for name in ("step-database.json", "step-database.seed.json", "common-move-explanations.json", "expanded-moves.json"):
        copy_inside(ROOT / "data" / name, destination / "data" / name, ROOT / "data")
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt", "PRIVACY.md"):
        if (ROOT / name).is_file():
            copy_inside(ROOT / name, destination / name, ROOT)


def copy_supplemental_notices(packages, destination: Path):
    """Retain notices omitted by wheels, recovered from matching official sdists."""
    source_dir = ROOT / "docs" / "steering" / "evidence" / "dependency-notices"
    source_manifest = source_dir / "provenance.json"
    if not source_manifest.exists():
        return
    by_name = {item["name"]: item for item in packages}
    included = []
    for notice in json.loads(source_manifest.read_text(encoding="utf-8")):
        package = by_name.get(canonicalize_name(notice["package"]))
        if not package or package["version"] != notice["version"]:
            continue
        name = notice["notice_file"]
        if Path(name).name != name:
            raise RuntimeError("Supplemental notice must have a plain filename.")
        source = source_dir / name
        if hashlib.sha256(source.read_bytes()).hexdigest() != notice["notice_sha256"]:
            raise RuntimeError(f"Supplemental notice hash mismatch: {name}")
        relative = Path("third-party-notices") / name
        copy_inside(source, destination / relative, source_dir)
        package["license_files"].append(relative.as_posix())
        included.append(notice)
    if included:
        (destination / "third-party-notices" / "provenance.json").write_text(
            json.dumps(included, indent=2) + "\n", encoding="utf-8")


BOOTSTRAP = '''from pathlib import Path
import os
import runpy
import sys
app = Path(__file__).resolve().parent / "app"
os.chdir(app)
if not os.environ.get("LINE_DANCE_DATA_DIR"):
    local = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    os.environ["LINE_DANCE_DATA_DIR"] = str(local / "HillbillyHellfire" / "LineDanceCreator")
data = Path(os.environ["LINE_DANCE_DATA_DIR"])
os.environ.setdefault("LINE_DANCE_LIBRARY_DIR", str(data / "library"))
os.environ.setdefault("LINE_DANCE_TOOLS_DIR", str(data / "tools"))
sys.path.insert(0, str(app))
runpy.run_path(str(app / "server.py"), run_name="__main__")
'''


def verify(destination: Path):
    # No server launch/browser opening, no network, no optional-model imports.
    code = """
import io, json, pathlib, sys
import fastapi, uvicorn, multipart, numpy, soundfile, librosa, pypdf, docx, openpyxl, icalendar, tzdata
from reportlab.pdfgen import canvas
audio = io.BytesIO()
soundfile.write(audio, numpy.zeros(4000), 8000, format='WAV')
audio.seek(0)
signal, rate = soundfile.read(audio)
assert len(signal) == 4000 and rate == 8000
assert librosa.feature.rms(y=signal).shape[0] == 1
pdf = io.BytesIO(); page = canvas.Canvas(pdf); page.drawString(20, 20, 'Portable check'); page.save()
assert len(pypdf.PdfReader(io.BytesIO(pdf.getvalue())).pages) == 1
document = docx.Document(); document.add_paragraph('Portable check'); document.save(io.BytesIO())
book = openpyxl.Workbook(); book.active['A1'] = 'Portable check'; book.save(io.BytesIO())
assert sys.prefix == sys.base_prefix
sys.path.insert(0, str(pathlib.Path.cwd() / 'app'))
import server
print(json.dumps({'python': sys.version.split()[0], 'prefix': sys.prefix,
                  'audio_frames': len(signal), 'pdf_pages': 1, 'word_xlsx': True,
                  'application_import_route_count': len(server.app.routes)}))
"""
    env = {key: value for key, value in os.environ.items()
           if key.upper() not in {"PATH", "PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}}
    env["PATH"] = str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
    with tempfile.TemporaryDirectory(prefix="portable-smoke-data-", dir=destination.parent) as scratch:
        scratch_root = Path(scratch).resolve()
        if not scratch_root.is_relative_to(destination.parent.resolve()):
            raise RuntimeError("Smoke storage must remain in the build directory.")
        env["LINE_DANCE_DATA_DIR"] = str(scratch_root)
        env["LINE_DANCE_PROJECTS_DIR"] = str(scratch_root / "projects")
        env["LINE_DANCE_LIBRARY_DIR"] = str(scratch_root / "library")
        env["LINE_DANCE_TOOLS_DIR"] = str(scratch_root / "tools")
        result = subprocess.run([str(destination / "runtime" / "python.exe"), "-I", "-B", "-c", code],
                                cwd=destination, env=env, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"Portable runtime smoke check failed:\n{result.stdout}\n{result.stderr}")
    return json.loads(result.stdout)


def build(destination: Path, archive: bool):
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12) or platform.machine() != "AMD64":
        raise RuntimeError("This candidate builder targets Windows x64 with CPython 3.12 only.")
    destination = destination.resolve()
    if destination.exists():
        raise RuntimeError("Output must be a new directory; existing files are never deleted.")
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise RuntimeError("Output cannot contain the source tree.")
    archive_path = destination.with_suffix(".zip")
    if archive and archive_path.exists():
        raise RuntimeError("Archive already exists; choose a new output path.")
    core = core_distributions()
    lock = ROOT / "requirements" / "core-win-py312.lock.txt"
    expected = {canonicalize_name(Requirement(x).name): str(Requirement(x).specifier)
                for x in lock.read_text().splitlines() if x and not x.startswith("#")}
    actual = {name: "==" + dist.version for name, dist in core.items()}
    if expected != actual:
        raise RuntimeError("Installed core differs from the reviewed lock. Resolve the locked environment first.")
    destination.mkdir(parents=True)
    copy_runtime(destination / "runtime")
    packages = copy_dependencies(core, destination / "runtime" / "Lib" / "site-packages")
    copy_supplemental_notices(packages, destination)
    copy_application(destination)
    (destination / "launch.py").write_text(BOOTSTRAP, encoding="utf-8")
    (destination / "Launch Line Dance Creator.bat").write_text(
        '@echo off\ncd /d "%~dp0"\n"%~dp0runtime\\python.exe" -I -B "%~dp0launch.py"\n'
        'if errorlevel 1 pause\n', encoding="utf-8")
    (destination / "RELEASE-STATUS.txt").write_text(
        "Internal portable candidate; not a certified public release.\n"
        "Extract and open Launch Line Dance Creator.bat.\n"
        "Data defaults to %LOCALAPPDATA%/HillbillyHellfire/LineDanceCreator; explicit data overrides are retained.\n"
        "The core needs no Python installation, internet, AI account or speech model.\n"
        "Optional local models are not included. Store a separate backup of your projects.\n"
        "Pending release gates include clean-machine/offline/upgrade testing, content and licence\n"
        "review, instructor/user acceptance, supported OS declaration and final freeware terms.\n",
        encoding="utf-8")
    notes = ["# Third-party distribution notices", "",
             "CPython's full notice is retained at `runtime/LICENSE.txt`.",
             "The following installed wheel files and their licence/NOTICE files are retained.",
             "Metadata labels are an inventory, not a legal certification. Native libraries may",
             "have additional obligations; inspect the linked files before distribution.", ""]
    for package in packages:
        notes.append(f"## {package['name']} {package['version']}")
        notes.append("\n" + package["license_metadata"] + "\n")
        notes.extend(f"- [{path}]({path})" for path in package["license_files"])
        if not package["license_files"]:
            notes.append("- No separate licence file identified; review retained METADATA before release.")
        notes.append("")
    (destination / "THIRD-PARTY-NOTICES.md").write_text("\n".join(notes), encoding="utf-8")
    result = verify(destination)
    result["prefix"] = "runtime (relocatable smoke check)"
    manifest = {"schema_version": 1, "python": platform.python_version(),
                "platform": "Windows x64", "release_status": "internal-candidate",
                "optional_models_included": False, "packages": packages,
                "smoke_check": result}
    (destination / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    hashes = [f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(destination).as_posix()}"
              for path in sorted(destination.rglob("*")) if path.is_file() and "__pycache__" not in path.parts]
    (destination / "SHA256SUMS.txt").write_text("\n".join(hashes) + "\n", encoding="utf-8")
    if archive:
        with zipfile.ZipFile(archive_path, "x", zipfile.ZIP_DEFLATED) as bundle:
            for path in sorted(destination.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(destination))
        print(f"Archive: {archive_path.name}; SHA256: {hashlib.sha256(archive_path.read_bytes()).hexdigest()}")
    print(json.dumps({"output": str(destination), "runtime_packages": len(packages), "smoke_check": result}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "portable-candidate")
    parser.add_argument("--zip", action="store_true", help="Also create a checksum-reported zip")
    parser.add_argument("--inventory-only", action="store_true", help="Explicitly refresh version snapshots; do not build")
    args = parser.parse_args()
    if args.inventory_only:
        write_inventory(ROOT / "docs" / "steering" / "evidence")
    else:
        build(args.output, args.zip)

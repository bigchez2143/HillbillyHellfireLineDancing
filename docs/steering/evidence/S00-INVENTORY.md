# S00 baseline and dependency inventory

Evidence date: 3 September 2026. Scope: isolated development copy, Windows x64, CPython 3.12.14. This is engineering evidence, not a completed release or instructor acceptance certificate. Original projects, songs and research files remain protected outside these test fixtures.

## Baseline execution

The baseline copy's `baseline-results.xml` records **111 tests: 110 passed, one failed, zero skipped**, in 5.408 seconds. The failure was `test_optional_ai_key_stays_private_to_the_local_server`: Windows DPAPI could not encrypt the synthetic test key inside the execution sandbox. The coordinating agent separately reran that single test outside the sandbox and reported a pass. This is a targeted retry, not evidence that the entire suite was rerun with 111 passes. Preserve the original XML and separate retry evidence. Subsequent implementation results belong in their own reports.

Existing tests cover generation, validation, timing, lyric scan/alignment, asynchronous analysis, tutorial plans and API behavior. They do not substitute for an observed dancer session, physical floor trial, clean-Windows install, measured audio latency, or visual print inspection. Most music/model tests use synthetic or mocked inputs; no paid calls or model downloads were performed for this inventory.

## Existing local capabilities and catalog

The FastAPI application serves the dance creator and Sound Repair Studio. Its engine handles deterministic assembly, validation, catalog/custom moves, music/phrase analysis, lyric alignment, optional AI proposals, project persistence, sheets/teaching outputs, tutorial planning and repair. Import parsing includes XLSX/CSV/TSV/DOCX/TXT/MD/JSON and text PDF. A tutorial plan is not a rendered video; a reference entry is not automatically a mechanically validated generator move.

The [source inventory](runtime-code-inventory.json) records imports, source hashes and 59 declared routes across the server and 17 engine modules at capture time. FastAPI/static mounts add framework routes. Other sprint work can change this snapshot; it is not a claim about every subsequent revision.

The common catalog contains **173 retained entries**: 26 concepts, 52 primitives, 77 patterns and 18 styling entries. The pre-existing engine had 39 built-in executable moves. These numbers describe coverage, not completeness or instructor review. Preserve common vocabulary/mechanics and truthful private history; publish only independently authored/cleared descriptions and permitted assets. Custom authoring must prevent the catalog becoming a ceiling.

## Dependency map

| Capability | Direct packages | Loading behavior |
|---|---|---|
| Local UI/API | FastAPI, Uvicorn, Pydantic, python-multipart | Startup; multipart supports file uploads |
| Audio DSP | librosa, NumPy, SoundFile | Imported by server engines at startup, including manual mode |
| PDF output/input | ReportLab / pypdf | Imported at use; old pypdf error calls it optional although requirements install it |
| Word/spreadsheet output | python-docx, openpyxl | New core resolution includes these for native exports |
| Local calendar exchange/timezones | icalendar, tzdata, python-dateutil/six transitively | S08 adds maintained serialization and offline Windows IANA timezone data |
| Tests | pytest, httpx | Development only, excluded from portable runtime |
| Optional lyric timing | WhisperX, faster-whisper, PyTorch and dependencies | Lazy import when selected; absent from core environment |
| Optional stem separation | Demucs/PyTorch and model dependencies | Subprocess uses application's interpreter; absent from core |
| Optional remote AI | Standard-library HTTP client | User configuration; no provider SDK/key required for core |
| Catalog/storage, document ZIP/XML | Python standard library | SQLite/JSON/ZIP/XML need no separate pip packages |

The old `app/requirements.txt` uses mostly open ranges and includes pytest. The old uv launcher always selected the lyric addon, making optional speech part of ordinary startup. New `requirements/` groups and `app/run.bat` separate this boundary; legacy app requirements remain pending coordinator review.

Exact observed versions: [development snapshot](installed-development-environment.txt); smaller runtime closure: [Windows core version lock](../../../requirements/core-win-py312.lock.txt). This is a resolved version snapshot, not a wheel/hash lock. Retain exact Windows wheels and hashes and reproduce on the supported target before release.

## Optional models and content rights

The lyric engine defaults to faster-whisper `small`, English, CPU/int8 or CUDA/float16 when available. `LINE_DANCE_WHISPER_MODEL` and `LINE_DANCE_WHISPER_LANGUAGE` configure it. Pasted-lyric alignment can load an additional language-specific alignment model. Demucs selects `htdemucs_6s`. First use can download weights; actual sizes, singing coverage, processing time and GPU behavior have not been measured here.

These tools are explicit user-managed addons, never an automatic startup dependency. Code licences do not establish model, input recording or output redistribution rights; inspect exact weights and codecs separately. [WhisperX licence](https://github.com/m-bain/whisperX/blob/main/LICENSE), [Demucs licence](https://github.com/facebookresearch/demucs/blob/main/LICENSE)

AI uses an optional user-owned provider/account/local endpoint. No shared keys, app-funded credits, company-funded hosted inference or AI proxy are permitted. Users pay their provider charges; disconnected core authoring, analysis, rehearsal and export remain independent.

## Distribution findings and remaining gates

Native dependencies need separate notices. SoundFile Windows wheels include libsndfile, whose licence differs from the wrapper. Installed soxr metadata declares LGPL-2.1-or-later; NumPy/SciPy/llvmlite include additional native-library notices, and certifi declares MPL-2.0. Retain full wheel notices and review native redistribution obligations rather than making a blanket permissive-license claim. [SoundFile distribution](https://pypi.org/project/soundfile/)

The openpyxl 3.1.5 and et_xmlfile 2.0.0 installed wheels contain MIT metadata but omit a separate full licence file. Their full notices were recovered from the matching official PyPI source distributions, with archive SHA-256 verified against PyPI's published digest. The [notice provenance](dependency-notices/provenance.json) records exact URLs, archive members and notice hashes; the builder includes these supplemental notices. No licence for a different version was substituted.

The portable foundation copies configured Windows CPython plus only the installed core dependency closure. It never copies `.venv` with its absolute base-Python path, or the base runtime's unrelated site-packages. It retains distribution licence files and generates a package manifest and SHA-256 list. Public source is allowlisted: application Python/static assets and two catalog JSON files. Projects, secrets, songs, database sidecars, research PDFs and private audit history are excluded. The build is an internal candidate until release gates pass.

Remaining gates: reviewed movement fixtures; observed UI journeys; rendered PDF/Word checks; supported Windows/hardware declaration; per-user data/upgrade/recovery and clean-machine offline/non-admin tests; retained wheel hashes/security checks; instructor/usability acceptance; final freeware terms and dependency/content rights review. No release upload or external-account access occurred.

## Packaging verification performed

`app\\run.bat --check` passed without starting the server or loading optional models. A private-runtime candidate containing 45 core distributions passed WAV read/write, librosa feature extraction, PDF generation/readback, DOCX generation and XLSX generation with PATH restricted to Windows System32 and Python environment overrides removed. It then passed the same checks after relocation to a path containing spaces; importing the packaged application exposed 64 framework-inclusive routes. The allowlist check excluded tests, optional model packages, private files and a copied `pyvenv.cfg`. See [smoke results](portable-smoke-results.json).

Reproduce from the tested environment: `.venv\\Scripts\\python.exe scripts\\build_portable.py --output build\\candidate-NEW` (optionally `--zip`). An output directory must be new; the builder never deletes an earlier candidate. Use `--inventory-only` only when deliberately reviewing/updating the dependency snapshot. This is host-level runtime/format evidence, not a clean-machine install or full UI test, and the candidate predates later sprint changes.

The S08 dependency update increased the core closure to **49 packages**. A subsequent package includes the instructor API/shared storage paths, retains all 49 notice sets and passes runtime/format checks plus checksum verification: [S08 package results](portable-instructor-results.json). Portable bootstrap defaults and explicit data/library/tools override preservation also passed a stubbed-launch check: [storage defaults results](portable-bootstrap-results.json). No real browser/server session was opened by that bootstrap check.

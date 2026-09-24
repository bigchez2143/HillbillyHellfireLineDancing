# Third-party software and content notices

Inventory date: 3 September 2026. This source-level index is not a replacement for the full licenses included with a binary, and is not a certification that every redistribution obligation has been discharged. The application's proposed freeware restrictions govern only material its licensor can license; upstream components retain their own permissions and obligations.

The tested Windows x64 / CPython 3.12.14 core resolution contains 49 distributions, pinned in `requirements/core-win-py312.lock.txt`. `scripts/build_portable.py` copies their installed wheel files, retains license/NOTICE files and emits `build-manifest.json`, `THIRD-PARTY-NOTICES.md` and `SHA256SUMS.txt` inside each candidate. The generated manifest names the actual license files for that build. CPython's notice is retained at `runtime/LICENSE.txt`. Consult those complete texts before redistribution.

## Observed core distribution metadata

Metadata labels below are transcribed as an inventory. Labels such as “BSD” and “Dual License” require the retained full text; native libraries can have additional licenses.

| Distribution | Version | Declared license metadata |
|---|---|---|
| annotated-doc | 0.0.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| anyio | 4.15.0 | MIT |
| certifi | 2026.7.22 | MPL-2.0 |
| cffi | 2.1.1 | MIT-0 |
| charset-normalizer | 3.5.1 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| cloudpickle | 3.1.2 | BSD-3-Clause |
| decorator | 5.3.1 | BSD-2-Clause |
| et-xmlfile | 2.0.0 | MIT |
| fastapi | 0.141.1 | MIT |
| h11 | 0.16.0 | MIT |
| icalendar | 7.3.0 | BSD-2-Clause |
| idna | 3.19 | BSD-3-Clause |
| joblib | 1.6.0 | BSD-3-Clause |
| lazy-loader | 0.5 | BSD-3-Clause |
| librosa | 1.0.0 | ISC |
| llvmlite | 0.49.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception |
| lxml | 6.1.3 | BSD-3-Clause |
| msgpack | 1.2.2 | Apache-2.0 |
| narwhals | 2.25.0 | MIT |
| numba | 0.67.0 | BSD; see full text |
| numpy | 2.5.2 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openpyxl | 3.1.5 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pillow | 12.3.0 | MIT-CMU |
| platformdirs | 4.11.7 | MIT |
| pooch | 1.9.0 | BSD-3-Clause |
| pycparser | 3.0 | BSD-3-Clause |
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| pypdf | 6.16.2 | BSD-3-Clause |
| python-dateutil | 2.9.0.post0 | Dual License; see full text |
| python-docx | 1.2.0 | MIT |
| python-multipart | 0.0.32 | Apache-2.0 |
| reportlab | 5.0.1 | BSD license; see license.txt |
| requests | 2.34.2 | Apache-2.0 |
| scikit-learn | 1.9.0 | BSD-3-Clause |
| scipy | 1.18.1 | See full distribution and bundled-library notices |
| six | 1.17.0 | MIT |
| soundfile | 0.14.0 | BSD 3-Clause wrapper; inspect native library separately |
| soxr | 1.1.0 | LGPL-2.1-or-later |
| starlette | 1.6.0 | BSD-3-Clause |
| threadpoolctl | 3.6.0 | BSD-3-Clause |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| tzdata | 2026.3 | Apache-2.0; retain packaged data notices |
| urllib3 | 2.7.0 | MIT |
| uvicorn | 0.52.4 | BSD-3-Clause |

The openpyxl and et_xmlfile wheels omitted separate complete notice files. Matching notices were recovered from their exact-version official PyPI source archives and verified against published archive hashes. They and their provenance are retained in [dependency notices](docs/steering/evidence/dependency-notices/provenance.json), and copied into portable candidates. No different-version notice was substituted.

## Native dependencies and release obligations

SoundFile's Windows wheel includes libsndfile, with a different license from its Python wrapper. The core also contains native binaries from soxr, NumPy, SciPy, llvmlite, Pillow/lxml and CPython, including runtime DLLs. Examine all applicable native notices and any source, relinking, redistributable or other requirements for the exact binaries being shipped. Merely listing a dependency or retaining its headline license is not a substitute. [SoundFile distribution information](https://pypi.org/project/soundfile/), [CPython license](https://docs.python.org/3.12/license.html)

Development-only tools are recorded separately in `requirements/dev-win-py312.lock.txt`; they are not deliberately bundled as application dependencies. The source repository lists installation requirements rather than vendoring the full environment. Keep the source tree free of `.venv`, uv caches and built runtimes.

## Optional tools, models and content

The core candidate bundles **no WhisperX/faster-whisper/Demucs/PyTorch models**, no shared AI credentials and no publisher-funded AI service. Optional local addons are user-installed and managed separately. Any later redistributable addon needs its own exact dependency, model-weight and codec inventory; a code license does not settle model/content rights. [WhisperX code license](https://github.com/m-bain/whisperX/blob/main/LICENSE), [Demucs code license](https://github.com/facebookresearch/demucs/blob/main/LICENSE)

No FFmpeg executable is included by the current core allowlist. If a later package adds FFmpeg, review its actual build configuration and applicable obligations. [FFmpeg legal guidance](https://ffmpeg.org/legal.html)

External songs, teaching PDFs, reference screenshots, demo media and service databases are not made redistributable by this file. The common-move catalog is retained; its descriptions, media, provenance and permissions require their own release-content review. Private research files remain outside public source and binaries. Resource hyperlinks are not a copied or licensed third-party database.

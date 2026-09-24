# S10 final internal packaging evidence

Measured on 2026-09-04. This is an internal Windows candidate, not an approved public release.

## Final candidate

The final artifact is `build/portable-final-2026-09-04-r3.zip`, extracted at
`build/portable-final-2026-09-04-r3`. It was built after the final app/data freeze,
including the human-readable calendar preview and the footer on the creator,
legacy, and Sound Repair pages. Earlier unnumbered/r2 candidates are superseded.

| Measurement | Observed result |
| --- | --- |
| ZIP size | 141,965,322 bytes (135.39 MiB) |
| Expanded file size total | 416,911,376 bytes (397.60 MiB) |
| Expanded files | 9,643 |
| Core Python distributions | 49 |
| Python runtime | 3.12.14, Windows x64 |
| App/data files matched to frozen source | 44 |
| Manifest file hashes verified after extraction | 9,642 |
| Routes registered by packaged server import | 72 |
| Bundled optional speech/AI models | None |

ZIP SHA-256: `82a62d44f5d0cc5c4a9828b0f1332f9b673d47519ebe77f67878669182931b08`.

`SHA256SUMS.txt` records package-file hashes; the checksum list itself is not one
of its own entries. The ZIP digest covers the complete archive.

## Allowlist and storage change

The portable builder and read-only source manifest both now include
`data/common-move-explanations.json` alongside the two existing catalog JSONs.
No other allowlist rule was broadened. The new file retains all 173 indexed move
identities and explicit draft/instructor-review status. Bundling it does not
approve the prose, repair catalog mechanics, or certify content rights.

The package includes the private CPython runtime and the locked core dependency
closure rather than a machine-bound virtual environment. The launcher defaults
user data to `%LOCALAPPDATA%/HillbillyHellfire/LineDanceCreator`, with library and
instructor tools beneath it, and honors explicit storage overrides. No existing
user data was moved during these checks. Projects, private references, credentials,
runtime caches from the source environment, optional models, and research PDFs
are not application allowlist inputs. Retained dependency notices and their
supplemental provenance are included; that inventory is not legal certification.

## Relocation and native dependency checks

The ZIP was extracted to the separate new directory
`build/relocated-final-2026-09-04-r3`. Every listed hash verified, and every packaged
app/data file matched the frozen source. Checks ran with that copy's `python.exe`
in isolated mode, bytecode writes disabled, external Python environment variables
removed, and PATH reduced to Windows System32. `sys.prefix` resolved to the
relocated private runtime. Temporary app storage was isolated under the build
directory and cleaned after the checks.

Passed in the relocated copy:

- Core library imports and application import with 72 registered routes.
- WAV write/read and librosa RMS calculation.
- FLAC write/read of 8,000 synthetic frames through SoundFile/libsndfile.
- soxr-backed librosa resampling to 16,000 frames.
- SciPy resampling and FFT through the packaged native libraries.
- Numba native compilation and execution, exercising the packaged LLVM dependency.
- PDF generation/readback, Word save/readback, and Excel save/readback in memory.
- iCalendar serialization/readback with America/New_York timezone data.

No browser or server was launched, no live user media was processed, and no network,
account, AI provider, or paid service calls were made by these verification commands.
AI remains optional bring-your-own connection; no shared key, owner-funded inference,
proxy service, provider credits, or required model download was added.

## Source dry run and release gates

The source allowlist snapshot contains 100 candidate files totaling
1,658,779 bytes. It is a dry run: no staging, copying to a public
repository, commit, push, or upload occurred. Documentation-only edits after this
snapshot can change source-manifest hashes without changing the packaged app.

Automated review flags at the snapshot:

- No automated content flags in this snapshot; manual review remains required.

Final software license present: **false**.
Git history checked by this manifest tool: **false**.
Ready to publish: **false**. License adoption, content/history/rights review,
native dependency obligations, supported-OS and clean-machine testing,
disconnected-machine/upgrade checks, and human instructor/user acceptance remain
separate gates. These same-host relocation checks do not certify an installer or
prove operation on a clean Windows machine.

Machine-readable details are retained locally in `portable-final-results.json`
and `final-source-manifest.json`; the first includes per-file app/data hashes.
The verification command was `.venv\Scripts\python.exe work/verify_final_portable.py 2026-09-04-r3`.

# S05–S06 music and generation integration evidence

Evidence date: 2026-09-03. All audio is generated locally by the test, all projects/settings use temporary directories, and optional-provider responses are stubbed. No external AI request or real user project is used.

Test source: `app/tests/test_music_generation_integration.py`. Production implementation ownership remains with the root task; this verification pass changes only the test and this evidence file.

## Timing and real audio measurements

The timing-map test represents 32 counts at 100 BPM followed by 32 at 120 BPM, starting two seconds into the recording. Explicit anchors are `(count 0, second 2)`, `(32, 21.2)`, `(64, 37.2)`. It verifies interpolation and inverse conversion at nine positions, including subdivisions, negative pickup positions, and extrapolation to count 10,000, with a `1e-9` absolute tolerance. Project save/reopen preserves the map, reviewed metadata, a manual key entry, and a three-beat meter without accepting a dance implicitly.

The actual analyzer is `engine.audio.analyze(path)`, imported in the server as `audio_engine`; there is no `audio_engine.py` file. Tests synthesize 22,050 Hz PCM WAV clicks, with 35 ms decaying 1,600 Hz pulses and an accent every fourth beat. Constant-tempo segments last 64 seconds; the changing fixture has 40 seconds at each tempo. A one-second lead-in and trailing silence are included. Constant BPM estimates must be within 3% of their known source; the tolerance accommodates the analyzer's 512-sample onset hop. Beat times must advance and median spacing must be within 4%.

| Synthetic signal | Observed estimate | Confidence and interpretation |
| --- | --- | --- |
| 100 BPM clicks | 99 BPM | High; four tempo estimates around 99.38, no drift flag |
| 120 BPM clicks | 120 BPM | Medium; a competing half/double-time grid is exposed |
| 100 → 120 BPM clicks | Global scalar 59 BPM | Low; first/second-half measurements 99.38/117.45 BPM, 30.63% drift flag, not steady |

The changing-tempo fixture demonstrates why a single estimated BPM cannot be the authoritative timing map. Its drift detection passes the requirement to flag the change, but the scalar 59 BPM is an ambiguous half-time result, not a faithful description of the two actual sections. Reviewed local anchors are required for accurate variable-tempo choreography. This is not evidence of automatic tempo-map inference, general meter detection, or real-song accuracy. The legacy analyzer's downbeat and bar estimates still assume four beats.

Key estimates use `engine.music_map.estimate_key(path)` on locally synthesized six-second examples (a two-second silence and a half-second short clip are separate cases):

| Signal | Observed result | Required presentation |
| --- | --- | --- |
| Silence | Empty key, insufficient confidence | Abstain |
| Half-second sample | Empty key, insufficient confidence | Abstain |
| Seeded broadband noise | D minor, low confidence; alternatives B-flat major and C-sharp minor | Estimate warning and alternatives; no confident tonal claim |
| Sustained C–E–G chord | E minor, low confidence; C major second, G major third | Show alternatives and uncertainty; a chord alone does not establish a song's key |

The C-major-chord result exposes a real limit of the heuristic. The test requires C major among the alternatives, not a claim that the system correctly identified the whole recording's key. These fixtures do not establish robust key detection for vocals, percussion-heavy mixes, modulations, or arbitrary commercial recordings.

## Generation, saved state, and optional-provider isolation

Successful generation tests both R and L selected starting feet. A core rocking-chair occurrence locked at zero-based count 4 must retain its exact ID, complete authored payload, nested teaching metadata, and count position in every candidate. Candidates must still have 32 counts and pass the existing sequence validator for the selected start foot and one-wall target.

Rejection tests cover a nonintegral lock position, changed instructions, an unknown move ID, a lock beyond the requested length, contradictory duration fields, and an explicit event graph that disagrees with the legacy summary. Each stores a draft first and compares the complete project after the request; failed generation must not save a different dance or revision.

Local request-boundary tests verify that an unrelated web origin and the literal `null` origin cannot perform writes, while the application's same origin can. The test checks project state and response security headers. This is focused same-origin regression evidence, not a full penetration test.

Provider tests simulate HTTP 401, timeout, and malformed JSON. Each requires one call to the exact user-owned endpoint with the supplied fake user key, a safe failure response, no fallback endpoint, no project mutation, and subsequent local generation working. A fresh interpreter blocks standard network connection helpers before importing the server, then opens the application, reads disabled settings, creates a project, reads its workspace, and generates locally. Asking AI with no connection returns a configuration error rather than starting a service or using a shared key.

Existing complementary tests in `test_engine.py` cover disabled/no-key settings, endpoint validation, Windows DPAPI key privacy, bounded conversation history, and rejection of unsupported provider adapters. `test_creator_workflows.py` covers manual creation/save/accept without music or AI. The new tests extend these with actual provider transport failures, fresh startup, and API-level saved-state comparisons.

## Defects exposed and validation status

Initial full run: **28 passed, 2 failed** in 16.35 seconds. A subsequent focused test established a third failure. These are intentionally failing requirements, not tests weakened to match current behavior:

1. **Fractional meter accepted:** `POST /api/creator/music-map/validate` with `meter: 3.5` returned 200 and normalized it to 3. Expected 422; meter must not silently change.
2. **Conflicting locked duration accepted:** a locked core move retained `counts: 4` while carrying `duration_counts: "8"`; generation returned 200 with the contradictory payload in a nominal 32-count result. Expected rejection before assembly.
3. **Conflicting authoritative events accepted:** a locked rocking-chair legacy summary with zero rotation also carried a four-count explicit event turning 180 degrees. Generation validated the legacy move then restored the different authoritative event graph. Expected rejection or proven equivalence using the shared compiler.

The root task fixed all three defects: meter must be an exact integer, locked duration must equal the core count, and legacy locking rejects authoritative `events`, `snapshot_id`, and `definition` overrides. The root task reran the complete **31-test suite: 31 passed in 8.08 seconds**. These regression gates are resolved; broader S05/S06 acceptance still includes live timing and user review.

Reproduction:

```text
.venv\Scripts\python.exe -B -m pytest app\tests\test_music_generation_integration.py -q -s --basetemp=.test-tmp\music-generation-1
.venv\Scripts\python.exe -B -m pytest app\tests\test_music_generation_integration.py -q -k explicit_events --basetemp=.test-tmp\music-lock-events-1
```

Only the existing Starlette/httpx and anyio deprecation warnings appeared. Live playback synchronization, device latency, instructor floor tests, and real-song listening remain separate acceptance gates.

## Recording replacement and accepted-dance preservation

The following independent S01/S05 regression was identified and fixed during integration: both legacy song-selection handlers previously assigned an empty object to the accepted dance when the recording changed. An upload with the same filename could also overwrite the earlier recording bytes.

The scoped fix in `server.py`, `engine/project_media.py`, and `media_api.py` preserves accepted choreography, its exact source/hash and move snapshots, and the working editor. Local `recording_history` retains the previous song, timing map, analysis, timed sections/alignment, related derived data, and accepted definitions. New uploads receive unique project-local paths; a later upload with the same display filename cannot destroy the prior original. Same-content relinking preserves review and analysis.

A changed recording starts with a clearly provisional 120 BPM map, zero first-count offset, no inherited beat anchors, and required timing review. It does not borrow an old recording's measured tempo or timestamps. Explicit review binds the exact saved timing-map hash and current file-content signature. Subsequent map edits, external file changes, or missing audio make that binding stale. The status endpoint exposes this condition to the Music UI. Accepting choreography or generating suggestions does not grant recording review.

Legacy sheet/tutorial production tools require a current recording review. After explicit review, their derived view uses the new reviewed BPM while the accepted dance's original tempo snapshot remains intact. Working choreography and the main manual-export path remain independently usable; the root-owned creator export integration displays the stale-recording warning and handles timed-caption restrictions.

Latest focused recording-plus-legacy run: **49 passed in 5.75 seconds**, with the same two test-client deprecation warnings:

```text
.venv\Scripts\python.exe -B -m pytest app\tests\test_recording_preservation.py app\tests\test_lyric_move_draft_api.py app\tests\test_analysis_jobs.py app\tests\test_acceptance_compatibility.py -q --basetemp=.test-tmp\recording-preserve-3
```

Evidence includes history retention, exact accepted/working choreography preservation, five legacy export guards, explicit confirmation and revision checks, invalidated review after map/file changes, same-content relinking, same-name upload preservation, failed-write cleanup, concurrent-save conflict cleanup, filename confinement, invalid uploads, no implicit review during generation/acceptance, and protection of recording identity against stale metadata from an older editor. Tests use placeholder local WAV bytes for persistence behavior; they do not claim to validate audio decoding or hearing-based timing review.

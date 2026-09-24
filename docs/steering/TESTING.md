# Testing and release evidence

**Execution update, 4 September 2026:** [Implementation status](IMPLEMENTATION-STATUS.md) and [final regression evidence](evidence/FINAL-REGRESSION.md) record 430 passing backend tests and two passing JavaScript suites. The NOT RUN labels below refer to the complete planned acceptance scenarios, including human/provider/clean-machine work; they are not a claim that no engineering tests have run.

**Document state:** Proposed steering plan. **All tests in this document: NOT RUN.**

**Scope:** Line Dance Creator and its local Creator Studio tools, Windows-first. Feature IDs F01–F36 and sprint IDs S00–S12 follow the companion product and roadmap documents. Test group T01 covers F01, T02 covers F02, and so on. A group can contain several focused scenarios; the IDs are traceability anchors, not a claim that one assertion proves a feature.

**Release boundary:** S00–S09 cover the local freeware v1. S10 is connected-feature feasibility and may start earlier. S11–S12 are later, dependency-gated releases. A connected feature cannot be marked complete merely because a mock passes. Unsupported integrations remain visible as planned or blocked by a named dependency.

**Important distinction:** Every tolerance, participant count, fixture count, and pass threshold below is a proposed **acceptance target**, not measured application capability. Adjust a target only with a recorded reason and a documented effect on the release decision. Do not retrospectively weaken a target to turn a failure into a pass.

**AI connection contract:** AI is optional and bring-your-own only: the user selects their provider/account/model/endpoint and supplies their own credentials. There is no shared developer key, app-funded credit pool, app-operated inference service/proxy, or hidden fallback provider. Paid API operations are user-triggered on that user's account. Optional local models are separately installed capabilities, not mandatory dependencies of the core application. A configured text-only provider does not imply image/video-analysis capability.

## 1. What this plan protects

The application must let a nontechnical person make, edit, practice, and export a dance without losing work or confusing a suggestion with verified choreography. The editor must also work without music. A mathematical validation result proves only the checks actually performed; it does not certify comfort, musicality, originality, instructor endorsement, or suitability for every dancer.

Test work should prioritize these failures:

1. Lost or silently replaced choreography, lyrics, section markers, cue reviews, or attachments.
2. Incorrect counts, weight transfer, facing, restart/tag placement, or exported instructions.
3. AI or imported descriptions promoted into trusted generation without review.
4. Misleading timing, recognition, link access, save, verification, or publication status.
5. A release that needs undeclared network access, contains private material, or cannot be restored on another supported Windows machine.
6. An external operation that sends unreviewed data, duplicates a publication, or hides failure.

Use the smallest meaningful test set that resolves each risk. Unit tests are appropriate for counting, parsing, migration, state changes, and formatting. API tests are appropriate for persistence and background-job behavior. Browser tests are appropriate for complete user tasks and state visibility. Human observation is required for teaching, feel, readability, and nontechnical usability. Do not create tests that merely repeat an implementation's calculations or check incidental CSS values.

## 2. Baseline and status discipline

S00 must first inventory the existing tests, their fixtures, and their last reproducible results. Existing test files identified during the read-only audit include `test_engine.py`, `test_anchored_assembler.py`, `test_analysis_jobs.py`, `test_alignment_loader.py`, `test_audio_tempo_resolution.py`, `test_emitter_count_labels.py`, `test_lyric_scan.py`, `test_lyric_scan_api.py`, `test_lyric_moves.py`, `test_lyric_move_draft_api.py`, `test_tutorial.py`, and `test_tutorial_api.py`. This list is an inventory starting point, not an assertion that those tests pass on the current checkout.

The README contains earlier verification claims. Preserve them as historical claims with their dates; do not reuse them as evidence for a new release. No application tests, installs, migrations, floor tests, or live service calls were executed to prepare this steering document.

The initial audit found two especially important regression targets:

- The current global Save/Ctrl+S path saves song details, sections, lyrics, and sheet metadata, while manual sequence and tutorial reviews have separate save paths. T03 must define and test the complete new draft-save contract so “Saved” cannot conceal unsaved work.
- The current project store replaces one JSON file atomically. Atomic replacement is useful, but it is not undo, version history, recovery, or a migration strategy. Those behaviors require separate T03 evidence.

Allowed evidence states are **NOT RUN**, **PASS**, **FAIL**, **BLOCKED**, and **NOT APPLICABLE**. A blocked result must name its dependency. A not-applicable result must name the scope decision that makes it inapplicable. Skipped or unavailable tests are never silently counted as passing.

## 3. Fixture policy and test environments

### 3.1 Public fixtures

Use synthetic or license-cleared fixtures that can legally be committed to GitHub and distributed with source or releases. Every third-party fixture needs a manifest entry recording its source, author, license or permission, acquisition date, allowed uses, and any required attribution. A public URL alone is not permission to redistribute its contents.

Preferred fixtures include:

- Generated click tracks with known beat positions, steady tempos, controlled drift, silence, and an explicitly constructed pickup or irregular phrase.
- Synthetic instrumental sounds for key-estimation checks, including an intentionally ambiguous example. A key estimate is not required to succeed on every sample.
- Invented lyrics and labeled sections, recorded by a consenting contributor where a human voice is necessary. Include clear vocals, no vocals, and unclear vocals.
- A small, independently reviewed set of movement definitions covering weight-bearing and non-weight-bearing actions, left/right variants, turns, syncopation, and intentionally unknown mechanics.
- Small XLSX, CSV, TSV, DOCX, TXT, MD, JSON, and text-PDF fixtures containing invented moves and sheets. Include malformed rows, duplicate aliases, multiline instructions, accents, missing fields, and incompatible variants. Add a scanned-PDF fixture only when the optional OCR route enters scope.
- Contributor-owned demonstration photos and short videos, with consent for the stated use. Include an intentionally mirrored demonstration and an attachment whose file is later missing.
- Provider response fixtures with fictitious users, tracks, events, and publications. Include pagination, empty results, throttling, revocation, and ambiguous outcomes. Never record real OAuth tokens or account data in fixtures.

Generate golden timing/count expectations from the fixture specification, not from the application function being tested. Record exact arithmetic expectations for fractions and counts. Have an independent instructor review the mechanics fixtures; do not use model output as its own ground truth.

### 3.2 Private material

Private songs, unreleased lyrics, classroom records, personal schedules, private sheets, access tokens, and unlicensed media must stay outside the repository and release package. If an owner authorizes a local check against a private song, keep the asset and detailed artifact in a private test location. Record a redacted result and a non-sensitive fixture identifier in shared evidence. Do not copy waveform images, transcripts, filenames revealing unreleased titles, or full source URLs into public CI logs by accident.

S00 must identify existing real-song regressions and determine whether they can be public, must remain optional private tests, or need equivalent synthetic regressions. Preserve their bug coverage rather than simply removing the tests.

### 3.3 Environment set

Proposed acceptance environments are the declared minimum supported Windows version and one current supported Windows version, including one clean standard-user VM with no preinstalled development tools. Record actual OS builds, CPU, memory, display scaling, browser or packaged runtime, Python/runtime versions, and audio device used. Do not promise a native mobile application; a narrow browser viewport is a layout check only.

Use separate environments for a fresh install, an upgrade from a retained previous release, a portable installation, offline operation after core dependencies are present, and optional first-time model installation. The baseline runner must not require paid APIs, private credentials, microphones, or optional large model downloads.

## 4. Feature acceptance matrix

Each row is a planned acceptance group. Use several named cases where necessary and link the eventual test files and manual evidence. **Every row is currently NOT RUN.** Sprint coverage includes preparatory and regression checks; the Product register and Roadmap define feature delivery. Rechecking a local feature in a later sprint does not defer its earlier acceptance. The BYO-AI workflows delivered in S06 are part of local v1 and do not depend on completion of the S11/S12 connected feature releases.

### Core project and move workflows

| Test / feature | Sprint coverage | Concrete scenarios and acceptance target | Planned evidence / status |
| --- | --- | --- | --- |
| **T01 / F01 — Basic and Advanced** | S02, S09 | Switch detail mode in a populated project. Basic exposes creation, editing, practice, save, and export without developer settings; Advanced exposes the extra tools. Changing detail mode preserves choreography difficulty, project data, and the current unsaved draft. A returning user can find the tools hub and understand the active mode. For S02.5, verify the Hillbilly Hellfire footer in both detail modes and both workspaces: the YouTube and Website links use the verified official destinations, open in a separate tab without losing project state, have visible keyboard focus and wrap on narrow screens. Check readable contrast in both themes and no overlap with controls. Ordinary exports omit the software-footer message; offline authoring still works without loading any external content. | Browser task and observed usability session. **NOT RUN** |
| **T02 / F02 — Two start paths** | S01, S02 | Create, edit, validate where mechanics permit, save, reopen, and export a dance with no audio. Add a song later to the same project without changing its choreography. Start another project with music and reach the same editor. Unavailable timing functions explain the missing music requirement without blocking manual work. | API state round trip and two end-to-end tasks. **NOT RUN** |
| **T03 / F03 — Save, history, recovery, migration** | S00, S01, S09 | Edit sequence, sections, lyrics, metadata, tutorial reviews, and attachment references; save, close, and reopen. Saving a working draft preserves the reviewed active dance until explicit application. Test dirty indicators, Ctrl+S, undo/redo after add/remove/reorder, redo invalidation after a new edit, named-version restore, and a failed write. Interrupt a save and open a recoverable draft. Migrate retained old projects, preserve an untouched backup, and clearly refuse an unsupported newer schema. Protect distinct edits from competing jobs/windows through a documented conflict rule. | Persistence/migration regressions and process-interruption drill. “Saved” must mean all fields in the published save contract are persisted. Recovery loss must be bounded by the documented autosave interval, not described as zero-loss. **NOT RUN** |
| **T04 / F04 — Choreography structure** | S03, S05, S07 | Round-trip patterns beyond the current fixed choices, supported meters, starting foot/facing, named parts, tags, restarts, and endings. Check exact fractional count arithmetic using independent expected totals. Exercise a tag/restart at a named song occurrence and a partial final pass. Verify a valid transition, an invalid transition, and unknown mechanics. Unsupported notation must report a limitation instead of silently rounding or inventing weight transfer. | Focused engine/API fixtures plus one reviewed multi-part sheet and rehearsal timeline. **NOT RUN** |
| **T05 / F05 — Reviewed catalog** | S00, S04, S06 | Search aliases and variants; show whether a move is reviewed, incomplete, or disputed. Distinguish similarly named moves with different mechanics. Confirm default generation excludes entries lacking the required reviewed mechanics. Coverage reports use declared denominators and distinguish catalog size from verified coverage. Existing projects retain the referenced movement meaning when the catalog changes. | Catalog contract tests and sampled instructor review. **NOT RUN** |
| **T06 / F06 — Custom moves and combos** | S03, S04 | Enter a complete move, an incomplete move, a mirrored variant, and a multi-move combo. Save and reuse each where permitted. Unknown mechanics remain usable as authored notes but produce an honest validation state and cannot silently enter verified generation. Editing a library move creates a version or explicit update choice; old projects retain their snapshot. | Authoring task, project snapshot regression, and eligibility checks. **NOT RUN** |
| **T07 / F07 — File imports** | S04, S06, S07 | Exercise each promised input format with a small known fixture, including a downloaded template and user-mapped columns. Preview extracted fields before acceptance; report rejected rows and absent mechanics; reconcile duplicate aliases without silent replacement. Test a corrupt file, a wrong extension, and a multi-page sheet. Optional OCR in S06 labels uncertain extraction and offers manual correction. Re-import does not multiply accepted entries without a review decision. | Per-format parser fixtures, template round trip, column-mapping and import-preview tasks. File uploads must not execute macros or embedded scripts. **NOT RUN** |
| **T08 / F08 — AI discovery and extraction** | S04, S06, S09 | Review a supported discovery result, an unsupported claim, two conflicting sources, and a duplicate. Show source evidence and the exact proposed fields. No-result, missing-source, provider error, and refusal leave the existing catalog unchanged. Roll back an imported batch without deleting preexisting entries or unrelated later work. Saving a suggestion does not promote it to generation; promotion requires mechanics review. Treat embedded source instructions as text, not app commands. | Deterministic user-owned-provider stubs plus a separately authorized live smoke test when available. **NOT RUN** |
| **T09 / F09 — Move media** | S04, S07 | Attach multiple images/videos, a diagram, remote reference, and captions. Check thumbnails, time ranges, and viewing/mirror orientation; mirroring preserves the original and remains consistent with instruction labels. Link attachments to a move version; handle deleted, unsupported, and relocated files. Export a permitted selected-media bundle and restore it elsewhere. Adding media never verifies footwork. Future inference capabilities need separate review and tests; they are not required to attach a clip. | Attachment round trips, media relink task, and instructor review of the presentation. **NOT RUN** |
| **T10 / F10 — Sheet links and QR codes** | S04, S07 | Export sheet and move-source links to all relevant formats. Check a public URL, private URL, broken URL, local-only attachment, and missing target. Show the destination and known access limitations. Hyperlinks remain associated with the correct move. Scan a printed QR from the declared print layout using an ordinary phone and verify its destination. A successful reachability check must not be presented as permanent access or redistribution permission. | Link fixtures, rendered-export inspection, and printed-QR check. **NOT RUN** |

### Music, rehearsal, creative tools, and exports

| Test / feature | Sprint coverage | Concrete scenarios and acceptance target | Planned evidence / status |
| --- | --- | --- | --- |
| **T11 / F11 — Existing audio and lyric analysis** | S00, S05, S06 | Retain analysis, tempo-resolution, alignment, lyric-scan, and job-supersession regressions. Use known click grids, silence, drift, half/double ambiguity, unclear vocals, and a manual section map. Edit lyrics or markers while a background job is running and switch the source recording; stale results cannot overwrite the newer state. No usable vocals produces no fabricated lyric map. For steady synthetic fixtures, proposed tempo target is within 1 BPM of an accepted known grid, with octave alternatives explicitly distinguished. | Existing regressions adapted to legal fixtures, deterministic job tests, and isolated model smoke checks. This target does not promise 1 BPM accuracy on arbitrary songs. **NOT RUN** |
| **T12 / F12 — Key, meter, and timing corrections** | S03, S05 | Estimate key on labeled synthetic examples and report an ambiguous example as uncertain; save manual overrides separately from estimates with recoverable history. Enter meter, tap a controlled tempo, choose half/double time, and set first count. Reopen and export the chosen interpretation. Mark dependent rehearsal/tutorial results stale when needed. Proposed tap target: with ideal synthetic tap events, computed tempo is within 1 BPM; human tapping accuracy is measured separately. | Known-input calculation tests and ear-check workflow. No universal key-detection accuracy claim. **NOT RUN** |
| **T13 / F13 — Rehearsal and teaching** | S05, S07, S09 | Play, pause, seek, loop an 8-count block, change supported playback speed with pitch preservation, toggle cues/metronome, and enter/exit fullscreen. Show current/next move, count, wall, and specified tags/restarts. Seeking/looping recomputes state. On a reference setup and synthetic fixture, proposed visual count target is within 100 ms after playback stabilizes; separately record cue offset/device limitations. At declared slower speeds, a steady 440 Hz fixture should remain within 1% of its original frequency outside transition transients. | Timeline/audio fixture checks, recorded browser playback, and instructor practice session. Pitch target is proposed; no zero-drift or exact Bluetooth timing claim. **NOT RUN** |
| **T14 / F14 — Generation and locked blocks** | S03, S06 | Preserve seeded generation and lyric-anchor regressions. Lock selected blocks and regenerate remaining counts; locks retain exact authored movement meaning and position. Compare the result with the prior draft and Undo the replacement. Validate the entire result, including boundary transitions. Exercise impossible locks, insufficient catalog coverage, high tempo, and stale lyric alignment; explain the failed constraint. Display heuristic scores as draft assessments, not measured floor appeal. | Independent validator checks, fixed-seed fixtures, infeasible-case tests, and human comparison. **NOT RUN** |
| **T15 / F15 — Advanced AI and lyric workshop** | S01, S06, S09 | Create a lyric revision, compare and restore it, and preview exactly what context will be sent. Test no connection, a valid user-owned provider/model/endpoint, missing or revoked credentials, timeout, and quota error through stubs. Enabling AI without credentials opens setup and makes no fallback request. Cancel before sending and verify no request occurred. A response creates a reviewable revision instead of overwriting the source. Disconnect immediately prevents subsequent use of the saved connection. Paid calls are user-triggered on that user's account. | Revision persistence, endpoint/request-spy tests, redacted credential/log inspection, core tasks with no connection, and one optional authorized provider smoke test. No shared key, app-funded service, or text-only provider presented as video-capable. **NOT RUN** |
| **T16 / F16 — Creator Studio** | S02, S05, S06 | Open tutorial production and audio repair from Advanced/Studio while retaining the same project. Preserve count-one, tempo-confirmation, cue approval, source-fingerprint, and stale-plan checks. Change source dance/audio after a tutorial is reviewed and verify readiness is invalidated appropriately. Run repair against a synthetic damaged mix, audition source/output, handle missing models and failed jobs, and keep the original unchanged. Exports accurately distinguish blueprint, audio output, and generated video if video is actually supported. | Existing tutorial regressions, controlled repair integration fixture, and Studio task. No claim that a master can reliably separate every instrument. **NOT RUN** |
| **T17 / F17 — Human-readable sheets** | S03, S07, S09 | Export PDF, DOCX, TXT, and HTML in supported standard, large-print, and cue-card layouts. Verify song/dance title, choreographer, source credits, counts, subdivisions, parts, tags/restarts, endings, caveats, and links against one independent golden sheet. Render A4 and Letter examples with long names, long instructions, and multiple pages. Print representative standard and large-print pages; inspect clipping, reading order, page breaks, and usable text size. | Field-level comparisons, rendered pages, and print/readability review. Every advertised format/layout combination needs a smoke check; deeper cases target distinct renderer risks. **NOT RUN** |
| **T18 / F18 — Data, captions, and portable restore** | S01, S04, S07, S09 | Export XLSX/CSV with fractional counts and multiline text, SRT/VTT with reviewed timing, and native project/move/lesson bundles. Check caption ordering and nonnegative valid time ranges. Open tabular output with formula-like input safely represented as text. Restore a bundle into a clean installation and compare source data plus attachments; missing media offers relinking. Reject corrupt manifests, unsupported schemas, and archive paths outside the chosen restore location. | Round-trip comparison, caption parser check, clean-machine restore, and archive validation cases. **NOT RUN** |

### Local library and instructor tools

| Test / feature | Sprint coverage | Concrete scenarios and acceptance target | Planned evidence / status |
| --- | --- | --- | --- |
| **T19 / F19 — Local dance library** | S02, S08, S09 | Import authorized sheets, organize folders/tags/favorites, and find a dance by title, alias, choreographer, and song. Rename and move entries without losing their project/media links. Search results distinguish local content from online references. With networking blocked, open and search cached content whose use is authorized. A missing cache produces a clear explanation. | Library task and offline fixture catalog. Proposed usability target: locate a named fixture dance within 30 seconds after brief orientation. **NOT RUN** |
| **T20 / F20 — Learning and practice progress** | S08 | Mark a dance as learning, known, practiced, or another configured category; edit practice history/checklists, add a note, undo an accidental change, and reopen. Progress belongs to the user's local library entry, not the shared canonical dance or an inferred claim of mastery. Changing a dance version prompts an explicit rule for retaining/reviewing prior progress. Confirm unrelated local records are not mixed. | Persistence/version scenario and nontechnical practice task. **NOT RUN** |
| **T21 / F21 — Class setlists and guides** | S07, S08 | Build and reorder a mixed setlist; include track choice, optional duration, notes, and teaching references. Missing durations are visibly unknown and do not masquerade as a complete class-length estimate. Print a guide and export a digital guide; every entry points to the intended dance/version. Share output contains only selected notes and links. | Class preparation task, ordered export comparison, and print inspection. **NOT RUN** |
| **T22 / F22 — Alternative tracks** | S05, S08 | Attach two tracks with different tempos/intros to one choreography. Switching tracks preserves the dance and restores that track's own first-count, sections, and review status. A timing correction to one track does not silently alter another. Flag an unreviewed song swap and let an instructor rehearse it; measured tempo compatibility alone cannot label the pairing suitable. | Per-track persistence/timing regressions and instructor pairing review. **NOT RUN** |
| **T23 / F23 — Local schedule and calendar** | S08 | Create, edit, duplicate, and remove a class/event with location, notes, and linked setlist. Export and re-import ICS through a supported calendar reader; test timezone offsets, a daylight-saving boundary, and special characters. Avoid duplicate events on repeated imports according to a documented identity rule. Local notes remain local unless explicitly included in a share/export. | Calendar fixture round trip and schedule task. Hosted synchronization is outside this test. **NOT RUN** |
| **T24 / F24 — Resource directory** | S02, S08, S09 | Open the verified starting resources, add/edit/favorite a custom link, identify a stale link, and keep local browsing functional when checks fail. Display source and last-check information. Link checking does not imply endorsement or scrape/import an external database. A failed check says unknown/unreachable rather than falsely declaring content deleted. Any site-search URL template needs separate verification against the real destination. | Stubbed link responses, verified initial directory, and resource management task. **NOT RUN** |

### Optional connected capabilities

| Test / feature | Sprint coverage | Concrete scenarios and acceptance target | Planned evidence / status |
| --- | --- | --- | --- |
| **T25 / F25 — Song recognition and dance matching** | S10, S11 | Use a licensed clip, unknown clip, noisy clip, and denied microphone permission. Recognition returns a reviewed candidate or no match; the user can correct it manually. Match a recognized recording to zero, one, and several dances, and one dance to multiple tracks. Never present track recognition as proof of a unique dance. Disclose the clip/context sent and keep local library search available if the provider fails. | Provider contract fixtures, consent task, and authorized live recognition smoke test. Accuracy reporting uses a declared sample and reports no-matches. **NOT RUN** |
| **T26 / F26 — Playlist adapters** | S10, S11 | For each supported provider, test connect, declined scopes, expiry, revocation, pagination, unavailable tracks, duplicates, and rate limits. Preview additions/removals before an authorized write. Reconcile a playlist changed remotely during the operation using an explicit conflict choice. Handle partial success and ambiguous network completion without blind duplicate retries. Disconnect preserves the local setlist. | Adapter contract suite and isolated user-authorized test playlist. Each provider is a separate gate. **NOT RUN** |
| **T27 / F27 — External sheet discovery** | S10, S11 | Test a permitted source, an unavailable source, a login boundary, and a source that allows linking but not caching. Preview content/provenance; keep omitted timing/mechanics unknown. Detect a source update and preview differences before replacing an imported version or local edits. Apply cache permissions/deletions as documented. A failed import cannot produce an apparently complete sheet. Preserve a manual-link fallback. | Source-specific permission evidence, adapter fixtures, and authorized small live import. No implied rights to bulk database access. **NOT RUN** |
| **T28 / F28 — Hosted events and accounts** | S10, S12 | Test account boundaries, event creation/editing, draft/public status, moderation/reporting, and deletion using synthetic accounts. Verify one user cannot edit another's private content. Check map/location behavior with missing data, rate limits, and unavailable geocoding; allow a text location. Test timezone display and visibility before publication. Offline local scheduling remains usable. | Access-control integration tests, moderation walkthrough, and a nonproduction deployment smoke test. **NOT RUN** |
| **T29 / F29 — Direct publishing** | S10, S12 | Prepare a concrete destination-specific preview, include credits and required fields, and require explicit final submission. Cancel and verify no write. Exercise validation rejection, moderation pending, success, timeout after possible success, and retry. Persist an operation identifier/status where supported and verify before resending; never declare published without evidence. Record what cannot be edited/recalled. Manual export remains usable when publishing is unavailable. | Request-spy tests and an expressly authorized nonpublic/test destination smoke test where possible. **NOT RUN** |
| **T30 / F30 — Optional analytics** | S10, S12 | Begin with analytics disabled. Test consent, enabled collection, opt-out, retention/deletion behavior, and unavailable data. Clearly separate local practice entries, provider-reported counts, and any estimates; do not merge them into an unsupported audience claim. Verify raw song/lyric/media content and credentials are excluded from analytics payloads. Date ranges and timezones reconcile against known synthetic events. | Synthetic event reconciliation, payload inspection, and privacy-setting task. **NOT RUN** |

### Release, access, rights, and verification

| Test / feature | Sprint coverage | Concrete scenarios and acceptance target | Planned evidence / status |
| --- | --- | --- | --- |
| **T31 / F31 — Freeware terms** | S00, S09 | Review the actual packaged license, repository text, installer notice, and About/download wording together. They must consistently reflect the approved ban on software resale/monetization and the explicit permission to use the software at paid dance events. Third-party component and content rights remain separately identified. Test only wording/package consistency; software tests cannot establish legal enforceability or license compatibility. Unresolved rights questions block redistribution of affected material. | Owner-approved wording checklist and dependency/content rights inventory. **NOT RUN** |
| **T32 / F32 — Source and Windows releases** | S00, S09 | Build from a clean checkout using documented pinned inputs; record the toolchain and dependency sources. Install as a standard user where supported, launch, create/save/export, upgrade a retained older project, and uninstall according to the documented user-data policy. Repeat the main task with the portable release. Scan the package/repo for secrets, private assets, unintended caches, absolute developer paths, and missing notices. A repeat build must explain any nondeterministic differences; do not claim bit-identical reproducibility without demonstrating it. | Clean-machine build/install logs, artifact manifest/checksums, package inspection, and upgrade evidence. **NOT RUN** |
| **T33 / F33 — Accessibility, usability, and offline core** | Every sprint; S09 release gate | Complete core tasks with keyboard navigation and visible focus; check labels, modal focus, error announcements, contrast, 200% zoom, and declared minimum window size. Do a screen-reader smoke task on the supported Windows setup. With networking blocked after core installation, create/edit/save/rehearse local audio/export/reopen; optional online tools explain unavailability. Observe nontechnical users in Basic and record unaided task completion and confusion. | Accessibility checks, offline network log, screenshots, and observed task evidence. Targets and sample are defined below; apply affected checks per sprint. **NOT RUN** |
| **T34 / F34 — Privacy and optional costs** | Every sprint; S09/S10 gates | Inspect what leaves the device for model downloads, AI prompts, recognition, playlist changes, publishing, and analytics. Show relevant scope/data/cost information before the optional action. With no AI connection or optional local model, core features still work. Missing credentials request setup rather than contacting a fallback; disconnect disables local connection use. Verify no shared key, inference proxy, app-funded credits, background paid calls, or secrets in bundles/source/releases/screenshots/logs. Exercise missing model, insufficient disk, failed download, and cancelled setup. | Request capture against stubs, core offline task with AI unconfigured, clean package scan, and optional-setup walkthrough. Every paid operation is user-triggered on their account and authorized for the specific test. **NOT RUN** |
| **T35 / F35 — Contributions and mechanics coverage** | S00, S04, S06, S09 | Accept a contributed move with source/license/reviewer records; hold incomplete or disputed submissions in review. Check alias collisions, revision history, and incompatible mechanics variants. Independent instructors review the declared representative movement set and record exact count/weight/facing disagreements. Coverage reports separate imported, reviewed, disputed, and generator-eligible entries. A single reviewed example cannot mark its entire movement family verified. | Contribution review records, instructor sign-offs, and a coverage report with denominators. **NOT RUN** |
| **T36 / F36 — Traceable release evidence** | S00–S12 | For each sprint, map implemented F IDs to T groups, change references, executed cases, results, and unresolved issues. Reproduce a historical bug with a focused test before accepting its fix. Link instructor/floor findings to any implementation changes. Verify the release checklist has no missing mandatory evidence and distinguishes local v1 from later connected scope. Publish only redacted evidence permitted for GitHub. | Completed evidence template, regression report, and release decision. This steering document alone is not a passing result. **NOT RUN** |

## 5. Cross-cutting acceptance targets

These targets make reviews repeatable without pretending to guarantee all hardware, audio, dancers, or documents.

- **Data:** Supported project and bundle round trips preserve authored values, order, version references, exact count fractions, and permitted attachments. Ignore only documented incidental fields such as export time. Compare semantic data rather than ZIP byte order.
- **Save feedback:** “Saved” follows successful persistence of the defined draft contract. A failed save remains visibly unsaved. An acceptance target for automatic draft saving is within 5 seconds after editing becomes idle on the reference setup; select and document the actual interval in S01. Recovery tests must report the maximum observed unsaved window.
- **Mechanical validation:** Golden fixtures have exact expected outcomes for counts, supported foot-state rules, facing, and part transitions. Unknown mechanics produce an explicit incomplete-check state. Do not average correctness across examples to hide a known wrong exported count.
- **Timing:** Use the T11–T13 synthetic-fixture targets only on declared supported conditions. Record tempo interpretation, first-count offset, playback speed, device, and measured offset. Treat real recordings with ambiguity as review cases, not compulsory successes.
- **Usability:** Initial proposed sample: at least five nontechnical adult users, including at least two who did not help design the app. At least four of five should complete the Basic creation/save/reopen/export task after a brief standard introduction without facilitator intervention. Record completion time and interventions; this small sample is a release signal, not a population estimate.
- **Accessibility:** Target WCAG 2.2 AA contrast requirements for applicable UI text and controls, keyboard access to core actions, visible focus, and no essential content loss at 200% zoom. Automated checks plus a focused screen-reader task are required; do not call the entire product certified based on a scan.
- **Responsiveness:** S00 records reference-device measurements. Proposed library target: with 1,000 synthetic dance entries and 250 move entries, a local search or filter shows results within 1 second after input settles. Audio/model processing has separate visible progress and honest indeterminate states; do not assign an unsupported universal completion time.
- **Exports:** No clipped essential instructions, missing required counts, orphaned move references, or fabricated credits in the reviewed golden layouts. Long content must wrap or continue visibly. A preview screenshot alone does not prove DOCX editability, PDF links, or printed QR legibility.

## 6. Human instructor and floor testing

Run instructor review before broad floor use. Initial proposed acceptance target: two independent instructors review the supported starter mechanics set and representative generated/manual dances. Record experience and any relationship to the project. Their review is scoped to the tested versions and movements, not an endorsement of the entire catalog.

The mechanics review should cover a one-wall pattern, a two-wall pattern, a four-wall pattern, both starting feet where supported, a syncopated example, a combination with unknown mechanics, and one part/tag/restart example. Check free foot and weight-bearing state after each action, the transition into the next move, facing, count labels, and repeat closure. An unresolved contradiction in a generator-eligible movement blocks that entry's promotion; the rest of the catalog can proceed with accurate coverage labels.

Use a small volunteer floor session to learn whether the actual instructional workflow works. Proposed first session: three to five adult dancers at the intended experience level, using two reviewed beginner routines and one instructor-led edit. Let participants stop or substitute movements freely. Record song fixture, tempo interpretation, room constraints, footwear context if relevant, software version, and routine version. Do not present this small test as a safety certification.

Observe whether dancers can follow the current/next cue, whether calls arrive early enough, whether a loop restarts intelligibly, whether they can see feet in the reference media, and whether transitions feel rushed or awkward. Ask the instructor to identify the precise counts involved rather than only rating “good” or “bad.” Test the same routine at its intended speed and one supported slower practice speed. Do not require unsupported high-speed or advanced movements merely to fill a test matrix.

Capture a concise finding: routine/version, counts, observation, reproduction steps, impact, instructor recommendation, resulting change, and recheck result. Separate mechanical errors from taste/preferences. Collect personal notes or recordings only with permission and keep participant identities and videos out of public evidence unless separately cleared.

## 7. Regression and sprint gates

### Gate A — Every behavior change

Run the smallest affected regression set plus the relevant end-to-end smoke task. A persistence change includes T03 and any affected T18 restore cases. A move model change includes T04–T06, T14, and affected T17/T18 exporters. Timing changes include T11–T13 and affected T16/T18 cues. Import changes include the affected T07/T08 cases plus trusted-catalog eligibility. UI-only changes need focused interaction/visual checks rather than redundant engine suites unless they alter state or input meaning.

Preserve a focused regression for each confirmed defect. Avoid tests bound to implementation details that would prevent harmless refactoring. Do not broaden testing after the material risk has been sufficiently resolved unless a required gate calls for it.

### Gate B — Sprint exit

Each sprint produces the evidence template below, updated feature/test mappings, a demo of the implemented user task, and a list of remaining limitations. Mark the feature slice actually delivered; do not mark an entire multi-sprint feature complete because its first data model exists.

Required emphasis by sprint:

| Sprint | Exit evidence focus |
| --- | --- |
| **S00** | Reproducible baseline inventory; fixture/rights/dependency manifest; existing regressions classified; initial coverage and environment records. |
| **S01** | T02/T03 draft-save contract, recovery drill, migration backup, and project round trip; no misleading saved state. |
| **S02** | T01/T02 Basic/Advanced tasks, resource entry point, and early T33 keyboard/nontechnical walkthrough. |
| **S03** | T04 exact model semantics and independent golden mechanics; compatibility with saved legacy projects and generation inputs. |
| **S04** | T05–T10 reviewed catalog, manual/file imports, attachments, provenance, and generator eligibility; T35 review records. |
| **S05** | T11–T13 timing/rehearsal evidence, T22 per-track foundations where implemented, and retained T16 tutorial behavior. |
| **S06** | T08/T14–T16 creative workflow, locked-block infeasibility, reviewed AI context and responses, stale-plan protection. |
| **S07** | T10/T17/T18 export and restore matrix, rendered/printed samples, portable media relink and exact choreography fidelity. |
| **S08** | T19–T24 complete local instructor/dancer tasks, song swaps, schedules and setlists; offline behavior remains intact. |
| **S09** | T31–T36 clean Windows build/install/upgrade/portable/offline evidence, package rights/privacy checks, local v1 usability and floor findings resolved or explicitly scoped. |
| **S10** | Provider feasibility records: permitted operations, scope/consent, costs, test environment, failure contract, and go/no-go dependency for each T25–T30 adapter. No production operation implied. |
| **S11** | T25–T27 per-provider contract tests plus authorized live smoke evidence and local fallback; unresolved providers remain separately blocked. |
| **S12** | T28–T30 account/visibility/moderation/write/analytics evidence, deployment checks, and external-operation recovery. |

### Gate C — Local v1 release candidate

For the S09 release candidate, run the full deterministic core suite in the declared build environment, the clean install and previous-release upgrade tasks, the complete local Basic task offline, representative Advanced tasks, export/restore checks, accessibility/usability checks, and the scoped instructor/floor review. Verify distributable rights and remove private artifacts and secrets. Review all unresolved failures before tagging a release.

Block release for reproducible data loss, a materially incorrect count/foot/facing claim in a supported reviewed workflow, a bundled secret/private asset, an unauthorized external transfer/write, a broken promised core install/save/export path, or a known unsupported feature presented as verified. Lower-impact limitations may ship only when their impact, workaround, and affected scope are clear and approved in the release decision. Do not waive a blocker by relabeling an incorrect result a warning while continuing to present it as ready.

### Gate D — Connected release

Keep deterministic provider simulations in ordinary CI. Before shipping each adapter, obtain the required authorized live smoke evidence against the actual supported provider and scope. Use a limited test object, avoid charges unless authorized, and document cleanup. Redact credentials and account data from evidence.

For external writes, test final preview, cancellation, explicit submission, partial completion, authentication expiry, and uncertain network completion. A retry must not blindly duplicate a playlist edit, event, or publication. If an adapter lacks a reliable confirmation/reconciliation mechanism, disclose that limitation and constrain the operation accordingly. A provider policy or API change can block that adapter without preventing the offline core release.

## 8. Reusable failure-path set

Apply this set only where it has material relevance, and record the applicable cases instead of testing every combination everywhere:

- Missing/unsupported/corrupt input; unknown mechanics; conflicting aliases; empty/no-match result.
- Save destination denied, disk-full simulation, source moved/deleted, interrupted process, unsupported schema, and restore corruption.
- Long-running job finishes after source replacement or manual edits; repeated click; cancellation where supported; progress stops or errors.
- Optional dependency/model absent; offline first launch; interrupted download; insufficient space; downloaded component not ready.
- Provider timeout, throttling, revoked authorization, denied scope, expired token, malformed response, pagination, and remote conflict.
- External write completes but the response is lost; partial success; retry; moderation pending; final rejection.
- Private, local-only, expired, or unreachable media/link; recipient has different access; print has no clickable interface.
- Basic mode, keyboard-only input, zoomed layout, and a user returning after a long interruption.

A failure is acceptable only when it preserves the user's existing work, reports the actual known state, and gives a useful recovery path. “Something went wrong” by itself is not sufficient for a recoverable known error.

## 9. Sprint completion evidence template

Copy this template into the sprint record. Keep public evidence redacted and link private artifacts through the approved private record rather than copying them into GitHub.

```text
Sprint / scope slice:
Build version / commit:
Date / tester:
Environment and declared support target:
Implemented feature IDs:
Acceptance test groups and individual cases:
Fixture IDs / rights-manifest version:

Results:
- Case ID:
  State: NOT RUN | PASS | FAIL | BLOCKED | NOT APPLICABLE
  Expected behavior / acceptance target:
  Observed behavior / measurement:
  Commands or manual steps actually performed:
  Evidence path/link and redaction status:
  Defect or dependency reference, if any:

Regression set run and result:
Skipped/not-applicable tests and reasons:
Migration/restore impact and evidence:
Accessibility/usability observations:
Instructor/floor review scope and findings:
External calls/writes performed, authorization, and cleanup:
Privacy/license/package review scope:
Known limitations and workarounds:
Remaining blocker(s), owner, next action:
Feature slices complete / still planned:
Release decision: NOT READY | READY FOR NEXT SPRINT | RELEASE CANDIDATE APPROVED
Decision owner / rationale / date:
```

Until these records contain actual execution evidence, the testing status remains **NOT RUN** and this document remains a plan.

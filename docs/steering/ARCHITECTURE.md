# Architecture and implementation handoff

Status: **proposed steering specification; not an implementation report**. Prepared 2026-09-03. Existing behavior is identified explicitly below. Every target model, migration, adapter, and behavior described after the baseline is proposed until its feature test passes and its evidence is recorded.

Feature IDs F01–F36, sprint IDs S00–S12, and matching test IDs T01–T36 follow the shared steering plan. S00–S09 deliver the local freeware release. S10 covers connected-feature feasibility; S11–S12 are later, dependency-gated releases. A listed integration is not a claim that its service grants access, permits redistribution, or has been connected.

## 1. Current application evidence

Audit source: the owner-provided local Line Dancing Application checkout. The baseline below is confirmed by source/file inspection, not a new live execution or acceptance-test run. This architecture pass does not modify the application. Recheck these observations during S00 because later development can change them.

| Area | Confirmed current behavior | Implication for the proposed design |
|---|---|---|
| Application | FastAPI backend, Python engines, vanilla JavaScript frontend; dance interface at `/dance`, with a separate sound-repair interface | Refactor in bounded slices. Preserve working workflows while changing their presentation and shared state. |
| Projects | Individual `app/projects/<id>/project.json` documents; saves use a temporary file and replacement | Retain a portable project document, add explicit schema/version/recovery rules, and make a save cover the whole draft. |
| Reference data | `data/step-database.json` contains **173 records**: 77 step patterns, 52 footwork primitives, 26 concepts, 18 styling entries | A vocabulary record is not automatically a move that the builder can execute or validate. |
| Buildable moves | `engine/steps.py` declares **39 built-in moves**, exposed as 78 right/left variants; 33 built-ins are generator eligible and 6 are editor-only fillers | Do not label the builder as containing 173 usable moves. Report reference, usable, reviewed, and generator-eligible coverage separately. |
| Custom moves | No `data/custom-moves.json` was present during this audit. The implementation supports creating/importing one | Preserve the capability and migrate it if a file is present when implementation starts. |
| Catalog storage | `engine/database.py` builds SQLite catalog rows from the glossary JSON; `all_moves()` uses Python built-ins plus custom JSON rather than that catalog | Eliminate competing definitions through a reviewed, versioned catalog migration. Do not activate every glossary record by copying it into the generator. |
| Current mechanics | Moves hold total whole counts, net rotation, start/end free foot, coarse travel, and a syncopation flag | These aggregates cannot describe all movement timing, weight states, or intermediate facings. |
| Custom restrictions | Custom duration is 1–8 whole counts; turns must be multiples of 90 degrees; travel is forward/back/right/left/in place | Support longer combinations, exact subdivisions, diagonal directions, and unverified mechanics. |
| Manual editor | Can save/validate a dance without audio. UI total-count choices are 16/32/48/64 and wall choices are 1/2/4 | Expose the existing music-optional path, then remove inappropriate model/UI restrictions. |
| Routine structure | `DanceBody` stores a flat sequence, total count target, wall setting, and turn direction | Parts, ordered part sequences, tags, restarts, and endings need first-class data. |
| Checking | Count/foot/wall checks; manual moves crossing an eight-count boundary are reported as errors; right free foot is the default | Keep exact mechanics checks but distinguish real contradictions from display grouping and intentional choreography. |
| Music | BPM methods, beat/downbeat arrays, octave alternatives, drift information, waveform, sections, lyrics, and local alignment/scanning | Preserve their evidence and manual edits; expand timing without replacing it with a single constant-BPM clock. |
| Meter/key | Downbeat calculation assumes four beats per bar; no musical-key detector is implemented | Label existing meter assumptions. Add editable meter and estimated key as separate proposed features. |
| Outputs | TXT/HTML/PDF sheets and related challenge/tutorial outputs already exist | DOCX and additional formats must consume the same normalized sheet model as existing formats. |

Relevant source anchors: `engine/steps.py:33`, `:168`, `:380`, `:436`, `:537`; `engine/assembler.py:786`; `engine/audio.py:269`; `engine/emitter.py:20`, `:96`; `engine/project.py:59`; `server.py:128`, `:287`, `:428`; `static/index.html:313`.

Two current correctness risks must have regression fixtures before replacement:

1. **Custom mirroring changes mechanics without necessarily changing instructions.** `Move.variant()` substitutes placeholders such as `{F}` and `{O}`. User prose such as “Rock R diagonally forward” contains literal R/L text, so a left variant can retain right-foot instructions. Never produce a reviewed mirrored variant merely by flipping mechanical fields. Use event-derived wording or explicitly reviewed text for each variant.
2. **Custom projects reference live move IDs.** Current custom sequences store `{move_id, lead}` and resolve definitions from the current library. Updating or deleting the library record can change or break an earlier dance. Project snapshots must preserve the definition actually used.

## 2. Proposed architectural decisions and ownership

The proposed application has one local domain model with several views. Basic and Advanced are a **detail preference**, independent of a dance's difficulty level. Switching views must not create another copy of the project, discard hidden values, or downgrade available choreography. Manual and music-assisted entry paths open the same project model. [F01–F04; S01–S03; T01–T04]

The product requirements are user-directed; the storage layout and internal service boundaries below are engineering recommendations, **not a user-selected stack migration or an approved rewrite**. During S00/S01, compare the recommendation with the least disruptive implementation that satisfies the invariants and record the chosen approach and tradeoffs in the decision log before changing persistence. Retaining FastAPI/Python/vanilla JavaScript is the working baseline; a framework replacement is not required by this plan.

The main boundaries are:

| Boundary | Owns | Must not own |
|---|---|---|
| Project service | Project identity, draft, accepted revision, history, saves, migrations, task result application | Provider secrets or mutable global definitions on which old dances depend |
| Choreography engine | Movement events, parts/routine expansion, mechanical checks, facing and weight propagation | UI-specific count arithmetic or assumptions that every dance must loop in eight-count blocks |
| Catalog service | Terms, aliases, explicit movement variants, source/review records, versioned definitions | Silent promotion of imported prose to verified choreography |
| Music-map service | Recording identity, measured timing, user corrections, sections, lyric alignment, per-track dance alignment | Rewriting authored parts/tags/restarts to fit detected music sections |
| Presentation service | Shared sheet, cue, rehearsal, and tutorial presentation records | A separate interpretation of choreography for each output format |
| Local library service | Dance collections, links, practice records, lessons, alternate-song mappings, local events | Public accounts, public event moderation, or assumptions that a third-party site is a licensed data feed |
| Integration adapters | Explicitly requested provider interactions, external identity mapping, reviewable proposals | Direct unreviewed mutation of accepted choreography, hidden background uploads, or provider-specific IDs as native IDs |

## 3. Proposed storage and project lifecycle

### 3.1 Native document and local database

The recommended storage design keeps a versioned native project document as the authoritative, portable record for an individual dance. A local SQLite store would manage the versioned move catalog and cross-project library metadata. Search indexes and denormalized summaries would be rebuildable; the project and its embedded movement snapshots must remain readable if an index is lost. Managed media would live outside database rows, referenced by manifest entries and content hashes. This proposed division extends current JSON/SQLite use rather than assuming a wholesale data-store migration. [F03, F05, F06, F18, F19]

Use stable generated IDs, explicit schema versions, and timestamps. Names and filenames are display values, not identifiers. Do not change an ID when the user renames a dance, move, part, or recording. Database migrations must distinguish authoritative tables from disposable indexes.

Illustrative project fields, subject to a reviewed schema before coding:

```text
project
  schema_version, project_id, document_revision
  metadata: title, choreographers[], contacts[], credits[], level_label, notes
  draft: choreography, sheet_options, pending_edits, selected_track_mapping
  accepted_revision_id: optional
  revisions[]: id, created_at, label, parent_id, document_hash, snapshot_reference
  movement_snapshots[]: definition_id, version, hash, events, text, provenance
  recordings[]: recording_id, media_reference, descriptive_metadata
  music_maps[]: map_id, recording_id, analysis, manual_overrides, revision
  track_mappings[]: mapping_id, recording_id, choreography_revision, alignment
  links[], media_manifest[], tutorial_plans[], review_records[]
```

This is a proposed field map, not an API contract. Large immutable revision snapshots may live in a project history directory; native bundles must include the revisions selected for export and identify whether the full history is included.

### 3.2 Draft, accepted revision, and export

- The editable **draft** is saved even when incomplete or invalid. Saving means preserving the user's work, not certifying it.
- An **accepted revision** is an explicit choreographer decision and records its check results, review status, source snapshots, and hash. It can still have disclosed unverified mechanics; acceptance must not relabel unknown facts as verified.
- Undo/Redo operates on authored document edits through a command history. Keep the current draft recoverable after a crash; do not rely exclusively on an in-memory Undo stack.
- Autosave and the main Save command serialize every editable part of the draft, including the sequence and its settings. UI state distinguishes unsaved changes, saving, saved, and save failure. A failed save cannot display success.
- Export and rehearsal identify whether they use the current saved draft or a named accepted revision. Draft exports retain relevant warnings and a version identifier. Acceptance is not required merely to save or print useful work.
- A provider result or analysis job is a proposal until its source revision is checked. On conflict, show the result for review rather than overwriting newer user edits.

Use atomic replacement, a last-known-good recovery copy, and optimistic revision checks. A document write and its related authoritative database changes need a recoverable operation record if they cannot share a transaction. Avoid introducing a full event-sourcing system solely for Undo. [F03, F14, F17; S01, S06–S07; T03, T14, T17]

## 4. Proposed choreography model

### 4.1 Exact movement timing

Represent count offsets and durations with reduced rational values, not floating-point additions. A movement event has an onset, duration or instant marker, instruction, and optional mechanical facts. This permits straight counts, `&` counts, sixteenth subdivisions, triplets, holds, and pickup events. A label formatter converts those values into the chosen teaching notation; a syncopation Boolean cannot be the timing source. [F04; S03; T04]

```text
movement_definition_version
  id, version, names[], aliases[], category, variant_label
  duration_counts: rational
  events[]
    event_id, offset_counts: rational, duration_counts: rational
    action_text, count_label_hint: optional
    moving_foot: right | left | both | neither | unknown
    support_before/support_after: known state or unknown
    rotation: optional signed rational turn
    facing_constraint: optional
    travel: optional qualitative direction or reviewed displacement
    styling/callout/teaching_notes: optional
  allowed_entry_states, exit_state_rule
  mirror_policy, reviewed_variants[], review_status
  provenance[], media[], generator_eligibility
```

Unknown is a real state and must propagate. If an author supplies count duration and text but no mechanics, the app can verify the count budget and display the instruction. It cannot prove subsequent foot continuity through that unknown movement. Show precisely which checks remain unverified.

Model weight/support explicitly where available: left, right, both, neither, or unknown. “Either foot” describes a conditional entry rule, not evidence that any claimed output state is correct. Do not infer all mechanical correctness from odd/even weight-change parity or from movement names.

Store turn magnitude and direction without restricting the author to quarter turns. Clock-facing labels may display eighth turns/diagonals; exact values remain in the model. Distinguish an absolute facing from a relative turn. Do not claim a distance in steps or meters from a coarse “travels forward” label.

Mirroring must transform the reviewed events and generated text together. A record containing only free prose is non-mirrorable by default. An author can add a separately reviewed opposite-lead variant. Longer combinations may reference component definitions during editing, but accepted project snapshots must resolve those dependencies reproducibly. [F05, F06; S03–S04; T05, T06]

### 4.2 Parts, routine order, and exceptions

A choreography contains named parts and an explicit routine specification. Parts contain ordered movement occurrences with stable IDs; an occurrence can preserve an intentional instance-specific variation without rewriting the catalog. Total counts can be derived from content or compared with an author-supplied target. Provide common presets alongside custom values, including waltz-oriented totals and longer combinations. [F04]

The routine represents part order/repetition, tags, restart points, and endings as structured events. Example intent: “A twice, B once; restart A after count 16 on its third occurrence; add Tag 1 after B; finish with Ending 1.” The stored boundary must say whether an event happens before or after the named count/sub-count; do not leave “restart at 16” ambiguous.

Distinguish **routine occurrence/pass number** from **physical facing wall**. For irregular/phrased dances they are not interchangeable. Restart rules and modified endings may apply to a particular occurrence or facing condition. Validate that the transition reaches a declared entry state, including intentional foot changes at a restart.

The initial free/supporting foot, facing, and repeat policy are authored properties. Validate a repeating phrase at the boundary where it actually repeats. Do not require every part, tag, ending, or nonrepeating routine to finish with the initial free foot or a fixed 1/2/4-wall result.

Teaching blocks are a presentation choice: normally eight counts, optionally six for waltz and other authored grouping. Crossing a display boundary is not automatically a choreography error. The formatter splits or continues instructions while preserving their timing and identity. Generation can use conservative block constraints for a chosen generation style without imposing those constraints on all manual dances.

### 4.3 One compiler and occurrence timeline

Build one shared choreography compiler:

```text
saved document + chosen revision + movement snapshots
          -> routine expansion and exact event timeline
          -> counts, entry/exit state, facing, issues, occurrence provenance
          -> sheet / rehearsal / cue / tutorial presentation records
```

The expansion result carries a source hash, stable occurrence IDs, original part/move IDs, exact count positions, and state before/after each event. All consumers use this result. **Do not implement another choreography runtime in the player, DOCX/PDF exporters, subtitle exporter, or tutorial generator.** Frontend animation may interpolate position/time for display, but it must not independently decide move duration, restart behavior, foot state, or facing. [F04, F13, F16–F18]

Validation issues are structured: code, severity, affected occurrence/event IDs, count range, evidence, and possible action. Use separate states for contradiction, unverified mechanics, advisory style guidance, and unavailable music evidence. The editor can navigate directly to the affected occurrence. Missing audio is not a mechanical failure in a manually authored dance.

## 5. Proposed music map and alternative recordings

A recording, a musical work/song, and a dance are different entities. One song can have many recordings and dances; one dance can suit several songs. Keep external service IDs as mappings, not identity for the native dance. [F11, F12, F22, F25, F26]

Each recording has its own music map: detected beat times, downbeat evidence, tempo estimates and alternatives, meter estimate/selection, section markers, lyrics/alignment, key estimate, confidence, and analysis provenance. Record the audio fingerprint/hash and algorithm version. Manual corrections are separately identifiable and take precedence when a new analysis proposes replacements.

An estimated key is advisory metadata with confidence and a user override; it is not a prerequisite for choreography or a reliable judgment that a song suits a dance. Do not label the current four-phase downbeat assumption as proven meter. Add manual meter first, then qualify any detection capabilities against real fixtures.

A **dance-to-recording mapping** owns first-count alignment, count-to-beat scale, applicable tempo grid, a selected authored routine variant/revision, suitability notes, and user review status. Actual tags/restarts remain structured choreography in that selected routine; the mapping must not introduce its own restart execution logic. A song swap requiring different tags creates a reviewed routine variant, preserving the prior one. Half/double-time changes belong in the timing mapping or in an explicitly selected music-grid revision; they cannot silently rescale accepted choreography. Preserve old mappings when the user selects another track.

Rehearsal converts exact choreography count positions to seconds through the selected mapping and beat grid. Use piecewise beat-time interpolation where needed for variable tempo. A fixed `count * 60 / BPM` clock is appropriate only for an explicit constant-tempo fallback. Without music, the same timeline runs against an authored practice tempo and is clearly identified as practice timing.

Pitch-preserving slowdown is a local audio-transport capability, with the source-recording time remaining the reference for cues and positions. Changing speed, pausing, seeking, or repeating a loop must update the transport mapping without changing authored count durations or producing a second choreography timeline. The metronome, current/next-move display, call cues, and full-screen teaching view consume that same transport position. Test pitch preservation, seek/loop behavior, and cue alignment against the supported playback range rather than assuming a browser rate control guarantees them. [F13; T13]

Section scanning, lyric alignment, key estimation, and other jobs retain their input hash/revision. Results from replaced audio cannot attach to the new recording. Newly completed automatic sections cannot overwrite manually changed markers. These guards preserve existing regression behavior. [S05; T11–T13, T22]

## 6. Proposed catalog, imports, discovery, and media

### 6.1 Catalog coverage and review

Keep terminology, buildable definitions, and generator eligibility distinct and queryable. A single catalog service can expose all three without pretending they are equivalent. Seed migration should retain provenance from the 173 glossary records and preserve the exact currently buildable definitions as separate versioned records until reviewed reconciliation is complete. Never choose one source's mechanics solely because its display name matches another. [F05, F35]

Proposed statuses: terminology-only; authored/unverified; mechanics-reviewed; generation-approved; deprecated. A deprecated definition remains resolvable by historical snapshots. Generator eligibility is an explicit version-specific approval plus constraints, not a consequence of importing a name and counts.

Coverage reports should list known reference names, aliases, explicit variants, missing definitions, and review gaps by movement family. The release claim is an extensible library supporting new authored moves, with a reported reviewed subset. It is not “every possible line-dance move is verified.” An independent instructor review supplies evidence beyond self-reported metadata.

### 6.2 File and optional AI imports

All import sources feed a common proposal/review pipeline:

```text
authorized source -> extraction -> candidate records with evidence
   -> duplicate/alias matching -> author review -> saved draft definitions
   -> separate mechanics review -> optional generation approval
```

Retain incomplete rows in a review queue rather than rejecting them permanently or inventing missing mechanics. Preserve original row/page/table coordinates, original text, extraction method, and confidence. An AI-created description is a proposal, not a source citation or verification.

Provide import templates and a column/field-mapping preview before applying file rows. Assign each applied batch an ID and record exactly which versions it created or changed, so rolling back that batch restores affected definitions without removing unrelated later edits. Review candidates and source evidence remain inspectable after partial acceptance. [F07, F08]

Support the requested structured/text formats through adapters: JSON, CSV/TSV, XLSX, DOCX, TXT/MD, text PDF. OCR is optional for scans and must retain image/page provenance for review. A sheet import must distinguish title/credits/count instructions/parts/tags from a move-library import. Do not flatten a phrased sheet into one repeated sequence. [F07, F08; S04, S06; T07, T08]

Parse document archives and bundles with file-size, expansion, and path limits. Import scripts/macros are never executed. Sanitize active markup and external links for rendering. Unknown custom records remain useful as authored text while checks disclose the mechanics gap.

### 6.3 Move media, links, and portable bundles

Media attachments have an ID, hash, media type, optional local managed path, source URL, caption, attribution/rights note, orientation/view, and optional in/out times. A reference can be a photo, diagram, video, or external link. Text instructions remain available without loading media. Associate media with a definition version or occurrence, so a changed demonstration cannot silently rewrite a historical reference. [F09]

Thumbnails and any transformed views are derived assets with their own reference to the original. Never overwrite the original to mirror a demonstration. Display orientation clearly; a mirrored image/video is not evidence that asymmetric mechanics or literal instruction text has been reviewed. Attaching a clip does not imply that the application or configured AI can recognize its movements.

Use URLs only as URLs; validate supported schemes and never treat supplied paths as executable content. Preserve link labels and provenance. Store optional last-checked status separately from the user's URL. A failed availability check marks a link for attention rather than deleting it. [F10, F24]

PDF/Word sheets may include hyperlinks and print QR codes generated from the same validated target. A QR code is an access convenience, not offline content. Private localhost/file links must be identified as local references and should not be presented as publicly reachable resources. Validate the digital and printed destinations in export testing.

Native bundles include a manifest, project data, embedded move snapshots, permitted managed media, and optional selected history/lesson content. The manifest states which linked media is external or omitted. Include only media the user is entitled to redistribute. On restore, verify hashes, use safe extraction paths, and offer media relinking for missing files. A bundle must not depend on the exporting computer's absolute paths or contain provider credentials. [F18, F34]

## 7. Proposed local dancer and instructor records

The local library indexes dances and their revisions without duplicating authoritative choreography. Add folders/collections, tags, favorites, permitted offline sheets, and searchable credits/levels. Cache a reference only when authorized; a directory link does not grant permission to copy a site's database. [F19, F24, F27]

Local practice records reference a dance and optionally a specific revision/part. Categories such as want to learn, learning, practiced, and confident are user-managed progress, not inferred skill ratings. Practice checklists and notes remain local unless a later explicit sharing action exports them. [F20]

Lesson/class setlists reference ordered dance revisions and selected song mappings, with teaching notes, breaks, durations, and optional checklist status. Printed and digital class guides use these records. A setlist can select a published revision while the underlying project has a newer draft. [F21]

Local class/event entries hold date, timezone, optional location, linked setlist, notes, and calendar identifiers. ICS import/export must preserve timezone and all-day semantics. Import previews retain external event UIDs and offer explicit duplicate/update handling; imported recurrence data must either round-trip correctly or disclose unsupported cases before application. This local schedule is a distinct feature from a hosted public event directory: no account or public location publication is required for local scheduling. [F23, F28]

Alternative song suitability is reviewable evidence: count scale, phrasing fit, intro, duration, tempo comfort, explicit tags/restarts, and instructor notes. A tempo match or recognized song title alone does not prove choreographic suitability. [F22]

## 8. Proposed optional integration boundaries

Provider integrations are adapters behind capability flags. The local manual editor, library, rehearsal with local media, and supported exports must work without service accounts or network access. Show capability-specific connection state; opening Basic mode must not start provider work. [F01, F25–F30, F33, F34]

**User-directed AI boundary:** this freeware application does not provide an app-owned AI service. Connected AI uses only the user's chosen provider/account/endpoint and their own credential, with provider charges paid by that user. Never ship a developer/shared key, credit pool, app-operated AI proxy, or automatic fallback to one. If the user's provider is unavailable, retain the draft and report that state; do not route its content elsewhere. Optional local-model plugins use models managed by the user and must not become a mandatory dependency of the core application. Every AI result, including lyrics, discovery, extraction, and choreography suggestions, is a proposal requiring the relevant user review. [F08, F15, F31, F34]

The selected model and its supported input types are part of the connection's capability record. A text-only endpoint cannot be offered as image/video analysis. Show the exact selected material before transmitting it to a provider; do not silently attach the rest of a project or its media. A user-managed local/self-hosted endpoint follows its actual authentication requirements and never receives an app-supplied shared credential.

| Integration | Native input/output boundary | Required handoff before implementation |
|---|---|---|
| AI setup, lyrics, move discovery | Explicit selected context in; versioned proposal/revision out | Provider capability, cost/model disclosure, credential storage, request review, and no automatic choreography acceptance [F08, F15] |
| Microphone/clip recognition | User-started clip in; ranked recording/work identity candidates out | Permission, retention behavior, ambiguous-match handling; dance matching is a separate many-to-many search [F25] |
| Spotify/YouTube playlists | External playlist/item IDs mapped to native recordings and setlists | Actual API/scopes/terms feasibility, OAuth lifecycle, unavailable items, duplicate/order conflicts, rate limits, local fallback [F26] |
| External sheet discovery/import | Authorized result/link or permitted file into the import review pipeline | Access method and content rights, attribution, caching/redistribution limits, robots/API constraints as applicable [F27] |
| Public events/maps | Explicit local-to-public event proposal | Hosting, account roles, moderation, abuse handling, public-location consent, operational owner [F28] |
| Direct publishing | Frozen reviewed export plus submission payload | Site adapter feasibility, user review of exact payload/destination, final explicit submission, returned receipt/status [F29] |
| Analytics | Authorized observations with source/time/metric definition | Scope, retention, privacy, opt-in behavior, and distinction between observed and unavailable metrics [F30] |

Secrets belong in a platform credential facility, not projects, SQLite catalog records, logs, exports, or GitHub releases. Existing Windows protection is a baseline to preserve. Use scoped tokens and revocation where supported. Logs redact secrets and limit user content. Optional model downloads must be separately identifiable, resumable where supported, and excluded from the default source/release payload. [F15, F32, F34]

Remote writes use reviewable payloads and idempotency/deduplication where the provider allows it. After an uncertain response, inspect status before retrying a publish or playlist mutation. Do not create a generic sync engine that assumes every provider supports the same operations. S10 feasibility records determine which S11–S12 adapters are buildable.

## 9. Proposed migration strategy

1. **S00: capture the real baseline.** Inventory project schemas, existing custom records, generated candidate snapshots, glossary versions, exports, dependencies, and rights. Create representative fixtures and backups without changing users' source songs or accepted project content. Record hashes and tested application version. [T03–T07, T11, T14, T16–T18, T31–T36]
2. **S01: wrap legacy projects with explicit lifecycle.** Add schema version, document revision, complete draft save, history/recovery, and source hashes. Preserve original documents for rollback. Do not claim the old main Save already covered sequence edits. [T03]
3. **S03: migrate choreography conservatively.** Convert a flat legacy sequence to a named default part with the same ordering and loop settings. Snapshot the exact current definition used by each move. Generated candidate dictionaries may already contain expanded definitions; prefer their stored snapshot where authoritative for that candidate. Flag missing custom IDs and text/mechanics contradictions for review; never substitute a similarly named move silently. [T04, T06]
4. **S04: unify catalog access.** Import built-ins, custom definitions, and glossary records with distinct source/review categories. Maintain legacy-ID mappings. Retain frozen legacy text until any correction is explicitly reviewed, so existing exports can be reproduced. [T05–T09, T35]
5. **S05–S08: add maps and local metadata.** Existing audio analysis attaches to its specific recording; existing manual sections remain manual. Add rehearsal alignment, alternate-song mappings, media manifests, local library/progress/events through versioned migrations with sensible absent-data defaults. [T11–T13, T18–T24]
6. **S09: package only migrated, tested assets.** Include a tested upgrade path, rollback instructions, clean install checks, third-party notices, and release evidence. Run on a clean Windows environment, not only the developer machine. [T31–T36]

Migrations are deterministic, idempotent, transactional where possible, and tested against older fixtures. A migration failure preserves the previous file/database and produces an actionable diagnostic. Reject unsupported future schema versions with a clear message rather than loading and silently discarding fields. Never run destructive migrations as part of ordinary read-only export or search.

## 10. Core regression invariants and testing phases

These invariants apply across the feature-specific test plan. Tests must assess meaningful behavior, not mirror implementation details.

| Invariant | Required evidence / related tests |
|---|---|
| Basic/Advanced and start-path changes preserve project content | Round-trip mode changes with unsaved/draft values and an advanced dance; music-optional creation/export [T01–T04, T33] |
| Save preserves all authored work and tells the truth | Edit sequence, metadata, timing and sheet options; save/reopen; failed write; crash recovery; Undo/Redo and named revision cases [T03] |
| Historical dance definitions are immutable | Update/delete catalog move; old revision and restored bundle still render the same timing/text; missing legacy ID is disclosed [T03, T06, T18] |
| Exact timing survives every representation | Straight, offbeat, `1,2&`, pickup, triplet, long combo, 24/40/custom count, waltz grouping, boundary-crossing movement fixtures [T04, T13, T17, T18] |
| No false validation through unknown mechanics | Count-valid prose move retains unverified foot/facing status; subsequent checks identify uncertainty instead of assuming a foot [T04–T08, T14] |
| Mirroring preserves text/mechanics agreement | Reviewed right/left event variants; literal custom prose remains unmirrored until reviewed; asymmetric moves refuse automatic mirroring [T06] |
| Routine exceptions have one meaning | Phrased A/B order, repeated tags, partial and modified restarts, one-time ending; same occurrences/counts/facings in editor, player, tutorial, sheets and subtitles [T04, T13, T16–T18] |
| Manual music decisions survive automatic jobs | Delayed analysis/alignment result after audio replacement or marker edit; half/double-time change; per-track first-count alignment [T11, T12, T22] |
| Imports remain reviewable and nonexecuting | Mixed valid/incomplete rows, duplicates, table/page evidence, OCR uncertainty, malformed archive/path, no automatic generator promotion [T07–T09, T18, T35] |
| Portable outputs are consistent and usable | PDF/DOCX/TXT/HTML counts/credits match; long names, links/QR, A4/Letter/large print; authorized media bundle restored on another machine [T09, T10, T17, T18] |
| Local metadata stays local and references stable entities | Song swap does not rewrite dance; progress survives rename; setlist pins revision; ICS timezone survives export [T19–T24, T34] |
| Disconnected operation remains useful | Fresh offline project, manual build, local rehearsal, exports and restoration; optional services visibly unavailable without blocking core [T25–T30, T33, T34] |
| AI is optional and uses only the user's configured resources | No key/model configuration still permits core work; provider failure never triggers a developer proxy/shared-key fallback; provider requests use selected context and all returned content remains reviewable [T08, T15, T31, T34] |
| Release licensing and privacy are auditable | Per-source rights/attribution inventory, allowed notices, license exception reflected consistently, clean bundle with no credentials/private songs/projects [T31, T32, T34, T35] |

Testing proceeds in phases: baseline characterization in S00; schema/save/migration regressions in S01; menu/start-path/mode-preservation and resource-directory checks in S02; exact choreography and catalog contract tests in S03–S04; real audio and player integration fixtures in S05; constrained generation and stale-proposal tests in S06; rendered/export/restore verification in S07; local instructor workflow tests in S08; clean Windows installation, accessibility, offline, independent instructor/floor review, and release evidence in S09. Connected adapters receive contract tests, mocked failure cases, and authorized sandbox/end-to-end checks after S10 establishes feasibility. [F36; T36]

Keep existing audio, lyric alignment, anchored generation, emitter, and tutorial regressions unless a documented intended behavior changes. Floor review complements automated timing/mechanics tests; it cannot be replaced by a count-valid label. Verification status reports the tested behavior and reviewed subset, not “all moves are safe” or “all songs fit.”

## 11. Rights and implementation handoff

The existing vocabulary was developed using common-step references and a seed catalog. Private research history is retained separately. Attribution alone is not redistribution permission for expressive explanations or source documents. Preserve the common movement identities while reviewing the actual shipped descriptions and assets. A new independent 173-entry explanation draft is available for instructor/content review; no private source PDF is included in the public candidate. Preserve source-level rights records and do not claim new ownership of common steps. [F05, F31, F35]

The proposed freeware restriction applies to this software under the chosen license, with the user's explicit allowance for earning from the dances they create for paid events. It cannot override dependency licenses or third-party media/text rights. Keep license enforcement out of choreography semantics: earning money at an allowed dance event does not alter validation, saving, or exports. Final license text and release rights are separate release gates. [F31]

Implementation handoff requirements:

- Start each sprint from its scoped feature IDs and attach evidence to the matching test IDs; do not treat this document as permission to implement every connected service immediately.
- Before S03 coding, review concrete native-document, movement-event, routine-event, and compiled-timeline schemas using fixtures for a simple legacy dance, an unknown custom move, a waltz, and a phrased routine with a modified restart.
- Before changing persistence, demonstrate migration/rollback and historical move-snapshot behavior on copies of representative projects.
- Before connecting an output/player, prove that it consumes the shared compiled timeline/presentation records and has no divergent count/turn/restart algorithm.
- Before accepting a catalog expansion, provide coverage, provenance, variant review, and generation-eligibility evidence; adding vocabulary alone does not complete the playable catalog.
- Record any unresolved API, rights, provider, or instructor-review dependency in the roadmap. Preserve the feature in the backlog with its explicit gate rather than quietly dropping it or claiming it has shipped.

### Catalog clarification — 3 September 2026

The subsequent catalog cleanup retains every one of the 173 original entries, their ordered names/aliases, and all mechanical fields. The 39 executable definitions are unchanged. Reference history remains private; selected prose and editorial notes were revised. Common move removal requires a common replacement plus legacy project compatibility, as recorded in DECISIONS. This is a focused cleanup, not completion of the planned catalog redesign.

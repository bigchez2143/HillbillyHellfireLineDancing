# Phases, sprints and delivery gates

Backlog revision: 3 September 2026. Implementation update: 4 September 2026. See [the dated sprint status and evidence](IMPLEMENTATION-STATUS.md). The stories below remain the complete target scope; a tested local slice does not imply every acceptance gate is finished.

## How to use this backlog

Deliver S00–S09 as a useful local freeware release. S10 investigates connected services and can run alongside local work; only approved, feasible slices proceed into S11/S12. Do not let an unavailable external provider prevent someone from writing, rehearsing or printing a dance.

A sprint here is a bounded outcome, not a promise that all listed work fits a week or two. S00 measures the baseline and sizes the stories. Split large sprints into the named story slices while preserving their exit gate. No calendar date, team capacity or cost estimate has been established. After S00, publish estimates and capacity assumptions before setting a release date.

IDs are stable: F01–F36 are requirements, T01–T36 their test groups, S00–S12 delivery increments. Story IDs such as S01.2 identify work within a sprint. Detailed acceptance scenarios and proposed numerical targets live in TESTING; reference them rather than inventing competing targets here. F33 accessibility, F34 privacy and F36 evidence apply throughout.

## Phase summary

| Phase | Sprints | What the user can demonstrate at its exit |
|---|---|---|
| A — Preserve work and simplify use | S00 baseline; S01 saving; S02 menu | Open an existing project, make edits safely, recover them, and find tools in Basic or Advanced |
| B — Author and extend the library | S03 choreography; S04 moves/media/imports | Build a dance with parts, tags and restarts; add a missing move and its teaching media |
| C — Music, rehearsal and creation | S05 music/player; S06 creator tools | Correct song timing, rehearse with cues, preserve favorite blocks and optionally use a personal AI connection |
| D — Share and teach | S07 exports/restore; S08 local class tools | Print a readable sheet, open it in Word, restore an editable package and prepare a class |
| E — Release the freeware | S09 Windows/GitHub | Install on a clean supported Windows machine and complete the core workflow offline without AI |
| F — Connected capabilities | S10 feasibility; S11 adapters; S12 hosted services | Use only the services with verified access, rights, cost ownership and tested failure behavior |

Main dependency chain: S00 → S01 → S02/S03 → S04 → S05/S06 → S07 → S08 → S09. This shows delivery order, not a requirement to serialize all engineering: menu work can proceed beside the domain model after the save contract is stable; export and local library work can overlap once schemas settle. S11 requires S10 plus the relevant local foundations; S12 additionally requires an approved hosting or provider publishing design.

## S00 — Reproducible baseline and release inventory

**Dependencies:** None. **Features:** F03, F31–F36 and the existing functionality underlying F01–F30.

- **S00.1 Baseline:** inventory routes, screens, tests, formats, local tools and optional AI/model dependencies. Run the existing tests on an isolated copy, record actual results/environment and demonstrate the current critical user journeys. Capture known failures separately from new regressions.
- **S00.2 Fixtures and protection:** create backed-up legacy projects, synthetic timing tracks and independently reviewed move fixtures. Record source hashes before any migration. Protect existing songs, personal settings and projects from test mutations.
- **S00.3 Rights and distribution:** inventory bundled glossary text, example sheets/images, software dependencies, codecs, fonts and model licenses. Classify cleared, replace, permission needed or exclude; create a public-fixture manifest and release exclusion list.
- **S00.4 Plan sizing:** confirm supported Windows targets and proposed architecture; estimate/split the stories. Prepare clean local source versioning and a GitHub publication plan; record the later repository owner/name/visibility choice. Public repository creation is not required for this gate.

**Demonstration:** a dated baseline report with reproducible commands, the actual Save gap, buildable/reference catalog counts and a protected legacy fixture.

**Tests/gate:** establish T03, T11, T14, T16–T18 and T31–T36 baselines. Every failure has a disposition; no historical pass count substitutes for a run. Baseline can finish with documented existing defects, but a regression introduced by baseline tooling cannot remain unexplained. Ready-to-build stories and release-content inventory exist.

## S01 — Saving, history and migration

**Dependencies:** S00. **Features:** F03; foundational parts of F06/F18/F34.

- **S01.1 Project contract:** versioned documents, movement snapshots and explicit working draft versus accepted revision. Preserve legacy files and identify unsupported fields rather than dropping them.
- **S01.2 Complete Save:** Save/Ctrl+S includes manual choreography, song/section/lyric edits, sheet details and tutorial review state. Show unsaved/saving/saved/failure accurately; incomplete drafts remain saveable.
- **S01.3 Confidence tools:** Undo/Redo for meaningful authored edits, autosave recovery, named versions and restore preview. Restoring creates a recoverable new state rather than destroying later work.
- **S01.4 Failure handling:** atomic writes, last good copy, stale-job/revision checks, interrupted-save handling and migration rollback. Handle missing custom definitions visibly.

**Demonstration:** change a manual dance, save, close/reopen, recover an interrupted session, restore a named revision and open an old project with identical authored content.

**Tests/gate:** T03/T06/T18/T34/T36. No loss of covered edits; failure never reports success; changing a library definition cannot silently change an old project. Accepted choreography changes only through an explicit apply/accept action. Draft save does not require acceptance.

## S02 — Menu, Basic/Advanced and starting paths

**Dependencies:** S01 save contract; menu inventory from S00. **Features:** F01/F02/F24/F33.

- **S02.1 Navigation:** implement the PRODUCT menu and tools hub; map every old control to its new location. Keep consistent project status and a clear next action.
- **S02.2 Detail preference:** Basic is the default for a new ordinary dancer; Advanced exposes technical generation, AI, lyric/stem and production settings. Preserve all values when switching. Dance difficulty remains separate.
- **S02.3 Start paths:** Start without music and Start with music open the same project/editor. Use a clear file picker/drop target; keep technical local-path controls under Advanced if still needed.
- **S02.4 Help/resources:** plain-language explanations, readable contrast, keyboard navigation and a curated sheet/resource directory with custom links and last-checked status.
- **S02.5 Hillbilly Hellfire promotion:** add a small, non-sticky footer message in the software, visible in Basic and Advanced and on the Line Dance Creator and Sound Repair Studio workspaces. Suggested copy: “Discover Hillbilly Hellfire — visit our YouTube channel and website.” Provide clearly labeled YouTube and Website links using the owner's verified official URLs. Keep the statement separate from project controls and readable in both themes. This is a simple publisher message; use no embeds, autoplay or tracking. The exact link destinations must be verified before implementation; no URLs have been guessed. Scope is the software interface, with ordinary dance-sheet exports unchanged. [F01; T01]

**Demonstration:** a nontechnical dancer starts without a song, finds the move library, saves, adds music later, switches detail modes and finds sheet websites without losing work.

**Tests/gate:** T01/T02/T24/T33, relevant T03 regressions. All existing functionality has a reachable home. Core actions do not demand AI setup. Run the first observed usability round before adding more screens.

## S03 — Flexible choreography and actionable checks

**Dependencies:** S01; UI integration with S02. **Features:** F04; foundations of F05/F06/F13/F17.

- **S03.1 Movement mechanics:** exact count subdivisions, support/weight states, initial foot/facing and flexible turns; unknown mechanics are represented honestly.
- **S03.2 Dance structure:** named parts, routine order, pickups, tags, restarts and endings; distinguish routine occurrence from physical facing wall. Support custom totals and meter/grouping, including waltz-oriented authoring.
- **S03.3 Shared interpretation:** compile one versioned occurrence timeline used by validation, editor, rehearsal, sheets and tutorial outputs. Avoid separate count logic in each view.
- **S03.4 Useful feedback:** display count blocks and facing cues; clicking an issue goes to its move/count/occurrence. Separate errors, unverified facts and style advice. A move crossing an eight-count display boundary is not inherently invalid.

**Demonstration:** author an ordinary 32-count dance and a phrased example with a tag/restart; show a syncopated move, diagonal turn and six-count grouping without forcing false eight-count boundaries.

**Tests/gate:** T04, relevant T03/T05/T06 and presentation contracts for T13/T17/T18. Exact arithmetic and reviewed mechanics fixtures pass; unknown facts do not become verified. The shared timeline agrees across consumers.

## S04 — Move library, common-file imports and media

**Dependencies:** S03 model and S00 rights inventory. **Features:** F05/F06/F07/F09/F35.

- **S04.1 Reviewed catalog:** migrate current buildable moves, reference terms and aliases into clearly distinguished records. Publish an instructor-reviewed coverage matrix across levels, families, lead variants and timing; identify remaining gaps.
- **S04.2 Add any missing move:** manual entry and reusable combinations, editable instructions, rational timing, mechanics/review state, explicit variants and immutable version snapshots. Descriptive moves remain usable while their mechanics are incomplete.
- **S04.3 Import center:** templates, column mapping, source preview, duplicate/variant decisions and row-level errors for XLSX/CSV/TSV/DOCX/TXT/MD/JSON/text PDF. Distinguish importing a move catalog from importing a whole sheet. Apply a reviewed batch transactionally and support batch rollback.
- **S04.4 Teaching media:** photos/diagrams, multiple video files/URLs, thumbnails, captions, time ranges and view orientation. Preserve originals; handle missing/relinked assets and do not invent an automatic left-lead demonstration.
- **S04.5 Contributions:** source/permission records and separate instructor/mechanical review before promotion into the default library or generator.

**Demonstration:** add a move missing from the built-ins, attach a demo, import a spreadsheet with a duplicate and a bad row, approve selected changes, use the move in a dance, then change the library version without changing that dance.

**Tests/gate:** T05/T06/T07/T09/T35 plus save/recovery regressions. Report actual reviewed coverage. No finite number is marketed as “every move”; extensible authoring must prevent the catalog from being a ceiling. File import works with no AI connection.

## S05 — Music mapping and rehearsal

**Dependencies:** S03 timeline; S04 movement/media model. **Features:** F11/F12/F13.

- **S05.1 Preserve analysis:** BPM methods, beat/downbeat evidence, drift/ambiguity, waveform, sections and lyric timing. Preserve manual boundaries/corrections across reanalysis.
- **S05.2 Correctable music map:** estimated key, editable meter, tap tempo, half/double BPM, first-count offset and variable beat mapping. Store recording identity and correction history. Explain low confidence and allow manual entry.
- **S05.3 Practice player:** local song or metronome, large count/current/next move, facing wall, count-in, seek, part/eight-count loops and playback speed with pitch preservation.
- **S05.4 Teaching:** full-screen cues, optional spoken calls from an available local voice, clear loop boundaries and paused-state behavior. Audio-less practice remains supported.

**Demonstration:** align a song's first dance count, correct a bad tempo interpretation, rehearse a tag/restart, loop a tricky block slowly and practice with a metronome offline.

**Tests/gate:** T11/T12/T13, T04 shared-timeline regressions and a documented instructor floor session. Timing tolerances and performance targets come from TESTING, with measured hardware/results. Pitch preservation and optional local voices must be tested rather than implied by a speed control. No AI service is required for this sprint.

## S06 — Generation and optional Creator Studio

**Dependencies:** S03–S05; S04 import review queue. **Features:** F08/F14/F15/F16; optional OCR slice of F07.

- **S06.1 Creative control:** preserve local/lyric-guided generation, lock favorite blocks, regenerate unlocked regions, compare candidates, explain impossible constraints and Undo applied drafts.
- **S06.2 BYO connection:** user-selected provider/account/model/endpoint; credentials stored outside projects. No developer key, shared credit pool, company-paid inference service or hidden fallback. No connection still leaves the entire core usable.
- **S06.3 Assisted writing/discovery:** user-triggered lyrics and move proposals with selected context, source evidence, missing fields and duplicate review. Only an appropriately capable connection can inspect images/video; otherwise offer text/file entry. Apply reviewed suggestions as a new recoverable draft.
- **S06.4 Existing Advanced tools:** preserve lyric scanning/alignment, audio/stem repair and reviewed tutorial/video blueprint. Separate optional local model installation from startup; document hardware/download requirements.
- **S06.5 Optional OCR:** scanned sheets enter an explicit optional OCR/import route with visible uncertainty and review. This does not change the ordinary text-file import contract.

**Demonstration:** finish a dance with AI disconnected; separately connect a user's provider, preview the context, request and review a proposal, reject another, disconnect and continue editing. Show favorite blocks surviving regeneration and the old production tools still reachable.

**Tests/gate:** T07/T08/T14/T15/T16/T34 plus draft/timeline regressions. Offline/mock failures are testable without paid calls; any real paid API smoke test is explicitly initiated using the user's own account. No feature passes merely because it returns fluent text.

## S07 — Sheets, export formats and portable restore

**Dependencies:** S03 shared presentation, S04 media, S05 timing, stable S01 project schema. **Features:** F09 packing/F10/F17/F18.

- **S07.1 Sheet presentation:** common metadata/count/part/exception model for PDF, DOCX, TXT and HTML; standard and large-print/cue styles, A4/Letter, creator/music credits and relevant warnings.
- **S07.2 Links:** labeled source/demo/song URLs and optional QR codes; printed links remain useful. Do not expose local drive paths as publicly accessible links.
- **S07.3 Data/cues:** CSV/XLSX tables and SRT/VTT based on the same selected recording/timeline, including clear no-timing behavior.
- **S07.4 Portability:** native project/move/lesson bundles with versioned manifests, checksums, selected history/media, inclusion preview and restore/relink workflow. Imported archives cannot write outside their destination.
- **S07.5 Publishing handoff:** export a submission-ready packet and open the relevant provider page; show this as a manual handoff, separate from later direct API publishing.

**Demonstration:** export a multi-page phrased sheet to PDF and Word, print/read it, follow a URL/QR, restore an editable package on a second profile and recover from a missing optional video.

**Tests/gate:** T09/T10/T17/T18 plus T03/T04/T34. Visual inspection is required for rendered PDF/Word pages; file existence alone is insufficient. Restored choreography, versions and selected attachments agree with the source; private credentials/music are not silently included.

## S08 — Local library, learning and instructor tools

**Dependencies:** S04/S05/S07; S01 recovery. **Features:** F19–F23.

- **S08.1 My Dances:** search, folders/tags/favorites, authorized offline sheets, relink/status and user-editable learning/practice checklists/history.
- **S08.2 Song swaps:** multiple recordings per dance with independent intro, alignment, tempo and restart/phrase review. Do not overwrite a working mapping or declare compatibility from BPM alone.
- **S08.3 Class planning:** ordered setlists, durations, notes and printable/portable digital guides with existing sheet/video links. Distinguish local HTML files from hosted public URLs.
- **S08.4 Schedules:** local events/classes, time zones, recurrence/cancellations and ICS import/export; link to external maps. Keep private notes out of exported public guides unless selected.

**Demonstration:** an instructor prepares a class, prints/exports its guide, teaches without internet, marks dances needing practice and changes an alternative track without corrupting its original timing.

**Tests/gate:** T19/T20/T21/T22/T23 plus T17/T18/T33/T34. Conduct a realistic instructor rehearsal/class trial; record usability problems. Local class features require no hosted accounts, Spotify subscription or AI.

## S09 — Freeware v1 and GitHub release

**Dependencies:** S00–S08 local release gates. **Features:** F31–F36 and regression evidence for F01–F24.

- **S09.1 License/content:** finalize software-specific freeware terms with the paid-class/event exception; decide remaining redistribution/support/output cases; clear/replace/exclude bundled material and include third-party notices.
- **S09.2 Distribution:** reproducible Windows installer and/or portable package, private runtime, per-user data, upgrade/uninstall preservation, optional model packages and troubleshooting. Confirm supported OS/hardware through testing.
- **S09.3 Release candidate:** clean-machine installation and offline/non-admin workflow, migration/restore drill, accessibility/user/floor acceptance and actual performance results. Resolve release-blocking defects.
- **S09.4 GitHub:** confirm repository owner/name/visibility, prepare a clean history and source tree, README/privacy/license/contribution guidance, checksums and draft tagged release assets. Publish the requested GitHub release when the concrete destination and release requirements are satisfied.

**Demonstration:** a new user installs the release candidate without Python/terminal/AI setup, authors and rehearses a dance, prints it, backs it up, upgrades and reopens it successfully.

**Tests/gate:** T31–T36 and the local-release regression matrix in TESTING. No unresolved data-loss/count-corruption/credential-exposure failures; required instructor/usability evidence is present. Optional feature limits are named. GitHub publication is a recorded action with real URLs/version/checksums, not a completed checkbox in this plan.

## S10 — Connected-service feasibility

**Dependencies:** S00 scope/rights inventory; may begin before S09. **Features:** F25–F30; F34.

- **S10.1 Recognition:** evaluate an eligible user-owned provider or local catalog; distinguish recording identification from song-to-dance mapping. Document sample handling, coverage, cost and no-match behavior.
- **S10.2 Playlists and external sheets:** verify each provider's actual access, intended-use eligibility, endpoints, OAuth/public-client design, quotas, caching and redistribution rules. Record known Spotify and BootStepper restrictions from INTEGRATIONS-AND-RELEASE and recheck current terms.
- **S10.3 Events/publishing/analytics:** establish allowed write/read workflows, moderation, metric origin, hosting/operator/cost requirements and data deletion. Hosted AI is excluded under the settled BYO rule.
- **S10.4 Decision record:** produce one dated go/conditional/no-go record per adapter, with evidence, fallback, accountable operator and unresolved dependencies. A separate user key is not a workaround for prohibited platform use.

**Demonstration:** a capability table a developer can act on, separating documented API, account eligibility, sandbox result and production approval.

**Tests/gate:** feasibility prerequisites for T25–T30/T34; no unapproved live paid calls required to produce the record. S10 can finish with no-go decisions; unavailable features remain planned with reasons and useful local/link/export fallbacks.

## S11 — Approved recognition, playlist and sheet adapters

**Dependencies:** relevant S10 go decisions; S08 local catalog/setlists and S09 credential/distribution protections. **Features:** F25/F26/F27.

- **S11.1 Recognition:** explicit short recording/clip request, recording confirmation and multiple linked dance candidates with sources; manual entry remains available.
- **S11.2 Playlist exchange:** begin with reviewed one-way operations; add bidirectional sync only after ownership/conflicts/retry behavior is defined. Show destination and changes before writes.
- **S11.3 External sheets:** permitted search/import/cache with provenance, rights/status, update handling and revoked/expired access behavior. Preserve independent user choreography.

**Demonstration:** real authorized provider workflows with no-match, wrong version, expired connection and rate-limit cases, followed by continued local use.

**Tests/gate:** T25/T26/T27/T34 and local regression checks. Fixtures/mocks plus account-authorized live evidence; unsupported providers cannot be labeled complete. Each approved adapter can ship independently.

## S12 — Approved hosted community capabilities

**Dependencies:** S10 go decisions and explicit service/operator funding plan; S08 class/events and S07 publishing packet. **Features:** F28/F29/F30.

- **S12.1 Public events/maps:** organizer accounts, public/private fields, source/freshness, cancellations, reporting/moderation and provider-compliant maps. No public hosting is implied by a local calendar.
- **S12.2 Direct publishing:** selected destination, final submission preview, attachment/version receipt, pending/rejected/published state and duplicate-safe retry. Respect provider moderation.
- **S12.3 Analytics:** only authorized measured statistics, with metric definition/coverage/refresh/privacy and deletion/export. Local progress does not imply worldwide audience data.
- **S12.4 Operations:** backups, monitoring appropriate to the service, costs, moderation ownership and shutdown/export plan. Keep offline projects usable if the service closes.

**Demonstration:** publish a test event with cancellation handling, submit a reviewed dance through a permitted workflow, and show the documented source of each metric.

**Tests/gate:** T28/T29/T30/T34 plus service isolation/account permissions, recovery and relevant local regressions. If no sustainable permitted host/provider exists, retain the backlog and local alternatives; do not add an owner-funded AI service to make it work.

## Definition of done for every sprint

Scope and decision changes are written down; code is reviewed; migration/backups and relevant existing features remain intact; mapped tests have actual results; the user journey is demonstrated; known issues have severity/owner/disposition; screenshots or rendered exports support visual claims; documentation matches behavior. Record the completed version, commands/environment and evidence using TESTING's template. A plan, mockup, mock provider or successful build alone does not satisfy this definition.

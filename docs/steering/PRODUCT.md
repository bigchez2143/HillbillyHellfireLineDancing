# Product steering and feature register

Status: target requirements, not a claim of implemented functionality. Feature IDs are stable across [ROADMAP](ROADMAP.md), [TESTING](TESTING.md), and [ARCHITECTURE](ARCHITECTURE.md).

## 1. Purpose and users

Create a freeware choreography, practice and teaching application for dancers, instructors, DJs and choreographers. Start with a dependable local Windows application, then add optional connected services where access and terms support them. Preserve Lee's advanced music/AI/video workflow without making ordinary dancers configure it.

The main success journeys are: write and print a dance without music; analyze a chosen song and build/rehearse a dance; maintain a personal multimedia move library; prepare a class and track learning; export/share a dance without losing its editable source.

## 2. Menu and workspace behavior

| Menu | Main tasks |
|---|---|
| My Dances | Recent projects, open/import, search, tags/favorites, offline sheets, learning state and versions |
| Create / Edit | Manual, generated or lyric-guided drafts; parts/count blocks; tags/restarts; live checks |
| Music | Add or relink track, BPM/estimated key, beat grid, first count, sections and timing corrections |
| Practice | Song/metronome player, current/next move, facing wall, loops, speed and teaching view |
| Line Dance Tools | Move library, count/wall checker, tap tempo/metronome, structure planner, class set lists, events/calendar, sheet-site directory |
| Export | Standard/large-print/Word/text/web sheets, links/QR, class packs, spreadsheets/captions, project backup |
| Creator Studio — Advanced | User-connected AI, lyric workshop, detailed generation, optional local lyric/stem tools and video/tutorial blueprint |
| Settings / Help | Basic/Advanced preference, readable appearance, author defaults, storage, optional provider connections, help and update information |

**Basic:** readable labels, one clear next action, simplified controls, all dance levels, all core editing/import/media/export features. **Advanced:** all Basic tools plus technical and production controls. Switching preferences preserves the same project and never discards settings. This is not a security boundary.

**Publisher message (F01 / S02.5):** include a modest Hillbilly Hellfire footer inviting users to visit the official YouTube channel and website. Show labeled links in Basic and Advanced across both software workspaces, using verified owner destinations. It must wrap on narrow screens, remain keyboard-accessible and leave the editing controls unobstructed. No embedded media, autoplay or tracking is needed. Keep ordinary exported dance sheets free of this software-footer message.

Two start choices use the same editor: **Start without music** and **Start with music**. AI is never a third mandatory startup path. Auto Generate, Manual Build and Follow Lyrics are drafting methods inside the workflow.

Keep the navy/orange visual identity, improve contrast/target sizes, group related controls, and support responsive sheet/teaching views. Windows-first does not imply an iPhone/Android release or a remotely accessible local server. Mark absent online capabilities as unavailable with usable local alternatives.

## 3. AI ownership and cost rule

AI means the user's optional external or self-hosted connection. The user supplies provider/account/model/endpoint/key and pays any provider charge. Do not include developer credentials, developer-funded credits, a common inference proxy or hidden fallback provider. With no connection, AI actions explain setup while the normal app remains usable. A text-only connection cannot be presented as a video-analysis connection.

Preserve ordinary local algorithms such as count validation and beat analysis. Existing optional local speech/stem models are user-managed add-ons with visible download/install state; no model download is required to write, save or print a dance. Where a provider is required, show the exact selected material before transmission. AI extraction and generated ideas remain proposals until reviewed/applied.

## 4. Full feature register

All rows have test groups T01–T36 matching their feature number. The “source state” column comes from inspection, not current execution. Later connected requirements remain planned even when provider permissions are unresolved.

| ID | Requirement and acceptance intent | Source state | Delivery |
|---|---|---|---|
| F01 | Main menu/tools hub with persistent Basic/Advanced; all difficulty levels remain accessible | New organization | S02 |
| F02 | Complete manual-without-song and music-assisted start paths; attach/change music without losing choreography | Backend partly present | S02 |
| F03 | Full draft saving, dirty state, Undo/Redo, named versions, crash recovery and legacy migration | Save gap confirmed | S01 |
| F04 | Parts/routine order, flexible counts, starting feet/facing, subdivisions, meter, tags, restarts and endings | Flat sequence limits | S03 |
| F05 | Reviewed move catalog, aliases, variations and documented coverage; reference terms distinct from usable definitions | 173 references / 39 buildable | S04 |
| F06 | Manual custom moves/combos, known/unknown mechanics, immutable project snapshots and versioned edits | Restricted custom moves present | S04 |
| F07 | Move and sheet imports from XLSX/CSV/TSV/DOCX/TXT/MD/JSON/text PDF, with templates/column mapping/preview; optional OCR for scans | Move import foundation present | S04; OCR S06 |
| F08 | Optional BYO-AI discovery from chosen sources; source evidence, missing fields, duplicates, batch rollback, explicit generator eligibility | New review workflow | S06 |
| F09 | Move photos/diagrams/video files and links, captions, ranges/view orientation, thumbnails, local storage/relink, selected media packs | New media model | S04; packing S07 |
| F10 | Clickable sheet/source/demo/song links and print QR; local files not masquerading as shared URLs | Some metadata URLs present | S07 |
| F11 | Preserve BPM/beat/downbeat/sections/lyric workflows, uncertainty and human music-map edits | Present in source | S05 regression |
| F12 | Estimated key, meter choice, tap-tempo/half-double correction and first-count alignment; manual override history | Key absent; 4/4 assumptions | S05 |
| F13 | Song/metronome rehearsal, count/current-next move/wall, loops, pitch-preserving slowdown, cues and full-screen teaching | Static tutorial/audio pieces | S05 |
| F14 | Preserve local and lyric-guided drafts; lock chosen blocks, regenerate the rest, compare/Undo and actionable checks | Anchored generation foundation | S06 |
| F15 | BYO-AI connection/settings and lyric workshop with draft versions/context review; no shared service/credits | Optional assistant present | S06 |
| F16 | Preserve audio/stem repair and reviewed tutorial/video production blueprint inside Advanced | Present in source | S06 regression |
| F17 | PDF/DOCX/TXT/HTML from one dance, readable print/cue layouts, A4/Letter, correct credits and structure | PDF/TXT/HTML present | S07 |
| F18 | CSV/XLSX tables, SRT/VTT timing, project/move/lesson bundles, verified restore and media relink | Partial tutorial/JSON export | S07 |
| F19 | Local searchable library, folders/tags/favorites and offline user-owned/authorized sheets | Project chooser foundation | S08 |
| F20 | Learning/know/practice states, checklists and practice history editable by the user | New | S08 |
| F21 | Class set lists, duration/order, printable packets and portable digital guides with sheet/video links | New | S08 |
| F22 | Multiple tracks per dance; version identity and per-track tempo/intro/restart suitability review | New | S08 |
| F23 | Local class/event schedules, time zones and calendar/ICS import/export | New | S08 |
| F24 | Curated sheet/resource links, user additions, favorites and last-check status; no implied endorsement/API rights | New | S02 |
| F25 | Optional microphone/clip song recognition followed by explicit song-to-dances lookup, including no-match/multiple-match cases | Provider-dependent | S10 → S11 |
| F26 | Optional Spotify/YouTube playlist exchange/sync, explicit changes, conflicts, OAuth disconnect and CSV/link fallback | Provider-dependent | S10 → S11 |
| F27 | Authorized external sheet discovery/import and permitted offline caching; provenance and source updates | Rights/API-dependent | S10 → S11 |
| F28 | Optional hosted public event listings/maps, organizer accounts, moderation and privacy controls | Hosting-dependent | S10 → S12 |
| F29 | Optional direct publishing through allowed adapters with submission review and provider status; manual export fallback | Publisher kit present | S10 → S12 |
| F30 | Optional analytics limited to legitimately measured/authorized data and defined retention/visibility | Hosting/API-dependent | S10 → S12 |
| F31 | Freeware software restriction with explicit paid-dance-event exception; output and third-party rights separated | No release license found | S00 inventory; S09 gate |
| F32 | Clean GitHub source/versioning and reproducible Windows distribution/releases with notices and documentation | Developer launcher; no repo detected | S00 setup planning; S09 release |
| F33 | Keyboard/readability/large print, nontechnical usability, offline core and clear errors; responsive views | Audit needed | Every sprint; S09 gate |
| F34 | BYO connections, no secret leakage, explicit selected-content operations, optional model installations/media sharing | Partial protections present | Every sprint; S09/S10 gates |
| F35 | Catalog source/permission tracking, contribution review and instructor coverage checks | Provenance recorded; rights unresolved | S00 inventory; S04; S09 gate |
| F36 | Traced acceptance, baseline regressions, user/floor trials and stored release evidence | Tests exist; not rerun here | Every sprint |

## 5. Special behavior requirements

### Move authoring and discovery

Preserve common move vocabulary. A reference guide is not evidence that its author invented the moves. If any move is removed, add a suitable common-move replacement in the same change and preserve compatibility for existing dances. This cleanup retains all 173 current catalog entries.

“Add moves” offers manual entry, import, and optional AI discovery. Show source page/sheet/row/timecode beside extracted fields. Treat aliases and deliberate variants differently from duplicates. Adding to the library does not automatically permit generator use. Save an incomplete descriptive move with unverified mechanics; never certify it by merely having an AI confidence number. Recognizing a video is a future assisted capability, separate from attaching a clip.

Each move can have multiple pictures/videos, view labels, timestamps and notes. Preserve originals when mirroring; left/right instruction text and media orientation must remain understandable. Manage local references, broken links and selected sharing explicitly. Public GitHub/build assets exclude personal media.

### Sheets and external resources

Start the sheet-site directory with verified destinations for CopperKnob, BootStepper and LineDance, plus relevant dance/community resources listed in the integration document. Users can add their own sites. Open sites in a browser and allow saving labeled links. A link is not a licensed copy of a sheet, a permission to scrape, or a live integration.

Offline files are copies the user is entitled to keep. Preserve credits and source links. Resource-site search/deep-link behavior must be verified before building URL templates; do not invent API endpoints or claim an official partnership.

### Learning and instructor work

Learning state belongs to the local user's library entry, not the shared canonical dance. Class guides may be exported as HTML/PDF with existing links in v1. Live public links, student accounts, attendance tracking and maps need separate hosting decisions. Alternative songs require per-track phrase review; a matching BPM alone does not establish that restarts fit.

### Recognition, playlists and publishing

Recognizing a recording identifies a track/version at best; multiple choreographies may fit the same song. Return candidates and source evidence, not an invented definitive dance. Playlist linking/export is not licensed streaming or a guarantee of continuous bidirectional sync. Direct publishing must respect platform review/verification and cannot promise “instant” acceptance. Analytics from an offline file cannot reveal worldwide reader geography.

## 6. Scope boundary

S00–S09 delivers local freeware v1 with optional user-supplied AI. S11/S12 deliver connected features only after S10 confirms feasible service access, acceptable usage/rights, cost ownership, credentials and hosting. Local/link/export fallbacks are part of v1; blocked connected features remain visible in the backlog with their reason. Do not replace requested features with marketing placeholders.

The Google overview is useful input, not a verified product specification. Official descriptions support offline sheets/lists for [CopperKnob](https://apps.apple.com/us/app/copperknob/id1112916047), learning/class guides for [Bring The Fun](https://bringthefun.dance/), and song/dance identification and event maps/schedules for [BootShuffle](https://apps.apple.com/us/app/bootshuffle-line-dancing/id6763358475). [BootStepper](https://bootstepper.com/features) advertises a broad connected platform. These descriptions do not establish our rights to reuse their data or integrate their services; see the integration gates.

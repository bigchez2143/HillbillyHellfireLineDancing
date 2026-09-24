# Integrations and freeware release

Status: steering specification, not an implemented integration or final legal license. Source checks: 3 September 2026. Read with `PRODUCT.md` and `ROADMAP.md`; feature and sprint IDs are shared across the steering set.

The S00–S09 release is a Windows-first local application. Dancers can create, rehearse, manage classes, and export without an account, internet connection, or AI service. Connected features remain in scope for later releases, with S10 feasibility evidence required before S11 adapters or S12 hosted services are promised. No account access, external submission, hosting purchase, or publishing is authorized by this document itself.

## 1. Non-negotiable service boundary — F15, F16, F25–F30, F34

AI is optional and **bring your own connection**. The user connects their own provider/account or local endpoint and pays any charges directly to that provider. The application must not supply shared keys, app-funded AI credits, a compulsory AI subscription, a developer- or company-funded hosted AI backend, or an app-operated proxy inference service. No hidden fallback AI account is allowed. Manual editing, the reviewed move catalog, local music analysis, rehearsal, and ordinary exports must work with AI disabled or unavailable.

Local speech alignment/transcription and stem separation remain optional, user-installed and user-managed modules. Their model downloads, disk/RAM requirements, hardware expectations, licenses, and first-run status must be visible before installation. They are not a bundled paid service or a prerequisite for Basic mode. Installation and cancellation cannot damage a saved project.

Every external action identifies the destination, data leaving the computer, account used, and any provider charge or quota implications. AI context is selectable and reviewable; never send an entire project, song, attachments, private notes, or third-party API content just because an integration is connected. AI discoveries and parsed imports enter the review queue; they do not become mechanically verified moves automatically.

Store credentials per Windows user, outside projects, exports, logs, and release artifacts. Never embed developer secrets in a public desktop binary or browser JavaScript. Use documented native/public-client authorization where supported; if a provider requires confidential server credentials, S10 must identify an approved architecture before implementation. Disconnection removes tokens and provider-governed cached personal data without deleting the user's independently authored dances.

## 2. Resource directory and offline material — F09, F10, F19, F24, F27

Present three distinct resource types so users understand what will work in a venue without internet:

| Resource type | User experience | Storage and sharing rule |
| --- | --- | --- |
| Website link | Open source page; save title, URL, category, and personal note | A bookmark does not copy a sheet, authorize API access, or grant redistribution rights |
| Owned or authorized local file | Open the saved PDF, Word sheet, image, or video offline | Preserve creator, source, permission/license note, import date, and file fingerprint; bundle only when the user has redistribution rights |
| Authorized provider API/cache item | Show provider attribution, retrieved date, online/offline availability, and source link | Follow provider-specific allowed fields, retention/refresh/deletion rules, export limitations, and access status |

The local library supports folders, favorites, tags, search, learning status, and attachment relinking. A missing link or expired provider cache must not invalidate the user's choreography. Portable exports provide a manifest of included files and reference-only links. Never disguise an external link as a guaranteed offline resource. Do not add a “download every sheet” crawler.

Suggested directory entries below were reachable in the source check. This is a curated starting list, not a ranking or partnership claim. Include a last-checked date, user-editable custom links, and a report-broken-link action. Recheck at release; avoid copying provider logos without an applicable permission.

| Resource | Verified link | Suggested category |
| --- | --- | --- |
| CopperKnob | [Stepsheet search](https://www.copperknob.co.uk/) | Find sheets, choreographers, and music |
| CopperKnob What's On | [Events page](https://www.copperknob.co.uk/whatson) | External event listings |
| CopperKnob submission | [Contact and sheet attachment page](https://www.copperknob.co.uk/contactus) | Submit through the provider's own workflow |
| BootStepper | [Dance community resources](https://bootstepper.com/) | Dances, songs, choreographers, collections, and events |
| BootStepper submission | [Submit a dance](https://bootstepper.com/dances/create) | Open the provider's review/submission workflow |
| LineDance.com | [Member and dance-list guide](https://www.linedance.com/how_to) | Dance discovery, sheets, videos, class lists, and provider publishing guidance |
| Linedancer | [Charts and resources](https://www.linedancerweb.com/) | Discover community charts and resources |
| Bring The Fun | [Instructor and dancer community](https://bringthefun.dance/) | Community/learning app; class guides and learning/practice lists |
| BootShuffle | [Developer's App Store listing](https://apps.apple.com/us/app/bootshuffle-line-dancing/id6763358475) | Community/event app; advertised learning progress, song-to-dance lookup, and event maps/schedules |

LineDance.com and Linedancer are distinct directory entries. Bring The Fun and BootShuffle belong in a **Community and learning apps** category, not a downloadable sheet-source catalog. Their official descriptions supply product-research examples, not evidence that our application can access their data or reproduce their services. A store listing is not an API agreement or a Windows integration. No account eligibility, data-sharing permission, API, or offline-cache right was established for these additions.

### Provider-specific evidence

**CopperKnob:** its published terms give limited personal, temporary viewing permission and restrict copying, transfer, mirroring, and public display. These terms do not establish the rights needed for an application-wide offline catalog. No usable public API agreement was established in this review. Default to links and separately authorized files; investigate permission before automated discovery/import. Its official contact page supports attaching a stepsheet and supplying video links. [Terms](https://www.copperknob.co.uk/terms), [submission instructions](https://www.copperknob.co.uk/contactus).

**BootStepper:** published terms describe an authenticated Public API with personal account keys. They permit certain complementary application uses but prohibit direct competition, systematic extraction beyond reasonable application use, standalone redistribution, and mirrored/competing repositories. Source metadata must remain intact. The terms also reserve API changes and revocation. Its public submission page offers document import followed by user review. This is evidence of an API and web workflow, not proof that the required endpoints, write access, offline retention, or this application's use case are approved. S10 must resolve those points and the competition restriction; a user login alone does not resolve them. [API terms](https://bootstepper.com/terms), [submission workflow](https://bootstepper.com/dances/create).

**LineDance.com:** its member guide describes dance lists containing sheets and teach/demo videos, private/public sharing controls, and a dance-submission workflow. Its immediate-publishing description is conditioned on first verifying or claiming the choreographer profile; an email mismatch can require administrator approval. Preserve those provider steps. This review establishes a user-facing workflow, not an authorized application write endpoint or reusable database license. [LineDance member guide](https://www.linedance.com/how_to).

**Community examples:** Bring The Fun's site describes instructor class guides and dancer learning/practice lists. BootShuffle's developer listing advertises song identification with associated dances, learning progress, and event maps/schedules. These are provider-described capabilities, not independently tested accuracy or availability guarantees. [Bring The Fun](https://bringthefun.dance/), [BootShuffle listing](https://apps.apple.com/us/app/bootshuffle-line-dancing/id6763358475).

User-authorized AI lookup is not a substitute for provider access rights. Preserve fetched evidence and attribution only to the extent allowed; never silently turn website text into a distributable “complete” move database.

## 3. Song recognition and dance matching — F25

Recognition is a two-stage process:

1. An optional microphone sample or user-selected clip is submitted to the configured recognition provider, or matched against a user-managed local catalog. Return a possible recording identity, source, version information, and confidence when the provider supplies it. Support no match, multiple matches, noisy audio, remixes, and covers.
2. The user confirms the recording. Search the local/authorized dance catalog for dances associated with it. Show several choreographies and their choreographers, levels, counts, versions, and source links. Let the user add a missing association.

**Recognizing a song does not identify which dance people are performing.** One song may have many dances, and one dance may use several songs. Never label a song match as “the correct dance,” infer detailed footwork from sound, or claim a particular dance has been visually recognized without a separate validated capability.

ACRCloud is a candidate to evaluate, not a selected or funded provider. Its documentation distinguishes exact-version audio fingerprinting from cover/humming identification, supports microphone/file recognition, and requires an account/project. Pricing must be checked in the applicable account; do not promise free unlimited recognition. [ACRCloud music recognition](https://docs.acrcloud.com/tutorials/recognize-music).

S10 evidence must include Windows/browser microphone support, consent and capture limits, provider coverage on representative music, false/no-match handling, current prices/quotas, permitted retention, and the user's connection model. Discard captured samples after the agreed purpose unless the user explicitly keeps them. Manual song entry and local library search remain available.

## 4. Playlist connections — F21, F22, F26

Keep the local class setlist authoritative. External playlist import/export is a separate, explicitly chosen operation. Model song identity, recording/version, service-specific ID, ordering, duplicates, unavailable tracks, and per-track rehearsal timing separately. A playlist track is not an audio file available for BPM/key extraction, slowdown, offline rehearsal, or redistribution.

Start with a reviewable one-way transfer. Before any write, show destination account/playlist, additions, removals, reorderings, unmatched songs, and privacy setting. Later two-way synchronization needs explicit ownership rules, change history, conflict resolution, and protection against duplicate writes after retries. Do not erase remote songs to match a local list without a clear user-reviewed diff. Handle expired tokens, denied scopes, rate limits, regional availability, and changed provider IDs.

**Spotify feasibility is a substantial gate.** Current official quota documentation limits development-mode apps to five allowlisted users and requires a Premium app owner; wider access has organization/eligibility requirements, including a stated minimum of 250,000 monthly active users. Do not promise broad freeware deployment based on a developer account. [Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes).

Spotify's developer policy restricts business-targeted uses including dance studios, synchronization of recordings with visual media, mixing, analysis, and AI ingestion. It also requires attribution and user data controls. Therefore Spotify-powered timed dance rehearsal, audio analysis, and commercial-class playback are not assumed capabilities. Even playlist-only integration needs a use-case/access review. Keep Spotify data out of the AI context by default. [Spotify developer policy](https://developer.spotify.com/policy). Evaluate the documented [PKCE authorization flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow) for an eligible desktop metadata adapter.

**YouTube:** the Data API documents authenticated playlist item insertion with a quota cost; access must be established for this application and intended scopes. The developer policy prohibits unauthorized audiovisual downloading/caching and offline playback. Use approved links/player behavior and separately authorized local music for rehearsal; do not build a download workaround. [Playlist insertion](https://developers.google.com/youtube/v3/docs/playlistItems/insert), [YouTube developer policies](https://developers.google.com/youtube/terms/developer-policies).

S10 must verify current read/write endpoints, app registration and review, quotas, scopes, privacy requirements, desktop redirect handling, branding, permitted caches, and actual account eligibility for each provider. Prices, user limits, and policies are date-sensitive. Local setlists, TXT/CSV exports, and source hyperlinks are the fallback when an adapter cannot be shipped.

Claims about other Google capabilities—automatic dance identification, line-dance-specific catalogs, event feeds, “free unlimited” maps, or unspecified Google AI integration—remain **unverified assumptions**, not release promises. Verify the exact product, official interface, terms, cost, and platform availability before adding one to a sprint. General YouTube playlist documentation does not establish those other capabilities.

## 5. Events, maps, publishing, and analytics — F23, F28–F30

### Local schedule first; public events later

S08 provides private/local class and event entries, notes, setlist links, time zones, recurrence, cancellations, and ICS import/export. Users can open an external map or listing link without operating a public directory.

S12 public listings require an actual hosted service plan: named operator, hosting/storage/bandwidth budget, moderation capacity, organizer accounts and permissions, correction/reporting tools, abuse handling, backups, deletion rules, and service shutdown/export arrangements. Separate public venue details from private attendee/contact notes. Show event source, organizer, last confirmation date, cancellation status, and time zone. Do not scrape public websites into a “complete” events map or publish private addresses automatically.

Map tiles, geocoding, event data, and hosting are separate dependencies. An open-data map does not mean unlimited free infrastructure: the OpenStreetMap Foundation's standard tile service requires attribution and policy-compliant caching and prohibits bulk/offline tile downloading. Choose a provider and budget or approved self-hosting plan; use list view and external map links until ready. [OSMF tile policy](https://operations.osmfoundation.org/policies/tiles/).

### Publishing is an explicit submission

S07 already supports an export-and-open-submission-page handoff. F29 direct publishing is a later adapter only where the provider offers and authorizes the required write workflow. Prepare the title, creator credits, sheet version, links, attachments, destination, and data-rights acknowledgement for final user review. Keep draft, submitted, pending review, rejected, and published states distinct; a successful upload is not proof of publication.

Preserve the provider's moderation, verification, access controls, and anti-spam rules. Never bypass a review queue, CAPTCHA, rate limit, profile claim requirement, or permission check. An API's existence does not imply submission access. Keep a receipt/external ID and avoid duplicate submissions after a timeout. A failed submission leaves the local project and export usable.

### Analytics must state what was measured

S08 learning/progress records under F20 can cover practice sessions, self-assessed learning status, and locally recorded class/setlist use. These describe this user's activity, not community popularity. F30's later connected/public analytics require an authorized data source and appropriate consent/retention design.

Every metric records origin, definition, time range, time zone, sample coverage, last refresh, and whether it is measured, user-entered, provider-reported, or estimated. Views, downloads, playlist appearances, practice completions, and attendance are different quantities. Do not infer attendance from views, add incompatible provider counts, claim global dance popularity from a local sample, or treat AI estimates as measured statistics. Do not ingest a provider's data into analytics when that provider prohibits it. No background telemetry by default; any optional aggregate reporting must have a clear opt-in and deletion path.

## 6. License intent and content provenance — F31, F35

This is a policy specification for a software-specific license to be reviewed before public release, not final legal text or a guarantee of enforceability.

| Topic | Intended policy |
| --- | --- |
| Application price | Free to obtain and use |
| Paid dance activity | Expressly allow use to create, teach, perform, and organize dances at paid classes and events |
| User outputs | Claim no application ownership of user-created projects; proposed default also permits paid choreography, sold sheets, and monetized dance videos, subject to separate content/music rights |
| Software monetization | Prohibit selling the application or modified versions, charging for access, paid hosted repackaging, and monetized software distribution without permission |
| Third-party components | Preserve their original licenses and notices; do not claim the app's restrictions revoke upstream rights |
| Free redistribution and modifications | Decide whether free unchanged redistribution and public modified versions are permitted; retain notices and distinguish unofficial builds if allowed |
| Paid installation/support, donations, sponsorship, bundled products | Unresolved policy choices; do not silently interpret these as approved |

Avoid a blanket “no commercial use” rule that would undermine the express paid-class/event exception. Use **freeware**, or **source-available freeware** if publishing source with restrictions. OSI open source requires commercial use and redistribution freedoms, so a no-sale license must not be described as OSI open source. [OSI Open Source Definition](https://opensource.org/osd). Creative Commons recommends against using CC licenses for software; do not substitute CC-BY-NC for an appropriate software license. [CC FAQ](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software).

The software license cannot grant music/public-performance, video, photo, or third-party sheet rights the owner does not control. Export templates and original bundled move descriptions should have an explicit output-use permission matching the paid-dance intent. Choreographer attribution should survive imports and exports, but attribution alone does not grant copying rights. Do not promise exclusive copyright in every dance: US Copyright Office guidance treats social line dances and individual/common steps differently from copyrightable choreographic works. [Circular 52](https://www.copyright.gov/circs/circ52.pdf).

### Original source inventory and subsequent clarification

The current `data/step-database.json` records 173 entries: 136 glossary-only, 25 seed-plus-glossary, and 12 seed-only. The original provenance identified a teaching glossary used as a reference for common moves; the user clarified that it was supplied as a guide, not as an invention claim. `references/step-levels-and-glossary.md` contains a section labeled verbatim; `references/sheet-examples.md` contains full example sheet transcriptions and accompanying screenshots. No application LICENSE/NOTICE file was found in the initial inventory. These are release-review findings, not accusations or a completed rights assessment.

Before bundling, record the author/source, permission or license, permitted uses, attribution, modification history, and review status for each original/imported description, illustration, video, and fixture. Obtain permission where needed or replace explanatory content with independently authored material. Keep a license/rights decision separate from instructor review of footwork mechanics. A technically verified move is not automatically cleared for redistribution, and a legally usable description is not automatically safe or mechanically complete. Imported community contributions require both reviews before promotion into the default catalog.

## 7. Windows packaging and clean GitHub release — F32–F36

Current implementation evidence: `app/run.bat` prefers `uv` and invokes `requirements-lyrics.txt`, pulling the optional speech stack into normal startup; the Python fallback assumes dependencies already exist. Core requirements are largely unpinned. Projects live beneath `app/projects`, settings beneath `app/settings.json`, and the service binds to localhost. Treat this as a development launcher, not the final nontechnical distribution.

S09 release checklist:

- Build from a tagged, reviewed revision using pinned dependencies, recorded Python/runtime versions, and a documented build recipe. Include a dependency/model inventory and checksums; keep testing/build tools out of the runtime where possible.
- Deliver a Windows installer and/or clearly documented portable package with a private runtime. The user should not need Python, `uv`, a terminal, an AI account, or a compiler for the core workflow. Verify supported Windows versions and hardware empirically; do not promise native mobile/macOS support from a browser frontend alone.
- Put preferences/caches in per-user storage and projects in a user-chosen documents location. Migrate existing `app/projects` safely. Distinguish portable mode storage explicitly. Upgrades/uninstall must preserve user projects unless the user deliberately requests removal.
- Keep the service on loopback, validate local origins/requests, handle occupied ports and second launches, and provide visible application shutdown. Test without admin privileges, with spaces/non-ASCII paths, and with a fresh Windows profile.
- Separate optional speech/stem module installation from first launch. Show download size and licenses, handle interrupted installs, verify model integrity, and preserve offline core use. No compulsory app-hosted AI service.
- Audit all transitive native libraries, codecs, fonts, images, and model weights. Include applicable third-party licenses/notices and required source/relinking materials. The application's license governs only rights it can grant.
- Prepare a clean release staging directory that excludes real songs, private projects, settings, API keys/tokens, browser profiles, screenshots/transcriptions lacking release rights, logs, caches, temporary exports, and development environments. Use synthetic or cleared test fixtures. Scan the full Git history before a first public source release; adding a file to `.gitignore` does not remove earlier committed data.
- Provide a short quick-start guide, Basic/Advanced explanation, supported-format list, offline/optional-feature table, known limitations, license summary, privacy statement, recovery/backup instructions, change log, and issue-report template that discourages attaching secrets or copyrighted songs.
- Decide signing and distribution format before promising a frictionless installer. Microsoft requires a valid trusted signature for deployable MSIX packages; signing has a separate publisher/certificate setup. Evaluate cost/eligibility without buying anything in this planning phase. [Microsoft MSIX signing](https://learn.microsoft.com/en-us/windows/msix/package/signing-package-overview).
- Attach tested binaries, checksums, release notes, and source/build information to a draft GitHub release tied to the intended tag. Verify the downloadable package on a clean machine before publication. GitHub supports release drafts and attached binary assets; a source ZIP is not an installed desktop app. [GitHub release documentation](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository).

Dependency evidence to preserve: WhisperX currently uses BSD-2-Clause, requiring notices with redistribution, and Demucs code uses MIT. Model and transitive component rights need their own exact-version inventory. [WhisperX license](https://github.com/m-bain/whisperX/blob/main/LICENSE), [Demucs license](https://github.com/facebookresearch/demucs/blob/main/LICENSE). If the packaged audio stack includes FFmpeg, inspect the actual build and redistribution obligations; optional components can change the applicable license. [FFmpeg legal guidance](https://ffmpeg.org/legal.html).

## 8. S10 feasibility record and acceptance evidence

S10 is an evidence gate, not a promise that all providers will approve access. It may run in parallel with local work, but failed external feasibility must not delay or disable the S00–S09 local freeware release. Preserve blocked features and evidence in the backlog with a working local/link/export fallback.

Create one dated record per proposed adapter/service with: exact use case; official interface/endpoints; operating system/runtime; authorized account/client type; available scopes; read/write/cache rights; provider/content restrictions; quota; user cost; operator cost; credential architecture; privacy/data flow; moderation requirements; expiry/revocation behavior; fallback; evidence link; and a go/conditional/no-go decision. Distinguish “documentation exists,” “account eligible,” “sandbox tested,” and “production approved.” Do not use unofficial endpoints or extra accounts to work around an access restriction.

| Slice | Features | Gate and test evidence |
| --- | --- | --- |
| S00 | F31, F32, F34, F35 | Rights/dependency inventory, source-history review, current baseline, private-data exclusions |
| S02/S04/S07/S08 | F09, F10, F19, F21, F23, F24 | T09/T10/T19/T21/T23/T24: authorized attachments and links survive save/restore; missing links, offline files, custom resources, time zones and ICS behave honestly |
| S09 | F31–F36 | T31/T32/T33/T34/T35/T36: license/output examples, clean install/upgrade/uninstall, offline/no-AI path, no secrets/media in release, notices, instructor and regression evidence |
| S10 | F25–F30 | Written capability/cost/permission decisions for every connected feature; no fabricated availability, free tier, partnership, or provider approval |
| S11 | F25, F26, F27 | T25: consent/no match/wrong version/many dances; T26: denied scopes/conflicts/retries/rate limits; T27: attribution/cache expiry/access revoked/rights-limited export |
| S12 | F28, F29, F30 | T28: private vs public fields/cancellations/moderation; T29: preview/submission/pending/rejection/no duplicate; T30: provenance/coverage/opt-in/deletion/no invented totals |

No AI credentials, recognition account, Spotify/YouTube connection, publishing account, paid service, or hosted event database was accessed or provisioned while preparing this specification.

### Common-move cleanup update — 3 September 2026

Keep the common moves. All 173 reference entries and 39 executable built-ins are preserved. Selected wording and source-specific editorial notes have been revised; original source records remain in a private backup. The source PDF/reference notes remain on the user's computer and are excluded from Git by explicit ignore rules. Ordinary move names, facts and mechanics are not removed merely because they appeared in a guide. Short conventional wording matches are not treated as proof of infringement. No new blanket clearance or authorship claim is made for unchanged descriptions. Any future removal must include a common-move replacement and protect existing projects.

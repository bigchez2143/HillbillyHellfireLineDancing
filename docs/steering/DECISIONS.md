# Decisions, unresolved choices and status

Revision: 3 September 2026. This register distinguishes user requirements, proposed engineering choices and decisions still needed before their relevant release. It does not require answers to all later-release questions before local work begins.

## Settled direction

| ID | Decision | Basis and consequence |
|---|---|---|
| D01 | Build for ordinary line dancers and advanced creators | User direction. Basic/Advanced changes detail; all levels and core editing remain available. |
| D02 | Use a menu and tools hub | User direction. Keep the existing visual identity, simplify first actions and preserve existing functions. |
| D03 | Support manual and music-assisted projects | User direction. Music can be attached later; manual creation does not depend on audio, AI or internet. |
| D04 | AI is optional and user-owned | Latest explicit user direction. The user connects their own account/provider/endpoint and pays charges. No developer key, shared credits, app-operated inference service or hidden fallback. |
| D05 | Allow users to extend the move library | User direction. Manual/file/optional AI-assisted additions, media attachments and sheet links are in scope. Review and versioning prevent silent changes to saved dances. |
| D06 | Prioritize complete authoring over a misleading catalog claim | Engineering interpretation of “any moves.” Add flexible descriptive/mechanical moves and publish reviewed coverage. No finite database can be guaranteed to contain every regional name and future variation. |
| D07 | Fix saving and add rehearsal/creative control | User approved the prior review: complete saves, Undo/recovery, clear status, large rehearsal cues, locked blocks and actionable checks. |
| D08 | Freeware with paid dance-event use allowed | User direction. Restrict monetizing the software; separate rights in user output and third-party music/media. Operative text is `LICENSE` version 1.0 (24 September 2026). It is not an OSI open source license. The rights-holder line is Lee Burnette, product published under Hillbilly Hellfire, and still needs his confirmation before a public release. |
| D09 | Offer multiple sheet/export formats | User direction. PDF/Word plus text/web/data/portable formats, shared choreography interpretation and verified restore. |
| D10 | Put the completed application on GitHub | User direction. Prepare a clean source/release package; destination, visibility, licensing and release evidence must be established before publication. |
| D11 | Plan first | Current user direction. This task creates steering documents and tested-delivery phases; it does not implement all requested features. |
| D12 | Local freeware first; optional connected releases follow | Proposed delivery sequence to protect the offline product. All requested connected capabilities stay traceable, with provider/hosting gates rather than false availability claims. |

## Proposed technical choices to confirm in S00/S01

Preserve the current FastAPI/Python and vanilla frontend foundations while refactoring in slices. Use a versioned portable project document, SQLite for catalog/cross-project metadata, managed media manifests and exact movement timelines shared by all consumers. These are architecture proposals, not a mandate to rewrite the app or a claim the user selected a new stack. Validate migration and recovery behavior before locking schemas.

Keep Basic as the new-user default, with Advanced available in Settings. Use ordinary labels such as My Dances, Practice and Line Dance Tools. Confirm these choices through observed dancer tasks; changes should improve discoverability without splitting project formats.

## Decisions needed later

| ID | Question and working assumption | Resolve by | Why it matters |
|---|---|---|---|
| O01 | Repository destination is now user-created: `https://github.com/bigchez2143/HillbillyHellfireLineDancing`, shown Public and empty in the follow-up screenshot. Confirm remote state before the first push. Public product name/publisher presentation remains to finalize; “Line Dance Creator” is the working product title. | S09, earlier for source setup | Repository creation is complete; uploading the application is a separate action. |
| O02 | Which Windows versions/hardware and installer/portable formats can be supported? Measure during baseline/release preparation. | S00 sizing; S09 final | Determines packaging and compatibility tests. |
| O03 | Free redistribution and modified versions are allowed with the notice conditions in `LICENSE` sections 2 and 5. Paid installation, technical support, Software donations, sponsorship, and commercial bundles are not granted. | Confirm the rights-holder line before public release | A blanket noncommercial rule would conflict with intended teaching use. |
| O04 | `LICENSE` sections 3 and 6 allow charges for the user's own choreography, teaching, sheets, and videos, subject to rights in that output and its music. The Software license does not grant music or third-party content rights. | Confirm the rights-holder line before public release | Paid dance work stays separate from selling the Software. |
| O05 | Which bundled descriptions/media have redistribution permission, and who can review mechanics? Inventory now; replace or exclude uncleared material. | S00/S04; S09 gate | Present glossary provenance does not settle publication rights or mechanical correctness. |
| O06 | What coverage benchmark and dance levels should the default library claim? Use a named family/variant matrix and independent instructor review. | S04 | Enables honest, measurable coverage instead of a “complete” badge. |
| O07 | Which BYO AI connections and optional local modules get first-class support? Preserve existing compatible routes initially; evaluate cost, capability and setup complexity. | S06 | Do not promise every model can browse, inspect video or produce structured moves. No owner-funded provider is an option. |
| O08 | Which recognition/playlist/catalog providers permit this app and have usable access? No provider selected merely by appearing in the Google overview. | S10 | Eligibility, quotas and restrictions may make an advertised capability unavailable. |
| O09 | Who would operate/fund/moderate public events or other hosted features? No hosting budget or operator committed. | S10/S12 | Freeware download alone does not fund a community service. |
| O10 | Which public publishing/analytics endpoints can be used? Keep export/manual submission and local metrics until verified. | S10/S12 | A successful upload is not publication, and local usage cannot establish public popularity. |
| O11 | What calendar/capacity estimate is realistic? Size stories after the baseline; do not equate a sprint ID with a fixed number of weeks. | S00 | Prevents a false launch date for a substantial expansion. |

These are decision checkpoints, not a request to stop current document work. Surface a question when its answer materially changes the next concrete implementation or release action.

## Material risks and responses

| Risk | Evidence or reason | Response and owner checkpoint |
|---|---|---|
| Save message hides unsaved work | Global save omits manual sequence/tutorial changes in the audited implementation | S01 complete draft contract and T03 failure/recovery tests before broad UI changes |
| Catalog count mistaken for usable coverage | 173 reference records versus 39 built-in buildable moves in the audit | S04 separate reference/reviewed/buildable/generator counts; custom descriptive authoring |
| Old dances change when moves change | Projects resolve mutable move IDs; mirroring literal R/L text is unsafe | Immutable snapshots, explicit reviewed variants, T06 migration/update cases |
| Choreography rules exclude legitimate dances | Flat repeated sequence, integer counts and restricted walls/turns | S03 exact events/structure and independent instructor fixtures; distinguish unknown checks |
| Rehearsal/exports disagree | New consumers could implement competing count/timing logic | Shared compiler/presentation model and cross-output fixtures in T04/T13/T17/T18 |
| “Freeware” still requires technical setup | Current launcher installs optional speech dependencies and uses app-local storage | S06 optional modules; S09 packaged runtime, per-user storage and no-AI clean-machine trial |
| AI creates costs or silently changes data | External calls and fluent but incorrect proposals | BYO-only, selected context, explicit user action, review queue, stale-result checks and T08/T15/T34 |
| GitHub exposes private or uncleared material | Existing songs/projects, glossary/example content and no release-license inventory | S00 inventory; S09 clean staging/history scan, replacement/permission and notices |
| Third-party access cannot support broad release | Current Spotify/BootStepper and content terms constrain use; no approved integrations established | S10 dated feasibility decisions and local/link/CSV fallbacks; recheck at implementation |
| All-in-one scope delays a usable product | Large authoring, teaching and hosted-service expansion | Story slices and local S09 release gate; later providers ship independently |
| Technically valid dance is awkward to teach | Arithmetic cannot prove feel, clarity or physical suitability | Observed nontechnical tasks and instructor floor sessions with recorded revision decisions |

## Current status and next work

| Item | State |
|---|---|
| Steering pack | Created as the planning deliverable; document consistency verification recorded separately |
| S00–S09 implementation | NOT STARTED by this task; current source features remain as audited |
| S10 feasibility | Preliminary public-document research informs this plan; full per-provider decisions NOT COMPLETE |
| S11–S12 implementation | NOT STARTED; external access/hosting gates unresolved |
| T01–T36 application tests | NOT RUN by this planning task |
| GitHub public repository/release | User created `bigchez2143/HillbillyHellfireLineDancing`; screenshot shows an empty public repository. No source uploaded or release published by this task. |
| AI connections | No accounts connected, no shared service introduced, no paid API calls made by this planning task |

Next engineering increment: S00 baseline and fixtures, followed by S01 saving/recovery. No new product UI, storage migration or final software license is claimed by the steering update.

## Change record

| Date | Change |
|---|---|
| 2026-09-03 | Consolidated approved UI/reliability improvements and expanded dancer/instructor/creator features into F01–F36, S00–S12 and T01–T36. |
| 2026-09-03 | Made the user's BYO-AI instruction normative throughout: no supplied shared AI, credits or owner-funded inference service. |
| 2026-09-03 | Superseded the August 1 steering scope with this set while preserving its exact original as historical context. Older marketing, catalog and test claims do not become current facts. |
| 2026-09-03 | User created the public GitHub repository `bigchez2143/HillbillyHellfireLineDancing`; recorded it as the release destination. |

For future changes record date, user request or evidence, affected F/S/T IDs, scope/timing impact and reviewer. Keep original IDs when splitting work, and never retroactively mark a test passed because a requirement changed.

## Common-move preservation — user clarification, 3 September 2026

The teaching guide was supplied as a reference for established moves; its author is not being credited with inventing that vocabulary. Preserve all 173 catalog entries and existing move mechanics. Remove source-specific editorial language from the active catalog without deleting common moves or relabeling them as newly invented. Keep the original research privately.

**Replacement rule:** if a move is removed in future, provide a suitable common-move replacement as part of the same change. Retain a compatibility definition or explicit migration for old projects; never silently substitute choreography in an existing dance. Show the removed/replacement mapping and test count, foot and facing continuity.

The focused cleanup preserves catalog membership, aliases, counts, turns, foot states, levels and the 39 executable built-ins. It revises selected descriptions and document-history notes. It does not claim that all retained text is newly authored or that the whole release rights inventory is complete. The planning task status above remains historical; this later cleanup has its own preservation-check evidence.

## Hillbilly Hellfire promotion — user request, 3 September 2026

Add the owner's requested short statement inviting users to the Hillbilly Hellfire YouTube channel and website. The user asked to put this in a sprint, so it is scheduled as **S02.5** under F01/T01 and remains **NOT STARTED**. Verify the exact official URLs before implementation. Use a small software footer in both detail modes/workspaces; ordinary sheet exports are outside the promotional scope. This authorizes the publisher's own statement and does not decide the unresolved license questions about third-party monetized distribution. No runtime UI change was made by this planning update.

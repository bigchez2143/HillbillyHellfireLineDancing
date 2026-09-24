# Line Dance Creator — steering documents

Owner: Lee Burnette / Hillbilly Hellfire  
Planning revision: September 3, 2026  
Status: local implementation and regression testing completed for the first review candidate; see [current implementation status](IMPLEMENTATION-STATUS.md) for the exact scope and remaining gates.

## Read in this order

1. [Product and complete feature register](PRODUCT.md) — who the app serves, the menu, required behavior, and F01–F36.
2. [Phases and sprint backlog](ROADMAP.md) — dependencies, stories, demonstrations, and exit gates for S00–S12.
3. [Architecture and migration](ARCHITECTURE.md) — current constraints, proposed documents/data, and invariants.
4. [Testing and acceptance](TESTING.md) — T01–T36, test fixtures, regression checks, user testing, and evidence.
5. [Integrations, licensing and GitHub release](INTEGRATIONS-AND-RELEASE.md) — provider gates, resources, permissions, packaging and publishing.
6. [Decisions, risks and current status](DECISIONS.md) — settled requirements, open release choices and unresolved dependencies.
7. [GitHub setup fields](GITHUB-SETUP.md) — the repository description and temporary license selection requested during planning.

The files are intended to live in the project at `docs/steering/`. The root `STEERING.md` points here. This set supersedes the older steering document where they differ; the earlier document is retained under `legacy/` in the project as historical context. New user instructions take precedence over this set.

## Non-negotiable product rules

- Basic/Advanced changes interface detail, not dance difficulty or access to the core tools.
- Starting without a song is a complete supported workflow. Music can be added later.
- **AI is optional and bring-your-own.** Users supply their own provider/account/endpoint/key and pay their provider. No shared developer key, app-funded credits, app-operated inference service, or hidden fallback AI account.
- Core authoring, manual/file imports, local music tools, saving, practice and normal exports work without an AI connection. Optional local model add-ons are installed/managed by the user and do not become mandatory startup dependencies.
- Existing features remain reachable and covered by regression evidence as menus and storage change.
- Save the working draft without silently replacing a reviewed active dance. Preserve old projects and exact move definitions through migration and library updates.
- Unknown move mechanics can remain usable as descriptive choreography, but must not be reported as verified or silently used by automatic generation.
- User media and projects remain local by default. Links, a local saved sheet, an API cache, and public publishing are different operations.
- Freeware licensing must prohibit software monetization while explicitly permitting the requested paid-dance-event use. Third-party rights remain separate.
- Never mark a feature or sprint complete merely because it appears in this plan. Record actual implementation and test evidence.

## Delivery sequence

| Phase | Sprints | Release outcome |
|---|---|---|
| A — Preserve work and simplify use | S00–S02 | Baseline, safe storage, recovery, Basic/Advanced menu and resource links |
| B — Author any supported dance | S03–S04 | Flexible choreography, reviewed/custom moves, media and file imports |
| C — Music, rehearsal and creation | S05–S06 | Music tools, rehearsal, stronger generation and optional BYO-AI studio |
| D — Share and teach | S07–S08 | Export/restore, linked sheets, offline library, learning progress and class tools |
| E — Release the freeware | S09 | Tested Windows distribution and clean GitHub release |
| F — Connected features | S10–S12 | Feasibility-gated recognition, playlists, external catalogs, public events/publishing/analytics |

S10 research can run before S09, but unresolved provider access must not hold the offline release hostage. S11/S12 remain recorded requirements for later connected releases, with explicit dependencies and fallback behavior. No calendar duration or launch date is promised; size and split sprint work after S00 baseline measurement.

## How to execute a sprint

Read its scope and dependencies in ROADMAP. Inspect current code before assuming a prior audit is still current. Work against backed-up fixtures or an isolated copy, especially during migration. Implement the selected scope; execute the mapped test groups and relevant existing regressions; demonstrate the requested user journey; record issues and evidence. Update the sprint status and decision log together. Public publication and external account mutations require the concrete destination, content and existing user authorization to be established.

## Current completion boundary

See [Implementation status](IMPLEMENTATION-STATUS.md) and its evidence links. Local development is now implemented and tested; external-provider, human acceptance and public-release gates remain distinct. Historical planning statements do not override this dated record.

# S09 release preparation and unresolved gates

Evidence date: 3 September 2026. This task prepared documents and reviewed local source/package evidence. It did not adopt a license, create a public commit, push source, upload a binary, open external accounts or publish a release.

## Documents prepared

- `LICENSE-DRAFT.md`: restricted freeware draft, free noncommercial redistribution/modification with notices, explicit paid dance teaching/events and original-output permission, upstream-license precedence. It is not operative until owner adoption.
- `PRIVACY.md`: observed local storage, browser recovery, optional provider data flow, credentials, private/public exports and deletion boundaries. Publisher contact is deliberately unfilled.
- `THIRD_PARTY_NOTICES.md`: 49-package core inventory, retained full-notice locations, supplemental exact-version notices and unresolved native-binary obligations.
- `CONTRIBUTING.md`: rights/provenance, useful verification, temporary fixtures, no paid/required AI and public-report hygiene. No contributor copyright assignment was invented.

## Exact remaining owner/legal decisions

The user explicitly permits earning from dances made for paid events while prohibiting software monetization. The draft proposes free noncommercial redistribution/modification and broader original-output permissions; those drafting choices are not an adopted license. Reconcile the decision log with the final wording when the owner adopts it.

Still to resolve: legal licensor/copyright notice and version/date; licensing/privacy/security contact; separately paid installation/technical support; voluntary Software donations and sponsorship; commercial bundles/redistribution arrangements; final warranty, liability, breach/cure/termination and governing-law wording. This draft supplies no unstated support, donation, sponsorship or bundle permission. No jurisdiction or enforceability guarantee has been invented.

This restricted freeware model is not OSI open source, whose definition requires redistribution/commercial-use freedoms incompatible with a no-sale restriction. Creative Commons advises against applying its licenses to software; no CC-BY-NC shortcut is proposed. [OSI definition](https://opensource.org/osd), [Creative Commons software FAQ](https://creativecommons.org/faq/#can-i-apply-a-creative-commons-license-to-software)

The software license cannot create copyright in common steps or guarantee exclusive rights in a social line dance. The US Copyright Office describes limits on registering common/simple movements and social dances; that does not decide permissions for copied expressive prose, recordings or images. Preserve common vocabulary while separately reviewing actual redistributed content. [Copyright Office Circular 52](https://www.copyright.gov/circs/circ52.pdf)

## Concrete source/content findings

At inspection, the local history contains baseline commit `c0d5ef9e427df19c30beeb9c25c43123e993f945`. It tracks the older `docs/steering/ARCHITECTURE.md`, whose line 9 contains the owner's absolute source path and line 277 contains a named teaching-reference narrative and old source-category counts. Those historical details belong in a private audit record; a public summary should describe the actual current catalog without reproducing private attribution remnants or falsely erasing how the research occurred. The root agent owns that edit. A sanitized working file alone would not remove the old committed copy from a pushed history.

The current active catalog JSON scan found no remaining occurrences of the named teaching-source terms searched in this pass. This is a targeted scan, not a blanket clearance or independent-authorship claim for every unchanged description. Preserve all 173 common catalog entries and the owner's physical reference files privately. Review/rewrite uncleared explanatory prose and assets rather than removing the common moves.

The existing ignore list excludes the original glossary PDF, reference notes/examples/screenshots, `docs/steering/legacy/`, `private-audit/`, projects, settings, database sidecars, caches, build outputs and development environments. It does not by itself prove a clean history. Source-mode `app/instructor-data/` also needs exclusion before normal local records can enter a source staging plan; check the final ignore rules and actual tree.

## Public source allowlist and exclusions

Prepare a fresh reviewed source manifest before staging. Candidate source: approved root README/license/privacy/contribution/notice files; application `.py` modules; reviewed HTML/CSS/JS and cleared static assets; the two reviewed catalog JSON files; Python tests using synthetic temporary fixtures; requirements/locks; build tooling; reviewed current design documentation. Include the two supplemental dependency notice files and their provenance because the build uses them.

Do not recursively upload the working folder. Exclude `.git` from any fresh clean export; `.venv`, uv/test caches, `build/`, runtime binaries, `work/`, `.test-tmp/`, generated outputs, raw logs/XML, project/history/settings stores, instructor state/backups, library/user attachments, custom user moves, SQLite files/sidecars, credentials/environment files, songs/media, reference PDFs/screenshots, legacy steering and private audits. Raw JUnit files can contain local paths; publish reviewed summaries or redacted evidence rather than assuming logs are safe. Include a media fixture only through an explicit synthetic/cleared fixture manifest.

If existing local history is retained for private development, prepare a separate clean public history after review rather than pushing uncleared historical copies. Preserve the private original and source audit; no history deletion or rewrite is performed by this document. Adding `.gitignore` does not remove already tracked history. [GitHub licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)

## Binary/runtime evidence and gates

The latest tested candidate carries private CPython 3.12.14 and 49 pinned core distributions. It passed the documented native audio/PDF/DOCX/XLSX/server-import checks, file checksums and per-user data-default/override verification. Earlier relocated-folder checks demonstrated a path containing spaces. These are host-level checks of source snapshots, not clean-machine or installer certification. See `portable-instructor-results.json`, `portable-bootstrap-results.json` and the earlier package evidence.

Version pins are not hashed wheel locks. Retain the exact wheels, hashes, source/build provenance and complete dependency/native notices; verify required source/relinking or redistributable obligations for the exact Windows binaries. Inspect CPython/runtime DLLs and bundled libraries as well as Python metadata. The two missing wheel notices were recovered from matching official source archives, but that does not certify every other legal obligation.

No local speech/stem model weights or shared AI service are bundled. Optional addons remain a separate user-managed install with independent model/codec/dependency review. No owner-funded hosted AI, paid inference proxy, shared key or credits may be introduced by release packaging.

Outstanding execution gates: stable final source revision; complete current regression run; rendered export inspection; migration/backup/restore and per-user upgrade preservation; supported Windows/hardware declaration; clean-machine offline/non-admin launch; real user/accessibility and instructor/floor sessions; installer/signing choice and verification where applicable; adopted terms/contact/content clearance; final source and binary manifests and checksums.

## GitHub publication state

The owner previously identified the public repository destination as `bigchez2143/HillbillyHellfireLineDancing`. Recheck the actual remote and intended branch before the first authorized push. This preparation task has made no remote write and does not certify the remote's present contents. A draft license is not a completed source-license gate, and a locally generated binary is not a published release.

After the applicable gates pass, stage the reviewed source, inspect the full public diff/history, build the final candidate from the declared revision, and prepare the matching tag, release notes and checksum-bearing assets. Review the concrete destination/assets before publication. [GitHub release workflow](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)

## Read-only source manifest helper

`scripts/source_release_manifest.py` produces a candidate allowlist with relative paths, byte counts and SHA-256 hashes on stdout. `--summary` omits the per-file list. It never stages, copies, commits, rewrites history or uploads anything. At the recorded dry run it selected 96 source files (about 1.54 MB), reported the architecture file's personal-path review flag and correctly reported that no adopted license file exists. Development runtimes, projects, caches, reference trees, raw logs and most internal evidence are outside its allowlist; the three dependency-notice inputs required by the builder are included.

This helper deliberately reports `ready_to_publish: false`. It does not inspect Git history, establish content ownership, discover every possible secret or approve a release. Static binary assets are flagged for separate rights review. Counts/hashes describe the inspected tree and must be regenerated after final edits.

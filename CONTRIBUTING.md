# Contributing to Line Dance Creator

Thank you for helping make a practical tool for line dancers. This is freeware under [LICENSE](LICENSE): paid dance teaching and people's own outputs are allowed, and selling the Software is not. [LICENSE-DRAFT.md](LICENSE-DRAFT.md) is the earlier draft, not a second license. This document does not assign your copyright to the publisher and does not create a separate contributor agreement.

## Useful contributions

- Clear bug reports with steps, expected behavior, actual behavior and the application/Windows version.
- Small, understandable improvements to authoring, rehearsal, accessibility, imports, exports and recovery.
- Independently written move explanations with timing/lead/weight/facing information and explicit unknowns.
- Synthetic test fixtures and documented instructor observations that help distinguish tested mechanics from assumptions.

A catalog entry need not be an inventor's original movement. Preserve established common names and vocabulary. Explain variants rather than claiming a finite list covers every possible move. Technical validation, instructor review and permission to redistribute text/media are separate checks.

## Keep source and examples safe to share

Contribute only code, descriptions and media that you can authorize for the intended project license and distribution. Identify third-party sources and their actual licenses/permissions; attribution alone is not permission. For a common move, write an explanation independently rather than copying a guide's distinctive wording. Do not upload teaching-reference PDFs, scraped sheet collections, screenshots of other people's sheets, commercial recordings, private projects, personal contact lists or credentials.

Keep a rights/provenance note for contributed content: author or source, relevant URL/date, permission/license, changes and review status. State whether a mechanics example has been checked by a dancer. Do not remove a common move merely because it appeared in a reference guide; improve or replace the explanatory text while preserving the usable vocabulary and existing project references.

Do not attach a live API key, protected settings file, full application data folder or unreviewed diagnostic log to an issue. Use a short synthetic example with no copyrighted song. A private security-reporting contact must be published before release; do not assume a public issue is a confidential channel.

## Development and verification

Use an isolated Windows x64 / Python 3.12 environment and the reviewed requirements under `requirements/`. `dev.txt` selects the full development version lock. The normal launcher and portable build install/package core dependencies only. Do not add optional speech models, GPU stacks, paid calls or account credentials to required startup or ordinary tests.

Run relevant tests with `.venv\Scripts\python.exe -m pytest app/tests`. Tests must use temporary projects and synthetic media; do not run destructive tests against someone's saved dances. Report actual commands, results and limitations. Windows DPAPI checks may require a normal Windows user context; distinguish a sandbox restriction from an application failure. Do not replace failing evidence with an unsupported “all passed” claim.

For changes to choreography, exercise the shared exact-count timeline and unknown-mechanics behavior. For persistence, verify a real edit survives save/reopen and a failed write does not report success. For exports, inspect rendered pages and restored content. For rehearsal, document actual playback and instructor/floor observations separately from automated checks.

Keep Basic mode useful without technical setup. Preserve existing values when changing detail mode. AI must stay optional and use the user's provider/account/local endpoint and charges; no shared keys, developer-funded credits, owner-operated paid inference backend, proxy AI or hidden fallback. Link-based directory features must not become unauthorized scraping, media downloads or publishing bypasses.

## Reviews and releases

Describe the concrete behavior changed, why it matters, and how it was checked. Flag schema migrations, compatibility limits, new dependencies, outbound data and content rights. Never put account secrets or protected project data in source, examples or release artifacts.

The maintainer reviews code, content permissions and instructor evidence before promotion into the default catalog or release. Follow [LICENSE](LICENSE) and retain upstream notices; this document does not create a separate contributor agreement or require assignment of ownership. A source commit, passing unit test, or generated zip alone does not establish a supported public release.

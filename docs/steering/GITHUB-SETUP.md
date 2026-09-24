# GitHub repository setup

Based on the user's repository-creation screenshot during planning, 3 September 2026. These are suggested form values; no repository was created by this document task.

**Update:** the user subsequently created [bigchez2143/HillbillyHellfireLineDancing](https://github.com/bigchez2143/HillbillyHellfireLineDancing). The follow-up screenshot shows an empty public repository. Its HTTPS remote is `https://github.com/bigchez2143/HillbillyHellfireLineDancing.git`. The settings below remain a record of setup guidance. No application source was uploaded or release published by this task.

## Description

Paste this into Description:

> Freeware line dance creator for dancers, instructors, and choreographers, with music analysis, step sheets, rehearsal tools, and optional bring-your-own AI.

This describes the intended product. The README and release notes must distinguish current functionality from planned features while development continues.

## Add license

Select **No license for now** in the GitHub creation form. Add a software-specific custom `LICENSE` before releasing the application. No license is a temporary setup choice, not the intended final freeware permission: default copyright restrictions apply, while GitHub's terms allow viewing/forking a public repository. [GitHub licensing guidance](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

The eventual terms need to grant free use and the requested use of dances at paid classes/events while prohibiting sale or monetization of the software. Ordinary open-source licenses allow commercial activity and therefore do not implement this restriction. Call a restricted public-source release **source-available freeware**, rather than OSI open source. [Open Source Definition](https://opensource.org/osd).

The license intent is already specified in [Integrations and release](INTEGRATIONS-AND-RELEASE.md), with remaining policy questions in [Decisions](DECISIONS.md). Those planning notes are not final legal license text. Complete the software-specific wording and review before public distribution; third-party component and content licenses remain separate.

## Other fields visible in the screenshot

- Owner/name: `bigchez2143/HillbillyHellfireLineDancing`; creation confirmed by the user's follow-up screenshot above.
- README: leave Off when preparing an empty remote for this existing local project; publish the project's reviewed README with the source.
- .gitignore: leave No .gitignore in this form for that same empty-remote workflow; prepare and review the project's local ignore rules before the first push.
- Public is the selected visibility. Upload only the reviewed release source and content described in the S09 gate.

AI wording remains explicit: users connect their own provider/account or endpoint and pay any provider charges. This freeware supplies no shared AI account, bundled paid credits or app-operated inference service.

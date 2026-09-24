# Hillbilly Hellfire Line Dance Creator

A local Windows application for writing, rehearsing and sharing line dances. Basic mode keeps the everyday tools easy to find; Advanced mode exposes the existing lyrics, AI connection and production tools. Core features work without an AI account.

## Start the application

Double-click `app/run.bat`. Source setup uses Python 3.12 and the pinned core requirements; the first setup needs internet. Later launches use the local environment and open `http://127.0.0.1:8766/dance`. Optional speech/stem models are not installed at startup. Existing project data remains under `app/projects` in source mode.

Install, launch, automated tests, and a five-step manual smoke list are in [TEST-IT.md](TEST-IT.md).

An internal portable Windows candidate includes its own runtime and stores new user data under `%LOCALAPPDATA%/HillbillyHellfire/LineDanceCreator`, unless you choose explicit data-directory overrides. Public distribution is pending the release gates below.

## Create and teach

- Start without music, or attach a song and measure its beat. Correct BPM, the first dance beat and tempo changes yourself.
- Build parts, tags, restarts and endings; use local generation and lock favorite moves. Save drafts, undo edits and keep named versions.
- Rehearse with count, current/next move, facing, count-in, playback speed and loops.
- Add your own moves, teaching pictures/videos and links. Preview CSV, Excel or JSON imports, including proposals from your own AI.
- Export PDF, Word, plain text, HTML, CSV, Excel, subtitles/captions and editable portable drafts.
- Keep local learning lists, checklists, class setlists, song alternatives and calendars.

The catalog retains 173 reference entries and 39 executable core moves (78 lead variants). Missing or unknown mechanics remain marked for review. This is an extensible vocabulary, not a claim to contain every named dance variation. Fresh explanations for all 173 entries are separate instructor-review drafts.

## Advanced tools

Creator Studio links to the existing detailed editor, lyric alignment/sections, tutorial review and Sound Repair Studio. Structured dances that cannot be represented faithfully by the older production model are rejected visibly instead of flattened. Sound repair and local transcription require separate optional dependencies/model downloads.

AI is bring-your-own: users choose their own provider/account/key/endpoint and pay any provider charges. No shared app key, paid credits or owner-funded inference is included. Local music analysis does not require a cloud AI provider.

## Review status

This is an internal review candidate. **430 backend tests and two JavaScript regression suites passed** in the documented final run. Human dancer/instructor sessions, full accessibility checks, clean-machine Windows testing, final license/content/native-library review and public release are still pending. Browser file-upload acceptance was declined by the browser permission check and is not reported as passed.

See [implementation status](docs/steering/IMPLEMENTATION-STATUS.md), [sprint backlog](docs/steering/ROADMAP.md), [test evidence](docs/steering/evidence/FINAL-REGRESSION.md), [privacy](PRIVACY.md), [third-party notices](THIRD_PARTY_NOTICES.md) and [license draft](LICENSE-DRAFT.md). The restricted-freeware draft is not an adopted license. It distinguishes software monetization from paid dance activities and original creative output; upstream terms remain separate.

Discover Hillbilly Hellfire on [YouTube](https://www.youtube.com/@HillbillyHellfire) and the [website](https://www.hillbillyhellfire.com/).

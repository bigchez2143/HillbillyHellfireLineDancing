# Hillbilly Hellfire Line Dance Creator

A local Windows application for writing, rehearsing and sharing line dances. Basic mode keeps the everyday tools easy to find; Advanced mode exposes the existing lyrics, AI connection and production tools. Core features work without an AI account.

## Start the application

Double-click `app/run.bat`. Source setup uses Python 3.12 and the pinned core requirements; the first setup needs internet. Later launches use the local environment and open `http://127.0.0.1:8766/dance`. Optional speech/stem models are not installed at startup. Existing project data remains under `app/projects` in source mode.

Install, launch, automated tests, and a five-step manual smoke list are in [TEST-IT.md](TEST-IT.md).

A one-page class guide is [release/Instructor one-pager.pdf](release/Instructor%20one-pager.pdf). The editable source is [release/instructor-one-pager.md](release/instructor-one-pager.md). Rebuild the PDF with `python scripts/render_instructor_one_pager.py`. The portable folder copies that PDF to the top, beside `Launch Line Dance Creator.bat`.

## Download (portable zip)

No account is required. There is no Setup installer and no desktop icon. Unzip the folder and double-click `Launch Line Dance Creator.bat` (`run.bat` in that folder starts the same launcher). Optional connections are zero-cost in this app: bring your own credentials. The download does not include a shared AI key.

Build the zip from this repository. This command runs on Linux and on Windows:

```bash
python scripts/build_release_zip.py
```

It writes `build/HillbillyHellfire-LineDanceCreator-windows.zip` with `Launch Line Dance Creator.bat`, `run.bat`, `app/run.bat`, `Instructor one-pager.pdf`, the Corn Maze sample, and `LICENSE`. That zip does not embed Windows Python. The first launch uses `app\run.bat`, which needs Python 3.12 once.

On Windows x64 with CPython 3.12 and the locked core environment, add the private runtime so a dancer does not install Python:

```bat
.venv\Scripts\python.exe scripts\build_portable.py --output build\portable-candidate --zip
```

Details are in [Windows portable zip](docs/windows-portable-zip.md). A page draft for hillbillyhellfire.com, not a live deploy, is [docs/download-page-draft.md](docs/download-page-draft.md).

The Windows runtime build stores new user data under `%LOCALAPPDATA%/HillbillyHellfire/LineDanceCreator`, unless you choose explicit data-directory overrides. Public download and the website page are still pending the release gates below.

## License

[LICENSE](LICENSE) is the freeware license (version 1.0, 24 September 2026). Copyright (c) 2026 Lee Burnette. Line Dance Creator is published under the Hillbilly Hellfire name. Lee Burnette still needs to confirm that rights-holder line before a public release.

You may use, study, copy, and modify the Software, including for paid dance classes, workshops, performances, and events. You may charge for your own choreography and teaching. You may not sell the Software or charge for access to it. Your dances and other original outputs stay yours. Third-party components and songs keep their own terms. The Software is provided as is.

This is freeware with those limits. It is not an OSI open source license.

[LICENSE-DRAFT.md](LICENSE-DRAFT.md) is only the earlier draft. It is not a second license.

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

See [implementation status](docs/steering/IMPLEMENTATION-STATUS.md), [sprint backlog](docs/steering/ROADMAP.md), [test evidence](docs/steering/evidence/FINAL-REGRESSION.md), [privacy](PRIVACY.md), [third-party notices](THIRD_PARTY_NOTICES.md) and [LICENSE](LICENSE). [LICENSE](LICENSE) is the operative freeware text. It distinguishes software monetization from paid dance activities and original creative output; upstream terms remain separate. Clean-machine publication is still open.

Discover Hillbilly Hellfire on [YouTube](https://www.youtube.com/@HillbillyHellfire) and the [website](https://www.hillbillyhellfire.com/).

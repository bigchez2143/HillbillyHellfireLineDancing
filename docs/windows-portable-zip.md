# Windows portable zip

This is the repo-side package for a future GitHub Release. There is no Setup installer and no desktop icon. It does not publish a release by itself, and it does not update hillbillyhellfire.com.

Two build commands share one folder layout: `Launch Line Dance Creator.bat`, `run.bat`, `app/run.bat`, `Instructor one-pager.pdf`, `sample/the-corn-maze-dance`, `LICENSE`, `START-HERE.txt`, and `RELEASE-NOTES.md`.

## Zip you can build on Linux

From the repository root, with the tested Python environment (the `packaging` package, which the portable builder already imports):

```bash
python scripts/build_release_zip.py
```

That writes:

- `build/HillbillyHellfire-LineDanceCreator/`
- `build/HillbillyHellfire-LineDanceCreator-windows.zip`

The script refuses to replace an existing output folder or zip. It does not download anything and it does not embed Windows CPython. On a PC, unzip it and double-click **Launch Line Dance Creator.bat**. That launcher calls `app\run.bat`, which needs Python 3.12 for the first setup (internet once) and then stays local.

This command is the path a Linux CI job can run. It checks the zip layout. It does not replace a clean Windows machine test.

## Zip with a private Python runtime (Windows)

On Windows x64, CPython 3.12, from the locked core environment:

```bat
.venv\Scripts\python.exe scripts\build_portable.py --output build\portable-candidate --zip
```

That folder includes `runtime\python.exe`. **Launch Line Dance Creator.bat** uses it, so the dancer does not install Python. The same bat falls back to `app\run.bat` if the runtime is absent. The Windows build still runs the local smoke check inside `scripts/build_portable.py` and still refuses to delete an existing output folder.

Attach that zip to a GitHub Release when the remaining release gates are done, including a clean Windows check. Prefer it over the Linux-built zip for the public download, because it is the copy that does not ask for a separate Python install.

Creating the Release, tagging, and posting the hillbillyhellfire.com page are separate steps. See `docs/download-page-draft.md` for the page Wendy can post. Do not treat a local zip as a published download.

## What the zip is for

No account is required. Optional AI and other connections stay zero-cost in this app: bring your own credentials. No shared key is included. The Corn Maze sample is teaching material written for this app, with no song file.

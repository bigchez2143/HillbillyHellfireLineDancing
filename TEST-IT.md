# Test Line Dance Creator

Internal review path for a local Windows checkout. Public release gates in [implementation status](docs/steering/IMPLEMENTATION-STATUS.md) are still open. AI stays bring-your-own: leave Optional AI settings empty for this smoke test.

The first Windows setup needs Python 3.12 (or [uv](https://docs.astral.sh/uv/)) and internet. Later launches stay offline. Speech and stem models are optional and are left uninstalled.

## Install and start on Windows

1. Open this folder.
2. Double-click `app\run.bat`.
3. Wait until the window says it is starting, then open [http://127.0.0.1:8766/dance](http://127.0.0.1:8766/dance) if the browser does not open itself.

The first run creates `.venv` at the repository root and installs `requirements\core-win-py312.lock.txt`. It does not install `addon-lyrics.txt` or `addon-repair.txt`. Projects stay under `app\projects`.

Check the environment without starting the server:

```bat
app\run.bat --check
```

The same setup from a terminal, if you prefer commands over the double-click:

```bat
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements\core-win-py312.lock.txt
cd app
..\.venv\Scripts\python.exe server.py
```

`run.bat` also accepts `uv` or a `python` that is already 3.12. Stop the server with Ctrl+C in that window.

## Run the tests on Windows

From the repository root, after the environment above exists:

```bat
.\.venv\Scripts\python.exe -B -m pytest -q
node app\tests\test_draft_merge.cjs
node app\tests\test_legacy_state.cjs
node --check app\static\creator.js
node --check app\static\app.js
```

The September 4 Windows record in [final regression evidence](docs/steering/evidence/FINAL-REGRESSION.md) is 430 passed backend tests plus those two Node scripts and the two syntax checks. This tree now collects 582 backend tests. One of them, `test_optional_ai_key_stays_private_to_the_local_server`, stores a synthetic key with Windows DPAPI and needs a normal Windows user session. A sandbox that blocks `CryptProtectData` fails that single test; the rest of the suite can still be read on its own.

These additional Node scripts are in the tree and passed on the Linux rerun below:

```bat
node app\tests\test_ai_connection_ui.cjs
node app\tests\test_move_browser.cjs
node app\tests\test_move_form.cjs
node app\tests\test_move_timing.cjs
node app\tests\test_phrases_ui.cjs
node app\tests\test_profile_storage.cjs
```

## Five manual smoke checks

Do these in the browser at [http://127.0.0.1:8766/dance](http://127.0.0.1:8766/dance). They are the first five browser checks listed in [implementation status](docs/steering/IMPLEMENTATION-STATUS.md).

1. **Create a project without music or AI.** On My Dances, choose **Start without music**, enter a dance name, and choose **Create dance**. You should land on Create / Edit. Leave Optional AI settings untouched.
2. **Add moves.** In the move list, choose a row marked with a plus (rows marked Preview open a preview and do not insert). The move should appear in the sequence for the current part.
3. **Save and reopen.** Choose **Save** and wait for **Saved locally**. Go back to My Dances, then open the same dance. The move should still be in the sequence.
4. **Undo and Redo.** Add or remove a move. **Undo** (or Ctrl+Z) should reverse it. **Redo** (or Ctrl+Shift+Z) should put it back.
5. **Practice Play, Pause, and count advance without audio.** Open Practice. Set Count-in to **None** so the first seconds are the dance count rather than the default 4-count Ready. Choose **Play**. The button label becomes **Pause**, and the big count should move past 1 at the dance BPM (120 until you change it). Choose **Pause**. The count should stay put. No song file is required.

A headless Linux browser completed this same five-step path against `server.py` on 24 September 2026, including Advanced mode (Workspace view shows **Creator Studio**). Repeat it on your Windows machine before treating the session as yours.

## Linux rerun used to check this checkout

Cloud verification used CPython 3.12.3. `requirements\core-win-py312.lock.txt` is a Windows version snapshot, so this host installed the ranges in `requirements\core.txt` plus the test tools:

```bash
sudo apt-get install -y python3.12-venv libsndfile1
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements/core.txt pytest httpx
.venv/bin/python -B -m pytest -q
```

Result: **581 passed, 1 skipped, 0 failed** in about 17 seconds. The skip is the Windows DPAPI key test. Every `app/tests/*.cjs` script exited 0, and `node --check` passed for every file in `app/static/*.js`.

Server start from `app\`, which is what `run.bat` does after its environment check:

```bash
cd app
../.venv/bin/python server.py
```

Confirmed: `GET /dance`, `/`, `/legacy`, the stylesheet and script tags on the dance page, `GET /api/health`, `GET /api/moves/summary` (39 buildable moves), and `POST /api/projects` all returned success. The only HTTP 404 in the browser smoke was `/favicon.ico`.

`.venv` is gitignored. Do not commit it, `app\projects`, `app\settings.json`, or media.

## Still needs a real Windows session

- Double-click `app\run.bat` on your PC, including a first-time install into `.venv`.
- The DPAPI API-key test in a normal Windows user session, if you want that one case green.
- A human dance session: a song you have rights to use, timing by ear, practice on the floor, and a print or export you can read.
- Clean-machine, non-admin, offline-after-install, and portable-candidate checks.
- Accessibility, screen reader, and zoom.
- Browser file upload of a song or a move import. The earlier automated browser pass declined that upload, so it is still unexecuted.
- Instructor review of move explanations and mechanics. Passing tests are an engineering rerun, not a public release.

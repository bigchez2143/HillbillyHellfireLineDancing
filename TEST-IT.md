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

The September 4 Windows record in [final regression evidence](docs/steering/evidence/FINAL-REGRESSION.md) is 430 passed backend tests plus those two Node scripts and the two syntax checks. This tree now collects 636 backend tests, including the Publish pack, Community shelf, Song card, Advanced drawer, Corn Maze starter, and instructor one-pager checks. Two of them store a synthetic key with Windows DPAPI and need a normal Windows user session: `test_optional_ai_key_stays_private_to_the_local_server` and `test_windows_dpapi_keeps_the_bootstepper_key_out_of_the_settings_file`. A sandbox that blocks `CryptProtectData` fails those two tests; the rest of the suite can still be read on its own.

These additional Node scripts are in the tree and passed on the Linux rerun below:

```bat
node app\tests\test_ai_connection_ui.cjs
node app\tests\test_move_browser.cjs
node app\tests\test_move_form.cjs
node app\tests\test_move_timing.cjs
node app\tests\test_phrases_ui.cjs
node app\tests\test_profile_storage.cjs
node app\tests\test_publish_ui.cjs
node app\tests\test_community_shelf_ui.cjs
node app\tests\test_song_card_ui.cjs
node app\tests\test_advanced_drawer_ui.cjs
```

## Five manual smoke checks

Do these in the browser at [http://127.0.0.1:8766/dance](http://127.0.0.1:8766/dance). They are the first five browser checks listed in [implementation status](docs/steering/IMPLEMENTATION-STATUS.md).

1. **Create a project without music or AI.** On My Dances, choose **Start without music**, enter a dance name, and choose **Create dance**. You should land on Create / Edit. Leave Optional AI settings untouched.
2. **Add moves.** In the move list, choose a row marked with a plus (rows marked Preview open a preview and do not insert). The move should appear in the sequence for the current part.
3. **Save and reopen.** Choose **Save** and wait for **Saved locally**. Go back to My Dances, then open the same dance. The move should still be in the sequence.
4. **Undo and Redo.** Add or remove a move. **Undo** (or Ctrl+Z) should reverse it. **Redo** (or Ctrl+Shift+Z) should put it back.
5. **Practice Play, Pause, and count advance without audio.** Open Practice. Set Count-in to **None** so the first seconds are the dance count rather than the default 4-count Ready. Choose **Play**. The button label becomes **Pause**, and the big count should move past 1 at the dance BPM (120 until you change it). Choose **Pause**. The count should stay put. No song file is required.

A headless Linux browser completed this same five-step path against `server.py` on 24 September 2026, including Advanced mode (Workspace view shows **Creator Studio**). Repeat it on your Windows machine before treating the session as yours.

## Publish pack and Community shelf

Do these after the five checks above. They stay on the normal menu. Optional AI settings stay empty.

6. **Publish.** With a dance open, choose **Publish** in the top bar (My Dances has the same button on each dance). Wait until the window says the step sheet and portable draft are in a folder on this computer. Choose **BootStepper**, **CopperKnob**, or **LineDance.com** and confirm the browser opens that site. You upload the step sheet yourself; the app does not send the dance. Choose **Copy folder** and confirm the folder path is copied. Choose **Show folder** if you want to see the files. Nothing on this screen asks for a key.
7. **Community.** Open **Line Dance Tools** (or **Open community links** under Settings / Help). The list should include BootStepper, CopperKnob, LineDance.com, BootStepper’s add-a-dance page, the Hillbilly Hellfire site, and the Hillbilly Hellfire YouTube channel. Add a link, edit it, remove it, then refresh the page. Your change should still be there. **Restore starter links** puts the original list back. This panel is not inside Optional AI settings.

LineDance.com opens [https://www.linedance.com/submit](https://www.linedance.com/submit) (Submit a Dance; sign in there if the site asks). CopperKnob opens [https://www.copperknob.co.uk/contactus](https://www.copperknob.co.uk/contactus). BootStepper opens [https://bootstepper.com/dances/create](https://bootstepper.com/dances/create).

## Song card

Do this with a dance open. Optional AI settings stay empty. Nothing on this screen asks you to sign in to Spotify or to paste a key.

8. **Spotify link.** Open **Music**. On **Song card**, paste a Spotify song, album, or playlist link (it starts with `https://open.spotify.com/`). The note should say the link is for sharing and opening, and that it does not play with the dance. Choose **Open Spotify link** and confirm the browser opens that page. Choose **Copy link** if you want to share it. Save, leave the dance, and open it again. The link should still be there.
9. **No local file.** Leave **Local audio file** empty. Open **Practice**. The note should say rehearsal uses the metronome. Set Count-in to **None**, then choose **Play**. The big count should advance. Spotify should not start playing.
10. **Local audio.** Back on **Music**, choose a local audio file you have permission to use. **Analyze local audio** uses that file. Open **Practice** again. The note should say rehearsal plays the local file, and **Play** should play that file. The Spotify link can stay filled in. It still does not replace the file.

## Advanced drawer

Do this only if you want to try a personal key. The checks above do not need it. Leave Advanced empty for a normal dance session.

11. **Empty by default.** Set Workspace view to **Advanced**. Open **Settings / Help** and open **Advanced**. It should say the app works with no keys, that a personal key stays on this computer, and that BootStepper search is read-only. **Spotify** should say a client id is not enabled, with no box to paste one. **Optional AI settings** opens the same connection screen as before. Leave the key blank. Switch Workspace view back to **Basic**. The Advanced drawer should be gone. Create, practice, and Publish still work, and Publish does not ask for a key.
12. **BootStepper search, if you have your own key.** On your BootStepper account, create a personal key. Paste it under Advanced and choose **Save key on this computer**. Search for a dance, a song, and a choreographer. Results should name BootStepper and offer **Open on BootStepper**. This app does not upload the dance. Choose **Forget saved key** when you are done. The key should not appear in a Publish folder or a portable draft.

## Starter dance and freeware line

These checks use a new projects folder. They do not need a song file or an Advanced key. Publish, the song card, and Advanced stay as they were.

13. **The Corn Maze Dance.** On My Dances, the list should include **The Corn Maze Dance**, marked as a starter sample, with no local audio. Open it. The steps are a beginner sample written in this app from its own moves. They are not a copy of a published step sheet. Open **Practice**, set Count-in to **None**, and choose **Play**. The count should advance. No song starts playing.
14. **About.** Open **Settings / Help**. About should say **Freeware from Hillbilly Hellfire** and link to [https://hillbillyhellfire.com](https://hillbillyhellfire.com). The same line is in the footer on the dance page, the older creator page, and Sound Repair Studio.

## Instructor one-pager

The class walkthrough is [release/Instructor one-pager.pdf](release/Instructor%20one-pager.pdf), written from [release/instructor-one-pager.md](release/instructor-one-pager.md). It follows the screens above: open the app, My Dances, The Corn Maze Dance, Create / Edit, Practice, the Song card, Export, Publish, and Community. It does not ask for an Advanced key. The portable candidate places the same PDF beside `Launch Line Dance Creator.bat`. After editing the markdown, rebuild it with `python scripts/render_instructor_one_pager.py`.

## Linux rerun used to check this checkout

Cloud verification used CPython 3.12.3. `requirements\core-win-py312.lock.txt` is a Windows version snapshot, so this host installed the ranges in `requirements\core.txt` plus the test tools:

```bash
sudo apt-get install -y python3.12-venv libsndfile1
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements/core.txt pytest httpx
.venv/bin/python -B -m pytest -q
```

The readiness rerun on 24 September 2026, before Publish and Community, was **581 passed, 1 skipped, 0 failed**. After those features, the same command was **595 passed, 1 skipped, 0 failed**. After the Song card, the same command was **616 passed, 1 skipped, 0 failed**. After the Advanced drawer, the same command was **626 passed, 2 skipped, 0 failed**. After the Corn Maze starter and the freeware line, the same command was **631 passed, 2 skipped, 0 failed**. After the instructor one-pager, the same command on this branch was **636 passed, 2 skipped, 0 failed** in about 20 seconds. The skips are the two Windows DPAPI key tests. Every `app/tests/*.cjs` script exited 0, including `test_publish_ui.cjs`, `test_community_shelf_ui.cjs`, `test_song_card_ui.cjs`, and `test_advanced_drawer_ui.cjs`, and `node --check` passed for every file in `app/static/*.js`.

Server start from `app\`, which is what `run.bat` does after its environment check:

```bash
cd app
../.venv/bin/python server.py
```

Confirmed: `GET /dance`, `/`, `/legacy`, the stylesheet and script tags on the dance page, `GET /api/health`, `GET /api/moves/summary` (39 buildable moves), and `POST /api/projects` all returned success. The only HTTP 404 in the browser smoke was `/favicon.ico`.

`.venv` is gitignored. Do not commit it, `app\projects`, `app\settings.json`, or media.

## Still needs a real Windows session

- Double-click `app\run.bat` on your PC, including a first-time install into `.venv`.
- The two DPAPI key tests in a normal Windows user session, if you want those cases green. One covers Optional AI. The other covers the BootStepper personal key.
- A human dance session: a song you have rights to use, timing by ear, practice on the floor, and a print or export you can read.
- Clean-machine, non-admin, offline-after-install, and portable-candidate checks.
- Accessibility, screen reader, and zoom.
- Browser file upload of a song or a move import. The earlier automated browser pass declined that upload, so it is still unexecuted.
- Instructor review of move explanations and mechanics. Passing tests are an engineering rerun, not a public release.

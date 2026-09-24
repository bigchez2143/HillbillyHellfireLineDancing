# Legacy project upgrade preservation check

**PASS: all four original project backups preserved their existing content through opening and saving with the new project store.** Executed 4 September 2026 at 04:12 America/New_York using CPython 3.12.14 in the development virtual environment. No application source was edited.

## Scope and method

The private backup manifest contains four schema-0 `project.json` files, totaling 562,599 bytes. Every backup's SHA-256 matched its manifest before execution and remained unchanged afterward. Tests ran only on fresh copies under `work/migration-verification/run-20260904-041210-035619/projects/`. Both project storage and the optional runtime-data root were explicitly redirected beneath that run directory before importing the production project store. No server or browser was started, and no media or private project data was uploaded.

For each copy, the verification script:

1. Loaded the project and opened its workspace, proving that these reads did not rewrite `project.json` and that every original field/value remained present and unchanged.
2. Saved the complete migrated draft, reopened it, and recursively compared all original fields, ordered arrays, strings and values. It checked every original nonempty path/file/URL reference field without printing its value.
3. Verified a byte-exact `project.pre-schema-1.json` and first last-good backup. It resolved the selected dance through the new frozen draft definitions and compared the resulting moves with the original concrete move records.
4. Changed only the copy's draft count target, saved it, and proved the accepted dance and every original top-level field stayed unchanged. It restored the original draft, leaving document revision 3, and confirmed that the original migration backup was still byte-exact.
5. Simulated an external same-revision edit in that copy, then attempted a stale `save_project` call. The source-hash guard rejected all four attempts with `RevisionConflict`, leaving the externally edited copy's bytes untouched.

## Preservation counts

Fixture numbers follow the private manifest order. Project titles, lyrics, move prose and media paths are intentionally omitted from this summary.

| Fixture | Original top-level fields | Candidates / move occurrences | Selected moves resolving identically | Music sections / lyric sections | Nonempty reference fields |
|---|---:|---:|---:|---:|---:|
| 1 | 12 | 3 / 26 | 9 | 10 / 10 | 3 |
| 2 | 14 | 0 / 0 | 0 | 0 / 0 | 3 |
| 3 | 15 | 3 / 29 | 10 | 11 / 7 | 5 |
| 4 | 13 | 0 / 0 | 0 | 0 / 7 | 3 |
| **Total** | **54** | **6 / 55** | **19** | **21 / 24** | **14** |

All four accepted-dance objects remained unchanged after draft saves. No accepted or draft missing-definition issues were reported. The one populated lyric-move draft, song metadata, analysis, alignment, phrase data, generation settings and all other original fields were retained by the recursive comparison. Original empty/null fields were also retained.

## Source drift check

All **52 files** in the development baseline manifest matched their recorded hashes in both the original source tree and the isolated baseline copy. No missing files or changed hashes were found in that manifest's scope at execution time. This is a point-in-time check of the listed files, not a complete inventory of every file in either tree.

## Reproducibility and limits

Private executable check: `work/migration-verification/check_upgrade.py`. Its SHA-256 was `5f9baf2d2b3d9f998b390413e3e2970815ec3aa7de64197439fd613117ba76fe`. Machine-readable counts and results are in the run directory's `results.json`. The tested `app/engine/project.py` SHA-256 was `b1eea6063c07776cf1f48cc9a027800cb5e87046ca70fe4bed8ec653776de532`.

These four backups contain no custom-dance move list, populated sheet-metadata fields or authored tutorial segments; tutorial fields are absent in two projects and null in two. Their empty/absent states were preserved, but populated custom/tutorial/metadata migration behavior relies on the separate synthetic automated fixtures. The 55 count above is candidate move occurrences, not a claim about distinct move vocabulary or every move proposal nested elsewhere.

Only JSON documents were copied. Reference preservation does not prove media-file availability, relinking, playback, rendered exports, browser recovery, installer behavior or a clean-machine upgrade. No original project, backup, source file, song or media asset was written. The run copies contain private project content and synthetic conflict markers; keep them out of public source and release packages.

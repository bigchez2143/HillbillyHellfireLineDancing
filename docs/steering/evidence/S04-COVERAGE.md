# S04 move coverage and local library evidence

Evidence date: 2026-09-03. Scope: the isolated development copy, its retained reference data, core move definitions, and the S04 backend. This is a code/data and automated-test audit, not instructor review or an assertion that every line-dance movement in the world is catalogued.

## Retained reference coverage

The reference catalog contains **173 records**, in its existing order, with all names, aliases, descriptions, and mechanical fields preserved by S04. The separate seed file contains **37 records**. S04 does not rewrite their provenance or rights statements.

| Reference category | Records | Stored numeric counts | Stored numeric net rotation |
| --- | ---: | ---: | ---: |
| Concept / terminology | 26 | 0 | 0 |
| Footwork primitive | 52 | 52 | 52 |
| Step pattern | 77 | 74 | 73 |
| Styling | 18 | 0 | 0 |
| Total | **173** | **126** | **125** |

Stored count values are 1 (40 records), 2 (59), 3 (5), and 4 (22). Forty-seven entries have no fixed stored count. Those include all 26 concepts, all 18 styling entries, and the patterns Extended Grapevine, Progressive Turn, and Ramble. A description containing count notation is not automatically an executable count schedule.

The catalog has 102 `foot_start: R`, 19 `either`, 51 `na`, and one `e`. The last is **Clap**, with `foot_end: either`; the unusual `e` value is retained as a reported fact, not silently corrected or interpreted. Break Turn, Heel Pivot, and Heel Turn have a stored count but no numeric net rotation. Existing `seed_verified` values occur on 37 records, and `ab_safe` is true on 19. Those retained legacy fields are not evidence of a new independent instructor assessment.

Catalog SHA-256 at this audit:

`47de580441f601c4bcc05bc59eca8a9a4f8832cbc65f8228bb943b970b8f8a3d`

## Executable definitions and manual use

`app/engine/steps.py` contains **39 core pattern definitions**: 33 admitted to the existing generator and 6 editor/filler definitions. Its R/L variant interface returns 78 concrete variant outputs. This is a different set and level of representation from the 173 vocabulary records; subtracting 39 from 173 is not a reliable count of missing moves. The core engine's aggregate count/free-foot/turn model does not supply every internal foot transfer of every pattern.

S04 adds manual access to **every reference record** through:

`GET /api/creator/library/reference/reference-{index}/snapshot`

Indices run from 0 to 172 in the retained order. The result embeds the complete reference record, its name/aliases/explanation, reported mechanical fields, and a content fingerprint. Known counts provide initial timing. For a record without fixed timing, the optional `duration_counts` query accepts an exact user-supplied value such as `3/2`; otherwise `requires_counts` is true and the missing timing remains visible.

The executable event deliberately retains unknown support/rotation until a choreographer defines the intended variant. Stored aggregate reference metadata is kept separately under `reported_mechanics`. A counted reference snapshot therefore compiles as **UNVERIFIED**, while missing duration additionally prevents a complete schedule. No automatic mirroring, generator admission, or instruction verification is inferred from a common name, description, or seed flag. Terminology may be used as an authored annotation with chosen timing; it is not automatically treated as a physical movement.

Custom records can hold names, aliases, original/user-supplied explanations, exact durations, explicit compiler events, difficulty, origin notes, links, and attachments. There is no fixed move-name whitelist. A new named move can remain useful as an unverified manual entry while the author supplies its mechanics. This extensibility is the route to supporting uncatalogued variations; it is not a claim of complete world vocabulary.

The editor must embed returned snapshots into its choreography document. The shared S03 compiler remains the sole interpretation of those events; S04 does not add a competing playback/export runtime or modify the legacy generator catalog.

## Saved history, imports, and media

- User records live in a separate transactional SQLite store. `LINE_DANCE_LIBRARY_DIR` takes precedence, then `LINE_DANCE_DATA_DIR/library`, then the platform's user-data directory. Reading the common catalog does not grant permission to rewrite it.
- Each record change creates an immutable version. Soft delete hides the current record; old snapshots remain available. `POST /records/{id}/restore` appends an undeleted version using an expected-version check. Restoring cannot overwrite a newer edit.
- CSV, XLSX, and JSON imports first produce a local digest-bound preview with mapping, row errors, and name/alias duplicates. Approval selects create, explicit variant, update, or skip. A user-supplied AI JSON file follows exactly the same review path. Imported verification/generator claims are discarded.
- Batches commit atomically and can be rolled back only if none of their affected records has changed since import. A rollback preserves the imported versions and later history. Retrying the same accepted decisions is idempotent; changing already-committed decisions is rejected.
- `AUTHOR_REVIEWED` requires explicit local confirmation plus complete, internally consistent compiler mechanics. It records the user's attestation, not instructor certification. It does not make the record generator eligible. Editing the move's authored fields resets review to `UNVERIFIED`.
- PNG/JPEG/WebP/GIF originals are decoded/verified and bounded. MP4/MOV/WebM receive container-signature checks, not a guarantee of playback or duration. Captions, orientation, and video reference ranges are retained. Ranges are explicitly `USER_ENTERED_NOT_MEASURED`. URLs are stored as links and never fetched by this library.
- Request streams, file sizes, spreadsheet expanded size/dimensions, formats, filenames, and served paths are bounded/checked. Credential-named fields and URLs containing recognized embedded credentials are rejected before persistence. This is not a promise to detect secrets hidden in arbitrary prose.

## Automated evidence and remaining integration gates

The latest focused run is **60 passed**, with two existing test-client deprecation warnings:

```text
.venv\Scripts\python.exe -B -m pytest app\tests\test_library_workflows.py -q --basetemp=.test-tmp\library-reference-1
```

It checks all 173 reference snapshots, retained facts, unknown mechanics, exact fractions, soft-delete/restore/history, concurrent writes, explicit review, duplicates, rollback, mid-batch disk failure, source/mapping errors, AI review claims, credential fields, safe upload/serving, attachment write failure, request streaming limits, and spreadsheet archive/dimension guards. After the reference and restore additions, the combined library/compiler/creator run passed **118 tests in 5.00 seconds**, with the same two deprecation warnings:

```text
.venv\Scripts\python.exe -B -m pytest app\tests\test_library_workflows.py app\tests\test_choreography.py app\tests\test_creator_workflows.py -q --basetemp=.test-tmp\library-reference-integration-2
```

Tests use temporary storage; no real user project or library is used as a fixture.

Remaining product gates are the root-owned UI flow and accessibility review, snapshot insertion in a live editor, and end-to-end instructor/user acceptance. Thumbnail generation, actual video trimming/transcoding, automatic move-recognition from videos, independent instructor certification, and exhaustive vocabulary coverage are **not implemented or established by this backend evidence**. No S04 sprint-complete or release-ready claim follows from these backend tests alone.

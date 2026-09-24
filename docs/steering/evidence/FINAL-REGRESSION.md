# Final local regression evidence

Executed 4 September 2026, approximately 04:08 America/New_York, against the current isolated development copy. This pass changed no application source. Runtime: Windows, development virtual environment CPython 3.12.14; Node.js v22.17.1.

## Executed checks

| Check | Exact command from the development root | Result |
|---|---|---|
| Entire collected backend suite | `.\.venv\Scripts\python.exe -B -m pytest --junitxml=docs/steering/evidence/final-results.xml -q` | **430 passed; 0 failed, 0 errors, 0 skipped.** Console duration 19.65 seconds; JUnit suite duration 19.230 seconds. |
| Pure three-way draft merge regressions | `node app/tests/test_draft_merge.cjs` | PASS; exit 0. |
| Production legacy state/save regressions | `node app/tests/test_legacy_state.cjs` | PASS; exit 0. |
| Creator JavaScript parse check | `node --check app/static/creator.js` | PASS; exit 0. |
| Legacy JavaScript parse check | `node --check app/static/app.js` | PASS; exit 0. |

The two Node scripts are independent script runs, not additional pytest cases. They check independent field changes, atomic ordered-array conflicts, deletions, concurrent acknowledgements, immutable inputs, prototype-key safety, legacy form deltas, frozen definitions, refusal to flatten irregular choreography, stale project responses, expected revisions and edits made during a pending save.

## Sandbox rerun and warnings

The first sandboxed backend run finished with 429 passed and one failure in `test_optional_ai_key_stays_private_to_the_local_server` (21.12 seconds). Windows `CryptProtectData` rejected the synthetic `testing-only-key` fixture. After approved execution outside the sandbox, the entire suite passed, including that test. The JUnit file records this successful complete rerun; no real provider credential was needed for the failing fixture.

The successful run emitted three non-failing warnings: Starlette's deprecated httpx TestClient integration, a deprecated AnyIO BlockingPortal alias, and pytest being unable to write its node-id cache because Windows denied access. Pytest exited 0 and wrote the complete JUnit report.

## Evidence identity

JUnit timestamp: `2026-09-04T04:07:59.934194-04:00`.

| File | SHA-256 observed after execution |
|---|---|
| `final-results.xml` | `390f066a5644236098d2decfd7686a76962a2e9561ed28a5fa4cbfee73a8c609` |
| `app/static/creator.js` | `0361429af9adb947ede6904942e0be379c872e7f9f3149eb12d8300fc51a3080` |
| `app/static/app.js` | `f71114853577b01e309fb846beec74d50b6826e5405bcfaadff5567fd770ff09` |
| `app/static/draft-merge.js` | `e1a5fc403eb25b817b1d4250ab70c60411ab52e29929da4fd7d830e80e40bdec` |

## Limits

No browser interaction or file uploads were performed in this pass. JavaScript parse checks do not establish rendered UI correctness, accessibility or live asynchronous browser behavior. The Node state test runs production functions in a controlled VM with mocked I/O.

These results verify the collected automated suite on this host, not complete T01–T36 acceptance or sprint completion. This pass did not install the application, test a clean/offline/non-admin Windows machine, publish anything, contact real AI providers, conduct human instructor/floor sessions, or repeat visual export inspection. Those gates require their separate evidence. Later source changes require relevant revalidation. Raw JUnit output may contain local paths and must be reviewed before public distribution.

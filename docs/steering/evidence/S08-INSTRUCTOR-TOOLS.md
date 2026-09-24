# S08 local instructor foundation

Implemented locally on 3 September 2026. The engine/router are `app/engine/instructor_tools.py` and `app/instructor_api.py`. The main application mounts the exported `router`; UI wiring is coordinated separately. No hosted calendar, map lookup, automatic provider call or AI service is involved.

## State/API contract

`GET /api/creator/tools` returns `schema_version: 1`, `revision`, `dances`, `setlists`, and `events`. Save the complete document with `PUT /api/creator/tools` and body `{ "expected_revision": 0, "state": { ... } }`. Arrays are required, IDs are unique, broken dance/recording references and unknown fields are rejected. On conflict the API returns 409 with the current revision. Get the current state before reapplying edits; do not blindly retry the old state.

- Dances: `id`, `title`, optional `project_id`, `sheet_url`, `video_url`, tags, favorite, `learning_status` (`new`, `learning`, `ready`, `review`), public/private notes, checklist `{id,label,done}`, practice history `{id,at,duration_minutes,notes}`, and recordings.
- Recordings: `id`, `title`, artist, HTTP(S) URL, optional private local path, independent `music_map`, `choreography_review` (`not_reviewed`, `compatible`, `needs_changes`), and review notes. Matching BPM never sets compatibility automatically.
- Setlists: `id`, `title`, ordered items `{dance_id,recording_id?,duration_minutes,public_notes,private_notes}`, and plan public/private notes. Repeating a dance is allowed.
- Events: `id`, `title`, ISO `start`/`end`, IANA `timezone`, location, public/private notes, optional `rrule`, status (`CONFIRMED`, `TENTATIVE`, `CANCELLED`), UID and sequence. Meaningful local changes increment sequence. Cancel by changing status; deleting an event does not send cancellation to an external calendar.

Storage uses `LINE_DANCE_TOOLS_DIR`, otherwise `LINE_DANCE_DATA_DIR/tools`, otherwise the source application's local `instructor-data` directory. Thread/process locks protect revision checks and atomic replacement; the preceding successful state is retained as `state.backup.json`. Corruption or unsupported schema produces a recovery error rather than silently overwriting data. The portable launcher sets a per-user data root and preserves explicit overrides.

## Guides and calendar exchange

`GET /api/creator/tools/setlists/{id}/guide.html` and `.txt` preserve setlist order, planned durations and public notes. HTML escapes authored content and offers labeled sheet/demo/song links with HTTP(S) validation. Private local recording paths and practice notes never become public links. `include_private=true` explicitly adds instructor notes and marks a private guide. An offline sheet attachment/portable file guide is not claimed by this module; existing project/library exports supply the other file workflows.

`GET /api/creator/tools/events.ics` exports local events. Optional `include_private=true` retains private notes in `X-LDC-PRIVATE-NOTES`, separate from public description; ordinary calendar apps may ignore that custom field. Import keeps its privacy classification. Calendar inclusion is a local file export, not a subscription or public URL.

`POST /api/creator/tools/events/import` accepts `{ics, expected_revision, apply:false}` and returns event details, add/update actions and `preview_token` without saving. To apply, resend the exact content and revision with `apply:true` and that token. Changes to the file or local revision invalidate the preview. Matching UIDs update existing events while preserving local private notes; older sequence numbers, duplicate UIDs and recurrence overrides are rejected.

The supported interchange is timed Gregorian events with known IANA timezones or UTC, start/end, title, location, notes, UID, sequence, status, and bounded DAILY/WEEKLY recurrence. Rules require COUNT (1–366) or UTC UNTIL within five years; interval is 1–52 and weekly BYDAY uses weekday names. At most 366 occurrences are accepted. DST gaps/folds in a recurring start or end require manual review. A single repeated-hour event can choose an explicit valid offset and exports through UTC without changing its instant.

All-day/floating-time events, custom timezone meanings, recurrence exceptions, unbounded/monthly rules, alarms, attachments, attendees/invitations, unsupported properties and private/confidential imported event classifications are rejected with an explanation. Embedded timezone offsets are checked against installed IANA data. Unsupported semantics are not silently dropped. The maintained `icalendar` library handles serialization, UTF-8 folding and timezone components; `tzdata` supplies the Windows offline timezone database. [iCalendar RFC](https://www.rfc-editor.org/rfc/rfc5545), [timezone API](https://icalendar.readthedocs.io/en/stable/reference/api/icalendar.cal.timezone.html)

## Executed checks and limits

The focused suite covers state round trips, recording independence, thread/subprocess stale-save races, failed atomic writes, corrupt state protection, escaped/public-by-default guides, safe external anchors, DST recurrence, repeated-hour precision, unknown recurrence rejection, cancellation/import preview, private-note preservation, conflicting timezone definitions and API errors. Actual results are in [instructor-results.xml](instructor-results.xml). These checks use isolated temporary storage and no external accounts.

No real instructor class/floor session, external calendar-client interoperability session, or clean-Windows install has been performed here. Those remain acceptance gates. Core dependency locks now include `icalendar`, `tzdata`, `python-dateutil` and `six`; earlier 45-package portable checks describe the earlier snapshot, and subsequent builds must use the refreshed closure.

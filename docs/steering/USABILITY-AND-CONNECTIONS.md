# Usability and optional connection pass

Owner-authorized scope, 4 September 2026: implement recommendations 1–4, then improve optional AI setup (recommendation 5). Stop development after this pass for owner review and video work. No recurring work or public release is scheduled.

## Delivered behavior

1. **Personal move editor.** Basic offers description-only or count-by-count rows with action text, exact starting counts and duration, weight before/after and plain-language turns. Unspecified mechanics stay unspecified. Advanced retains explicit JSON editing. Versioned saves, notes, links, media and import controls remain available.
2. **Unified move browser.** Search built-in, expanded, current personal and older custom moves together; filter difficulty, move family and favorites. My moves retains personal authorship, while Glossary remains a separate reference collection. Previews use exact count labels and saved-version insertion. Favorites persist in the selected data profile.
3. **Complete private backup.** Preview an allowlisted archive containing saved projects/current and accepted drafts/named versions/last-good copies, library and phrase histories, teaching records, favorites and safe interface preferences. Music/photos/videos stored in owned application folders are optional. External references appear in a relinking report. Restore validates the archive and creates a separate profile and locally generated launcher. Existing data is not overwritten.
4. **Reusable eight-count phrases.** Save consecutive whole moves totaling exactly eight counts, name/favorite/rename/archive/restore them, and preview original or mirrored insertion. Inserted moves are independent snapshots and participate in Undo/Redo. Source and transformation provenance survive draft JSON/ZIP export. Unsupported mirroring produces an explanation without changing footwork.
5. **Optional AI setup.** Connection settings stay in the current interface, with provider guidance, saved-versus-tested status, explicit testing and visible data-flow explanations. Every user supplies their own supported provider/model/credentials. A connection test uses only a fixed short prompt and sends no dance context. No paid-provider test is performed during automated development.

## Preservation and limits

The 216 reference identities, 39 original buildable patterns and 43 expanded definitions remain intact. Expanded variants still require instructor review, and provisional technical cues remain marked. Existing project snapshots are not replaced by current catalog definitions. The built-in generator remains independent of AI.

Backup consistency is per store, not a global transaction. The active draft is saved before preparation; unsaved edits in other windows are outside that snapshot. Media outside owned project/library storage requires relinking. A restored launcher reuses its profile's local port and reports an occupied port instead of opening an unrelated service. Keep the restored folder and application runtime available.

Saving AI preferences is local only. Changing provider/destination must not reuse a previous provider's credential. Test results apply to the tested connection configuration; saving a new configuration requires another test. Stored keys are not returned by settings or included in application backups. Actual provider access, model availability and charges remain the user's account responsibility.

Provider setup references checked 4 September 2026: [OpenAI authentication](https://developers.openai.com/api/reference/overview) and [Claude API overview](https://platform.claude.com/docs/en/api/overview). Model IDs are user-entered rather than a hardcoded claim about account availability.

## Verification and handoff

Run the full Python suite and all JavaScript regression scripts after final integration. Test move creation/reopen, unified filters/favorites, personal insertion, phrase mirror/Undo/Redo, backup preview/download, restore integrity/rollback/path boundaries and connection error/state handling using isolated synthetic data. Build and verify the portable runtime and preserve live user stores during scoped installation. Record final counts and package checksum in the delivery report.

Observed browser checks include a four-count step-touch entered without JSON, saved foot/weight/turn preview, personal favorite persistence after reload, combined picker insertion, an eight-count phrase saved and mirrored to sixteen counts, Undo to eight and Redo to sixteen, and a backup preview listing the test project/move/phrase. The browser backup download route completed. File-upload acceptance remains a manual gate after the earlier browser authorization rejection; independent in-process restore fixtures are separate evidence.

Public GitHub publication, adopted freeware license, instructor/floor acceptance, accessibility user trials and clean-machine installation gates remain open. Stop after delivery so the owner can review the app and work on the video.

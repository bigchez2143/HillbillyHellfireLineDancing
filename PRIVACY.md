# Privacy and local data

Release-preparation draft, 4 September 2026. This describes the current local application and the intended release configuration. The publisher must approve the final statement and provide the contact listed below before public release.

Line Dance Creator works on your computer. The standard launcher serves the interface on `127.0.0.1`; its core authoring, analysis, rehearsal, library and export features do not require a hosted account or an AI connection. The application does not include an analytics or automatic crash-reporting service. Opening a third-party website or choosing an optional external tool is a separate data flow.

## What stays on your computer

Projects can contain dance moves, working drafts, named versions, song metadata and paths, analysis, lyrics, teaching notes and references to media. Local uploads and teaching attachments may create copies in application storage. Instructor tools store favorites, checklists, practice history, alternative recording maps, setlists, event details, and public/private notes. Custom moves and library media are stored locally.

The portable launcher defaults to `%LOCALAPPDATA%\HillbillyHellfire\LineDanceCreator`. Its library and instructor stores are under that data root. Explicit `LINE_DANCE_DATA_DIR`, `LINE_DANCE_LIBRARY_DIR`, `LINE_DANCE_TOOLS_DIR` and applicable project overrides can select other locations. A source checkout preserves its existing source-relative locations unless configured otherwise. Application updates should preserve the separate data folder; keep your own backup before updating.

The browser also stores interface preferences, the last project, custom resource bookmarks and recoverable unsaved drafts in local browser storage for the application's origin, separated by data-profile identity. Those recovery copies can contain authored text. Clearing browser site data removes those browser copies and preferences, not necessarily the saved project files. Move favorites and reusable phrases are stored in local databases. Local terminal output, browser diagnostics and manually saved logs can contain filenames, paths or error details.

The application does not operate cloud synchronization. A backup or synchronization service you choose for these folders may copy their contents under that service's own settings and policy.

## Optional AI connections

AI is bring-your-own: you select a provider/account/model/endpoint and pay any provider charges. There are no shared publisher keys, pooled credits, company-funded hosted inference services, proxy inference services or hidden fallback providers.

Saving connection settings does not contact a provider. The separate Test connection action displays its destination and requires confirmation before sending one short fixed test prompt. The test sends no project, conversation history, music or lyrics; it may incur your provider's normal API charge. A saved configuration alone does not prove that the connection works.

When you explicitly ask the connected assistant, the local server sends the text you enter and a limited conversation history to the chosen endpoint. If project context is selected, the current implementation adds song title/artist and analysis figures, section timing, dance-fit information and a summary of the current moves. That automatic context omits raw audio, file paths and lyric text. Anything you type or paste into the prompt, including lyrics or personal information, can still be sent. The provider processes requests under its own terms and retention settings.

On Windows, the saved API key is protected with Windows DPAPI in the local settings file. It is decrypted by the local server when needed for the selected request; the settings response does not reveal the stored key to the browser. The core project exporter excludes provider settings and credentials. This is not a promise that a compromised Windows account or an indiscriminate folder backup cannot expose sensitive material.

Disabling AI prevents normal assistant requests but may retain its saved key. The remove-key action deletes the local saved key; it does not revoke a credential at the provider or delete the provider's existing records. Manage those controls in your own provider account. A custom endpoint requires a supported adapter; saving an address does not establish support for every service.

## Advanced personal keys

The Advanced drawer on the dance page is optional and empty until you save a key. Basic writing, practice, Publish, and the song card do not ask for one.

A BootStepper personal key, when you save one, is protected with the same Windows DPAPI store as an AI key. The local server uses it only as a request header for a search you start. That search reads dances, songs, or choreographers. It does not upload a dance, and the results are not written into your project or into a saved catalog. The settings response, backups, and dance exports do not include the key. Forgetting the key removes the local copy. It does not delete the key in your BootStepper account.

A Spotify client id is not collected. The song card stores a share link only.

## Optional local tools and links

Speech transcription/alignment and stem separation are optional user-managed modules. Their packages and model weights may need network downloads during installation or first use. The core portable package does not include these models. Review the chosen packages/model hosts and any additional settings before installing them. Normal Basic startup does not install or download them.

Resource, sheet, song, demo and publisher links open the site you choose; that site can receive ordinary browser request information and apply its own cookies or policy. The publisher footer uses simple links without embeds or autoplay. Local guides, calendars and files are not automatically posted to an external directory, public map, social account or event service. Optional rehearsal voice cues select an available voice marked local by the browser; visual cues remain available without one.

## Exports, deletion and sharing

Inspect an export before sharing it. Authored names, credits, links, notes and selected lyric text may identify people or contain content you cannot redistribute. The current portable project export omits audio/media bytes, local paths, connection settings, revision history and analysis caches; lyrics are included only when selected. It is an editable draft transfer, not a full backup of every local file and history record.

Back up everything creates a separate, private archive of saved projects, accepted and working versions, named history and recovery files, custom library history, reusable phrases, move favorites and teaching records. It includes authored notes and lyrics. Stored music, pictures and videos can be selected; external file references remain in its private relinking report. Provider settings and stored credentials, application/runtime files, caches and model weights are excluded. Each store is snapshotted consistently, but stores do not share a single global transaction; finish editing before preparing a backup. The current browser draft is saved first. Unsaved drafts in other browser windows are not collected.

Backup previews are retained locally for up to one hour and cleaned on later backup activity. A restore validates the archive and creates a separate data profile without replacing the current one. Its generated local launcher opens that profile at a stable separate loopback address. Restored data, reports and downloaded archives remain until you remove them. The private archive is intended for recovery, not public sharing.

Class guides and calendars exclude private instructor notes by default. An explicit private export can include them; calendar private notes use a separate application field that other calendar programs may ignore. Local practice history and private file paths are not converted into public guide links. Once you share a file or post data elsewhere, the application cannot recall other copies.

Data remains until removed from its storage locations. Project history, last-good backups, browser recovery copies, exported files, original media and separately synchronized backups can survive deletion of an individual current record. Remove the relevant copies when you no longer want them. Deleting application files alone is not a complete data-erasure process.

For support, send a small synthetic example and a redacted error report. Do not post credentials, private projects, copyrighted songs, attendee details or unreviewed logs in public issues.

**Publisher privacy/security contact: to be supplied before public release.** This draft does not invent an email address or an operational support service.

# Changelog

## 1.2.0

Fixes the fault found when 1.1.0 was run on a device, and adds what that test asked for.

Fixed:

- "There was a problem running the shortcut" after every download. On iOS 27.2 a-Shell's Get File action fails unless it is asked for a copy ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). UMDL now always asks for one. A download that failed this way is offered again on the next run.
- The same wordless failure could follow any background command that ended in an error, such as an update check with no connection. Background commands now continue after an error and UMDL reads their output instead.
- An unsaved download whose files are gone is explained, not attempted.

Added:

- Sign-in confirms itself. The helper opens the site's sign-in page, waits for the sign-in to be stored, and returns to Shortcuts with "Signed in to" and the site's name. "Sign in to this site" after a failed download now opens that site's sign-in page, not its front page.
- Status, in the main menu: tool versions, which sites are signed in, storage, whether GitHub can be reached, and the result of the last download. One tap copies it with the log.
- Copy error details now includes the end of the helper's log.

Changed:

- Files over 1 GB are kept in Files. Copy mode loads a file into memory, and a-Shell times out on very large ones.
- "Run diagnostics" under About is replaced by Status.

## 1.1.0

Fixes for the faults found when 1.0.0 was first run on a device, and the changes that test asked for.

Fixed:

- "An earlier download was not saved" appeared on every run, with nothing to save. On a device an empty text counts as a value, and the shortcut tested for emptiness the wrong way throughout.
- Opening UMDL from the Shortcuts app showed "No link found" in place of the main menu. Same cause.
- Downloads failed with "No module named 'yt_dlp'". The tools are no longer installed into a virtual environment, and the helper now installs any tool that is missing, and finds tools that pip placed where Python was not looking.
- A callback that cannot be read no longer stops the shortcut with an error.

Added:

- Quick setup: one tap creates the album, installs everything and downloads the shared link. Custom setup keeps the two questions.
- The helper script is downloaded by the shortcut in the background, so a failed download is an alert, not text left in a terminal. Setup resumes on the next run without repeating the questions.
- A shortcut and helper from different versions say so, with a link to the latest release.
- A symbol on each action button, and consistent, more formal wording throughout.
- docs/BEHAVIOR.md: every screen, choice and message, with the setup flow chart, each mapped to a test.

Changed:

- Protocol 2. The helper for 1.0 and the helper for 1.1 are not interchangeable; the shortcut downloads the right one.
- Setting names: "Unsupported video formats", "Forget saved sign-ins".
- CI cancels a run that a newer push has replaced, and can publish releases by itself when the repository variable `AUTO_RELEASE` is `true`.

## 1.0.0

First release.

- One tap from the share sheet: the best quality Photos can play, saved to your album.
- Videos, photo posts, playlists, albums and profiles, through yt-dlp and gallery-dl.
- Asks before downloading when a link has more than 10 items.
- Video Photos cannot import is rewrapped or converted on the device, or kept in Files.
- First-run setup, settings, site sign-in, and update checks for the tools and the shortcut.
- Interrupted downloads resume; downloads that were not saved are offered again.

Not confirmed on a physical device at the time of release. The first device test found that setup did not complete; see 1.1.0.

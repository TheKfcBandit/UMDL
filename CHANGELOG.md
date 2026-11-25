# Changelog

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

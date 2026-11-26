# Changelog

## 1.5.0

One tap, and nothing else. Install the new shortcut; it brings its helper with it.

Changed:

- **a-Shell saves to Photos itself.** Files no longer travel through Shortcuts, so a video of any size is saved. In 1.4 a long video downloaded and then failed with "There was a problem running the shortcut", because a-Shell cannot hand Shortcuts a large file.
- **Saved items carry their title as their name**, or the name they were uploaded under, in place of `:private:var:mobile:…`.
- **Saved items are dated the day they were downloaded**, not the day they were uploaded.
- **Photos decides what it can play.** A file is offered as it is and converted only if Photos refuses it. Before, anything that was not H.264 or HEVC was converted without asking.
- Conversion is always at the best quality. The Convert setting is gone.
- The **Update tools** message shows the helper that is installed now, not the one that did the updating.

Removed:

- **Advanced mode**, with its version list and its questions. Resolution and Frame rate in Settings decide the version.
- **Enter a link.** Download from clipboard does the same.

Added:

- Reddit: when Reddit refuses the post's data even to its signed-in browser, the browser reads the post's page instead. Written without a captured page to check against, and not yet run on a device.

If saving from a-Shell fails on a device, the helper falls back to handing files to Shortcuts, as before, and the log says at which step it failed.


## Helper 1.4.1

A helper-only update. Open UMDL and choose **Update tools** once; the shortcut stays as it is.

- **YouTube links opened the YouTube app on "This video is unavailable" and nothing was downloaded.** yt-dlp solves YouTube's JavaScript challenges with a script that, to look like a page of the site, assigns `https://www.youtube.com/watch?v=yt-dlp-wins` to the page's location. In a-Shell that script runs in a real web view, where the assignment is a navigation, and iOS answers a navigation to a YouTube address by opening the YouTube app, on a video that does not exist. a-Shell was then no longer in front and could not hand the result to Shortcuts. The helper now turns that assignment into an ordinary variable when the runtime is a web view. Found from a screen recording of 1.4.0; this is what the 1.3.0 report was too.
- The log names the JavaScript runtime yt-dlp used and says how many navigations were removed.


## 1.4.0

Which version to download and what to do with a file Photos cannot play are now two separate things. Install the new shortcut; it brings its helper with it.

Changed:

- **The best version is always downloaded**, within the Resolution and Frame rate limits. 1.3.0 preferred versions Photos already plays, which stopped YouTube at 1080p. Between versions of the same size and frame rate, one Photos plays is still taken, since converting gains nothing there.
- **Convert** replaces Conversion and is a quality: **Best quality** (the default, also when nothing was ever set), **Smaller file**, or **Off**. It has no say in which version is downloaded. Earlier settings are mapped: "Only when needed" and "For best quality" become Best quality, "Never" becomes Off.
- **Advanced mode asks whenever there is a choice**, and only then. The versions are now shown as an icon list like the main menu, each with a line of detail and its size. Choosing a version Photos cannot play asks, straight away, how to convert it, so a-Shell opens once more and not twice. A file that turns out unplayable after the download is asked about then.
- A frame rate limit is now kept even when a larger version exists above it. In 1.3.0 it gave way to resolution, so on YouTube it never applied.
- Sound Photos plays is preferred when a site offers it, so it is copied and not re-encoded.
- Shorter text in the welcome screen, the Convert and Reset menus and the sign-in notice. Sizes read "83 MB", not "83.0 MB".

Added:

- **Smaller file**, a second conversion quality at about half the size.
- A conversion shows its progress in per cent.
- The log records what advanced mode offered, when the helper handed back to Shortcuts, when the shortcut received the list and when a version was chosen.

Not fixed, because the cause is not known: in the one device test of 1.3.0's advanced mode, a YouTube link ended in the YouTube app showing "video unavailable" after the helper had listed the versions. Nothing in UMDL opens a link. The list is now built from actions already confirmed on a device, and the new log lines will show where a run stops.


## 1.3.0

Quality settings, two modes, a better conversion, and shorter wording throughout. Install the new shortcut; the helper follows by itself.

Added:

- **Resolution** and **Frame rate** limits, each set on its own. Both default to Best available. A site with nothing under a limit still downloads, at its smallest version above it.
- **Mode.** Simple uses the settings and asks nothing, as before. Advanced shows what the site offers (best video, best audio, best single file, with codec and size) and lets you pick the version; if a download turns out to be something Photos cannot play, it shows the source and what it would be converted to, and asks.
- **Conversion** has three settings. "Only when needed" is the behaviour of earlier versions. "For best quality" takes the best version a site has, whatever its codec, and converts it; this is what reaches 4K on YouTube. "Never" keeps unplayable files in Files.
- Custom setup is now the settings list, so all of the above can be set before the first download.
- Status lists the video encoders a-Shell's ffmpeg has.

Changed:

- Conversion now targets HEVC with the device's hardware encoder at a quality level, in place of H.264 at a fixed quality. Size and frame rate are kept, 10-bit sources stay 10-bit, and the sound is copied when Photos can play it. Three fallbacks follow for an ffmpeg without that encoder. The notification names each conversion.
- Settings is one list that stays open. Rows with two values switch on a tap; no row leads to more than one menu.
- "Forget saved sign-ins" and "Reset UMDL" are one row, **Reset**. "Sign out of all sites" also clears the tokens the download tools keep. "Remove everything" now also uninstalls yt-dlp and gallery-dl and signs out, leaving a-Shell as it was before UMDL. It does not touch other files kept in a-Shell.
- Prompts, descriptions and button labels are shorter.

Fixed:

- Reddit through a-Shell's browser stopped at its first step with "JavaScript execution returned a result of an unsupported type". Scripts now report through a-Shell's print channel. Not yet confirmed on a device.

Settings from earlier versions are kept and read as Simple mode with no limits.

## Helper 1.2.2

A helper-only update, picked up by **Update tools** or within a day.

- Reddit: on the test device Reddit refused the API route of 1.2.1 as well. When Reddit blocks the download tools, the helper now has a-Shell's own browser, where the sign-in lives, ask Reddit for the post, and gives the photo or video links to the tools. This covers photos, galleries, Reddit-hosted video and links to other sites. Every step is written to the log.

## Helper 1.2.1

A helper-only update: installed copies of UMDL 1.2.0 pick it up within a day, or at once with **Update tools**. The shortcut is unchanged.

- Reddit: when Reddit's website refuses the request with "You've been blocked by network security", which it does to many networks whether signed in or not, the link is fetched again through Reddit's API.
- A site that blocks the request while UMDL is signed in is no longer answered with "sign in to the site". The message says the account is not the cause.
- The log now records why gallery-dl could not read a link.

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

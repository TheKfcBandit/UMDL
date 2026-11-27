# Changelog

## 1.8.0

Reddit again, and fewer words. Install the new shortcut; it brings its helper with it.

Reddit:

- **Why it failed.** Around 9 October 2026 Reddit closed the data pages yt-dlp and gallery-dl read. They answer "You've been blocked by network security" to everyone: any network, signed in or not, even a browser. It was never the network or a VPN, and UMDL no longer says so.
- **What UMDL does now.** It opens the post in a-Shell's browser, as a visitor would, reads from the page where the photo or video is, and hands those addresses to the tools. Share links from the Reddit app (`/s/…`) are followed the same way. This is the only route for Reddit; the four that could no longer work are gone.
- Not yet run on a device. Reddit cannot be opened from where UMDL is built, so the page reader is tested against pages modelled on Reddit's markup. The log records every step.

Wording, throughout:

- **Higher quality available** shows the title and two buttons, "2160p60 · Converted" and "1080p60 · Native". No explanation.
- "Converting 2160p60 HDR AV1 + AAC", without "for Photos". The same for "Repacking", "Installing tools", "Updating tools", "Downloading".
- Notifications: "Saved to UMDL.", "3 saved to UMDL.", "Converted AV1 → HEVC.", "1 kept in Files.", "Not saved to Photos."
- Main menu: Download, Resume, Settings, Sign in, Status, Update tools, About.
- Settings values: Best, Ask, Always, Never, Library, Notify, Notify and open. Menus are titled by what they set: Resolution, Frame rate, Convert for higher quality.
- Failure menu: Retry; Update tools, retry; Sign in; Copy log. Shorter advice under it.
- Every other prompt and alert, the same way.

Also:

- Status has a "Web view" line: whether a-Shell's browser can decode VP9 and encode HEVC in hardware. Nothing uses it yet; it answers whether a conversion through the browser would be worth building.
- A failure on a site you are signed in to no longer advises signing in.

Looked into: other ways to hardware-decode VP9. Only WebKit's own decoder, through WebCodecs in a-Shell's web view, is open to an app without Apple's entitlement, and it would mean a second transcoder written in JavaScript. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#hardware-decoding-what-is-and-is-not-reachable).


## 1.7.0

A choice where there is one, Files as a destination, and what the first run of 1.6 on a device showed. Install the new shortcut; it brings its helper with it.

Added:

- **Save to › Files.** Every download goes to the Files app under *a-Shell › UMDL › Saved*, exactly as downloaded. Nothing is repacked or converted, so nothing waits on a conversion.
- **Higher quality available.** When the best version would have to be converted for Photos and a smaller one would not, UMDL asks which you want and names both: "2160p60, converted" or "1080p60, as it is". The link is read once; the answer carries on from there.
- **Settings › Conversion** answers that question for good: ask each time, always convert for the best quality, or never and take what Photos plays.
- **When finished** can open the Files app at the folder, when that is where the download went.

Fixed, from the 1.6 device log:

- **A YouTube video was named by its id**, `njX2bu-_Vw4.mp4`, not its title. Video and sound arrive as two files with names of their own, and the title was filed under those.
- **A converted video landed outside the album.** Photos refuses an AV1 file with the same error it gives for a bad album, and the helper dropped the album for the rest of the run.
- **Every conversion began with an attempt that could not work**, run twice. On iOS, ffmpeg refuses to ask the hardware encoder for a quality level. The attempt is gone, and a failed attempt is no longer repeated.
- **1.6 would have taken VP9 after Photos refused AV1.** Photos refuses both; AV1 is the one the chip reads, and it converted a two-minute 4K60 HDR video in two minutes. AV1 is now taken because it converts faster.
- "WARNING: Unknown codec" no longer prints into the progress line. It goes to the log.

Changed:

- A conversion passes the source's colour information on, so HDR stays HDR, and gives the encoder more room: 1.6 times the source's bitrate from AV1, 1.3 times from VP9.
- "Converting…" and the question say "HDR" where it applies.
- Settings › *Album* is now *Save to*.

Looked into: hardware decoding of VP9. iPhones have it, but iOS gives it only to apps holding an entitlement Apple grants (YouTube's has it). a-Shell does not, and nothing in UMDL can change that. AV1 needs no entitlement on an iPhone 15 Pro or later.


## 1.6.0

One route, and a download that survives being interrupted. Install the new shortcut; it brings its helper with it.

Removed:

- **Saving through Shortcuts.** 1.5 kept it for when a-Shell could not save. Now a file goes to Photos from a-Shell, or it stays in Files, and the notification says why. With it went the "An earlier download was not saved" prompt, the 1 GB limit, and every step in which the shortcut touched a file.
- The **New album** and **Existing album** choices. Album asks for a name; the album is used if Photos has it and made if not.

Added:

- **A working folder.** Each download works in *a-Shell › UMDL › Working* and notes how far it got. If a-Shell is closed or iOS stops it, sharing the link again or **Resume last download** carries on: nothing is downloaded twice, and nothing already in Photos is added twice. A conversion that was cut short starts again from the downloaded file.
- **AV1 in place of VP9, where that is free.** YouTube above 1080p has only those two. Where the device's chip reads AV1 and a-Shell's ffmpeg can read it too, UMDL takes AV1, which Photos may accept untouched. If Photos refuses it once, that file is converted and UMDL takes VP9 from then on. Status shows which applies on its "AV1" line.

Changed:

- **The size in "Converting…" is the usual name.** A 3840×1920 video is 2160p; 1.5 called it "1920p".
- **Conversion asks the hardware to read the source as well as write the result**, where a-Shell's ffmpeg can. VP9 is still read in software, because iOS gives apps no hardware reader for it, so a long 4K VP9 video remains slow. The log now records how long each conversion took and with which arguments.
- HEVC under the `hev1` label is relabelled, not converted.
- **Resume last download** is no longer forgotten when Status, Settings or Update tools is opened first.
- Stopping the helper with Control-C says where the download stands.
- The first download with 1.6 deletes the working files 1.5 and earlier left in a-Shell, including any video they never finished saving.
- Internally, a download is a job with a state (`fetch`, `save`, `done`) saved after each step; see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#a-download-is-a-job).

Not possible: converting in the background. iOS pauses a-Shell when it leaves the screen.


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

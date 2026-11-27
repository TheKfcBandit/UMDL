# Requirements

What UMDL sets out to do, how each point is met, and how it is checked.

"Flow tests" are `tests/test_shortcut_flow.py`: they execute the compiled shortcut in a simulator against the real helper. "Helper tests" are `tests/test_umdl.py`. Neither replaces a run on a real device; see [Verification](#verification).

## Matrix

| # | Requirement | How it is met | Checked by |
|---|---|---|---|
| R1 | One tap from the share sheet. One question at most, and a setting removes it | The shortcut accepts URLs and text, pulls out the first link and hands it to the helper. No menu appears on this path, except **Higher quality available** when the best version would have to be converted and no preference is set | Flow test `test_download_asks_nothing` fails if any question is asked; flow tests in `HigherQuality` |
| R2 | Works without the share sheet | Opened on its own, UMDL shows its main menu at once: clipboard, resume, settings, sign in, status, update, about | Flow tests for each menu item; `test_opening_from_the_app_goes_straight_to_the_main_menu` |
| R3 | Universal site support | yt-dlp and gallery-dl, each tried in the order that suits the site, the other as fallback | Routing checked against the real extractor lists; fallback in helper tests |
| R4 | The best quality by default, with limits the user can set | The best version a site has is downloaded, whatever its format. Resolution and frame rate default to **Best** and can each be capped on their own. Nothing else affects the choice | Flow tests in `Quality`; helper tests in `Quality`, `VersionPlan` and `Labels`; the format string, filter and sort fields run against real yt-dlp on a test video with five versions |
| R19 | One route: saved by a-Shell itself, any size, under its title, dated the day of download. Files is the only exception | The helper adds each file to Photos through the system's interface. What Photos cannot hold, or cannot be reached for, is kept in Files, and the notification says why. Nothing passes through Shortcuts | Flow tests in `Saving`; the real interface only exists on a device |
| R20 | Converted only when Photos will not take the file as it is, and then at the best quality | The file is offered first; a refusal leads to hardware HEVC at the same size and frame rate, HDR kept. Between versions of the same size and frame rate, the one that costs least afterwards is downloaded | Flow tests in `Saving` and `Quality`; helper tests in `Saving`, `ConversionOrder`, `RepackAndConvert`, `VersionPlan` and `AlbumOrFile`, with real ffmpeg |
| R21 | The user decides between quality and waiting | When the best version needs converting and a smaller one does not: ask, naming both. **Conversion** in Settings answers in advance: always, or never | Flow tests in `HigherQuality`; the question, the remembered reading and the format filter run against real yt-dlp |
| R22 | Files as a destination | **Save to › Files** keeps every download in a-Shell › UMDL › Saved exactly as downloaded: nothing repacked, nothing converted, nothing asked | Flow tests in `ToFiles` |
| R6 | Media Photos cannot take is not lost | Repacked without re-encoding when the wrapper is the obstacle; converted when Photos refuses the picture; otherwise kept in Files | Helper tests with real H.264, HEVC, VP9, AV1 and audio files |
| R7 | First-run setup, possible in one tap | **Quick setup** saves the defaults, downloads the helper, installs the tools and downloads the shared link with no further input. **Custom setup** opens the settings list first, so the album, resolution and frame rate can be set before anything is installed | Flow tests in `Onboarding`, including declined setup, no connection, and tools that will not install |
| R8 | Settings can be changed later, without nested menus | One list showing every value. It stays open; two-value rows switch on a tap, others open a single menu. **Reset** signs out, or removes everything UMDL put into a-Shell | Flow tests per row, including invalid input and settings saved by earlier versions |
| R9 | Ask before large downloads | More than 10 items (configurable) returns to Shortcuts with a native menu: everything, first N, first one, cancel | Flow tests; real yt-dlp against a 12-video page |
| R10 | Tools install and update themselves | The shortcut downloads the helper; pip installs the tools on setup; the helper installs any that are missing on every run, upgrades them daily and updates itself; "Update tools" on demand | Flow and helper tests against stand-in pip and curl; the real pip and network steps only run on device |
| R11 | Bulletproof: failures are explained and recoverable | Every helper exit path calls back; errors are classified with a suggested fix; every download works in a folder of its own under *Working*, with its state saved after each step, so an interrupted run carries on without downloading again | Flow tests for error, retry, resume and recovery paths |
| R12 | Sign-in for private content, with confirmation | The helper opens the site's sign-in page in a-Shell's browser, waits for the sign-in to be stored, and returns to Shortcuts to say so; the tools read the same cookies | Flow and helper tests against a stand-in browser and a cookie store in Apple's format; the real browser only runs on device |
| R13 | Update notice for the shortcut | Daily check of `version.json`; menu after a download; manual check under About | Flow tests |
| R14 | Fit and finish | Shortcut icon and colour; icon menus with subtitles; a symbol on each action button; short, formal wording; live progress in a-Shell; notification on completion | Icons reviewed visually; every label in flow tests |
| R18 | A status screen | **Status** reports tool versions, which sites are signed in, storage, connectivity and the last download, and copies itself and the log to the clipboard | Flow tests `test_status_*` |
| R17 | Behaviour is specified and tested screen by screen | [BEHAVIOR.md](BEHAVIOR.md) describes every screen and names the test for each | `tests/test_behavior_doc.py` fails if the shortcut shows a label that document does not describe, or the document names a test that does not exist |
| R15 | Private | No UMDL server, no analytics | By construction: the only hosts contacted are the media site, PyPI and this repository |
| R16 | FOSS and reproducible | MIT; Cherri source, helper and tests in the repository; CI compiles and tests every push | CI |

## Decisions

Made with the project owner before building:

- **Quality**: best Photos-native format, rather than re-encoding 4K VP9/AV1 or diverting it to Files.
- **Large downloads**: ask when a link has more than 10 items.
- **Extras in 1.0**: site sign-in helper and self-update check. Audio-only mode and download history were left out.

Made during the build:

- **a-Shell comes to the foreground while downloading.** iOS does not run Python in a background extension. This is the same constraint SW-DLT works under.
- **Files Photos cannot hold stay in a-Shell's folder** (*a-Shell › UMDL › Saved* in Files) rather than being copied elsewhere. One less permission prompt and one less way to fail.
- **Settings live in a-Shell's folder**, read without opening the app. Removing a-Shell or choosing Reset removes everything.
- **No Cherri functions.** They re-run the shortcut and read its input, which is the channel the helper's callback uses.
- **Licence**: MIT, matching SW-DLT.

Changed in 1.3.0 and 1.4.0, at the owner's request:

- **Quality is configurable.** Resolution and frame rate limits, each on its own, both defaulting to best.
- **One mode (1.5.0).** Advanced mode, added in 1.3, was removed: the goal is one tap, and the two quality settings say what is wanted. The conversion setting went with it; conversion is always at the best quality.
- **Enter a link was removed (1.5.0).** Download covers it.
- **One route (1.6.0).** Saving through Shortcuts, which 1.5 kept for when a-Shell could not save, was removed. A file goes to Photos from a-Shell, or stays in Files. With it went the album actions in the shortcut, the "unsaved download" prompt and the 1 GB limit.
- **A choice came back, as one question (1.7.0).** 1.5 removed the conversion setting on the grounds that the best quality is always wanted. A 4K conversion on a device changed that: the owner asked to be offered the best version that needs none, with a setting to decide for good, and for Files as a destination that never converts.
- **Reddit has one route (1.8.0).** gallery-dl, gallery-dl through the API, yt-dlp and the browser's data request were all removed for Reddit: Reddit closed what they read. The post's page, opened in the browser, is what is left.
- **Fewer words (1.8.0).** Every menu, prompt, alert, notification and progress line was shortened at the owner's request: no explanations in prompts, "Native" for a version that needs no converting.
- **A working folder and a state machine (1.6.0).** A download is a job with a state, saved in *a-Shell › UMDL › Working*, so an interruption costs no second download.
- **The best version is always downloaded (1.4.0).** 1.3.0 preferred versions Photos already plays unless told otherwise, which stopped YouTube at 1080p. The device test showed a-Shell's ffmpeg has the hardware encoders, so that caution was dropped. A version Photos plays is still preferred between versions of the same size and frame rate.
- **Conversion is a separate step (1.4.0).** It no longer influences which version is downloaded. Its setting is a quality, **Best quality**, **Smaller file** or **Off**, and best quality applies when nothing was set.
- **A frame rate limit is strict.** Versions above it are passed over even when they are larger. On YouTube a 60 fps video has 30 fps versions only at 480p and below, so "Up to 30 fps" gives 480p there. The alternative, a limit that gives way to resolution, would never apply on the site where it matters most.
- **Reset removes what UMDL installed, not the user's other files in a-Shell.** A shortcut cannot reset another app, and a-Shell is a general-purpose terminal that may hold unrelated work. Deleting the app is the complete wipe.

Changed after the first device test (1.1.0):

- **No virtual environment.** 1.0 installed the tools into a Python virtual environment, as SW-DLT does, and on the test device the helper then could not import yt-dlp. The tools are now installed with a-Shell's own pip, and the helper repairs a missing or misplaced install by itself.
- **The helper is downloaded by the shortcut, in the background**, with a download inside a-Shell as the fallback, so a failure is reported as an alert and not left in a terminal.
- **Quick setup.** One choice in place of two questions; the questions remain under Custom setup.

## Known limits

- YouTube above 1080p is AV1 or VP9 only, and Photos takes neither, so those downloads are converted when saved to Photos. With AV1 on an iPhone 15 Pro or later that takes about as long as the video runs. VP9 is much slower: its hardware decoder on iOS is reserved for apps Apple grants an entitlement to, which a-Shell is not, so it is read in software. UMDL takes AV1 where it can, asks before converting unless told not to, and never converts for Files.
- An HDR version is taken over a plain one of the same size, and a conversion passes its colour information on. Whether Photos then shows it as HDR has not been checked on a device.
- iOS pauses a-Shell when it leaves the screen. A download or conversion does not move in the background; it carries on when a-Shell is in front again, or from its working folder if iOS closed a-Shell meanwhile.
- Reddit is read by opening the post in a-Shell's own web view. Since October 2026 that page is the only thing Reddit serves about a post without an approved API application, so there is nothing to fall back to: if Reddit changes the page, or stops showing it to the web view, Reddit links fail until UMDL is updated.
- The shortcut must keep the name "UMDL".
- Shortcuts has no custom animation. Progress is shown as a live bar in a-Shell and a notification at the end.
- Live streams are skipped while they are live.
- Sign-in uses a-Shell's own browser. Sites that block embedded browsers (Google sign-in often does) will not work there.
- Instagram often refuses downloads that are not signed in, and sometimes those that are. Reddit shows age-restricted and some other posts only to a signed-in visitor.
- a-Shell mini is untested.

## Verification

| Layer | Status |
|---|---|
| Helper logic | Automated tests, with real ffmpeg |
| Helper against real yt-dlp and gallery-dl | Run by hand during development against a local test site: single video, multi-video page, image, audio, VP9 conversion, dead link |
| Shortcut logic and the shortcut-helper protocol | Automated flow tests in a simulator |
| Shortcut compiles | CI, every push |
| Behaviour on a real iPhone or iPad | 1.0.0 failed in setup. 1.1.0 set up, downloaded and reported errors correctly, then failed when saving. 1.2.0 saved to Photos, signed in, and downloaded private posts from Instagram and X; Reddit was refused. 1.3.0 confirmed the Settings list and the hardware encoders, and failed on its first YouTube link. 1.4.1 downloaded from YouTube; a long video then failed at the hand-over to Shortcuts. 1.5.0 reached the conversion of a 4K VP9 video, which was very slow. 1.6.0 saved from a-Shell into Photos and converted a 4K60 HDR AV1 video in about its own length; it named that video by its id and left it out of the album. 1.7.0 asked the quality question, read the link once, named the video by its title, kept the album, and converted 2160p60 HDR AV1 in 103 s; Reddit failed on every route, which turned out to be Reddit's change of October 2026 and not the network. 1.8.0 is **not yet confirmed** |

The simulator models each Shortcuts action as UMDL uses it. Where iOS behaves differently from that model, only a device will show it. The 1.0.0 device test showed one such difference: **an empty text counts as having a value in an If action.** The simulator assumed the opposite, which hid three faults: a false "unsaved download" prompt, no main menu, and a misleading "no link" message. The simulator now matches the device and the shortcut no longer uses that test.

The same device test confirmed that background commands return their output, that the helper starts and its callback reaches the shortcut, and that text comparisons behave as modelled.

The 1.1.0 device test found a second difference, this one in a-Shell and specific to iOS 27.2: **"Get File" stops the shortcut unless it is asked for a copy** ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). SW-DLT, whose pattern UMDL follows, fails the same way on that iOS version. The simulator now refuses a Get File without the copy option, and a background command that fails without "continue after an error", so the 1.1.0 build fails in the simulator exactly where it failed on the phone.

Assumptions still unconfirmed:

- "Match Text" with no match, followed by "Get Group", yields nothing rather than an error.
- The Files app opens at a-Shell › UMDL › Saved when given `shareddocuments://` and that folder's path.
- a-Shell's browser writes its cookie store within seconds of a sign-in, while the page is still open. If it writes later, sign-in ends with "not confirmed" and Status shows it afterwards.

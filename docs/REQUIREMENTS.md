# Requirements

What UMDL sets out to do, how each point is met, and how it is checked.

"Flow tests" are `tests/test_shortcut_flow.py`: they execute the compiled shortcut in a simulator against the real helper. "Helper tests" are `tests/test_umdl.py`. Neither replaces a run on a real device; see [Verification](#verification).

## Matrix

| # | Requirement | How it is met | Checked by |
|---|---|---|---|
| R1 | One tap from the share sheet, no questions | The shortcut accepts URLs and text, pulls out the first link and hands it to the helper. No menu appears on this path. | Flow test `test_download_asks_nothing` fails if any question is asked |
| R2 | Works without the share sheet | Opened on its own, UMDL shows its main menu at once: clipboard, typed link, resume, settings, sign in, update, about | Flow tests for each menu item; `test_opening_from_the_app_goes_straight_to_the_main_menu` |
| R3 | Universal site support | yt-dlp and gallery-dl, each tried in the order that suits the site, the other as fallback | Routing checked against the real extractor lists; fallback in helper tests |
| R4 | Always the best quality, no quality menu | One fixed format preference: best H.264/HEVC stream, then anything | Format string checked against real yt-dlp format selection |
| R5 | Saved straight to a chosen Photos album | "Save to Photo Album" with the album from settings; no album means the library | Flow tests, including album names with quotes, commas and non-Latin text |
| R6 | Media Photos cannot take is not lost | Rewrapped without re-encoding when possible; converted when allowed; otherwise kept in Files | Helper tests with real H.264, HEVC, VP9 and audio files |
| R7 | First-run setup, possible in one tap | **Quick setup** creates the album, saves the defaults, downloads the helper, installs the tools and downloads the shared link with no further input. **Custom setup** asks for the album and the conversion preference first | Flow tests in `Onboarding`, including declined setup, no connection, and tools that will not install |
| R8 | Settings can be changed later | Settings menu showing current values | Flow tests per setting, including invalid input |
| R9 | Ask before large downloads | More than 10 items (configurable) returns to Shortcuts with a native menu: everything, first N, first one, cancel | Flow tests; real yt-dlp against a 12-video page |
| R10 | Tools install and update themselves | The shortcut downloads the helper; pip installs the tools on setup; the helper installs any that are missing on every run, upgrades them daily and updates itself; "Update tools" on demand | Flow and helper tests against stand-in pip and curl; the real pip and network steps only run on device |
| R11 | Bulletproof: failures are explained and recoverable | Every helper exit path calls back; errors are classified with a suggested fix; partial downloads resume; unsaved downloads are offered again | Flow tests for error, retry, resume and recovery paths |
| R12 | Sign-in for private content, with confirmation | The helper opens the site's sign-in page in a-Shell's browser, waits for the sign-in to be stored, and returns to Shortcuts to say so; the tools read the same cookies | Flow and helper tests against a stand-in browser and a cookie store in Apple's format; the real browser only runs on device |
| R13 | Update notice for the shortcut | Daily check of `version.json`; menu after a download; manual check under About | Flow tests |
| R14 | Fit and finish | Shortcut icon and colour; icon menus with subtitles; a symbol on each action button; consistent, formal wording; live progress in a-Shell; notification on completion | Icons reviewed visually; every label in flow tests |
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

Changed after the first device test (1.1.0):

- **No virtual environment.** 1.0 installed the tools into a Python virtual environment, as SW-DLT does, and on the test device the helper then could not import yt-dlp. The tools are now installed with a-Shell's own pip, and the helper repairs a missing or misplaced install by itself.
- **The helper is downloaded by the shortcut, in the background**, with a download inside a-Shell as the fallback, so a failure is reported as an alert and not left in a terminal.
- **Quick setup.** One choice in place of two questions; the questions remain under Custom setup.

## Known limits

- YouTube above 1080p is usually VP9 or AV1 only, so YouTube downloads usually stop at 1080p.
- The shortcut must keep the name "UMDL".
- Shortcuts has no custom animation. Progress is shown as a live bar in a-Shell and a notification at the end.
- Live streams are skipped while they are live.
- Sign-in uses a-Shell's own browser. Sites that block embedded browsers (Google sign-in often does) will not work there.
- A file over 1 GB is kept in Files, not Photos, until a-Shell's Get File works without copying again.
- Reddit and Instagram often refuse downloads that are not signed in, and sometimes those that are. For Reddit, UMDL then goes through Reddit's API, and after that through a-Shell's own browser. On the test device the API route was refused too; the browser route has not been run on a device yet. Otherwise UMDL reports what the site said.
- a-Shell mini is untested.

## Verification

| Layer | Status |
|---|---|
| Helper logic | Automated tests, with real ffmpeg |
| Helper against real yt-dlp and gallery-dl | Run by hand during development against a local test site: single video, multi-video page, image, audio, VP9 conversion, dead link |
| Shortcut logic and the shortcut-helper protocol | Automated flow tests in a simulator |
| Shortcut compiles | CI, every push |
| Behaviour on a real iPhone or iPad | 1.0.0 failed in setup. 1.1.0 set up, downloaded and reported errors correctly, then failed when saving. 1.2.0 is **not yet confirmed** |

The simulator models each Shortcuts action as UMDL uses it. Where iOS behaves differently from that model, only a device will show it. The 1.0.0 device test showed one such difference: **an empty text counts as having a value in an If action.** The simulator assumed the opposite, which hid three faults: a false "unsaved download" prompt, no main menu, and a misleading "no link" message. The simulator now matches the device and the shortcut no longer uses that test.

The same device test confirmed that background commands return their output, that the helper starts and its callback reaches the shortcut, and that text comparisons behave as modelled.

The 1.1.0 device test found a second difference, this one in a-Shell and specific to iOS 27.2: **"Get File" stops the shortcut unless it is asked for a copy** ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). SW-DLT, whose pattern UMDL follows, fails the same way on that iOS version. The simulator now refuses a Get File without the copy option, and a background command that fails without "continue after an error", so the 1.1.0 build fails in the simulator exactly where it failed on the phone.

Assumptions still unconfirmed:

- "Match Text" with no match, followed by "Get Group", yields nothing rather than an error.
- "Save to Photo Album" accepts the album name from a variable.
- "Get File" in copy mode returns a file Photos accepts when given an absolute path. The a-Shell issue confirms copy mode for a path inside a-Shell's shared folder.
- a-Shell's browser writes its cookie store within seconds of a sign-in, while the page is still open. If it writes later, sign-in ends with "not confirmed" and Status shows it afterwards.

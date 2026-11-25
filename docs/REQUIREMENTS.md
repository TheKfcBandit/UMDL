# Requirements

What UMDL sets out to do, how each point is met, and how it is checked.

"Flow tests" are `tests/test_shortcut_flow.py`: they execute the compiled shortcut in a simulator against the real helper. "Helper tests" are `tests/test_umdl.py`. Neither replaces a run on a real device; see [Verification](#verification).

## Matrix

| # | Requirement | How it is met | Checked by |
|---|---|---|---|
| R1 | One tap from the share sheet, no questions | The shortcut accepts URLs and text, pulls out the first link and hands it to the helper. No menu appears on this path. | Flow test `test_one_tap_download_asks_nothing` fails if any question is asked |
| R2 | Works without the share sheet | Opened on its own, UMDL shows a menu: clipboard, typed link, resume | Flow tests for each menu item |
| R3 | Universal site support | yt-dlp and gallery-dl, each tried in the order that suits the site, the other as fallback | Routing checked against the real extractor lists; fallback in helper tests |
| R4 | Always the best quality, no quality menu | One fixed format preference: best H.264/HEVC stream, then anything | Format string checked against real yt-dlp format selection |
| R5 | Saved straight to a chosen Photos album | "Save to Photo Album" with the album from settings; no album means the library | Flow tests, including album names with quotes, commas and non-Latin text |
| R6 | Media Photos cannot take is not lost | Rewrapped without re-encoding when possible; converted when allowed; otherwise kept in Files | Helper tests with real H.264, HEVC, VP9 and audio files |
| R7 | First-run setup | Welcome, album, conversion preference, then tool install in a-Shell | Flow tests, including declined setup and a failed install |
| R8 | Settings can be changed later | Settings menu showing current values | Flow tests per setting, including invalid input |
| R9 | Ask before large downloads | More than 10 items (configurable) returns to Shortcuts with a native menu: everything, first N, first one, cancel | Flow tests; real yt-dlp against a 12-video page |
| R10 | Tools install and update themselves | pip install on setup; daily upgrade; helper self-update; "Update tools" on demand | Helper tests; the pip and network steps themselves only run on device |
| R11 | Bulletproof: failures are explained and recoverable | Every helper exit path calls back; errors are classified with a suggested fix; partial downloads resume; unsaved downloads are offered again | Flow tests for error, retry, resume and recovery paths |
| R12 | Sign-in for private content | Opens the site in a-Shell's browser; tools read its cookies | Flow tests confirm the right page is opened; cookie use only runs on device |
| R13 | Update notice for the shortcut | Daily check of `version.json`; menu after a download; manual check under About | Flow tests |
| R14 | Fit and finish | Shortcut icon and colour; icon menus with subtitles; live progress in a-Shell; notification on completion | Icons reviewed visually; menus in flow tests |
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

## Known limits

- YouTube above 1080p is usually VP9 or AV1 only, so YouTube downloads usually stop at 1080p.
- The shortcut must keep the name "UMDL".
- Shortcuts has no custom animation. Progress is shown as a live bar in a-Shell and a notification at the end.
- Live streams are skipped while they are live.
- Sign-in uses a-Shell's own browser. Sites that block embedded browsers (Google sign-in often does) will not work there.
- a-Shell mini is untested.

## Verification

| Layer | Status |
|---|---|
| Helper logic | Automated tests, with real ffmpeg |
| Helper against real yt-dlp and gallery-dl | Run by hand during development against a local test site: single video, multi-video page, image, audio, VP9 conversion, dead link |
| Shortcut logic and the shortcut-helper protocol | Automated flow tests in a simulator |
| Shortcut compiles | CI, every push |
| Behaviour on a real iPhone or iPad | **Not yet confirmed** |

The simulator models each Shortcuts action as UMDL uses it. Where iOS behaves differently from that model, only a device will show it. The assumptions that matter most:

- An empty text counts as "has no value" in an If action.
- "Match Text" with no match, followed by "Get Group", yields nothing rather than an error.
- "Save to Photo Album" accepts the album name from a variable.
- a-Shell's "Execute Command" and "Get File" actions accept the same parameters SW-DLT uses.

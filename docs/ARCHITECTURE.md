# Architecture

UMDL has two halves:

- **The shortcut** (`src/UMDL.cherri`) is everything you see in Shortcuts: reading the shared link, menus, settings, saving to Photos, notifications.
- **The helper** (`src/umdl.py`) runs inside a-Shell. It downloads with yt-dlp or gallery-dl, makes the result importable by Photos, and reports back.

They talk in one direction at a time. The shortcut starts the helper with a command line. The helper answers by opening a `shortcuts://` URL that runs the shortcut again with the result as its input.

## Flow

```mermaid
flowchart TD
    A["Share sheet, or UMDL opened directly"] --> B{"Input starts with UMDLCB:?"}
    B -- no --> C["Find the first link in the input"]
    B -- yes --> D["Decode the helper's callback"]

    C --> E["Read settings and state from a-Shell, in the background"]
    E --> F{"Settings exist?"}
    F -- no --> G["Welcome: quick setup, or the settings list"] --> H["Save settings"]
    H --> I{"Helper present, and fetched by this version?"}
    F -- yes --> J{"Unsaved download waiting?"}
    J -- yes --> K["Offer to save or discard it"]
    J -- no --> L{"Have a link?"}
    K --> L
    L -- no --> M["Menu: clipboard, enter link, settings, sign in, status, update, about"]
    M --> I
    L -- yes --> I
    I -- no --> N["Download the helper, in the background or in a-Shell"]
    N --> O
    I -- yes --> O["a-Shell: helper 'run' with the payload"]

    O --> P["Install missing tools; update them if a day has passed"]
    P --> Q["Pick tool order for this site"]
    Q --> R["Count the items at the link"]
    R --> S{"More than the ask-first limit?"}
    S -- yes --> T["Callback: confirm"]
    S -- no --> U["Download the best version within the limits"]
    U --> SV{"Can a-Shell save to Photos?"}
    SV -- yes --> PH["Offer each file to Photos; convert only on a refusal"]
    PH --> W["Callback: done, with what was saved"]
    SV -- no --> HO["Prepare each file by the format list, write manifest"]
    HO --> W2["Callback: done, with the manifest"]
    U -- nothing downloaded --> X["Callback: error"]

    T --> D
    W --> D
    W2 --> D
    X --> D

    D --> Y{"Callback type"}
    Y -- setup --> AE["Say that UMDL is ready"]
    Y -- confirm --> Z["Menu: all, first N, first only, cancel"] --> O
    Y -- error --> AA["Menu: try again, update and retry, sign in, copy details"]
    AA --> O
    Y -- "info, status" --> AB["Show the message"]
    Y -- "done, saved" --> AD["Notify, offer shortcut update"]
    Y -- "done, manifest" --> AC["Read manifest, rename and save each file to the album, delete working files"]
    AC --> AD
```

Version 1.5 removed the mode branch of 1.3 and 1.4 and moved saving into a-Shell. The saving part is drawn on its own in [BEHAVIOR.md](BEHAVIOR.md#saving).

The first-run part of this chart is drawn in full in [BEHAVIOR.md](BEHAVIOR.md#first-run), which also describes every screen.

## Why a-Shell opens

a-Shell's Shortcuts actions run commands in two ways. "In extension" runs in the background and returns the output, but with tight memory and no Python. "In app" opens a-Shell and has the full environment.

UMDL uses the background mode for small things: reading settings, writing settings, deleting working files, checking the version file, downloading the helper script. Downloads need Python, so they open the app. iOS suspends an app that leaves the foreground, which is why a-Shell has to stay in front until the helper hands back.

## The payload (shortcut to helper)

A JSON object, base64-encoded so it survives a-Shell's command line whatever the link contains:

```
python umdl.py run <base64 JSON>
```

| Field | Meaning |
|---|---|
| `v` | Shortcut version |
| `p` | Protocol number |
| `name` | The shortcut's name, used for the callback |
| `url` | The link (or the shared text containing it) |
| `mode` | `auto` (ask above the limit), `all`, `limit`, `first` |
| `limit` | Item count for `mode: limit` |
| `force_update` | `1` to upgrade the tools before downloading |
| `cfg` | The settings: `album`, `threshold`, `after`, `res` (`best` or a height), `fps` (`best`, `60`, `30`) |

Other commands take the same payload: `setup`, `update`, `status`, `signin` (the page to open travels in `url`), `logout`, `reset`. A command the helper does not know, or a payload with another protocol number, is answered with an `outdated` error.

## The callback (helper to shortcut)

```
shortcuts://run-shortcut?name=UMDL&input=text&text=UMDLCB:<base64 JSON>
```

Every callback includes `cfg`, echoed from the payload, so the shortcut does not need a second trip to a-Shell to know the album.

| `t` | Other fields | The shortcut then |
|---|---|---|
| `done` | Either `msg`, the sentence to show when the helper saved everything itself; or `m`, the path of a manifest of files left for the shortcut to save, with `nk`, `nf`, `nb`, `nc`, `conv` for its summary. Always `title`, and `upv` and `upurl` when a newer release exists | Notifies, after saving what the manifest lists |
| `confirm` | `url`, `n` item count or empty when only "more than" is known, `thr`, `title` | Asks how much to download |
| `error` | `kind`, `msg`, `url` | Explains and offers fixes |
| `setup` | `ver` | Says that UMDL is ready |
| `info` | `title`, `msg` | Shows the message |
| `status` | `msg` | Shows the report and offers to copy it with the log |

Error kinds: `auth`, `network`, `gone`, `unsupported`, `drm`, `install`, `outdated`, `nolink`, `unknown`.

One result does not come from the helper. When the helper script cannot be downloaded in a-Shell, the shell itself reopens the shortcut with the plain text `UMDL-HELPER-MISSING`.

The file list is not in the callback. It is in the manifest (`jobs/<id>/manifest.json`), which the shortcut reads with a background `cat`, so a 500-item download does not need a 500-item URL. Each file is then fetched with a-Shell's "Get File".

## Saving

a-Shell's Info.plist has declared `NSPhotoLibraryAddUsageDescription` since 2021, so its process may add to the Photos library. The helper does, with PhotoKit called through `ctypes` (`PhotosLibrary`): one `PHAssetCreationRequest` per file, with `originalFilename` set to the title, `creationDate` set to now, and the album added in the same change. `performChangesAndWait:error:` reports whether Photos took the file, which makes Photos itself the test of what it can play: the file is offered as it is, and converted only on a refusal.

Album access needs more than add-only permission. If the app also declares `NSPhotoLibraryUsageDescription` and an album is set, full access is asked for; otherwise, or if that is refused, files go to the library.

None of this can run off a device, so it is fenced:

- `open_library()` returns nothing unless the declarations are present and access is granted.
- Before each step, the step's name is written to `photos.step`, and removed after. If a-Shell stops in between, the next run finds the name, records it with the helper's version, and saves through Shortcuts until a different helper is installed.
- Any error from the calls ends direct saving for that run, and the files go through Shortcuts.

**Through Shortcuts** is what every version before 1.5 did. a-Shell's "Get File" has two modes. By default it hands Shortcuts a reference to the file; on iOS 27.2 that stops the shortcut ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). With `copyFile` set, a-Shell reads the file into memory first, which works on 27.2 but stops on large files; a-Shell's source says of that line, "causes a crash for large files". So this path keeps anything over 1 GB in Files, and that limit is a guess. The copy is named after its whole path, so each file sits in a folder of its own under its final name, and the shortcut renames the copy to the last part of the path before saving.

Background commands have a similar trap. a-Shell reports the action as failed when the last command exits with an error, unless `keepGoing` is set, and Shortcuts then stops in the same wordless way. Every background command UMDL sends sets `keepGoing`, and reads the output to decide what happened.

## Sign-ins

a-Shell's `internalbrowser` is a web view inside the app. Its cookies are stored in `~/Library/Cookies/Cookies.binarycookies`, which is where yt-dlp and gallery-dl look when told to use Safari's cookies, so a sign-in made there is available to both tools with nothing copied.

The helper reads the same file to answer one question: is this site signed in? It parses the names and domains only, never the values. For the listed sites it looks for the site's own session cookie (`sessionid` for Instagram, `reddit_session` for Reddit, and so on); for any other site, for a cookie whose name looks like a session. `signin` opens the page, polls the file until that cookie appears or ten minutes pass, and calls back either way. `status` uses the same check.

## Files in a-Shell

Everything is under `~/Documents/UMDL`, visible in the Files app as *a-Shell › UMDL*.

| Path | Purpose |
|---|---|
| `umdl.py` | The helper |
| `helper.for` | The shortcut version that downloaded the helper. A different version downloads it again |
| `config.b64` | Settings, as base64 JSON |
| `state.json` | When the tools and the version file were last checked, and any extra folder pip installs to |
| `jobs/<id>/` | Working folder for one link. `<id>` is derived from the link, so sharing the same link again resumes |
| `jobs/<id>/out/` | Finished files with plain names (`001.mp4`) |
| `jobs/<id>/manifest.json` | What to save to Photos and what was kept |
| `photos.step` | The step of saving to Photos that is under way. Left behind only if a-Shell stopped during it |
| `pending` | Path of a manifest that has not been saved to Photos yet |
| `last.b64` | The payload of a download in progress; left behind only if it was interrupted |
| `last.log` | Log of the last run |
| `Saved/` | Files Photos cannot hold |

## Quality

The format string is always `bv*+ba/b/ba`, the best there is. What "best" means is given to yt-dlp as sort fields, `lang, res, fps, vcodec:h265, acodec:aac`:

- `res` and `fps` first, so size and smoothness decide before anything else. A resolution limit turns `res` into `res:1080`, which yt-dlp reads as "the largest up to this, and the smallest above it only when nothing fits".
- `vcodec:h265` and `acodec:aac` after them. These rank H.265, then H.264, above VP9 and AV1, and AAC above Opus, but only between versions already equal in size and frame rate.
- `lang` leads so that the sound stays in the original language whatever its codec.

A frame rate limit cannot be a sort field: placed after `res` it would never apply where a site's larger versions are all 60 frames a second. It is a filter with a fallback instead: `bv*[fps<=?30]+ba/b[fps<=?30]/bv*+ba/b/ba`.

A conversion, when Photos refuses a file, never changes the picture's size or frame rate. `conversion_attempts` returns the ffmpeg arguments to try, in order, limited to the encoders `ffmpeg -encoders` reports:

1. `hevc_videotoolbox -q:v 75 -tag:v hvc1`, with `main10` and `p010le` for a 10-bit source.
2. `hevc_videotoolbox -b:v <rate>`, for an ffmpeg build without the quality mode, which iOS builds may be.
3. `h264_videotoolbox -profile:v high -b:v <1.6 × rate>`.
4. `libx264 -crf 17 -preset veryfast`.

Progress is read from a file ffmpeg writes (`-progress <file>`), not from its output.

## Which tool goes first

- A site known for image or mixed posts (X, Instagram, Reddit, Bluesky, Imgur, Pixiv and others): gallery-dl, then yt-dlp.
- Any other site yt-dlp has an extractor for: yt-dlp, then gallery-dl if it also knows the site.
- A site only gallery-dl knows: gallery-dl, then yt-dlp's generic extractor.
- Neither: yt-dlp's generic extractor, which looks for media in the page.

The second tool runs only if the first produced nothing. If both fail, the first tool's error is the one shown.

Reddit gets one more attempt. Both tools read a post from `www.reddit.com/…/.json`, and Reddit refuses that to many networks with "You've been blocked by network security", signed in or not; yt-dlp words the same refusal as "Your IP address is unable to access the Reddit API". The block page points to Reddit's API as the alternative, so when gallery-dl is blocked the helper runs it again with `-o api=oauth -o refresh-token=`, which makes it request a public API token and read the post from `oauth.reddit.com`. The empty `refresh-token` matters: without it gallery-dl 1.32.21 stops with an `AttributeError` before making any request.

On the test device that was refused as well, so there is a last route that does not depend on Reddit accepting a download tool at all. a-Shell has a real browser: the web view behind `internalbrowser`, which is also where the sign-in lives. a-Shell's `jsc` command runs JavaScript in that web view. The helper sends the web view to `www.reddit.com/robots.txt` (a page of the site that runs no scripts), runs a short script there that follows the share link and fetches the post's JSON as the signed-in browser, polls for the answer, and sends the web view back with `history.back()`. From the answer it takes only where the media is: a DASH manifest on `v.redd.it` for a video, which goes to yt-dlp; original files on `i.redd.it` for photos and galleries, which go to gallery-dl as direct links; or a link to another site, which goes through the normal tool order. Those hosts are plain file servers and take no part in the block. `jsc` does not wait for a script's promises, so the script stores its answer in the page and a second script reads it. On iOS 27.2 `jsc` also refuses to hand back a script's own value ("JavaScript execution returned a result of an unsupported type"), so every script sends its result through the message handler a-Shell gives page scripts for printing, `window.webkit.messageHandlers.aShell.postMessage("print:…")`, and ends in `void 0`. The script itself is tested in Node against canned answers (`tests/test_reddit_js.py`).

## YouTube in a web view

YouTube's stream addresses carry challenges that only the site's own player code can answer, so yt-dlp runs that code in a JavaScript runtime. a-Shell has none of the stand-alone ones (Deno, Node, Bun, QuickJS). The `yt-dlp-apple-webkit-jsi` plugin fills the gap by running the code in a `WKWebView` inside a-Shell's process.

yt-dlp's solver script (`yt-dlp-ejs`) prepares the ground for the player code with a few assignments, one of which is

```js
globalThis.location = new URL("https://www.youtube.com/watch?v=yt-dlp-wins");
```

In a stand-alone runtime this creates a variable. In a web view `globalThis` is the window, and assigning to a window's location navigates it. The plugin's web view has no say over navigations, so WebKit applies its default: a main-frame navigation to another site's universal link is offered to the app that owns it. iOS opens the YouTube app on the video `yt-dlp-wins`, which does not exist, and a-Shell is left in the background, where it finishes its work but may not open the `shortcuts://` link that hands the result back.

`tame_solver()` wraps the method of yt-dlp that assembles the script (`EJSBaseJCP._construct_stdin`) and, for a runtime whose name says it is a web view, renames the target of such assignments to `umdlLocation`. Reads of `location` are untouched. The player code then sees the web view's real location, `about:blank`, which is also what it saw before: the navigation was asynchronous and the challenges were solved before it took effect. If a later yt-dlp moves that method, the wrap finds nothing, says so in the log, and changes nothing.

The same hazard applies to any script UMDL itself runs in a-Shell's web view. The Reddit route's `location.href = "https://www.reddit.com/robots.txt"` is the one case; whether iOS treats that path as a link for the Reddit app is not known.

## Staying current

- **Tools**: yt-dlp and gallery-dl are installed with a-Shell's own pip, with no virtual environment. The shortcut runs pip in the a-Shell window whenever it has just downloaded the helper. The helper then checks for itself on every run: a missing tool is installed, one package at a time so that one failure does not hold back the rest, and if pip reports a location Python is not searching, that folder is added and remembered. Tools are upgraded once a day, and on demand.
- **Helper, first copy**: downloaded by the shortcut, which records its own version next to it. A shortcut of another version downloads the helper again, so the two always match after an update.
- **Helper**: once a day the helper reads `version.json` from this repository. If `helper` is newer and `protocol` matches, it downloads the new `src/umdl.py`, checks that it compiles, and swaps it in for the next run.
- **Shortcut**: the same check notes a newer `shortcut` version, and the shortcut offers the release page after the next download.

Bump `protocol` only when the payload or callback changes incompatibly. A helper will not update itself across a protocol change, so an old shortcut keeps a helper it can talk to.

## Things that look odd but are deliberate

- **File names are `001.mp4`, not titles.** a-Shell has no fork/exec, so commands are passed as one string. Names without spaces or symbols cannot be mis-parsed. Titles are restored for files kept in Files.
- **The shortcut is linear, with flags.** Each section runs if its flag is set, and shared steps (saving settings, launching a-Shell) appear once near the end.
- **Settings is a counted loop.** Shortcuts has no "repeat until". The list sits in a "Repeat 40 times" whose body is skipped once **Done** is tapped, which is what keeps the list on screen between changes without a second level of menus.
- **"Open App" then a one-second wait before each foreground command.** Copied from SW-DLT, where it makes the hand-off to a-Shell reliable.
- **Emptiness is never tested with "has any value".** On a device an empty text counts as a value, so that test is true when it looks like it should be false. The shortcut wraps the text in brackets and compares with `[]`. A test fails the build if a "has any value" condition appears.
- **Dictionary conversions are guarded.** Shortcuts stops with an error if asked to turn non-JSON text into a dictionary, so anything that came over the network or from disk is checked for an expected key first.

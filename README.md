# UMDL

[![Build](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml/badge.svg)](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/TheKfcBandit/UMDL)](https://github.com/TheKfcBandit/UMDL/releases/latest)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

**Universal Media Downloader for iPhone and iPad.** Share a post or a video to UMDL and it is saved to your Photos at the best quality. One tap, no menus, unless you ask for them.

UMDL is a free and open-source Shortcut. Downloads run on your own device with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [gallery-dl](https://github.com/mikf/gallery-dl) inside the free [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) app. Nothing you share is sent to a UMDL server, because there isn't one.

> **Status: 1.6.0.** On a device, setup, sign-in, private posts from Instagram and X, and YouTube are confirmed with earlier versions. Not yet seen on a device: saving from a-Shell straight into Photos, which since 1.6 is the only route. Reddit is refused on the test network. [docs/BEHAVIOR.md](docs/BEHAVIOR.md) keeps the list. Please [report](https://github.com/TheKfcBandit/UMDL/issues) what you find.

## Install

1. Install [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) from the App Store and open it once.
2. On your iPhone or iPad, download `UMDL.shortcut` from the [latest release](https://github.com/TheKfcBandit/UMDL/releases/latest) and tap **Add Shortcut**.
3. Share a post or video to UMDL, or run it from the Shortcuts app, and tap **Quick setup**. a-Shell opens and installs the download tools, and the shared post is downloaded to an album named UMDL. That takes about two minutes. **Custom setup** opens the settings first.

Built for iOS and iPadOS 18 and later. Keep the shortcut's name as **UMDL**, and keep only one copy: a-Shell uses that name to hand results back. When updating, choose **Replace** if Shortcuts asks, or delete the old copy first.

The first few runs show permission prompts from iOS (run a-Shell, let a-Shell add to Photos, open links). Allow them and they stop.

## Use

In any app, tap **Share**, then **UMDL**. a-Shell opens, downloads, and saves to your album; then you are sent back with a notification saying so.

- **Videos** are saved at the highest resolution and frame rate available, or up to the limits you set.
- **Saved items** are named by their title and dated the day you downloaded them.
- **Posts with several photos or videos** are saved whole.
- **Playlists, albums and profiles** with more than 10 items ask first: everything, the first 10, or just the first. You can change the number.
- **Audio and other files** Photos has no place for are kept in the Files app under *a-Shell › UMDL › Saved*. That is the only other place a download can end.
- **An interrupted download** carries on. Each one works in *a-Shell › UMDL › Working*; share the link again, or choose **Resume last download**, and what was already downloaded is not downloaded twice.

Open UMDL on its own, without sharing anything, for the menu:

| Menu item | What it does |
|---|---|
| Download from clipboard | Downloads the link you copied last |
| Resume last download | Appears when a download was interrupted, and carries on from where it stopped |
| Settings | Album, resolution, frame rate, the ask-first limit, what happens when a download finishes, reset |
| Sign in to a site | For private posts. UMDL confirms when the sign-in is saved |
| Status | Which sites are signed in, tool versions, storage, and a button to copy the log |
| Update tools | Installs the newest yt-dlp and gallery-dl now |
| About UMDL | Version, update check, project page |

Every screen, choice and message is described in [docs/BEHAVIOR.md](docs/BEHAVIOR.md).

## Quality

UMDL downloads the best version a site has. Two settings limit that, and both start at **Best available**:

| Setting | Choices |
|---|---|
| Resolution | Best available, or up to 2160p, 1440p, 1080p, 720p, 480p |
| Frame rate | Best available, or up to 60 or 30 fps |

The file is then offered to Photos as it is. Most sites serve H.264, which Photos plays, so most downloads are saved untouched. If Photos refuses a file, as it does YouTube's VP9 above 1080p, the picture is converted to HEVC on your device at the best quality, same size and frame rate, and saved. The notification says so: "1 converted (VP9 → HEVC)". Setting Resolution to 1080p avoids conversion on YouTube.

Between versions of the same size and frame rate, UMDL takes the one that needs no conversion. That never costs quality: a 4K version is taken over a 1080p one whatever its format.

**4K from YouTube is the slow case.** Above 1080p YouTube has only VP9 and AV1. iOS gives apps no hardware reader for VP9, so converting a long 4K video takes a long time, and it only moves while a-Shell is on screen. Where the device's chip reads AV1, UMDL takes AV1 instead, which may go into Photos untouched; that has not been confirmed on a device yet. To skip conversion altogether, set Resolution to 1080p: YouTube has H.264 up to there.

[docs/BEHAVIOR.md](docs/BEHAVIOR.md#saving) has the flow chart.

## Signing in

Some posts need an account, and some sites (Reddit and Instagram among them) often refuse downloads that are not signed in. Choose **Sign in to a site** in the menu: a-Shell opens the site's sign-in page in its own browser. Sign in as usual. As soon as the site has stored the sign-in, UMDL brings you back to Shortcuts and says **Signed in to** *site*.

**Status** in the menu lists which sites are signed in at any time.

The sign-in is a cookie kept by a-Shell on your device. yt-dlp and gallery-dl read it from there. UMDL never sees your password and never reads a cookie's value, only which site it belongs to. Some sites, Google among them, do not allow signing in from an app's built-in browser.

Settings › *Reset* › **Sign out of all sites** deletes the cookie file the download tools read.

## If something goes wrong

A failed download returns to Shortcuts with the reason and these choices:

- **Try again**
- **Update tools and retry.** Sites change often, and a newer yt-dlp fixes most failures.
- **Sign in**
- **Copy details**, for a bug report. This includes the end of the helper's log

Other things worth knowing:

- **"There was a problem running the shortcut."** Versions before 1.6 could stop this way after a download, at the hand-over of the file from a-Shell to Shortcuts. Update UMDL: since 1.6 no file is handed over.
- **Is it set up properly?** Open **Status**. It shows the tool versions, whether GitHub can be reached, which sites are signed in, and the result of the last download. **Copy** puts all of it, and the log, on the clipboard.
- **You are left in a-Shell, or you left it.** Keep a-Shell in the foreground while it works; iOS pauses it otherwise. Coming back to a-Shell lets it carry on. If iOS closed it meanwhile, share the same link again or choose **Resume last download**: the files already downloaded are in *a-Shell › UMDL › Working* and are used as they are.
- **"Nothing was added to Photos."** The notification's last line says why, and the files are in the Files app under *a-Shell › UMDL › Saved*. If it says a-Shell is not allowed to add to Photos, allow it in the Settings app under a-Shell, Photos.
- **A conversion is slow.** See [Quality](#quality): 4K from YouTube is the slow case. Set Resolution to 1080p and YouTube needs no conversion.
- **"Setup incomplete."** The helper or the download tools could not be downloaded. The message says which, and why. Check the connection and run UMDL again; it continues from where it stopped.
- **Items are in the library but not in the album.** Saving to an album needs fuller access to Photos than adding to the library. Allow it in the Settings app under a-Shell, Photos.
- **Start over.** Settings › *Reset* › **Remove everything** removes UMDL's files, the download tools and every sign-in from a-Shell. It leaves anything else you keep in a-Shell alone; deleting the a-Shell app removes that too.

## Privacy and security

- Links go from your device straight to the site being downloaded.
- The helper script and the download tools install and update themselves. Setup downloads the helper script from this repository and yt-dlp and gallery-dl from PyPI. Once a day UMDL upgrades the tools and checks this repository for a newer helper script, which it installs after checking that it compiles. That means code from this repository's `main` branch runs inside a-Shell on your device. If you would rather pin it, fork the repository and build from your fork.
- UMDL collects no analytics and has no account.

## How it works

The shortcut is the front end; a Python helper in a-Shell does the downloading and calls the shortcut back with the result. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) has the flow chart and the details. [docs/BEHAVIOR.md](docs/BEHAVIOR.md) describes every screen, with the setup flow chart. [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) lists what UMDL sets out to do and how each point is covered.

## Build it yourself

The shortcut is written in [Cherri](https://cherrilang.org) and lives in [`src/UMDL.cherri`](src/UMDL.cherri). See [docs/BUILDING.md](docs/BUILDING.md).

```sh
make test       # compile unsigned and run every test
make sign       # compile, sign and verify
```

Release files are built and signed by this repository's [CI](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml). Signing goes through a third-party service, so CI reads the workflow back out of the signed file and publishes it only if it matches the build exactly.

## Credits

- [SW-DLT](https://github.com/net00-1/SW-DLT) by net00 showed how to drive yt-dlp and gallery-dl from a shortcut through a-Shell. UMDL follows the same pattern.
- [TVDL](https://tvdl.app) by Saif Al Falah was the model for the one-tap experience.
- [yt-dlp](https://github.com/yt-dlp/yt-dlp), [gallery-dl](https://github.com/mikf/gallery-dl), [a-Shell](https://github.com/holzschu/a-shell) and [Cherri](https://github.com/electrikmilk/cherri) do the real work.

## Licence and fair use

MIT. See [LICENSE](LICENSE).

UMDL is a tool for saving media you have the right to save, such as your own posts or freely licensed work. Downloading other content may break a site's terms of service or the law where you live. That is your responsibility.

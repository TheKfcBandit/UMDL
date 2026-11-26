# UMDL

[![Build](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml/badge.svg)](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/TheKfcBandit/UMDL)](https://github.com/TheKfcBandit/UMDL/releases/latest)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

**Universal Media Downloader for iPhone and iPad.** Share a post or a video to UMDL and it is saved to your Photos, at the best quality your library can play. One tap, no menus.

UMDL is a free and open-source Shortcut. Downloads run on your own device with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [gallery-dl](https://github.com/mikf/gallery-dl) inside the free [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) app. Nothing you share is sent to a UMDL server, because there isn't one.

> **Status: 1.2.0.** Two rounds of testing on a device have each found a fault, and each is fixed: setup (1.1.0), and a failure after every download on iOS 27.2 (1.2.0). On a device, setup, the menus, downloading and error reporting are confirmed; saving to Photos, the sign-in confirmation and the Status screen are not yet. [docs/BEHAVIOR.md](docs/BEHAVIOR.md) keeps the list. Please [report](https://github.com/TheKfcBandit/UMDL/issues) what you find.

## Install

1. Install [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) from the App Store and open it once.
2. On your iPhone or iPad, download `UMDL.shortcut` from the [latest release](https://github.com/TheKfcBandit/UMDL/releases/latest) and tap **Add Shortcut**.
3. Share a post or video to UMDL, or run it from the Shortcuts app, and tap **Quick setup**. UMDL creates an album named UMDL, a-Shell opens and installs the download tools, and the shared post is downloaded. That takes about two minutes. **Custom setup** lets you choose the album first.

Built for iOS and iPadOS 18 and later. Keep the shortcut's name as **UMDL**, and keep only one copy: a-Shell uses that name to hand results back. When updating, choose **Replace** if Shortcuts asks, or delete the old copy first.

The first few runs show permission prompts from iOS (run a-Shell, save to Photos, open links). Choose **Always Allow** and they stop.

## Use

In any app, tap **Share**, then **UMDL**. a-Shell opens and shows progress, then sends you back with the media in your album and a notification saying so.

- **Videos** are saved at the highest resolution available in a format Photos plays (H.264 or HEVC).
- **Posts with several photos or videos** are saved whole.
- **Playlists, albums and profiles** with more than 10 items ask first: everything, the first 10, or just the first. You can change the number.
- **Audio and other files** Photos has no place for are kept in the Files app under *a-Shell › UMDL › Saved*.
- **Videos over 1 GB** are kept there too. a-Shell can only hand a file to Shortcuts by loading it into memory on iOS 27.2, and that fails for very large files.

Open UMDL on its own, without sharing anything, for the menu:

| Menu item | What it does |
|---|---|
| Download from clipboard | Downloads the link you copied last |
| Enter a link | Type or paste one |
| Resume last download | Appears when a download was interrupted |
| Settings | Album, the ask-first limit, what to do with unsupported video formats, what happens when a download finishes, forget sign-ins, reset |
| Sign in to a site | For private or age-restricted posts. UMDL confirms when the sign-in is saved |
| Status | Which sites are signed in, tool versions, storage, and a button to copy the log |
| Update tools | Installs the newest yt-dlp and gallery-dl now |
| About UMDL | Version, update check, project page |

Every screen, choice and message is described in [docs/BEHAVIOR.md](docs/BEHAVIOR.md).

## What "best quality" means

Photos only imports H.264 and HEVC video. UMDL asks each site for its best stream in one of those, so the result plays everywhere on your devices without conversion.

On most sites that is the best stream there is. YouTube is the exception: above 1080p it mostly offers VP9 and AV1, which Photos cannot import, so YouTube downloads usually top out at 1080p.

When a site offers no playable format at all, UMDL either converts the video on your device (the default, slower) or keeps the original in Files. Settings › *Unsupported video formats* decides.

## Signing in

Some posts need an account, and some sites (Reddit and Instagram among them) often refuse downloads that are not signed in. Choose **Sign in to a site** in the menu: a-Shell opens the site's sign-in page in its own browser. Sign in as usual. As soon as the site has stored the sign-in, UMDL brings you back to Shortcuts and says **Signed in to** *site*.

**Status** in the menu lists which sites are signed in at any time.

The sign-in is a cookie kept by a-Shell on your device. yt-dlp and gallery-dl read it from there. UMDL never sees your password and never reads a cookie's value, only which site it belongs to. Some sites, Google among them, do not allow signing in from an app's built-in browser.

**Forget saved sign-ins** in Settings deletes the cookie file the download tools read.

## If something goes wrong

A failed download returns to Shortcuts with the reason and these choices:

- **Try again**
- **Update tools and try again.** Sites change often, and a newer yt-dlp fixes most failures.
- **Sign in to this site**
- **Copy error details**, for a bug report. This includes the end of the helper's log

Other things worth knowing:

- **"There was a problem running the shortcut."** With UMDL 1.1.0 or earlier on iOS 27.2 this appears after every download: a-Shell's Get File action fails on that iOS version ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). Update UMDL; 1.2.0 uses the mode that still works. The download that failed is not lost: the next run offers to save it.
- **Is it set up properly?** Open **Status**. It shows the tool versions, whether GitHub can be reached, which sites are signed in, and the result of the last download. **Copy status and log** puts all of it on the clipboard.
- **You are left in a-Shell.** Keep a-Shell in the foreground while it works. iOS suspends it otherwise. Share the same link again and the download resumes where it stopped.
- **"A download from an earlier run has not been saved to Photos."** The download finished but saving was interrupted, for example by a permission prompt. Choose **Save it now**.
- **"Setup incomplete."** The helper script or the download tools could not be downloaded. The message says which, and why. Check the connection and run UMDL again; it continues from where it stopped.
- **The album was not found.** If you renamed or deleted the album, pick it again under Settings › *Save to*.
- **Start over.** Settings › *Reset UMDL* removes the helper and settings. Deleting a-Shell removes everything, the download tools included.

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

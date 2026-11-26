# UMDL

[![Build](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml/badge.svg)](https://github.com/TheKfcBandit/UMDL/actions/workflows/build.yml)
[![Release](https://img.shields.io/github/v/release/TheKfcBandit/UMDL)](https://github.com/TheKfcBandit/UMDL/releases/latest)
[![Licence: MIT](https://img.shields.io/badge/licence-MIT-blue.svg)](LICENSE)

**Universal Media Downloader for iPhone and iPad.** Share a post or a video to UMDL and it is saved to your Photos at the best quality. One tap, no menus, unless you ask for them.

UMDL is a free and open-source Shortcut. Downloads run on your own device with [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [gallery-dl](https://github.com/mikf/gallery-dl) inside the free [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) app. Nothing you share is sent to a UMDL server, because there isn't one.

> **Status: 1.3.0.** On a device, 1.2.0 set up, saved to Photos, signed in, and downloaded private posts from Instagram and X. 1.3.0 adds quality settings, Simple and Advanced modes and a new conversion path, none of which has run on a device yet. Reddit is still refused on the test network. [docs/BEHAVIOR.md](docs/BEHAVIOR.md) keeps the list. Please [report](https://github.com/TheKfcBandit/UMDL/issues) what you find.

## Install

1. Install [a-Shell](https://apps.apple.com/app/a-shell/id1473805438) from the App Store and open it once.
2. On your iPhone or iPad, download `UMDL.shortcut` from the [latest release](https://github.com/TheKfcBandit/UMDL/releases/latest) and tap **Add Shortcut**.
3. Share a post or video to UMDL, or run it from the Shortcuts app, and tap **Quick setup**. UMDL creates an album named UMDL, a-Shell opens and installs the download tools, and the shared post is downloaded. That takes about two minutes. **Custom setup** opens the settings first: album, mode, resolution, frame rate and conversion.

Built for iOS and iPadOS 18 and later. Keep the shortcut's name as **UMDL**, and keep only one copy: a-Shell uses that name to hand results back. When updating, choose **Replace** if Shortcuts asks, or delete the old copy first.

The first few runs show permission prompts from iOS (run a-Shell, save to Photos, open links). Choose **Always Allow** and they stop.

## Use

In any app, tap **Share**, then **UMDL**. a-Shell opens and shows progress, then sends you back with the media in your album and a notification saying so.

- **Videos** are saved at the highest resolution and frame rate available, or up to the limits you set.
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
| Settings | Album, mode, resolution, frame rate, conversion, the ask-first limit, what happens when a download finishes, reset |
| Sign in to a site | For private posts. UMDL confirms when the sign-in is saved |
| Status | Which sites are signed in, tool versions, storage, and a button to copy the log |
| Update tools | Installs the newest yt-dlp and gallery-dl now |
| About UMDL | Version, update check, project page |

Every screen, choice and message is described in [docs/BEHAVIOR.md](docs/BEHAVIOR.md).

## Quality

Settings has four rows for this. Resolution and frame rate both start at **Best available**.

| Setting | Choices |
|---|---|
| Mode | **Simple** uses the settings below and asks nothing. **Advanced** asks each time |
| Resolution | Best available, or up to 2160p, 1440p, 1080p, 720p, 480p |
| Frame rate | Best available, or up to 60 or 30 fps |
| Conversion | **Only when needed**, **For best quality**, or **Never** |

**Conversion** matters because Photos only plays H.264 and HEVC video.

- **Only when needed** (the default) asks each site for its best version in one of those, so nothing has to be converted. On most sites that is the best version there is. YouTube is the exception: above 1080p it mostly offers VP9 and AV1, so this setting stops at 1080p there.
- **For best quality** takes the best version whatever its codec and converts it to HEVC on your device, at the same size and frame rate. This is how 4K from YouTube reaches Photos. It takes longer.
- **Never** keeps a file Photos cannot play in Files.

Nothing is re-encoded unless it has to be. A playable video in the wrong kind of file is repacked with the picture copied bit for bit. A conversion uses the device's hardware HEVC encoder at a quality level, keeps 10-bit colour, and is named in the notification ("1 converted (VP9 → HEVC)"). [docs/BEHAVIOR.md](docs/BEHAVIOR.md#quality-and-conversion) has the flow chart and every step.

**Advanced mode** shows what the site has before downloading:

> Best video: 2160p60 VP9 · 650 MB
> Best audio: Opus · 160 kbps
> Single file: 360p H.264 + AAC

and offers up to three versions, such as **2160p60 · VP9 → HEVC**, **1080p · H.264** and **360p · H.264 · single file**. If a download turns out to be something Photos cannot play, it shows the source and what it would become, and asks whether to convert or keep the original in Files.

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

- **"There was a problem running the shortcut."** With UMDL 1.1.0 or earlier on iOS 27.2 this appears after every download: a-Shell's Get File action fails on that iOS version ([a-Shell issue 1138](https://github.com/holzschu/a-shell/issues/1138)). Update UMDL; 1.2.0 uses the mode that still works. The download that failed is not lost: the next run offers to save it.
- **Is it set up properly?** Open **Status**. It shows the tool versions, whether GitHub can be reached, which sites are signed in, and the result of the last download. **Copy** puts all of it, and the log, on the clipboard.
- **You are left in a-Shell.** Keep a-Shell in the foreground while it works. iOS suspends it otherwise. Share the same link again and the download resumes where it stopped.
- **"An earlier download was not saved."** The download finished but saving was interrupted, for example by a permission prompt. Choose **Save now**.
- **A conversion is slow.** Open Status and look at "Converts with". If it does not list `hevc_videotoolbox`, a-Shell's ffmpeg has no hardware encoder and converts in software. Set Conversion to **Only when needed**, or lower the resolution limit.
- **"Setup incomplete."** The helper or the download tools could not be downloaded. The message says which, and why. Check the connection and run UMDL again; it continues from where it stopped.
- **The album was not found.** If you renamed or deleted the album, pick it again under Settings › *Album*.
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

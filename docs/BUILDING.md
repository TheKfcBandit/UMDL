# Building, testing and releasing

## What you need

| To | You need |
|---|---|
| Compile | The [Cherri](https://github.com/electrikmilk/cherri) compiler. `brew install electrikmilk/cherri/cherri`, or `go install github.com/electrikmilk/cherri@98d5191ae121a6bcf663ed0e55495f4ee4c7a6e2` for the exact commit UMDL is verified against |
| Test | Python 3.9 or later, `dash`, and ffmpeg with ffprobe (tests that need a missing tool are skipped) |
| Sign | A Mac, or a signing service (see below) |
| Redraw icons | `pip install pillow` |

Always run the compiler from the repository root. The menu icons are embedded by paths relative to where the compiler runs.

## Compile

```sh
cherri src/UMDL.cherri --skip-sign --debug
```

This writes `src/UMDL_unsigned.shortcut` and, because of `--debug`, `src/UMDL.plist`, which the flow tests read. `make build` does the same.

To read a build as pseudo-code:

```sh
python tools/dump_shortcut.py src/UMDL.plist
```

## Test

```sh
make test
# or
python -m unittest discover -s tests -v
```

| File | Covers |
|---|---|
| `tests/test_umdl.py` | The helper: link parsing, error classification, tool order, the Photos-ready pipeline against real media made with ffmpeg, and full runs with stand-in download tools |
| `tests/test_shortcut_flow.py` | The compiled shortcut, run in `tests/shortcut_sim.py` against the real helper: setup, one-tap download, large downloads, errors, recovery, every menu and setting |
| `tests/test_versions.py` | The version and repository name agree everywhere they are written |

The simulator is a model of Shortcuts, not Shortcuts. It catches logic and protocol mistakes. It cannot tell you how iOS behaves. Before a release, run through [the device checklist](#device-checklist).

## Sign

iOS only imports signed shortcuts, and Apple's signing tool only works on a Mac that is signed in to iCloud. GitHub's build machines are not, so CI cannot sign on its own. Four ways to get a signed shortcut:

**In the Cherri Playground**, with no Mac and no key. [`playground/UMDL.cherri`](../playground/UMDL.cherri) is the same source with the menu icons inlined, so it is one self-contained file. Copy all of it, paste it into the [Cherri Playground](https://playground.cherrilang.org), build, and export the signed shortcut. The Playground may run a different compiler version from the one UMDL is tested with. After changing `src/UMDL.cherri` or an icon, run `make playground` to refresh the copy; a test fails if you forget.

**On a Mac.** Cherri signs with the built-in `shortcuts` command. The Mac must be signed in to iCloud.

```sh
cherri src/UMDL.cherri --share=anyone      # writes src/UMDL.shortcut
```

**With RoutineHub's HubSign**, from any platform. This needs a RoutineHub API key from an account with a paid Developer membership. A key from a free account is refused with `401 Unauthorized`.

```sh
cherri src/UMDL.cherri --hubsign --routinehub-api-key=YOUR_KEY
```

**With your own signing server** running [shortcut-signing-server](https://github.com/scaxyz/shortcut-signing-server) on a Mac:

```sh
cherri src/UMDL.cherri --signing-server=https://your.server/sign
```

`make sign` uses HubSign when `ROUTINEHUB_API_KEY` is set and the Mac's own signing otherwise.

## Continuous integration

`.github/workflows/build.yml` runs on every push and pull request:

1. **Compile and test** on Linux. The unsigned shortcut is attached to the run as `UMDL-unsigned`.
2. **Sign** on a macOS runner. It first tries the runner's own `shortcuts sign`, which currently fails with "you must be signed into iCloud". If the repository has a `ROUTINEHUB_API_KEY` secret, it then signs with HubSign, and the signed shortcut is attached to the run as `UMDL`. If the secret is missing or RoutineHub refuses the key, the job still passes and says so in its summary.
3. **Release**, only for a `v*` tag: checks the tag against `version.json` and publishes the signed shortcut. It fails if there is no signed shortcut.

To add the secret: repository **Settings › Secrets and variables › Actions › New repository secret**, named `ROUTINEHUB_API_KEY`. Never commit the key or paste it into an issue.

## Release

1. Add a section for the new version at the top of `CHANGELOG.md`, and run `make playground`.
2. Set the new version in three places: `@umdlVersion` in `src/UMDL.cherri`, `HELPER_VERSION` in `src/umdl.py` (if the helper changed) and `version.json`. `tests/test_versions.py` fails if they disagree.
3. Put one line in `version.json` `notes`. It is shown in the update prompt.
4. Run `make test` and the device checklist.
5. Commit, then tag: `git tag v1.2.3 && git push origin main v1.2.3`.

Order matters for one reason. `version.json` on `main` is what installed copies read, so pushing it announces the update to everyone. Push it together with the tag, so the release exists when people tap **Get the update**.

A helper-only fix needs no release: bump `HELPER_VERSION` and `helper` in `version.json`, push to `main`, and installed copies pick it up within a day.

## Device checklist

On an iPhone or iPad with a-Shell installed and UMDL not yet set up:

- [ ] Share a YouTube link to UMDL. Setup runs, tools install, the video lands in the new album.
- [ ] Share a second link. No questions, saved, notification shown.
- [ ] Share a post with several images from X, Instagram or Reddit.
- [ ] Share a playlist with more than 10 videos. The menu appears; **Only the first 10** saves ten.
- [ ] Share an audio link (SoundCloud). The file appears in Files under a-Shell › UMDL › Saved.
- [ ] Share a link to a page with nothing on it. The error menu appears; **Cancel** works.
- [ ] Open UMDL directly. Try every menu item and every setting.
- [ ] Start a long download, leave a-Shell, share the same link again. It resumes.
- [ ] Sign in to a site, then download a post that needs the login.
- [ ] Settings › Reset UMDL, then run UMDL. Setup starts again.

## Layout

```
src/UMDL.cherri          the shortcut
src/umdl.py              the helper that runs in a-Shell
assets/icons/            menu icons, embedded at compile time
tools/make_icons.py      draws the icons
tools/dump_shortcut.py   prints a compiled shortcut as pseudo-code
tools/make_playground.py refreshes the single-file source
playground/UMDL.cherri   the source as one file, for the Cherri Playground
tests/                   tests, the shortcut simulator, stand-in download tools
docs/                    requirements, architecture, this file
version.json             what installed copies check for updates
CHANGELOG.md             what changed in each version
```

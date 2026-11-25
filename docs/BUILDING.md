# Building, testing and releasing

## What you need

| To | You need |
|---|---|
| Compile | The [Cherri](https://github.com/electrikmilk/cherri) compiler. `brew install electrikmilk/cherri/cherri`, or `go install github.com/electrikmilk/cherri@98d5191ae121a6bcf663ed0e55495f4ee4c7a6e2` for the exact commit UMDL is verified against |
| Test | Python 3.9 or later, `dash`, and ffmpeg with ffprobe (tests that need a missing tool are skipped) |
| Sign | `curl` and Go (for the check afterwards), or a Mac |
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

iOS only imports signed shortcuts, and Apple's signing tool only works on a Mac that is signed in to iCloud. GitHub's build machines are not, so UMDL is signed by a signing service and then checked.

**With the Shortcuty signing service.** This is what CI and `make sign` use. It is free and needs no account: you upload the unsigned shortcut and get the signed one back. [API documentation](https://github.com/Shortcuty/Signing-Server-API-Documentation).

```sh
make sign
# which runs:
curl --fail --user-agent "UMDL (+https://github.com/TheKfcBandit/UMDL)" \
     --form 'file=@src/UMDL_unsigned.shortcut;filename=UMDL.shortcut' \
     --output dist/UMDL.shortcut https://sign.shortcuty.app/api/v1/sign
cd tools/verifysigned && go run . ../../src/UMDL_unsigned.shortcut ../../dist/UMDL.shortcut
```

Send a User-Agent that says who is calling: the one request made with curl's default was refused with `403`.

The service is run by a third party, so the result is not taken on trust. A signed shortcut is signed but not encrypted, and `tools/verifysigned` reads the workflow back out of it and compares it with the build, action for action. Signing itself changes two things, which the check allows: the Shortcuts version stamp, and an empty triggers list that Apple's tool drops. CI refuses to publish a signed file that differs in any other way.

Save the signed file as `UMDL.shortcut`. Shortcuts names an imported shortcut after its file, and UMDL has to be called UMDL.

**On a Mac.** Cherri signs with the built-in `shortcuts` command. The Mac must be signed in to iCloud.

```sh
cherri src/UMDL.cherri --share=anyone      # writes src/UMDL.shortcut
```

**In the Cherri Playground**, in a browser. Open [`playground/UMDL.cherri`](../playground/UMDL.cherri) on GitHub and press **Copy raw file**; it is the same source with the menu icons inlined. Paste it over the sample in the [Cherri Playground](https://playground.cherrilang.org), press the hammer to build, then the share icon and **Sign Shortcut**. A QR code and a download button appear. After changing `src/UMDL.cherri` or an icon, run `make playground` to refresh the copy; a test fails if you forget.

**With RoutineHub's HubSign.** This needs an API key from an account with a paid Developer membership. A key from a free account is refused with `401 Unauthorized`.

```sh
cherri src/UMDL.cherri --hubsign --routinehub-api-key=YOUR_KEY
```

## Continuous integration

`.github/workflows/build.yml` runs on every push and pull request:

1. **Compile and test.** The unsigned shortcut is attached to the run as `UMDL-unsigned`.
2. **Sign.** Sends the unsigned shortcut to the Shortcuty service, then runs `tools/verifysigned` on what comes back. If the contents differ from the build, the job fails. The signed shortcut is attached to the run as `UMDL`, with its SHA-256 in the run summary. If the service is unreachable and the repository has a `ROUTINEHUB_API_KEY` secret, HubSign is tried instead. If nothing could sign, the job still passes and says so.
3. **Release**, only for a `v*` tag: checks the tag against `version.json`, then creates the release (or reuses one you made by hand) and attaches the signed shortcut. With no signed shortcut it publishes nothing and says so in its summary.

## Release

1. Add a section for the new version at the top of `CHANGELOG.md`, and run `make playground`.
2. Set the new version in three places: `@umdlVersion` in `src/UMDL.cherri`, `HELPER_VERSION` in `src/umdl.py` (if the helper changed) and `version.json`. `tests/test_versions.py` fails if they disagree.
3. Put one line in `version.json` `notes`. It is shown in the update prompt.
4. Run `make test` and the device checklist.
5. Commit, then tag: `git tag v1.2.3 && git push origin main v1.2.3`.
6. CI signs, verifies and publishes the release. If the signing service is down, re-run the workflow later, or sign another way and attach `UMDL.shortcut` to the release by hand.

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
tools/verifysigned/      checks a signed shortcut against the build
playground/UMDL.cherri   the source as one file, for the Cherri Playground
tests/                   tests, the shortcut simulator, stand-in download tools
docs/                    requirements, architecture, this file
version.json             what installed copies check for updates
CHANGELOG.md             what changed in each version
```

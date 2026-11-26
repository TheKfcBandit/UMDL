"""End-to-end flows: the compiled shortcut and the real helper, together.

Each test class covers one section of docs/BEHAVIOR.md, and each test names
the behaviour it pins down. Needs the compiled plist. From the repository root:

    cherri src/UMDL.cherri --skip-sign --debug     # writes src/UMDL.plist
    python -m unittest discover -s tests -v

Set UMDL_PLIST to point somewhere else. See tests/shortcut_sim.py for what
the simulator does and does not prove.
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

from shortcut_sim import ASHELL, PREFIX, SimError, World  # noqa: E402


def find_plist():
    candidates = [os.environ.get("UMDL_PLIST"), os.path.join(ROOT, "build", "UMDL.plist"),
                  os.path.join(ROOT, "src", "UMDL.plist"), os.path.join(ROOT, "UMDL.plist")]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


PLIST = find_plist()
HAVE_DASH = shutil.which("dash") is not None
CONFIG = {"album": "Clips", "threshold": "10", "after": "notify", "mode": "simple",
          "res": "best", "fps": "best", "convert": "needed"}
DEFAULTS = dict(CONFIG, album="UMDL")
ADVANCED = dict(CONFIG, mode="advanced")
VIDEO = "https://video.test/watch/abc"
TOOLS = ["yt-dlp", "gallery-dl", "yt-dlp-ejs", "yt-dlp-apple-webkit-jsi"]
# First run: the shortcut installs the two required tools in the a-Shell window,
# then the helper's first daily check brings everything up to date.
FIRST_RUN_PIP = ["yt-dlp gallery-dl", " ".join(TOOLS)]
MAIN_MENU = ["Download from clipboard", "Enter a link", "Settings", "Sign in to a site",
             "Status", "Update tools", "About UMDL"]
SETTINGS_MENU = ["Album", "Mode", "Resolution", "Frame rate", "Conversion", "Large downloads",
                 "When finished", "Reset", "Done"]

with open(os.path.join(ROOT, "version.json")) as _handle:
    VERSION = json.load(_handle)


@unittest.skipUnless(PLIST, "compile the shortcut first (see the top of this file)")
@unittest.skipUnless(HAVE_DASH, "needs the dash shell")
class Flow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = os.path.join(ROOT, "build", "test-media")
        os.makedirs(cls.media, exist_ok=True)
        cls.clip = os.path.join(cls.media, "clip.mp4")
        cls.song = os.path.join(cls.media, "song.m4a")
        cls.jpg = os.path.join(cls.media, "pic.jpg")
        cls.webm = os.path.join(cls.media, "old.webm")
        quiet = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi"]
        if shutil.which("ffmpeg"):
            video = ["-i", "testsrc=size=160x120:rate=10:duration=1"]
            if not os.path.exists(cls.clip):
                subprocess.run(quiet + video + ["-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip],
                               check=True)
            if not os.path.exists(cls.song):
                subprocess.run(quiet + ["-i", "sine=frequency=440:duration=1", "-c:a", "aac",
                                        cls.song], check=True)
            if not os.path.exists(cls.jpg):
                subprocess.run(quiet + video + ["-frames:v", "1", cls.jpg], check=True)
            if not os.path.exists(cls.webm):
                made = subprocess.run(quiet + video + ["-c:v", "libvpx-vp9", "-b:v", "200k", cls.webm])
                if made.returncode:
                    subprocess.run(quiet + video + ["-c:v", "libvpx", "-b:v", "200k", cls.webm],
                                   check=True)
        else:
            for path, data in ((cls.clip, b"\x00\x00\x00\x18ftypmp42"), (cls.jpg, b"\xff\xd8\xff"),
                               (cls.song, b"\x00\x00\x00\x18ftypM4A ")):
                with open(path, "wb") as handle:
                    handle.write(data)

    def setUp(self):
        self.world = self.new_world()

    def new_world(self):
        world = World(PLIST)
        self.addCleanup(world.close)
        return world

    def one_video(self, title="My clip"):
        return {"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": title},
                          "files": [["abc.mp4", self.clip, title]]},
                "gallery": {"found": False}}

    @staticmethod
    def notifications(world):
        return [e[1:] for e in world.seen("notification")]

    @staticmethod
    def alerts(world):
        return [e[1:] for e in world.seen("alert")]

    @staticmethod
    def helper_commands(world):
        return [command for command, _ in world.helper_runs]

    @staticmethod
    def jobs_left(world):
        jobs = os.path.join(world.workspace, "jobs")
        return os.listdir(jobs) if os.path.isdir(jobs) else []

    @staticmethod
    def foreground_commands(world):
        return [text for window, text in world.commands if window == "open"]


class Onboarding(Flow):
    """docs/BEHAVIOR.md, "First run"."""

    def test_quick_setup_from_the_share_sheet_is_one_tap_and_downloads(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.script(("menu", "Quick setup"))
        w.share("Watch this " + VIDEO)

        welcome = w.seen("menu")[0]
        self.assertTrue(welcome[1].startswith("Welcome to UMDL"))
        self.assertEqual(welcome[2], ["✅ Quick setup", "⚙️ Custom setup", "Not now"])
        self.assertEqual(len(w.seen("menu")), 1)           # nothing else was asked
        self.assertEqual(w.albums, ["UMDL"])
        self.assertEqual(w.read_config(), DEFAULTS)
        self.assertEqual(w.pip_log(), FIRST_RUN_PIP)        # tools installed with no further input
        self.assertEqual(self.helper_commands(w), ["run"])  # straight into the download
        self.assertEqual(w.photos, [("001.mp4", "UMDL", os.path.getsize(self.clip))])
        self.assertEqual(self.notifications(w), [("My clip", "Saved to the UMDL album.")])
        self.assertEqual(self.alerts(w), [])
        self.assertEqual(self.jobs_left(w), [])

    def test_quick_setup_opened_from_the_app_installs_and_reports_ready(self):
        w = self.world
        w.script(("menu", "Quick setup"))
        w.share(None)
        self.assertEqual(self.helper_commands(w), ["setup"])
        self.assertEqual(w.pip_log(), FIRST_RUN_PIP)
        self.assertEqual([a[0] for a in self.alerts(w)], ["UMDL is ready"])
        self.assertEqual(len(w.seen("menu")), 1)
        self.assertEqual(w.seen("list"), [])               # the main menu is not shown during setup
        self.assertEqual(w.photos, [])

    def test_custom_setup_is_the_settings_list_then_the_same_install(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.script(("menu", "Custom setup"),
                 ("list", "Album"), ("menu", "New album"), ("ask", "Clips"),
                 ("list", "Resolution"), ("menu", "1080p"),
                 ("list", "Frame rate"), ("menu", "30 fps"),
                 ("list", "Done"))
        w.share(VIDEO)
        first = w.seen("list")[0]
        self.assertEqual(first[1], "Settings")
        self.assertEqual(first[2], [row for row in SETTINGS_MENU if row != "Reset"])   # nothing to reset yet
        self.assertEqual(first[4][-1], "Install and finish")
        self.assertEqual(w.seen("menu")[1][1:3], ("Save to", ["🆕 New album", "🖼️ Existing album",
                                                               "📚 Library only"]))
        self.assertEqual(w.albums, ["Clips"])
        self.assertEqual(w.read_config(), dict(CONFIG, res="1080", fps="30"))
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual(w.photos[0][1], "Clips")
        self.assertEqual(w.helper_runs[0][1]["cfg"], dict(CONFIG, res="1080", fps="30"))

    def test_custom_setup_left_as_it_is_equals_quick_setup(self):
        w = self.world
        w.script(("menu", "Custom setup"), ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config(), DEFAULTS)
        self.assertEqual(w.albums, ["UMDL"])                 # the default album is still created
        self.assertEqual(self.helper_commands(w), ["setup"])

    def test_custom_setup_with_an_existing_album_or_none(self):
        w = self.world
        w.script(("menu", "Custom setup"), ("list", "Album"), ("menu", "Existing album"),
                 ("ask", "Holiday"), ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config(), dict(DEFAULTS, album="Holiday"))
        self.assertEqual(w.albums, [])                      # an existing album is not created again

        w = self.new_world()
        w.script(("menu", "Custom setup"), ("list", "Album"), ("menu", "Library only"), ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config(), dict(DEFAULTS, album="Recents"))
        self.assertEqual(w.albums, [])

    def test_an_empty_album_name_falls_back(self):
        w = self.world
        w.script(("menu", "Custom setup"), ("list", "Album"), ("menu", "New album"), ("ask", ""),
                 ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config()["album"], "UMDL")
        self.assertEqual(w.albums, ["UMDL"])

    def test_declining_setup_changes_nothing(self):
        w = self.world
        w.script(("menu", "Not now"))
        w.share(VIDEO)
        self.assertFalse(os.path.exists(w.workspace))
        self.assertEqual(w.helper_runs, [])
        self.assertEqual(w.albums, [])

    def test_no_connection_during_setup_is_reported_and_the_next_run_finishes(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.set_offline(True)
        w.script(("menu", "Quick setup"))
        w.share(VIDEO)
        self.assertEqual(self.alerts(w), [("Setup incomplete", "The helper could not be downloaded. "
                                           "Check the connection, then run UMDL again.")])
        self.assertEqual(w.helper_runs, [])
        self.assertEqual(w.photos, [])
        # The next attempt keeps the answers already given and finishes the job.
        w.set_offline(False)
        w.share(VIDEO)
        self.assertEqual(len(w.seen("menu")), 1)
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual(len(w.photos), 1)

    def test_helper_is_downloaded_in_the_app_when_the_background_cannot(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.set_background_network(False)
        w.script(("menu", "Quick setup"))
        w.share(VIDEO)
        self.assertEqual(self.alerts(w), [])
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual(len(w.photos), 1)
        self.assertIn("curl -fsL", self.foreground_commands(w)[0])
        # Once fetched, later runs go straight to the helper.
        w.share(VIDEO)
        self.assertNotIn("curl", self.foreground_commands(w)[-1])
        self.assertEqual(len(w.photos), 2)

    def test_tools_that_fail_to_install_are_reported_and_retried_next_time(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.set_pip_failure("No matching distribution found for yt-dlp")
        w.script(("menu", "Quick setup"))
        w.share(VIDEO)
        title, body = self.alerts(w)[0]
        self.assertEqual(title, "Setup incomplete")
        self.assertIn("Could not install yt-dlp and gallery-dl", body)
        self.assertIn("No matching distribution found", body)
        self.assertEqual(w.photos, [])
        # Nothing to redo by hand: the next run installs and carries on.
        w.set_pip_failure(None)
        w.share(VIDEO)
        self.assertEqual(len(w.seen("menu")), 1)
        self.assertEqual(len(w.photos), 1)

    def test_setup_never_reports_an_unsaved_download(self):
        w = self.world
        w.script(("menu", "Quick setup"))
        w.share(None)
        self.assertFalse(any("was not saved" in m[1] for m in w.seen("menu")))

    def test_upgrade_from_1_0_refetches_the_helper_and_removes_the_old_environment(self):
        w = self.world
        w.install(CONFIG)
        os.remove(os.path.join(w.workspace, "helper.for"))
        os.makedirs(os.path.join(w.workspace, "env", "bin"))
        with open(os.path.join(w.workspace, "umdl.py"), "w") as handle:
            handle.write("raise SystemExit('old helper')\n")
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "env")))
        self.assertEqual(len(w.photos), 1)
        with open(os.path.join(w.workspace, "helper.for")) as handle:
            self.assertEqual(handle.read().strip(), VERSION["shortcut"])


class OneTap(Flow):
    """docs/BEHAVIOR.md, "Sharing a link"."""

    def test_download_asks_nothing(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.share(VIDEO)  # no scripted answers: any question would fail the test
        self.assertEqual(w.photos, [("001.mp4", "Clips", os.path.getsize(self.clip))])
        self.assertEqual(w.seen("menu") + w.seen("list") + w.seen("alert"), [])
        payload = w.helper_runs[0][1]
        self.assertEqual((payload["mode"], payload["name"], payload["cfg"]), ("auto", "UMDL", CONFIG))
        self.assertEqual((payload["v"], payload["p"]), (VERSION["shortcut"], str(VERSION["protocol"])))
        self.assertEqual(self.foreground_commands(w)[0].split("\n")[0], "cd $HOME/Documents/UMDL")
        with open(w.record_path) as handle:
            opts = [json.loads(line) for line in handle]
        self.assertTrue(all("avc" in o["format"].split("/")[0] for o in opts))

    def test_link_is_pulled_out_of_shared_text(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.share("So good \U0001f602 https://video.test/watch/abc?si=xyz&t=5 via @someone")
        self.assertEqual(w.helper_runs[0][1]["url"], "https://video.test/watch/abc?si=xyz&t=5")
        self.assertEqual(len(w.photos), 1)

    def test_shared_text_without_a_link_opens_the_main_menu(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share("just some words")
        self.assertEqual(w.seen("list")[0][2], MAIN_MENU)
        self.assertEqual(w.helper_runs, [])

    def test_no_album_saves_to_the_library(self):
        w = self.world
        w.install(dict(CONFIG, album="Recents"))
        w.set_scenario(self.one_video(title=""))
        w.share(VIDEO)
        self.assertEqual(w.photos[0][1], "Recents")
        self.assertEqual(self.notifications(w), [("UMDL", "Saved to Photos.")])

    def test_open_photos_when_finished(self):
        w = self.world
        w.install(dict(CONFIG, after="photos"))
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual(w.seen("openurl"), [("openurl", "photos-redirect://")])

    def test_awkward_titles_and_album_names_survive(self):
        w = self.world
        album = "Sam's \"best\" clips; vol, 2 — 日本"
        title = "L'été \"quoted\" & <tags> \U0001f3ac"
        w.install(dict(CONFIG, album=album))
        w.set_scenario(self.one_video(title=title))
        w.share(VIDEO)
        self.assertEqual(w.photos[0][1], album)
        self.assertEqual(self.notifications(w)[0][1], "Saved to the %s album." % album)
        self.assertEqual(w.helper_runs[0][1]["cfg"]["album"], album)

    def test_gallery_post_saves_every_image(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": True, "error": "No video could be found"},
                        "gallery": {"found": True, "count": 4, "sample": self.jpg}})
        w.share("https://x.com/someone/status/123")
        self.assertEqual([p[0] for p in w.photos], ["001.jpg", "002.jpg", "003.jpg", "004.jpg"])
        self.assertEqual(self.notifications(w)[0][1], "Saved 4 items to the Clips album.")

    def test_audio_is_kept_in_files(self):
        if not shutil.which("ffprobe"):
            self.skipTest("ffprobe not installed")
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "s", "title": "Song"},
                                  "files": [["s.m4a", self.song, "Song"]]},
                        "gallery": {"found": False}})
        w.share("https://audio.test/s")
        self.assertEqual(w.photos, [])
        self.assertEqual(self.notifications(w)[0][1],
                         "Nothing was added to Photos.\n"
                         "1 kept in Files (a-Shell, UMDL, Saved).")
        self.assertEqual(os.listdir(os.path.join(w.workspace, "Saved")), ["Song.m4a"])

    def test_partial_download_saves_what_arrived_and_says_what_did_not(self):
        w = self.world
        w.install(CONFIG)
        files = [["a.mp4", self.clip, "A"], ["b.mp4", self.clip, "B"]]
        w.set_scenario({"ytdlp": {"raw": {"_type": "playlist", "title": "Set", "playlist_count": 3,
                                          "entries": []},
                                  "files": files, "download_error": "HTTP Error 500"},
                        "gallery": {"found": False}})
        w.share("https://video.test/playlist/2")
        self.assertEqual(len(w.photos), 2)
        self.assertEqual(self.notifications(w)[0],
                         ("Set", "Saved 2 items to the Clips album.\n1 failed."))

    def test_file_too_large_to_hand_over_is_kept_in_files(self):
        w = self.world
        w.install(CONFIG)
        w.extra_env["UMDL_MAX_PHOTOS_MB"] = "0.00001"       # ten bytes
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual(w.photos, [])
        self.assertEqual(self.notifications(w)[0][1],
                         "Nothing was added to Photos.\n"
                         "1 kept in Files (a-Shell, UMDL, Saved).\n"
                         "1 over 1 GB, kept in Files.")
        self.assertEqual(os.listdir(os.path.join(w.workspace, "Saved")), ["My clip.mp4"])

    def test_reddit_link_blocked_on_the_website_is_fetched_through_the_api(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".reddit.com", "reddit_session")])
        w.set_scenario({"ytdlp": {"suitable": True, "error": "HTTP Error 403: Blocked"},
                        "gallery": {"found": True, "count": 2, "sample": self.jpg,
                                    "blocked_unless_api": "\"You've been blocked by network security.\""}})
        w.share("https://www.reddit.com/r/pics/s/AbCdEfGhIj")
        self.assertEqual(len(w.photos), 2)
        self.assertEqual(w.seen("menu") + w.seen("alert"), [])

    def test_tools_removed_behind_umdls_back_are_reinstalled_on_the_way(self):
        w = self.world
        w.install(CONFIG, tools=False)
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual(w.pip_log(), TOOLS)                # one at a time, by the helper
        self.assertEqual(len(w.photos), 1)

    def test_tools_installed_where_python_is_not_looking_are_found(self):
        w = self.world
        w.install(CONFIG, tools=False)
        w.set_pip_target("elsewhere")
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(self.alerts(w), [])
        # The location is remembered, so nothing is installed again.
        installs = len(w.pip_log())
        w.share(VIDEO)
        self.assertEqual(len(w.photos), 2)
        self.assertEqual(len(w.pip_log()), installs)

    def test_newer_release_is_offered_after_the_download(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.set_version_json(dict(VERSION, shortcut="9.9.9", helper=VERSION["helper"]))
        w.script(("menu", "Get the update"))
        w.share(VIDEO)
        self.assertEqual(len(w.photos), 1)
        prompt = w.seen("menu")[0][1]
        self.assertEqual(prompt, "UMDL 9.9.9 is available. Installed: %s."
                         % VERSION["shortcut"])
        self.assertEqual(w.seen("openurl")[-1][1], VERSION["url"])

    def test_declining_the_update_ends_quietly(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.set_version_json(dict(VERSION, shortcut="9.9.9"))
        w.script(("menu", "Later"))
        w.share(VIDEO)
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(w.seen("openurl"), [])
        self.assertEqual(w.seen("list"), [])               # and no main menu afterwards

    def test_unreadable_callback_falls_back_to_the_main_menu(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share("UMDLCB:bm90IGpzb24")
        self.assertEqual(w.seen("list")[0][2], MAIN_MENU)
        self.assertEqual(w.photos, [])

    def test_helper_from_another_version_is_reported_as_out_of_date(self):
        w = self.world
        w.install(CONFIG)
        path = os.path.join(w.workspace, "umdl.py")
        with open(path) as handle:
            source = handle.read()
        with open(path, "w") as handle:
            handle.write(source.replace("PROTOCOL = %d" % VERSION["protocol"], "PROTOCOL = 99"))
        w.script(("menu", "Get the latest version"))
        w.share(VIDEO)
        self.assertIn("out of date", w.seen("menu")[0][1])
        self.assertEqual(w.seen("openurl")[0][1], VERSION["url"])


class RedditThroughTheBrowser(Flow):
    """docs/BEHAVIOR.md, "Reddit". Reddit turns both download tools away; the
    post is read through a-Shell's own browser instead."""

    SHARE = "https://www.reddit.com/r/me_irl/s/cUdJnFfPwD"
    BLOCK = "\"You've been blocked by network security.\""

    def blocked(self, browser, **ytdlp):
        scenario = {"ytdlp": dict({"suitable": True, "error": "HTTP Error 403: Blocked"}, **ytdlp),
                    "gallery": {"found": True, "sample": self.jpg, "blocked_unless_api": self.BLOCK,
                                "api_fail": self.BLOCK}}
        if browser is not None:
            scenario["browser"] = browser
        return scenario

    def gallery_post(self, count):
        ids = ["img%02d" % i for i in range(count)]
        return {"id": "1abcde", "title": "Holiday photos", "is_gallery": True,
                "url": "https://www.reddit.com/gallery/1abcde",
                "gallery_data": {"items": [{"media_id": i} for i in ids]},
                "media_metadata": {i: {"status": "valid", "m": "image/jpg", "s": {
                    "u": "https://preview.redd.it/%s.jpg?width=1080&s=abc" % i}} for i in ids}}

    def test_photo_post_is_saved_with_no_question(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".reddit.com", "reddit_session")])
        w.set_scenario(self.blocked({"post": self.gallery_post(3)}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 3)
        self.assertEqual(w.seen("menu") + w.seen("alert"), [])
        self.assertEqual(self.notifications(w), [("Holiday photos", "Saved 3 items to the Clips album.")])
        # The browser went to Reddit, asked for the shared link, and was put back.
        self.assertEqual(w.browser_visits(), ["https://www.reddit.com/robots.txt", "fetch " + self.SHARE])
        self.assertEqual(w.browser_page(), "https://localhost:8443/wasm.html")
        # The originals were fetched, not the resized previews.
        self.assertEqual(w.direct_links(), [["https://i.redd.it/img00.jpg", "https://i.redd.it/img01.jpg",
                                             "https://i.redd.it/img02.jpg"]])

    def test_video_post_goes_to_yt_dlp_with_its_manifest(self):
        w = self.world
        w.install(CONFIG)
        manifest = "https://v.redd.it/abc123/DASHPlaylist.mpd?a=1&v=1&f=sd"
        post = {"id": "1abcde", "title": "Cat falls off shelf", "is_video": True,
                "url": "https://v.redd.it/abc123",
                "secure_media": {"reddit_video": {"dash_url": manifest, "hls_url": "h", "fallback_url": "f"}}}
        w.set_scenario(self.blocked({"post": post}, urls={"DASHPlaylist": {
            "raw": {"_type": "video", "id": "DASHPlaylist", "title": "DASHPlaylist"},
            "files": [["DASHPlaylist.mp4", self.clip, "DASHPlaylist"]]}}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(self.notifications(w), [("Cat falls off shelf", "Saved to the Clips album.")])

    def test_post_that_links_elsewhere_is_downloaded_from_there(self):
        w = self.world
        w.install(CONFIG)
        post = {"id": "1abcde", "title": "Great clip", "url": "https://clips.test/watch/9",
                "url_overridden_by_dest": "https://clips.test/watch/9"}
        w.set_scenario(self.blocked({"post": post}, urls={"clips.test": {
            "raw": {"_type": "video", "id": "9", "title": "Nine"},
            "files": [["9.mp4", self.clip, "Nine"]]}}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 1)

    def test_large_gallery_still_asks_first(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.blocked({"post": self.gallery_post(12)}))
        w.script(("menu", "First 10"))
        w.share(self.SHARE)
        self.assertEqual(w.seen("menu")[0][1], "Holiday photos\n\n12 items.")
        self.assertEqual(len(w.photos), 10)

    def test_browser_is_returned_to_the_page_it_was_showing(self):
        w = self.world
        w.install(CONFIG)
        here = "https://www.instagram.com/accounts/login/"       # left open after a sign-in
        w.set_scenario(self.blocked({"post": self.gallery_post(1), "start": here}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(w.browser_page(), here)

    def test_refusal_in_the_browser_too_is_reported_as_reddits(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".reddit.com", "reddit_session")])
        w.set_scenario(self.blocked({"http": "403 " + self.BLOCK}))
        w.script(("menu", "Cancel"))
        w.share(self.SHARE)
        prompt = w.seen("menu")[0][1]
        self.assertIn("Reddit refused this device or network: " + self.BLOCK, prompt)
        self.assertEqual(w.photos, [])
        self.assertEqual(w.browser_page(), "https://localhost:8443/wasm.html")   # put back all the same

    def test_post_without_media_and_a_browser_that_never_answers(self):
        for browser in ({"post": {"id": "1abcde", "title": "A question", "is_self": True,
                                  "url": "https://www.reddit.com/r/me_irl/comments/1abcde/a_question/"}},
                        {"silent": True}, None):
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.blocked(browser))
            w.script(("menu", "Cancel"))
            w.share(self.SHARE)
            self.assertIn("Download failed", w.seen("menu")[0][1])
            self.assertEqual(w.photos, [])

    def test_other_sites_never_involve_the_browser(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"error": "HTTP Error 403: Blocked"}, "gallery": {"found": False},
                        "browser": {"post": self.gallery_post(1)}})
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        self.assertEqual(w.browser_visits(), [])


class AdvancedMode(Flow):
    """docs/BEHAVIOR.md, "Advanced mode"."""

    FORMATS = [
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "width": 640,
         "height": 360, "fps": 30, "tbr": 500, "filesize": 10_000_000},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "width": 1920,
         "height": 1080, "fps": 30, "tbr": 4000, "filesize": 80_000_000},
        {"format_id": "315", "vcodec": "vp09.00.51.08", "acodec": "none", "width": 3840,
         "height": 2160, "fps": 60, "tbr": 26000, "filesize": 650_000_000},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "abr": 160},
    ]
    # The conversion named is the one this machine's ffmpeg would do; a device names HEVC.
    TARGET = "H.264" if shutil.which("ffmpeg") and "hevc_videotoolbox" not in subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        universal_newlines=True).stdout else "HEVC"
    OPTIONS = ["⬇️ 2160p60 · VP9 → " + TARGET, "⬇️ 1080p · H.264", "⬇️ 360p · H.264 · single file"]

    def many_versions(self, **more):
        scenario = self.one_video()
        scenario["ytdlp"]["formats"] = self.FORMATS
        scenario["ytdlp"].update(more)
        return scenario

    def test_shows_what_the_site_has_and_downloads_the_version_picked(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario(self.many_versions())
        w.script(("list", "1080p"))
        w.share(VIDEO)
        _, prompt, options, picked = w.seen("list")[0][:4]
        self.assertEqual(prompt, "My clip\n\nBest video: 2160p60 VP9 · 650 MB\n"
                                 "Best audio: Opus · 160 kbps\nSingle file: 360p H.264 + AAC")
        self.assertEqual(options, self.OPTIONS)
        self.assertEqual(self.helper_commands(w), ["run", "run"])
        self.assertEqual(w.helper_runs[1][1]["pick"], "⬇️ 1080p · H.264")
        self.assertTrue(w.recorded_options()[-1]["format"].startswith("137+140/"))
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(self.notifications(w), [("My clip", "Saved to the Clips album.")])

    def test_the_resolution_limit_is_shown_and_applied(self):
        w = self.world
        w.install(dict(ADVANCED, res="1080", fps="30"))
        w.set_scenario(self.many_versions())
        w.script(("list", "1080p"))
        w.share(VIDEO)
        _, prompt, options = w.seen("list")[0][:3]
        self.assertTrue(prompt.endswith("Your limit: 1080p 30 fps"))
        self.assertEqual(options, self.OPTIONS[1:])          # nothing above the limit is offered
        self.assertEqual(w.recorded_options()[-1]["format_sort"], ["res:1080", "fps:30"])

    def test_one_playable_version_asks_nothing(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario(self.many_versions(formats=[self.FORMATS[0]]))
        w.share(VIDEO)
        self.assertEqual(w.seen("list"), [])
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual(len(w.photos), 1)

    def test_a_link_with_several_videos_asks_once_for_all(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario({"ytdlp": {"raw": {"_type": "playlist", "title": "Set", "entries": [
            {"id": "a", "title": "One"}, {"id": "b", "title": "Two"}]},
            "files": [["a.mp4", self.clip, "One"], ["b.mp4", self.clip, "Two"]]}})
        w.script(("list", "Best that Photos plays"))
        w.share(VIDEO)
        _, prompt, options = w.seen("list")[0][:3]
        self.assertEqual(prompt, "Set\n\n2 items. One choice applies to all.")
        self.assertEqual(options, ["⬇️ Best available · converts if needed", "⬇️ Best that Photos plays"])
        self.assertEqual(len(w.photos), 2)

    def test_cancelling_the_choice_downloads_nothing(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario(self.many_versions())
        w.script(("list", None))
        w.share(VIDEO)
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual(w.photos, [])

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_a_file_photos_cannot_play_asks_before_converting(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": "Old clip"},
                                  "files": [["abc.webm", self.webm, "Old clip"]]}})
        w.script(("menu", "Convert"))
        w.share(VIDEO)
        prompt, items = w.seen("menu")[0][1:3]
        lines = prompt.split("\n")
        self.assertEqual(lines[:4], ["Old clip", "", "Photos cannot play this video.", ""])
        self.assertRegex(lines[4], r"^Source: 120p VP[89] · [0-9.]+ (KB|bytes)$")
        self.assertRegex(lines[5], r"^Converted: 120p (HEVC|H\.264)$")
        self.assertEqual(len(lines), 6)
        self.assertEqual(items, ["🎞️ Convert", "📁 Keep in Files"])
        self.assertEqual(self.helper_commands(w), ["run", "finish"])
        self.assertEqual(w.helper_runs[1][1]["decision"], "convert")
        self.assertEqual([p[0] for p in w.photos], ["001.mp4"])
        title, text = self.notifications(w)[0]
        self.assertEqual(title, "Old clip")
        self.assertRegex(text, r"^Saved to the Clips album\.\n1 converted \(VP[89] → (HEVC|H\.264)\)\.$")

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_keeping_the_original_puts_it_in_files(self):
        w = self.world
        w.install(ADVANCED)
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": "Old clip"},
                                  "files": [["abc.webm", self.webm, "Old clip"]]}})
        w.script(("menu", "Keep in Files"))
        w.share(VIDEO)
        self.assertEqual(w.helper_runs[1][1]["decision"], "keep")
        self.assertEqual(w.photos, [])
        self.assertEqual(len(w.kept_files()), 1)
        self.assertEqual(self.notifications(w), [("Old clip", "Nothing was added to Photos.\n"
                                                  "1 kept in Files (a-Shell, UMDL, Saved).")])

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_simple_mode_converts_without_asking_and_says_so(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": "Old clip"},
                                  "files": [["abc.webm", self.webm, "Old clip"]]}})
        w.share(VIDEO)
        self.assertEqual(w.seen("menu"), [])
        self.assertEqual(self.helper_commands(w), ["run"])
        self.assertEqual([p[0] for p in w.photos], ["001.mp4"])
        self.assertIn("1 converted (VP", self.notifications(w)[0][1])

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_simple_mode_set_to_never_convert_keeps_the_original(self):
        w = self.world
        w.install(dict(CONFIG, convert="never"))
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": "Old clip"},
                                  "files": [["abc.webm", self.webm, "Old clip"]]}})
        w.share(VIDEO)
        self.assertEqual(w.photos, [])
        self.assertEqual(len(w.kept_files()), 1)

    def test_simple_mode_applies_the_saved_limits_without_asking(self):
        w = self.world
        w.install(dict(CONFIG, res="720", fps="30"))
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual(w.seen("list"), [])
        self.assertEqual(w.recorded_options()[-1]["format_sort"], ["res:720", "fps:30"])
        self.assertEqual(len(w.photos), 1)

    def test_best_quality_conversion_asks_the_site_for_its_best_version(self):
        w = self.world
        w.install(dict(CONFIG, convert="best"))
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual(w.recorded_options()[-1]["format"], "bv*+ba/b/ba")


class LargeDownloads(Flow):
    """docs/BEHAVIOR.md, "Large downloads"."""

    def big_playlist(self):
        files = [["v%d.mp4" % i, self.clip, "Video %d" % i] for i in range(12)]
        return {"ytdlp": {"raw": {"_type": "playlist", "title": "Mix", "playlist_count": 37,
                                  "entries": []}, "files": files},
                "gallery": {"found": False}}

    def test_more_than_ten_items_asks_then_limits(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.big_playlist())
        w.script(("menu", "First 10"))
        w.share("https://video.test/playlist/1")
        menu = w.seen("menu")[0]
        self.assertEqual(menu[1], "Mix\n\n37 items.")
        self.assertEqual(menu[2], ["⬇️ Download all", "⬇️ First 10",
                                   "⬇️ First only", "Cancel"])
        self.assertEqual([(c, p["mode"], p["limit"]) for c, p in w.helper_runs],
                         [("run", "auto", ""), ("run", "limit", "10")])
        self.assertEqual(len(w.photos), 10)
        self.assertEqual(self.notifications(w)[0], ("Mix", "Saved 10 items to the Clips album."))

    def test_download_all_first_only_and_cancel(self):
        for choice, mode, saved in (("Download all", "all", 12),
                                    ("First only", "first", 1),
                                    ("Cancel", None, 0)):
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.big_playlist())
            w.script(("menu", choice))
            w.share("https://video.test/playlist/1")
            self.assertEqual(len(w.photos), saved, choice)
            self.assertEqual(len(w.helper_runs), 2 if mode else 1, choice)
            if mode:
                self.assertEqual(w.helper_runs[1][1]["mode"], mode)

    def test_threshold_setting_is_respected(self):
        w = self.world
        w.install(dict(CONFIG, threshold="50"))
        w.set_scenario(self.big_playlist())
        w.share("https://video.test/playlist/1")  # 37 items, limit 50: no question
        self.assertEqual(len(w.photos), 12)

    def test_unknown_size_says_more_than(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": False},
                        "gallery": {"found": True, "count": 40, "sample": self.jpg}})
        w.script(("menu", "Cancel"))
        w.share("https://x.com/someone/media")
        self.assertEqual(w.seen("menu")[0][1], "More than 10 items.")


class Errors(Flow):
    """docs/BEHAVIOR.md, "When a download fails"."""

    @staticmethod
    def failing(message):
        return {"ytdlp": {"error": message}, "gallery": {"found": False}}

    def test_error_menu_explains_and_cancels(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Sign in to confirm your age"))
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        menu = w.seen("menu")[0]
        self.assertEqual(menu[1], "Download failed\n\nSign in to confirm your age\n\n"
                                  "Sign in to the site, then try again.")
        self.assertEqual(menu[2], ["🔄 Try again", "🛠️ Update tools and retry",
                                   "🔑 Sign in", "📋 Copy details", "Cancel"])
        self.assertEqual(w.photos, [])

    def test_each_kind_of_failure_gets_its_own_advice(self):
        cases = {
            "HTTP Error 500": "Updating the tools fixes most failures.",
            "getaddrinfo failed": "Check the connection.",
            "Video unavailable": "The post may be private, removed or region-locked.",
            "This video is DRM protected": "Copy-protected media cannot be downloaded.",
            "Unsupported URL": "This site may not be supported.",
        }
        for message, advice in cases.items():
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.failing(message))
            w.script(("menu", "Cancel"))
            w.share(VIDEO)
            self.assertTrue(w.seen("menu")[0][1].endswith(advice), message)

    def test_a_block_while_signed_in_is_not_blamed_on_the_account(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".reddit.com", "reddit_session")])
        blocked = "\"You've been blocked by network security.\""
        w.set_scenario({"ytdlp": {"suitable": True, "error": "HTTP Error 403: Blocked"},
                        "gallery": {"found": True, "blocked_unless_api": blocked,
                                    "api_fail": "\"403: Blocked\""}})
        w.script(("menu", "Cancel"))
        w.share("https://www.reddit.com/r/pics/s/AbCdEfGhIj")
        prompt = w.seen("menu")[0][1]
        self.assertIn("Reddit refused this device or network: " + blocked, prompt)
        self.assertIn("Being signed in did not help.", prompt)
        self.assertNotIn("Sign in to the site", prompt)
        # Not signed in: the usual advice stands.
        w = self.new_world()
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": True, "error": "HTTP Error 403: Blocked"},
                        "gallery": {"found": True, "blocked_unless_api": blocked,
                                    "api_fail": "\"403: Blocked\""}})
        w.script(("menu", "Cancel"))
        w.share("https://www.reddit.com/r/pics/s/AbCdEfGhIj")
        self.assertTrue(w.seen("menu")[0][1].endswith("Sign in to the site, then try again."))

    def test_try_again_succeeds_once_the_site_recovers(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("HTTP Error 500"))
        w.script(("menu", "Try again"))
        w.run(VIDEO)
        w.set_scenario(self.one_video())
        w.share(w.callbacks.pop(0))
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(w.helper_runs[1][1]["force_update"], "")

    def test_update_tools_and_try_again(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Unable to extract player response"))
        w.script(("menu", "Update tools and retry"), ("menu", "Cancel"))
        w.share(VIDEO)
        self.assertEqual([p["force_update"] for _, p in w.helper_runs], ["", "1"])
        self.assertEqual(w.pip_log(), [" ".join(TOOLS)] * 2)  # the daily check, then the forced one

    def test_sign_in_from_a_failed_download_opens_that_sites_sign_in_page(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("This post is private; log in"))
        w.set_sign_in([["instagram.com", "sessionid"]])
        w.script(("menu", "Sign in"))
        w.share("https://www.instagram.com/reel/abc/?igsh=1&x=2")
        self.assertEqual(w.seen("browser"), [("browser", "https://www.instagram.com/accounts/login/")])
        self.assertEqual([a[0] for a in self.alerts(w)], ["Sign in", "Signed in to Instagram"])

    def test_error_details_can_be_copied_with_the_log(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Unsupported URL: " + VIDEO))
        w.script(("menu", "Copy details"))
        w.share(VIDEO)
        head, log = w.clipboard.split("\n\nLog\n")
        self.assertEqual(head, "UMDL %s\n%s\nunsupported: Unsupported URL: %s"
                         % (VERSION["shortcut"], VIDEO, VIDEO))
        self.assertIn("mode=auto", log)                     # the helper's own log of that run
        self.assertEqual(self.notifications(w), [("UMDL", "Details copied.")])


class Recovery(Flow):
    """docs/BEHAVIOR.md, "Unsaved and interrupted downloads"."""

    def test_unsaved_download_is_offered_again(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)                 # helper finishes...
        w.callbacks.clear()          # ...but the hand-back to Shortcuts never happens
        self.assertTrue(os.path.exists(os.path.join(w.workspace, "pending")))
        w.script(("menu", "Save now"))
        w.share(None)
        menu = w.seen("menu")[0]
        self.assertEqual(menu[1], "An earlier download was not saved.")
        self.assertEqual(menu[2], ["💾 Save now", "🗑️ Discard"])
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(self.jobs_left(w), [])
        self.assertEqual(self.notifications(w), [("UMDL", "Saved to the Clips album.")])

    def test_unsaved_download_can_be_discarded(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)
        w.callbacks.clear()
        w.script(("menu", "Discard"), ("list", "About UMDL"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.photos, [])
        self.assertEqual(self.jobs_left(w), [])
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "pending")))

    def test_saving_an_earlier_download_then_continues_with_the_new_link(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)
        w.callbacks.clear()
        w.script(("menu", "Save now"))
        w.share("https://video.test/watch/other")
        self.assertEqual(len(w.photos), 2)
        self.assertEqual(w.helper_runs[-1][1]["url"], "https://video.test/watch/other")

    def test_interrupted_download_can_be_resumed_from_the_menu(self):
        w = self.world
        w.install(CONFIG)
        blob = base64.b64encode(json.dumps({
            "v": VERSION["shortcut"], "p": str(VERSION["protocol"]), "name": "UMDL", "url": VIDEO,
            "mode": "limit", "limit": "3", "force_update": "", "cfg": CONFIG}).encode()).decode()
        with open(os.path.join(w.workspace, "last.b64"), "w") as handle:
            handle.write(blob)
        w.set_scenario(self.one_video())
        w.script(("list", "Resume last download"))
        w.share(None)
        self.assertEqual(w.seen("list")[0][2], MAIN_MENU[:2] + ["Resume last download"] + MAIN_MENU[2:])
        self.assertEqual(w.helper_runs[0], ("run", json.loads(base64.b64decode(blob))))
        self.assertEqual(len(w.photos), 1)
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "last.b64")))

    def test_unsaved_download_whose_files_are_gone_is_explained(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)
        w.callbacks.clear()
        shutil.rmtree(os.path.join(w.workspace, "jobs"))
        w.script(("menu", "Save now"))
        w.share(None)
        self.assertEqual(self.alerts(w)[0][0], "Nothing to save")
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "pending")))
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share(None)                                       # and it is not offered again
        offers = [m for m in w.seen("menu") if "was not saved" in m[1]]
        self.assertEqual(len(offers), 1)

    def test_damaged_settings_file_restarts_setup_instead_of_failing(self):
        w = self.world
        w.install()
        with open(os.path.join(w.workspace, "config.b64"), "w") as handle:
            handle.write("bm90IGpzb24gYXQgYWxs\n")
        w.script(("menu", "Not now"))
        w.share(VIDEO)
        self.assertIn("Welcome to UMDL", w.seen("menu")[0][1])


class MainMenu(Flow):
    """docs/BEHAVIOR.md, "Opening UMDL from the Shortcuts app"."""

    def test_opening_from_the_app_goes_straight_to_the_main_menu(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.events[0][0], "list")            # nothing is shown before the menu
        kind, prompt, names, _, details = w.seen("list")[0]
        self.assertEqual((prompt, names), ("UMDL", MAIN_MENU))
        self.assertEqual(details, [
            "The link you copied", "Type or paste", "Album, quality, mode", "For private posts",
            "Sign-ins, versions, log", "Latest yt-dlp and gallery-dl",
            "Version %s" % VERSION["shortcut"]])
        self.assertEqual(w.helper_runs, [])
        self.assertEqual(self.alerts(w), [])

    def test_download_from_clipboard(self):
        w = self.world
        w.install(CONFIG)
        w.clipboard = "check " + VIDEO
        w.set_scenario(self.one_video())
        w.script(("list", "Download from clipboard"))
        w.share(None)
        self.assertEqual(w.helper_runs[0][1]["url"], VIDEO)
        self.assertEqual(len(w.photos), 1)

    def test_clipboard_without_a_link_is_explained(self):
        for clipboard in ("nothing useful", ""):
            w = self.new_world()
            w.install(CONFIG)
            w.clipboard = clipboard
            w.script(("list", "Download from clipboard"))
            w.share(None)
            self.assertEqual(self.alerts(w)[0][0], "No link", repr(clipboard))
            self.assertEqual(w.helper_runs, [])

    def test_enter_a_link(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.script(("list", "Enter a link"), ("ask", VIDEO))
        w.share(None)
        self.assertEqual(len(w.photos), 1)

    def test_entering_something_that_is_not_a_link(self):
        for typed in ("not a link", ""):
            w = self.new_world()
            w.install(CONFIG)
            w.script(("list", "Enter a link"), ("ask", typed))
            w.share(None)
            self.assertEqual(self.alerts(w)[0], ("No link", "That is not a web link."))
            self.assertEqual(w.helper_runs, [])

    def test_sign_in_is_confirmed_once_the_site_has_stored_it(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([[".reddit.com", "reddit_session"], [".reddit.com", "csv"]])
        w.script(("list", "Sign in to a site"), ("menu", "Reddit"))
        w.share(None)
        self.assertEqual(w.seen("menu")[0][2], ["Instagram", "X (Twitter)", "Reddit", "TikTok",
                                                "Facebook", "Another site"])
        self.assertEqual(self.helper_commands(w), ["signin"])
        self.assertEqual(w.seen("browser"), [("browser", "https://www.reddit.com/login/")])
        first, second = self.alerts(w)
        self.assertEqual(first[0], "Sign in")
        self.assertIn("UMDL returns here once the sign-in is saved", first[1])
        self.assertEqual(second, ("Signed in to Reddit",
                                  "UMDL will use this sign-in for Reddit links."))

    def test_sign_in_that_was_not_completed_says_so(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([[".instagram.com", "csrftoken"], [".instagram.com", "mid"]])  # visited only
        w.script(("list", "Sign in to a site"), ("menu", "Instagram"))
        w.share(None)
        title, body = self.alerts(w)[-1]
        self.assertEqual(title, "Sign-in not confirmed")
        self.assertIn("Status shows whether it was saved", body)

    def test_signing_in_again_reports_the_existing_sign_in(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".x.com", "auth_token")])
        w.script(("list", "Sign in to a site"), ("menu", "X (Twitter)"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Already signed in to X (Twitter)")
        self.assertEqual(w.seen("browser"), [])              # the page is not opened again

    def test_sign_in_to_another_site(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([["forum.example.org", "session_id"]])
        w.script(("list", "Sign in to a site"), ("menu", "Another site"),
                 ("ask", "https://forum.example.org/login?next=/a&b=1"))
        w.share(None)
        self.assertEqual(w.seen("browser"), [("browser", "https://forum.example.org/login?next=/a&b=1")])
        self.assertEqual(self.alerts(w)[-1][0], "Signed in to example.org")

        w.script(("list", "Sign in to a site"), ("menu", "Another site"), ("ask", "not an address"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1], ("Sign in", "That is not a web address."))

    def test_status_shows_sign_ins_versions_and_storage(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".instagram.com", "sessionid"), (".reddit.com", "reddit_session", 1000),
                       ("forum.example.org", "session_id"), (".tiktok.com", "tt_webid")])
        w.script(("list", "Status"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(self.helper_commands(w), ["status"])
        title, body = self.alerts(w)[0]
        self.assertEqual(title, "Status")
        lines = body.split("\n")
        self.assertEqual(lines[0], "UMDL %s, helper %s" % (VERSION["shortcut"], VERSION["helper"]))
        self.assertIn("yt-dlp 2099.01.01-fake", lines)
        self.assertIn("Instagram: signed in", lines)
        self.assertIn("Reddit: not signed in", lines)       # that cookie expired long ago
        self.assertIn("TikTok: not signed in", lines)       # visited, never signed in
        self.assertIn("Other sites that may be signed in: example.org", lines)
        self.assertIn("Unsaved download: none", lines)
        self.assertIn("Download tools: ready", lines)
        self.assertIn("Last download: none yet", lines)
        self.assertEqual(w.seen("menu")[0][2], ["📋 Copy", "Done"])
        self.assertEqual(w.clipboard, "")

    def test_status_and_log_can_be_copied(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"error": "HTTP Error 500"}, "gallery": {"found": False}})
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        w.script(("list", "Status"), ("menu", "Copy"))
        w.share(None)
        status, log = w.clipboard.split("\n\nLog\n")
        self.assertIn("No sign-ins are stored.", status)
        self.assertRegex(status, r"Last download: \d\d \w+ \d\d:\d\d, failed \(unknown\)")
        self.assertIn("HTTP Error 500", log)
        self.assertEqual(self.notifications(w)[-1], ("UMDL", "Status and log copied."))

    def test_copying_status_before_any_download_does_not_fail(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Status"), ("menu", "Copy"))
        w.share(None)                                       # there is no log file yet
        self.assertIn("UMDL %s" % VERSION["shortcut"], w.clipboard)

    def test_update_tools_reports_back(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Update tools"))
        w.share(None)
        self.assertEqual(self.helper_commands(w), ["update"])
        title, body = self.alerts(w)[-1]
        self.assertEqual(title, "Download tools updated")
        self.assertIn("yt-dlp  2099.01.01-fake", body)

    def test_about_project_page_and_done(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About UMDL"), ("menu", "Project page"))
        w.share(None)
        about = w.seen("menu")[0]
        self.assertTrue(about[1].startswith("UMDL %s\n" % VERSION["shortcut"]))
        self.assertEqual(about[2], ["🔄 Check for updates", "🌐 Project page", "Done"])
        self.assertEqual(w.seen("openurl")[-1][1], "https://github.com/TheKfcBandit/UMDL")
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.helper_runs, [])

    def test_check_for_new_version(self):
        w = self.world
        w.install(CONFIG)
        w.set_version_json(VERSION)
        w.script(("list", "About UMDL"), ("menu", "Check for updates"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Up to date")

        w.set_version_json(dict(VERSION, shortcut="9.9.9", notes="Faster."))
        w.script(("list", "About UMDL"), ("menu", "Check for updates"),
                 ("menu", "Get the update"))
        w.share(None)
        self.assertEqual(w.seen("menu")[-1][1], "UMDL 9.9.9 is available. Installed: "
                                                "%s.\n\nFaster." % VERSION["shortcut"])
        self.assertEqual(w.seen("openurl")[-1][1], VERSION["url"])

        w.set_offline(True)
        w.script(("list", "About UMDL"), ("menu", "Check for updates"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Update check")


class Settings(Flow):
    """docs/BEHAVIOR.md, "Settings"."""

    def open_settings(self, world, *answers):
        world.script(("list", "Settings"), *answers)
        world.share(None)

    def test_one_list_shows_every_setting_with_its_value(self):
        w = self.world
        w.install(dict(CONFIG, album="Recents", convert="never", after="photos", threshold="25",
                       mode="advanced", res="1080", fps="30"))
        self.open_settings(w, ("list", "Done"))
        _, prompt, names, _, details = w.seen("list")[1]
        self.assertEqual((prompt, names), ("Settings", SETTINGS_MENU))
        self.assertEqual(details, ["Library only", "Advanced · asks each time", "Up to 1080p",
                                   "Up to 30 fps", "Never", "Ask above 25 items", "Open Photos",
                                   "Sign out, or remove everything", "Close settings"])
        self.assertEqual(self.notifications(w), [])          # nothing changed, nothing to announce
        self.assertEqual(w.helper_runs, [])

    def test_defaults_read_plainly(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Done"))
        self.assertEqual(w.seen("list")[1][4][:7], [
            "Clips", "Simple · uses these settings", "Best available", "Best available",
            "Only when needed", "Ask above 10 items", "Show a notification"])

    def test_the_list_stays_open_and_each_change_is_saved_at_once(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Resolution"), ("menu", "1440p"),
                           ("list", "Frame rate"), ("menu", "60 fps"),
                           ("list", "Conversion"), ("menu", "For best quality"),
                           ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, res="1440", fps="60", convert="best"))
        self.assertEqual(len(w.seen("list")), 5)             # main menu, then the list four times
        self.assertEqual(w.seen("list")[4][4][2:5], ["Up to 1440p", "Up to 60 fps", "For best quality"])
        self.assertEqual(self.notifications(w), [("UMDL", "Settings saved.")])
        self.assertEqual(w.helper_runs, [])                  # settings never open a-Shell

    def test_resolution_and_frame_rate_choices(self):
        w = self.world
        w.install(dict(CONFIG, res="720", fps="30"))
        self.open_settings(w, ("list", "Resolution"), ("menu", "Best available"),
                           ("list", "Frame rate"), ("menu", "Best available"), ("list", "Done"))
        menus = w.seen("menu")
        self.assertEqual(menus[0][1:3], ("Highest resolution", ["Best available", "2160p (4K)", "1440p",
                                                                 "1080p", "720p", "480p"]))
        self.assertEqual(menus[1][1:3], ("Highest frame rate", ["Best available", "60 fps", "30 fps"]))
        self.assertEqual(w.read_config(), CONFIG)

    def test_two_value_rows_switch_when_tapped(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Mode"), ("list", "When finished"), ("list", "Done"))
        self.assertEqual(w.seen("menu"), [])                 # no menu in between
        self.assertEqual(w.read_config(), dict(CONFIG, mode="advanced", after="photos"))
        self.open_settings(w, ("list", "Mode"), ("list", "When finished"), ("list", "Done"))
        self.assertEqual(w.read_config(), CONFIG)

    def test_conversion_choices_are_explained_in_one_menu(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Conversion"), ("menu", "Never"), ("list", "Done"))
        prompt, items = w.seen("menu")[0][1:3]
        self.assertTrue(prompt.startswith("Convert for Photos\n\nOnly when needed:"))
        self.assertEqual(items, ["Only when needed", "For best quality", "Never"])
        self.assertEqual(w.read_config(), dict(CONFIG, convert="never"))

    def test_change_album(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Album"), ("menu", "Existing album"), ("ask", "Holiday"),
                           ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, album="Holiday"))
        self.assertEqual(w.albums, [])
        self.assertEqual(w.seen("ask")[0][2], "Clips")       # the current name is offered

    def test_change_threshold(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Large downloads"), ("ask", "25"), ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, threshold="25"))
        self.assertEqual(w.seen("ask")[0][2], "10")         # the current value is offered

    def test_a_bad_threshold_is_refused_and_the_list_returns(self):
        for bad in ("0", "abc", "12.5", "-3", ""):
            w = self.new_world()
            w.install(CONFIG)
            self.open_settings(w, ("list", "Large downloads"), ("ask", bad), ("list", "Done"))
            self.assertEqual(w.read_config(), CONFIG, bad)
            self.assertEqual(self.alerts(w)[0], ("Not saved", "Enter a whole number from 1 to 9999."), bad)
            self.assertEqual(len(w.seen("list")), 3, bad)    # back in the list after the alert

    def test_settings_saved_before_1_3_are_read_and_upgraded(self):
        w = self.world
        w.install({"album": "Old", "threshold": "7", "convert": "0", "after": "photos"})
        self.open_settings(w, ("list", "Mode"), ("list", "Done"))
        self.assertEqual(w.seen("list")[1][4][:7], [
            "Old", "Simple · uses these settings", "Best available", "Best available", "Never",
            "Ask above 7 items", "Open Photos"])
        self.assertEqual(w.read_config(), {"album": "Old", "threshold": "7", "after": "photos",
                                           "mode": "advanced", "res": "best", "fps": "best",
                                           "convert": "never"})

    def test_reset_sign_out(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".instagram.com", "sessionid")])
        self.open_settings(w, ("list", "Reset"), ("menu", "Sign out of all sites"))
        prompt, items = w.seen("menu")[0][1:3]
        self.assertTrue(prompt.startswith("Reset\n\nSign out:"))
        self.assertEqual(items, ["🔑 Sign out of all sites", "🗑️ Remove everything", "Cancel"])
        self.assertEqual(self.helper_commands(w), ["logout"])
        self.assertFalse(os.path.exists(w.cookie_store))
        self.assertEqual(self.alerts(w)[-1], ("Signed out", "All saved sign-ins were removed."))
        self.assertEqual(w.read_config(), CONFIG)            # settings are kept

    def test_reset_everything_removes_umdl_the_tools_and_the_sign_ins(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".instagram.com", "sessionid")])
        other = os.path.join(w.home, "Documents", "my-notes.txt")
        with open(other, "w") as handle:
            handle.write("mine")
        self.open_settings(w, ("list", "Reset"), ("menu", "Remove everything"))
        self.assertEqual(self.helper_commands(w), ["reset"])
        self.assertFalse(os.path.exists(w.workspace))
        self.assertFalse(os.path.exists(w.cookie_store))
        self.assertEqual(w.pip_log()[-1], "uninstall " + " ".join(TOOLS))
        self.assertTrue(os.path.exists(other))               # the user's own files stay
        self.assertEqual(self.alerts(w)[-1][0], "UMDL was reset")
        w.script(("menu", "Not now"))
        w.share(None)  # and the next run is a first run again
        self.assertIn("Welcome to UMDL", w.seen("menu")[-1][1])

    def test_reset_can_be_cancelled(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Reset"), ("menu", "Cancel"), ("list", "Done"))
        self.assertTrue(os.path.exists(w.workspace))
        self.assertEqual(w.helper_runs, [])


class Hygiene(Flow):
    def test_every_action_in_the_shortcut_is_modelled(self):
        known = {"gettext", "setvariable", "nothing", "exit", "number", "math", "count",
                 "dictionary", "detect.dictionary", "getvalueforkey", "text.replace", "text.match",
                 "text.match.getgroup", "base64encode", "detect.link", "getitemfromlist",
                 "geturlcomponent", "setitemname", "choosefromlist", "ask", "alert",
                 "notification", "openurl", "setclipboard", "delay", "openapp",
                 "photos.createalbum", "savetocameraroll", "conditional", "choosefrommenu",
                 "repeat.each", "repeat.count"}
        known = {PREFIX + k for k in known} | {ASHELL + "ExecuteCommandIntent",
                                               ASHELL + "GetFileIntent"}
        used = {a["WFWorkflowActionIdentifier"] for a in self.world.plist["WFWorkflowActions"]}
        self.assertEqual(used - known, set())

    def test_no_condition_relies_on_has_any_value(self):
        # An empty text counts as a value on a real device, so these conditions
        # (codes 100 and 101) silently take the wrong branch. See src/UMDL.cherri.
        offenders = [i for i, a in enumerate(self.world.plist["WFWorkflowActions"])
                     if a["WFWorkflowActionIdentifier"] == PREFIX + "conditional"
                     and a["WFWorkflowActionParameters"].get("WFCondition") in (100, 101)]
        self.assertEqual(offenders, [])

    def test_get_file_always_asks_for_a_copy(self):
        # Without it the action stops the shortcut on iOS 27.2, with no message.
        # https://github.com/holzschu/a-shell/issues/1138
        actions = [a["WFWorkflowActionParameters"] for a in self.world.plist["WFWorkflowActions"]
                   if a["WFWorkflowActionIdentifier"] == ASHELL + "GetFileIntent"]
        self.assertTrue(actions)
        self.assertTrue(all(p.get("copyFile") is True for p in actions))

    def test_background_commands_survive_a_failing_command(self):
        # a-Shell fails the action, and Shortcuts the whole run, when a background
        # command exits with an error and "keepGoing" is off.
        actions = [a["WFWorkflowActionParameters"] for a in self.world.plist["WFWorkflowActions"]
                   if a["WFWorkflowActionIdentifier"] == ASHELL + "ExecuteCommandIntent"]
        background = [p for p in actions if p.get("openWindow") == "close"]
        self.assertGreater(len(background), 8)
        self.assertTrue(all(p.get("keepGoing") is True for p in background))

    def test_shortcut_metadata(self):
        plist = self.world.plist
        self.assertEqual(plist["WFWorkflowTypes"], ["ActionExtension"])
        self.assertEqual(sorted(plist["WFWorkflowInputContentItemClasses"]),
                         ["WFStringContentItem", "WFURLContentItem"])
        self.assertTrue(plist["WFWorkflowIcon"]["WFWorkflowIconGlyphNumber"])

    def test_unscripted_question_fails_loudly(self):
        with self.assertRaises(SimError):
            self.world.share(VIDEO)  # not set up, so the welcome menu appears unannounced


del Flow  # only the subclasses hold tests

if __name__ == "__main__":
    unittest.main()

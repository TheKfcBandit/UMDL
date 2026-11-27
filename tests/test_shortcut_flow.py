"""End-to-end flows: the compiled shortcut and the real helper, together.

Each test class covers one section of docs/BEHAVIOR.md, and each test names
the behaviour it pins down. Needs the compiled plist. From the repository root:

    cherri src/UMDL.cherri --skip-sign --debug     # writes src/UMDL.plist
    python -m unittest discover -s tests -v

Set UMDL_PLIST to point somewhere else. See tests/shortcut_sim.py for what
the simulator does and does not prove.
"""

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import reddit_pages  # noqa: E402
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
CONFIG = {"album": "Clips", "dest": "photos", "convert": "ask", "threshold": "10", "after": "notify",
          "res": "best", "fps": "best"}
DEFAULTS = dict(CONFIG, album="UMDL")
VIDEO = "https://video.test/watch/abc"
TOOLS = ["yt-dlp", "gallery-dl", "yt-dlp-ejs", "yt-dlp-apple-webkit-jsi"]
# First run: the shortcut installs the two required tools in the a-Shell window,
# then the helper's first daily check brings everything up to date.
FIRST_RUN_PIP = ["yt-dlp gallery-dl", " ".join(TOOLS)]
MAIN_MENU = ["Download", "Settings", "Sign in",
             "Status", "Update tools", "About"]
SETTINGS_MENU = ["Save to", "Resolution", "Frame rate", "Conversion", "Large downloads",
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
        self.assertEqual(w.photos, [("My clip.mp4", "UMDL", os.path.getsize(self.clip))])
        self.assertEqual(self.notifications(w), [("My clip", "Saved to UMDL.")])
        self.assertEqual(self.alerts(w), [])
        self.assertEqual(self.jobs_left(w), [])

    def test_quick_setup_opened_from_the_app_installs_and_reports_ready(self):
        w = self.world
        w.script(("menu", "Quick setup"))
        w.share(None)
        self.assertEqual(self.helper_commands(w), ["setup"])
        self.assertEqual(w.pip_log(), FIRST_RUN_PIP)
        self.assertEqual([a[0] for a in self.alerts(w)], ["Ready"])
        self.assertEqual(len(w.seen("menu")), 1)
        self.assertEqual(w.seen("list"), [])               # the main menu is not shown during setup
        self.assertEqual(w.photos, [])

    def test_custom_setup_is_the_settings_list_then_the_same_install(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.script(("menu", "Custom setup"),
                 ("list", "Save to"), ("menu", "Album"), ("ask", "Clips"),
                 ("list", "Resolution"), ("menu", "1080p"),
                 ("list", "Frame rate"), ("menu", "30 fps"),
                 ("list", "Done"))
        w.share(VIDEO)
        first = w.seen("list")[0]
        self.assertEqual(first[1], "Settings")
        self.assertEqual(first[2], [row for row in SETTINGS_MENU if row != "Reset"])   # nothing to reset yet
        self.assertEqual(first[4][-1], "Install")
        self.assertEqual(w.seen("menu")[1][1:3], ("Save to", ["🖼️ Album", "📚 Library", "📁 Files"]))
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
        self.assertEqual(self.helper_commands(w), ["setup"])

    def test_custom_setup_with_an_existing_album_or_none(self):
        w = self.world
        w.script(("menu", "Custom setup"), ("list", "Save to"), ("menu", "Album"),
                 ("ask", "Holiday"), ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config(), dict(DEFAULTS, album="Holiday"))

        w = self.new_world()
        w.script(("menu", "Custom setup"), ("list", "Save to"), ("menu", "Library"), ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config(), dict(DEFAULTS, album="Recents"))

    def test_an_empty_album_name_falls_back(self):
        w = self.world
        w.script(("menu", "Custom setup"), ("list", "Save to"), ("menu", "Album"), ("ask", ""),
                 ("list", "Done"))
        w.share(None)
        self.assertEqual(w.read_config()["album"], "UMDL")

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
        self.assertEqual(self.alerts(w), [("Setup incomplete", "Helper download failed. "
                                           "Check the connection and run UMDL again.")])
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
        self.assertEqual(w.photos, [("My clip.mp4", "Clips", os.path.getsize(self.clip))])
        self.assertEqual(w.seen("menu") + w.seen("list") + w.seen("alert"), [])
        payload = w.helper_runs[0][1]
        self.assertEqual((payload["mode"], payload["name"], payload["cfg"]), ("auto", "UMDL", CONFIG))
        self.assertEqual((payload["v"], payload["p"]), (VERSION["shortcut"], str(VERSION["protocol"])))
        self.assertEqual(self.foreground_commands(w)[0].split("\n")[0], "cd $HOME/Documents/UMDL")
        with open(w.record_path) as handle:
            opts = [json.loads(line) for line in handle]
        self.assertTrue(all(o["format"] == "bv*+ba/b/ba" for o in opts))     # the best there is

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
        w.script(("list", "About"), ("menu", "Done"))
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
        self.assertEqual(self.notifications(w)[0][1], "Saved to %s." % album)
        self.assertEqual(w.helper_runs[0][1]["cfg"]["album"], album)

    def test_gallery_post_saves_every_image(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": True, "error": "No video could be found"},
                        "gallery": {"found": True, "count": 4, "sample": self.jpg}})
        w.share("https://x.com/someone/status/123")
        self.assertEqual([p[0] for p in w.photos], ["pic 0.jpg", "pic 1.jpg", "pic 2.jpg", "pic 3.jpg"])
        self.assertEqual(self.notifications(w)[0][1], "4 saved to Clips.")

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
                         "Not saved to Photos.\n"
                         "1 kept in Files.")
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
                         ("Set", "2 saved to Clips.\n1 failed."))

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
        w.script(("menu", "Update"))
        w.share(VIDEO)
        self.assertEqual(len(w.photos), 1)
        prompt = w.seen("menu")[0][1]
        self.assertEqual(prompt, "UMDL 9.9.9 available\n\nInstalled: %s"
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
        w.script(("list", "About"), ("menu", "Done"))
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
        w.script(("menu", "Update"))
        w.share(VIDEO)
        self.assertIn("out of date", w.seen("menu")[0][1])
        self.assertEqual(w.seen("openurl")[0][1], VERSION["url"])


@unittest.skipUnless(shutil.which("node"), "needs Node.js to stand in for a-Shell's browser")
class RedditThroughTheBrowser(Flow):
    """docs/BEHAVIOR.md, "Reddit". Reddit shows a post only to a browser, so
    the post is opened in a-Shell's and read off the page."""

    SHARE = "https://www.reddit.com/r/me_irl/s/cUdJnFfPwD"
    HOME_PAGE = "https://localhost:8443/wasm.html"

    def reddit(self, browser, **ytdlp):
        # The tools would be refused if they were asked about the post itself.
        scenario = {"ytdlp": dict({"suitable": True, "error": "HTTP Error 403: Blocked"}, **ytdlp),
                    "gallery": {"found": True, "sample": self.jpg}}
        if browser is not None:
            scenario["browser"] = browser
        return scenario

    def test_photo_post_is_saved_with_no_question(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.gallery(3)}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 3)
        self.assertEqual(w.seen("menu") + w.seen("alert"), [])
        self.assertEqual(self.notifications(w), [("Holiday photos", "3 saved to Clips.")])
        # The browser went to Reddit, then to the post as a link within the site, and was put back.
        self.assertEqual(w.browser_visits(), ["https://www.reddit.com/robots.txt", self.SHARE])
        self.assertEqual(w.browser_page(), self.HOME_PAGE)
        # The originals were fetched, not the resized previews, and nothing from the comments.
        self.assertEqual(w.direct_links(), [["https://i.redd.it/img00.jpg", "https://i.redd.it/img01.jpg",
                                             "https://i.redd.it/img02.jpg"]])
        self.assertIn("Reading post", w.helper_output)
        self.assertNotIn("Reading link", w.helper_output)    # the tools were never asked about the post

    def test_single_image_is_fetched_once(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.IMAGE}))
        w.share("https://www.reddit.com/r/me_irl/comments/1abcde/a_picture/?utm_source=share")
        self.assertEqual(w.direct_links(), [["https://i.redd.it/qyvi7xrehmwh1.jpeg"]])
        self.assertEqual(w.browser_visits()[-1], "https://www.reddit.com/r/me_irl/comments/1abcde/a_picture/")
        self.assertEqual(self.notifications(w), [("A picture", "Saved to Clips.")])

    def test_video_post_goes_to_yt_dlp_with_its_manifest(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.VIDEO}, urls={"v.redd.it/abc123/DASHPlaylist.mpd": {
            "raw": {"_type": "video", "id": "DASHPlaylist", "title": "DASHPlaylist"},
            "files": [["DASHPlaylist.mp4", self.clip, "DASHPlaylist"]]}}))
        w.share(self.SHARE)
        self.assertEqual([name for name, _, _ in w.photos], ["Cat falls off shelf.mp4"])
        self.assertEqual(self.notifications(w), [("Cat falls off shelf", "Saved to Clips.")])

    def test_post_that_links_elsewhere_is_downloaded_from_there(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.LINK}, urls={"clips.test": {
            "raw": {"_type": "video", "id": "9", "title": "Nine"},
            "files": [["9.mp4", self.clip, "Nine"]]}}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 1)

    def test_large_gallery_still_asks_first(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.gallery(12)}))
        w.script(("menu", "First 10"))
        w.share(self.SHARE)
        self.assertEqual(w.seen("menu")[0][1], "Holiday photos\n\n12 items")
        self.assertEqual(len(w.photos), 10)

    def test_the_page_is_waited_for_while_reddit_checks_the_browser(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.reddit({"page": reddit_pages.gallery(1), "challenge": 3}))
        w.share(self.SHARE)
        self.assertEqual(len(w.photos), 1)

    def test_browser_is_returned_to_the_page_it_was_showing(self):
        for here, first_stop in (("https://www.instagram.com/accounts/login/", ["https://www.reddit.com/robots.txt"]),
                                 ("https://www.reddit.com/r/me_irl/", [])):     # already on Reddit: no detour
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.reddit({"page": reddit_pages.gallery(1), "start": here}))
            w.share(self.SHARE)
            self.assertEqual(len(w.photos), 1, here)
            self.assertEqual(w.browser_visits(), first_stop + [self.SHARE], here)
            self.assertEqual(w.browser_page(), here)

    def test_a_block_is_reported_as_reddits_and_not_blamed_on_the_account(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".reddit.com", "reddit_session")])
        w.set_scenario(self.reddit({"blocked": True}))
        w.script(("menu", "Cancel"))
        w.share(self.SHARE)
        self.assertEqual(w.seen("menu")[0][1], "Download failed\n\nReddit blocked a-Shell's browser.\n\n"
                                               "Updating tools fixes most failures.")
        self.assertEqual(w.photos, [])
        self.assertEqual(w.browser_page(), self.HOME_PAGE)       # put back all the same

    def test_a_post_reddit_does_not_show_points_to_signing_in_only_when_signed_out(self):
        for cookies, text in (([], "Reddit did not show the post. Sign in to Reddit.\n\nSign in, then retry."),
                              ([(".reddit.com", "reddit_session")],
                               "Reddit did not show the post.\n\nUpdating tools fixes most failures.")):
            w = self.new_world()
            w.install(CONFIG)
            w.set_cookies(cookies)
            w.set_scenario(self.reddit({"silent": True}))
            w.script(("menu", "Cancel"))
            w.share(self.SHARE)
            self.assertEqual(w.seen("menu")[0][1], "Download failed\n\n" + text)

    def test_post_without_media_and_a_browser_that_never_answers(self):
        for browser, said in (({"page": reddit_pages.TEXT}, "No photo or video in this post."),
                              (None, "a-Shell's browser did not answer")):
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.reddit(browser))
            w.script(("menu", "Cancel"))
            w.share(self.SHARE)
            self.assertIn("Download failed\n\n" + said, w.seen("menu")[0][1])
            self.assertEqual(w.photos, [])

    def test_other_sites_never_involve_the_browser(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"error": "HTTP Error 403: Blocked"}, "gallery": {"found": False},
                        "browser": {"page": reddit_pages.gallery(1)}})
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        self.assertEqual(w.browser_visits(), [])


MANY = [
    {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "width": 640,
     "height": 360, "fps": 30, "tbr": 500},
    {"format_id": "401", "vcodec": "av01.0.13M.08", "acodec": "none", "width": 3840,
     "height": 2160, "fps": 60, "tbr": 21000},
    {"format_id": "315", "vcodec": "vp09.00.51.08", "acodec": "none", "width": 3840,
     "height": 2160, "fps": 60, "tbr": 26000},
    {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129},
]


class WithVersions(Flow):
    def many_versions(self, **more):
        scenario = self.one_video()
        scenario["ytdlp"]["formats"] = MANY
        scenario["ytdlp"].update(more)
        return scenario

    def old_clip(self):
        """A site whose only version is one Photos cannot play."""
        return {"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": "Old clip"},
                          "files": [["abc.webm", self.webm, "Old clip"]]}}

    @staticmethod
    def log_of(world):
        with open(os.path.join(world.workspace, "last.log"), encoding="utf-8") as handle:
            return handle.read()


class Quality(WithVersions):
    """docs/BEHAVIOR.md, "Which version is downloaded"."""

    def test_the_best_version_is_taken_and_nothing_is_asked(self):
        w = self.world
        w.install(dict(CONFIG, convert="yes"))
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual(w.seen("list") + w.seen("menu"), [])
        asked = w.recorded_options()[-1]
        self.assertEqual(asked["format"], "315+140/bv*+ba/b/ba")     # the 4K one, with the AAC sound
        self.assertEqual(asked["format_sort"], ["lang", "res", "fps", "vcodec:h265", "acodec:aac"])
        self.assertEqual(len(w.photos), 1)

    def test_av1_is_taken_in_place_of_vp9_where_the_chip_reads_it(self):
        w = self.world
        w.install(dict(CONFIG, convert="yes"))
        w.extra_env["UMDL_TEST_HARDWARE"] = "av01"
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual(w.recorded_options()[-1]["format"], "401+140/bv*+ba/b/ba")   # the same size and rate
        w.script(("list", "Status"), ("menu", "Done"))
        w.share(None)
        self.assertIn("AV1: preferred over VP9", self.alerts(w)[-1][1].split("\n"))

    def test_each_limit_works_on_its_own(self):
        expected = {
            ("1080", "best"): ("bv*+ba/b/ba", "res:1080", "fps"),
            ("best", "30"): ("bv*[fps<=?30]+ba/b[fps<=?30]/bv*+ba/b/ba", "res", "fps:30"),
            ("720", "60"): ("bv*[fps<=?60]+ba/b[fps<=?60]/bv*+ba/b/ba", "res:720", "fps:60"),
        }
        for (res, fps), (fmt, res_field, fps_field) in expected.items():
            w = self.new_world()
            w.install(dict(CONFIG, res=res, fps=fps, convert="yes"))
            w.set_scenario(self.many_versions())
            w.share(VIDEO)
            asked = w.recorded_options()[-1]
            self.assertTrue(asked["format"].endswith("/" + fmt), (res, fps))
            self.assertEqual(asked["format_sort"][1:3], [res_field, fps_field], (res, fps))
            self.assertEqual(w.seen("list") + w.seen("menu"), [], (res, fps))

    def test_settings_left_over_from_advanced_mode_are_ignored(self):
        w = self.world
        w.install(dict(CONFIG, mode="advanced", convert="off"))     # saved by 1.3 or 1.4
        w.set_scenario(self.many_versions())
        w.script(("menu", "Converted"))
        w.share(VIDEO)
        self.assertEqual(w.seen("list"), [])                         # no list of versions
        self.assertIn("Higher quality available", w.seen("menu")[0][1])   # that "convert" is no preference
        self.assertEqual(len(w.photos), 1)


class HigherQuality(WithVersions):
    """docs/BEHAVIOR.md, "Higher quality available"."""

    def test_the_question_names_both_versions_and_converted_is_one_tap(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.many_versions())
        w.script(("menu", "Converted"))
        w.share(VIDEO)
        _, prompt, items = w.seen("menu")[0][:3]
        self.assertEqual(prompt, "Higher quality available\n\nMy clip")
        self.assertEqual(items, ["🎞️ 2160p60 · Converted", "⚡ 360p · Native", "Cancel"])
        self.assertEqual([(c, p["convert"]) for c, p in w.helper_runs], [("run", ""), ("run", "yes")])
        self.assertEqual(w.recorded_options()[-1]["format"], "315+140/bv*+ba/b/ba")
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(len(w.seen("menu")), 1)                     # asked once
        self.assertIn("reading: kept from before the question", self.log_of(w))   # and the link read once

    def test_native_takes_the_best_photos_plays(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.many_versions())
        w.script(("menu", "Native"))
        w.share(VIDEO)
        self.assertEqual(w.helper_runs[-1][1]["convert"], "no")
        self.assertTrue(w.recorded_options()[-1]["format"].startswith("18/bv*[vcodec~="))
        self.assertEqual(len(w.photos), 1)
        self.assertNotIn("converted", self.notifications(w)[0][1])

    def test_cancel_downloads_nothing(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.many_versions())
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        self.assertEqual((len(w.helper_runs), w.photos, self.notifications(w)), (1, [], []))

    def test_a_preference_in_settings_answers_in_advance(self):
        for convert, first in (("yes", "315+140/"), ("no", "18/")):
            w = self.new_world()
            w.install(dict(CONFIG, convert=convert))
            w.set_scenario(self.many_versions())
            w.share(VIDEO)
            self.assertEqual(w.seen("menu"), [], convert)
            self.assertTrue(w.recorded_options()[-1]["format"].startswith(first), convert)
            self.assertEqual(len(w.photos), 1, convert)

    def test_nothing_is_asked_when_there_is_no_choice(self):
        # The best version needs no converting; or nothing the site has is playable as it is.
        for scenario in (self.one_video(), self.old_clip()):
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(scenario)
            w.share(VIDEO)
            self.assertEqual(w.seen("menu"), [])
            self.assertEqual(len(w.photos), 1)

    def test_a_list_of_many_follows_the_preference_and_never_asks(self):
        w = self.world
        w.install(dict(CONFIG, convert="no"))
        scenario = {"ytdlp": {"raw": {"_type": "playlist", "title": "Pair", "entries": [1, 2]},
                              "files": [["a.mp4", self.clip, "One"], ["b.mp4", self.clip, "Two"]]},
                    "gallery": {"found": False}}
        w.set_scenario(scenario)
        w.share(VIDEO)
        self.assertTrue(w.recorded_options()[-1]["format"].startswith("bv*[vcodec~="))
        w2 = self.new_world()
        w2.install(CONFIG)
        w2.set_scenario(scenario)
        w2.share(VIDEO)
        self.assertEqual(w2.seen("menu"), [])                        # not set: the best, converted if need be
        self.assertEqual(w2.recorded_options()[-1]["format"], "bv*+ba/b/ba")


class ToFiles(WithVersions):
    """docs/BEHAVIOR.md, "Saving to Files"."""

    def test_the_best_version_is_kept_as_downloaded_and_nothing_is_asked(self):
        w = self.world
        w.install(dict(CONFIG, dest="files"))
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual(w.seen("menu"), [])
        self.assertEqual(w.recorded_options()[-1]["format"], "315+140/bv*+ba/b/ba")
        self.assertEqual((w.photos, w.kept_files()), ([], ["My clip.mp4"]))
        self.assertEqual(self.notifications(w), [("My clip", "Saved to Files.")])

    def test_a_format_photos_cannot_play_is_not_converted(self):
        w = self.world
        w.install(dict(CONFIG, dest="files"))
        w.set_scenario(self.old_clip())
        w.share(VIDEO)
        self.assertEqual(w.kept_files(), ["Old clip.webm"])
        self.assertNotIn("converted", self.log_of(w))
        self.assertNotIn("Repacking", w.helper_output)

    def test_several_items(self):
        w = self.world
        w.install(dict(CONFIG, dest="files"))
        w.set_scenario({"ytdlp": {"raw": {"_type": "playlist", "title": "Pair", "entries": [1, 2]},
                                  "files": [["a.mp4", self.clip, "One"], ["b.mp4", self.clip, "Two"]]},
                        "gallery": {"found": False}})
        w.share(VIDEO)
        self.assertEqual(self.notifications(w), [("Pair", "2 saved to Files.")])

    def test_open_when_finished_shows_the_folder_in_files(self):
        w = self.world
        w.install(dict(CONFIG, dest="files", after="photos"))
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        (_, link), = w.seen("openurl")
        self.assertEqual(link, "shareddocuments://" + os.path.join(w.workspace, "Saved"))


class Saving(WithVersions):
    """docs/BEHAVIOR.md, "Saving"."""

    def test_the_helper_saves_it_itself_under_its_title_dated_today(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video("AMD's Gaslighting: Part 2"))
        w.share(VIDEO)
        today = time.strftime("%Y-%m-%d")
        self.assertEqual([entry[:3] for entry in w.library()], [("Clips", "AMD's Gaslighting Part 2.mp4", today)])
        self.assertEqual(self.notifications(w), [("AMD's Gaslighting Part 2", "Saved to Clips.")])
        self.assertEqual(self.jobs_left(w), [])
        self.assertEqual(w.seen("menu") + w.seen("alert"), [])

    def test_no_album_saves_to_the_library(self):
        w = self.world
        w.install(dict(CONFIG, album="Recents"))
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual([entry[:2] for entry in w.library()], [("Library", "My clip.mp4")])
        self.assertEqual(self.notifications(w), [("My clip", "Saved to Photos.")])

    def test_several_items_get_names_that_do_not_collide(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"raw": {"_type": "playlist", "title": "Set", "entries": [
            {"id": "a", "title": "Same"}, {"id": "b", "title": "Same"}]},
            "files": [["a.mp4", self.clip, "Same"], ["b.mp4", self.clip, "Same"]]}})
        w.share(VIDEO)
        self.assertEqual([entry[1] for entry in w.library()], ["Same.mp4", "Same 2.mp4"])
        self.assertEqual(self.notifications(w), [("Set", "2 saved to Clips.")])

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_photos_is_asked_first_and_a_file_it_takes_is_not_converted(self):
        w = self.world
        w.install(CONFIG)
        w.photos_plays("h264", "hevc", "vp9", "vp8")         # a device whose Photos plays VP9
        w.set_scenario(self.old_clip())
        w.share(VIDEO)
        self.assertEqual([entry[1] for entry in w.library()], ["Old clip.mp4"])
        self.assertEqual(self.notifications(w), [("Old clip", "Saved to Clips.")])
        self.assertNotIn("converted", self.log_of(w) if os.path.exists(
            os.path.join(w.workspace, "last.log")) else "")

    @unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
    def test_a_file_photos_refuses_is_converted_and_saved(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.old_clip())
        w.share(VIDEO)
        self.assertEqual([entry[1] for entry in w.library()], ["Old clip.mp4"])
        title, text = self.notifications(w)[0]
        self.assertRegex(text, r"^Saved to Clips\.\nConverted VP[89] → (HEVC|H\.264)\.$")
        log = self.log_of(w)
        self.assertIn("Photos would not take Old clip.mp4 as it is", log)
        self.assertLess(log.index("Photos would not take"), log.index("converted "))    # in that order

    def test_a_video_joined_from_two_files_keeps_its_title(self):
        # The parts arrive as abc.f315.mp4 and abc.f140.mp4; 1.6 named the result "abc".
        w = self.world
        w.install(dict(CONFIG, convert="yes"))
        w.set_scenario(self.many_versions())
        w.share(VIDEO)
        self.assertEqual([name for name, _, _ in w.photos], ["My clip.mp4"])

    def test_a_refused_file_does_not_cost_the_album(self):
        # 1.6 took a refusal of the file for a refusal of the album, and saved
        # the converted file to the library.
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.old_clip())
        w.share(VIDEO)
        self.assertEqual([(name, album) for name, album, _ in w.photos], [("Old clip.mp4", "Clips")])
        self.assertNotIn("the album was refused", self.log_of(w))

    def test_warnings_the_tool_writes_past_its_logger_stay_off_the_screen(self):
        w = self.world
        w.install(CONFIG)
        scenario = self.one_video()
        scenario["ytdlp"]["stray_warning"] = "Unknown codec iamf.001.001.Opus"
        w.set_scenario(scenario)
        w.share(VIDEO)
        self.assertNotIn("Unknown codec", w.helper_output)
        self.assertIn("yt-dlp: WARNING: Unknown codec iamf.001.001.Opus", self.log_of(w))

    def test_when_photos_cannot_be_used_files_are_kept_and_the_reason_given(self):
        w = self.world
        w.install(CONFIG)
        w.refuse_photos()
        w.set_scenario(self.one_video())
        w.share(VIDEO)
        self.assertEqual(w.photos, [])
        self.assertEqual(w.kept_files(), ["My clip.mp4"])
        self.assertEqual(self.notifications(w), [("My clip", "Not saved to Photos.\n"
            "1 kept in Files.\n"
            "a-Shell has no Photos access. Allow it in Settings › a-Shell › Photos.")])

    def test_nothing_ever_travels_through_shortcuts(self):
        actions = {a["WFWorkflowActionIdentifier"] for a in self.world.plist["WFWorkflowActions"]}
        self.assertNotIn(ASHELL + "GetFileIntent", actions)
        self.assertNotIn(PREFIX + "savetocameraroll", actions)

    def test_audio_is_still_kept_in_files(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"raw": {"_type": "video", "id": "s", "title": "Song"},
                                  "files": [["s.m4a", self.song, "Song"]]}})
        w.share(VIDEO)
        self.assertEqual(w.library(), [])
        self.assertEqual(w.kept_files(), ["Song.m4a"])
        self.assertEqual(self.notifications(w), [("Song", "Not saved to Photos.\n"
                                                  "1 kept in Files.")])


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
        self.assertEqual(menu[1], "Mix\n\n37 items")
        self.assertEqual(menu[2], ["⬇️ All", "⬇️ First 10",
                                   "⬇️ First only", "Cancel"])
        self.assertEqual([(c, p["mode"], p["limit"]) for c, p in w.helper_runs],
                         [("run", "auto", ""), ("run", "limit", "10")])
        self.assertEqual(len(w.photos), 10)
        self.assertEqual(self.notifications(w)[0], ("Mix", "10 saved to Clips."))

    def test_download_all_first_only_and_cancel(self):
        for choice, mode, saved in (("All", "all", 12),
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
        self.assertEqual(w.seen("menu")[0][1], "10+ items")


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
                                  "Sign in, then retry.")
        self.assertEqual(menu[2], ["🔄 Retry", "🛠️ Update tools, retry",
                                   "🔑 Sign in", "📋 Copy log", "Cancel"])
        self.assertEqual(w.photos, [])

    def test_each_kind_of_failure_gets_its_own_advice(self):
        cases = {
            "HTTP Error 500": "Updating tools fixes most failures.",
            "getaddrinfo failed": "Check the connection.",
            "Video unavailable": "Private, removed or region-locked.",
            "This video is DRM protected": "Copy-protected.",
            "Unsupported URL": "Site may not be supported.",
        }
        for message, advice in cases.items():
            w = self.new_world()
            w.install(CONFIG)
            w.set_scenario(self.failing(message))
            w.script(("menu", "Cancel"))
            w.share(VIDEO)
            self.assertTrue(w.seen("menu")[0][1].endswith(advice), message)

    def test_try_again_succeeds_once_the_site_recovers(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("HTTP Error 500"))
        w.script(("menu", "Retry"))
        w.run(VIDEO)
        w.set_scenario(self.one_video())
        w.share(w.callbacks.pop(0))
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(w.helper_runs[1][1]["force_update"], "")

    def test_update_tools_and_try_again(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Unable to extract player response"))
        w.script(("menu", "Update tools, retry"), ("menu", "Cancel"))
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
        w.script(("menu", "Copy log"))
        w.share(VIDEO)
        head, log = w.clipboard.split("\n\nLog\n")
        self.assertEqual(head, "UMDL %s\n%s\nunsupported: Unsupported URL: %s"
                         % (VERSION["shortcut"], VIDEO, VIDEO))
        self.assertIn("mode=auto", log)                     # the helper's own log of that run
        self.assertEqual(self.notifications(w), [("UMDL", "Log copied.")])


class Recovery(Flow):
    """docs/BEHAVIOR.md, "Interrupted downloads"."""

    def test_interrupted_download_can_be_resumed_from_the_menu(self):
        w = self.world
        w.install(CONFIG)
        blob = base64.b64encode(json.dumps({
            "v": VERSION["shortcut"], "p": str(VERSION["protocol"]), "name": "UMDL", "url": VIDEO,
            "mode": "limit", "limit": "3", "force_update": "", "cfg": CONFIG}).encode()).decode()
        with open(os.path.join(w.workspace, "last.b64"), "w") as handle:
            handle.write(blob)
        w.set_scenario(self.one_video())
        w.script(("list", "Resume"))
        w.share(None)
        self.assertEqual(w.seen("list")[0][2], MAIN_MENU[:1] + ["Resume"] + MAIN_MENU[1:])
        self.assertEqual(w.helper_runs[0], ("run", json.loads(base64.b64decode(blob))))
        self.assertEqual(len(w.photos), 1)
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "last.b64")))

    def test_a_download_stopped_while_saving_is_finished_without_downloading_again(self):
        w = self.world
        w.install(CONFIG)
        request = {"v": VERSION["shortcut"], "p": str(VERSION["protocol"]), "name": "UMDL", "url": VIDEO,
                   "mode": "auto", "limit": "", "force_update": "", "cfg": CONFIG}
        with open(os.path.join(w.workspace, "last.b64"), "w") as handle:
            handle.write(base64.b64encode(json.dumps(request).encode()).decode())
        # What an interrupted run leaves in a-Shell > UMDL > Working: the file and its job.
        folder = os.path.join(w.workspace, "Working", hashlib.md5(VIDEO.encode()).hexdigest()[:16])
        os.makedirs(os.path.join(folder, "out"))
        waiting = os.path.join(folder, "out", "001-My-clip.mp4")
        shutil.copy(self.one_video()["ytdlp"]["files"][0][1], waiting)
        with open(os.path.join(folder, "job.json"), "w") as handle:
            json.dump({"url": VIDEO, "state": "save", "title": "My clip", "failed": 0, "converted": [],
                       "items": [{"path": waiting, "stem": "My clip", "state": "waiting"}]}, handle)
        w.set_scenario({"ytdlp": {"error": "HTTP Error 500"}, "gallery": {"found": False}})   # no second download
        w.script(("list", "Status"), ("menu", "Done"))
        w.share(None)
        self.assertIn("Unfinished: 1", self.alerts(w)[0][1].split("\n"))
        w.script(("list", "Resume"))
        w.share(None)
        self.assertEqual([(name, album) for name, album, _ in w.photos], [("My clip.mp4", "Clips")])
        self.assertEqual(self.notifications(w), [("My clip", "Saved to Clips.")])
        with open(os.path.join(w.workspace, "last.log"), encoding="utf-8") as handle:
            self.assertIn("carrying on: 1 file already downloaded", handle.read())
        self.assertEqual(os.listdir(os.path.join(w.workspace, "Working")), [])

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
        w.script(("list", "About"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.events[0][0], "list")            # nothing is shown before the menu
        kind, prompt, names, _, details = w.seen("list")[0]
        self.assertEqual((prompt, names), ("UMDL", MAIN_MENU))
        self.assertEqual(details, [
            "From clipboard", "Save to, quality, conversion", "Private posts",
            "Tools, sign-ins, log", "yt-dlp, gallery-dl",
            "Version %s" % VERSION["shortcut"]])
        self.assertEqual(w.helper_runs, [])
        self.assertEqual(self.alerts(w), [])

    def test_download_from_clipboard(self):
        w = self.world
        w.install(CONFIG)
        w.clipboard = "check " + VIDEO
        w.set_scenario(self.one_video())
        w.script(("list", "Download"))
        w.share(None)
        self.assertEqual(w.helper_runs[0][1]["url"], VIDEO)
        self.assertEqual(len(w.photos), 1)

    def test_clipboard_without_a_link_is_explained(self):
        for clipboard in ("nothing useful", ""):
            w = self.new_world()
            w.install(CONFIG)
            w.clipboard = clipboard
            w.script(("list", "Download"))
            w.share(None)
            self.assertEqual(self.alerts(w)[0][0], "No link", repr(clipboard))
            self.assertEqual(w.helper_runs, [])

    def test_sign_in_is_confirmed_once_the_site_has_stored_it(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([[".reddit.com", "reddit_session"], [".reddit.com", "csv"]])
        w.script(("list", "Sign in"), ("menu", "Reddit"))
        w.share(None)
        self.assertEqual(w.seen("menu")[0][2], ["Instagram", "X (Twitter)", "Reddit", "TikTok",
                                                "Facebook", "Another site"])
        self.assertEqual(self.helper_commands(w), ["signin"])
        self.assertEqual(w.seen("browser"), [("browser", "https://www.reddit.com/login/")])
        first, second = self.alerts(w)
        self.assertEqual(first[0], "Sign in")
        self.assertIn("UMDL returns by itself", first[1])
        self.assertEqual(second, ("Signed in to Reddit",
                                  "Used for Reddit links from now on."))

    def test_sign_in_that_was_not_completed_says_so(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([[".instagram.com", "csrftoken"], [".instagram.com", "mid"]])  # visited only
        w.script(("list", "Sign in"), ("menu", "Instagram"))
        w.share(None)
        title, body = self.alerts(w)[-1]
        self.assertEqual(title, "Sign-in not confirmed")
        self.assertIn("Status shows whether it was saved", body)

    def test_signing_in_again_reports_the_existing_sign_in(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".x.com", "auth_token")])
        w.script(("list", "Sign in"), ("menu", "X (Twitter)"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Already signed in to X (Twitter)")
        self.assertEqual(w.seen("browser"), [])              # the page is not opened again

    def test_sign_in_to_another_site(self):
        w = self.world
        w.install(CONFIG)
        w.set_sign_in([["forum.example.org", "session_id"]])
        w.script(("list", "Sign in"), ("menu", "Another site"),
                 ("ask", "https://forum.example.org/login?next=/a&b=1"))
        w.share(None)
        self.assertEqual(w.seen("browser"), [("browser", "https://forum.example.org/login?next=/a&b=1")])
        self.assertEqual(self.alerts(w)[-1][0], "Signed in to example.org")

        w.script(("list", "Sign in"), ("menu", "Another site"), ("ask", "not an address"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1], ("Sign in", "Not a web address."))

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
        self.assertIn("Unfinished: none", lines)
        self.assertIn("Tools: ready", lines)
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
        self.assertEqual(self.notifications(w)[-1], ("UMDL", "Copied."))

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
        self.assertEqual(title, "Tools updated")
        self.assertIn("yt-dlp  2099.01.01-fake", body)

    def test_about_project_page_and_done(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About"), ("menu", "Project page"))
        w.share(None)
        about = w.seen("menu")[0]
        self.assertTrue(about[1].startswith("UMDL %s\n" % VERSION["shortcut"]))
        self.assertEqual(about[2], ["🔄 Check for updates", "🌐 Project page", "Done"])
        self.assertEqual(w.seen("openurl")[-1][1], "https://github.com/TheKfcBandit/UMDL")
        w.script(("list", "About"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.helper_runs, [])

    def test_check_for_new_version(self):
        w = self.world
        w.install(CONFIG)
        w.set_version_json(VERSION)
        w.script(("list", "About"), ("menu", "Check for updates"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Up to date")

        w.set_version_json(dict(VERSION, shortcut="9.9.9", notes="Faster."))
        w.script(("list", "About"), ("menu", "Check for updates"),
                 ("menu", "Update"))
        w.share(None)
        self.assertEqual(w.seen("menu")[-1][1], "UMDL 9.9.9 available\n\nInstalled: "
                                                "%s\n\nFaster." % VERSION["shortcut"])
        self.assertEqual(w.seen("openurl")[-1][1], VERSION["url"])

        w.set_offline(True)
        w.script(("list", "About"), ("menu", "Check for updates"))
        w.share(None)
        self.assertEqual(self.alerts(w)[-1][0], "Update check")


class Settings(Flow):
    """docs/BEHAVIOR.md, "Settings"."""

    def open_settings(self, world, *answers):
        world.script(("list", "Settings"), *answers)
        world.share(None)

    def test_one_list_shows_every_setting_with_its_value(self):
        w = self.world
        w.install(dict(CONFIG, album="Recents", after="photos", threshold="25", res="1080", fps="30"))
        self.open_settings(w, ("list", "Done"))
        _, prompt, names, _, details = w.seen("list")[1]
        self.assertEqual((prompt, names), ("Settings", SETTINGS_MENU))
        self.assertEqual(details, ["Library", "Up to 1080p", "Up to 30 fps", "Ask",
                                   "Ask above 25 items", "Notify and open",
                                   "Sign out or remove all", "Close"])
        self.assertEqual(self.notifications(w), [])          # nothing changed, nothing to announce
        self.assertEqual(w.helper_runs, [])

    def test_defaults_read_plainly(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Done"))
        self.assertEqual(w.seen("list")[1][4][:6], [
            "Clips", "Best", "Best", "Ask", "Ask above 10 items",
            "Notify"])

    def test_the_list_stays_open_and_each_change_is_saved_at_once(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Resolution"), ("menu", "1440p"),
                           ("list", "Frame rate"), ("menu", "60 fps"),
                           ("list", "When finished"),
                           ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, res="1440", fps="60", after="photos"))
        self.assertEqual(len(w.seen("list")), 5)             # main menu, then the list four times
        self.assertEqual(w.seen("list")[4][4][1:3], ["Up to 1440p", "Up to 60 fps"])
        self.assertEqual(w.seen("list")[4][4][5], "Notify and open")   # a two-value row switches on a tap
        self.assertEqual(self.notifications(w), [("UMDL", "Settings saved.")])
        self.assertEqual(w.helper_runs, [])                  # settings never open a-Shell

    def test_resolution_and_frame_rate_choices(self):
        w = self.world
        w.install(dict(CONFIG, res="720", fps="30"))
        self.open_settings(w, ("list", "Resolution"), ("menu", "Best"),
                           ("list", "Frame rate"), ("menu", "Best"), ("list", "Done"))
        menus = w.seen("menu")
        self.assertEqual(menus[0][1:3], ("Resolution", ["Best", "2160p", "1440p",
                                                                 "1080p", "720p", "480p"]))
        self.assertEqual(menus[1][1:3], ("Frame rate", ["Best", "60 fps", "30 fps"]))
        self.assertEqual(w.read_config(), CONFIG)

    def test_settings_saved_by_earlier_versions_are_read(self):
        w = self.world
        w.install({"album": "Old", "threshold": "7", "convert": "0", "after": "photos"})      # 1.2
        self.open_settings(w, ("list", "When finished"), ("list", "Done"))
        self.assertEqual(w.seen("list")[1][4][:6], [
            "Old", "Best", "Best", "Ask", "Ask above 7 items",
            "Notify and open"])                         # its "convert" meant something else: not set
        self.assertEqual(w.read_config(), dict(CONFIG, album="Old", threshold="7"))   # and written as today's

    def test_change_album(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Save to"), ("menu", "Album"), ("ask", "Holiday"),
                           ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, album="Holiday"))
        self.assertEqual(w.albums, [])
        self.assertEqual(w.seen("ask")[0][2], "Clips")       # the current name is offered
        self.assertEqual(w.seen("menu")[0][1:3], ("Save to", ["🖼️ Album", "📚 Library", "📁 Files"]))

    def test_save_to_files_and_back(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Save to"), ("menu", "Files"), ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, dest="files"))        # the album is remembered
        self.assertEqual(w.seen("list")[2][4][0], "Files")
        self.assertEqual(w.seen("list")[2][4][3], "Off for Files")
        self.open_settings(w, ("list", "Save to"), ("menu", "Library"), ("list", "Done"))
        self.assertEqual(w.read_config(), dict(CONFIG, album="Recents"))

    def test_conversion_preference(self):
        w = self.world
        w.install(CONFIG)
        self.open_settings(w, ("list", "Conversion"), ("menu", "Never"),
                           ("list", "Conversion"), ("menu", "Always"), ("list", "Done"))
        prompt, items = w.seen("menu")[0][1:3]
        self.assertEqual(prompt, "Convert for higher quality")
        self.assertEqual(items, ["❓ Ask", "🎞️ Always", "⚡ Never"])
        self.assertEqual(w.seen("list")[2][4][3], "Never")
        self.assertEqual(w.seen("list")[3][4][3], "Always")
        self.assertEqual(w.read_config(), dict(CONFIG, convert="yes"))

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
            self.assertEqual(self.alerts(w)[0], ("Not saved", "Enter 1 to 9999."), bad)
            self.assertEqual(len(w.seen("list")), 3, bad)    # back in the list after the alert

    def test_reset_sign_out(self):
        w = self.world
        w.install(CONFIG)
        w.set_cookies([(".instagram.com", "sessionid")])
        self.open_settings(w, ("list", "Reset"), ("menu", "Sign out everywhere"))
        prompt, items = w.seen("menu")[0][1:3]
        self.assertEqual(prompt, "Reset\n\nPhotos are kept.")
        self.assertEqual(items, ["🔑 Sign out everywhere", "🗑️ Remove everything", "Cancel"])
        self.assertEqual(self.helper_commands(w), ["logout"])
        self.assertFalse(os.path.exists(w.cookie_store))
        self.assertEqual(self.alerts(w)[-1], ("Signed out", "All sign-ins removed."))
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
        self.assertEqual(self.alerts(w)[-1][0], "Reset")
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

    def test_background_commands_survive_a_failing_command(self):
        # a-Shell fails the action, and Shortcuts the whole run, when a background
        # command exits with an error and "keepGoing" is off.
        actions = [a["WFWorkflowActionParameters"] for a in self.world.plist["WFWorkflowActions"]
                   if a["WFWorkflowActionIdentifier"] == ASHELL + "ExecuteCommandIntent"]
        background = [p for p in actions if p.get("openWindow") == "close"]
        self.assertGreater(len(background), 5)
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

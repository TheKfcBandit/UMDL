"""End-to-end flows: the compiled shortcut and the real helper, together.

Needs the compiled plist. Build it first (from the repository root):

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

from shortcut_sim import SimError, World  # noqa: E402


def find_plist():
    candidates = [os.environ.get("UMDL_PLIST"), os.path.join(ROOT, "build", "UMDL.plist"),
                  os.path.join(ROOT, "src", "UMDL.plist"), os.path.join(ROOT, "UMDL.plist")]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


PLIST = find_plist()
HAVE_DASH = shutil.which("dash") is not None
CONFIG = {"album": "Clips", "threshold": "10", "convert": "1", "after": "notify"}

with open(os.path.join(ROOT, "version.json")) as _handle:
    VERSION = json.load(_handle)
VIDEO = "https://video.test/watch/abc"


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
        else:
            for path, data in ((cls.clip, b"\x00\x00\x00\x18ftypmp42"), (cls.jpg, b"\xff\xd8\xff"),
                               (cls.song, b"\x00\x00\x00\x18ftypM4A ")):
                with open(path, "wb") as handle:
                    handle.write(data)

    def setUp(self):
        self.world = World(PLIST)
        self.addCleanup(self.world.close)

    def one_video(self, title="My clip"):
        return {"ytdlp": {"raw": {"_type": "video", "id": "abc", "title": title},
                          "files": [["abc.mp4", self.clip, title]]},
                "gallery": {"found": False}}

    def notifications(self):
        return [e[1:] for e in self.world.seen("notification")]

    def alerts(self):
        return [e[1:] for e in self.world.seen("alert")]

    def jobs_left(self):
        jobs = os.path.join(self.world.workspace, "jobs")
        return os.listdir(jobs) if os.path.isdir(jobs) else []

    # ------------------------------------------------------------ first run

    def test_first_run_from_share_sheet_sets_up_then_downloads(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.script(("menu", "Set up UMDL"), ("menu", "A new album"), ("ask", "Clips"),
                 ("menu", "Convert it"))
        w.share("Watch this " + VIDEO)

        self.assertEqual(w.albums, ["Clips"])
        self.assertEqual(w.read_config(), CONFIG)
        self.assertEqual([c for c, _ in w.helper_runs], ["installed", "run"])
        self.assertEqual(w.helper_runs[0][1]["url"], VIDEO)
        self.assertEqual(w.photos, [("001.mp4", "Clips", os.path.getsize(self.clip))])
        self.assertEqual(self.notifications(), [("My clip", "Saved to the Clips album.")])
        self.assertIn("One-time install", [a[0] for a in self.alerts()])
        self.assertEqual(self.jobs_left(), [])
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "pending")))

    def test_first_run_without_a_link_ends_ready(self):
        w = self.world
        w.script(("menu", "Set up UMDL"), ("menu", "No album"), ("menu", "Keep the original"))
        w.share(None)
        self.assertEqual(w.read_config(),
                         {"album": "Recents", "threshold": "10", "convert": "0", "after": "notify"})
        self.assertEqual(self.alerts()[-1][0], "UMDL is ready")
        self.assertEqual(w.photos, [])

    def test_declining_setup_changes_nothing(self):
        w = self.world
        w.script(("menu", "Not now"))
        w.share(VIDEO)
        self.assertFalse(os.path.exists(w.workspace))
        self.assertEqual(w.helper_runs, [])

    def test_failed_install_is_reported_and_retried_next_time(self):
        w = self.world
        w.set_scenario(self.one_video())
        w.offline = True  # the helper script never arrives
        w.script(("menu", "Set up UMDL"), ("menu", "No album"), ("menu", "Convert it"))
        w.share(VIDEO)
        self.assertEqual(w.seen("helper-missing")[0][0], "helper-missing")
        self.assertEqual(w.photos, [])
        # Next tap: settings are kept, the questions are not asked again, install reruns.
        w.offline = False
        w.share(VIDEO)
        self.assertEqual([c for c, _ in w.helper_runs][-2:], ["installed", "run"])
        self.assertEqual(len(w.photos), 1)

    # ------------------------------------------------------------- one tap

    def test_one_tap_download_asks_nothing(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.share(VIDEO)  # no scripted answers: any question would fail the test
        self.assertEqual(w.photos, [("001.mp4", "Clips", os.path.getsize(self.clip))])
        payload = w.helper_runs[0][1]
        self.assertEqual((payload["mode"], payload["name"], payload["cfg"]), ("auto", "UMDL", CONFIG))
        self.assertEqual(payload["v"], VERSION["shortcut"])
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

    def test_no_album_saves_to_the_library(self):
        w = self.world
        w.install(dict(CONFIG, album="Recents"))
        w.set_scenario(self.one_video(title=""))
        w.share(VIDEO)
        self.assertEqual(w.photos[0][1], "Recents")
        self.assertEqual(self.notifications(), [("UMDL", "Saved to Photos.")])

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
        self.assertEqual(self.notifications()[0][1], "Saved to the %s album." % album)
        self.assertEqual(w.helper_runs[0][1]["cfg"]["album"], album)

    def test_gallery_post_saves_every_image(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": True, "error": "No video could be found"},
                        "gallery": {"found": True, "count": 4, "sample": self.jpg}})
        w.share("https://x.com/someone/status/123")
        self.assertEqual([p[0] for p in w.photos], ["001.jpg", "002.jpg", "003.jpg", "004.jpg"])
        self.assertEqual(self.notifications()[0][1], "Saved 4 items to the Clips album.")

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
        self.assertEqual(self.notifications()[0][1],
                         "Nothing here could go into Photos.\n"
                         "1 kept in Files, under a-Shell, UMDL, Saved.")
        self.assertEqual(os.listdir(os.path.join(w.workspace, "Saved")), ["Song.m4a"])

    # ------------------------------------------------------- big downloads

    def big_playlist(self):
        files = [["v%d.mp4" % i, self.clip, "Video %d" % i] for i in range(12)]
        return {"ytdlp": {"raw": {"_type": "playlist", "title": "Mix", "playlist_count": 37,
                                  "entries": []}, "files": files},
                "gallery": {"found": False}}

    def test_more_than_ten_items_asks_then_limits(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.big_playlist())
        w.script(("menu", "Only the first 10"))
        w.share("https://video.test/playlist/1")
        menu = w.seen("menu")[0]
        self.assertEqual(menu[1], "Mix\n\nThis link has 37 items.")
        self.assertEqual(menu[2], ["Download everything", "Only the first 10",
                                   "Only the first one", "Cancel"])
        self.assertEqual([(c, p["mode"], p["limit"]) for c, p in w.helper_runs],
                         [("run", "auto", ""), ("run", "limit", "10")])
        self.assertEqual(len(w.photos), 10)
        self.assertEqual(self.notifications()[0], ("Mix", "Saved 10 items to the Clips album."))

    def test_big_download_everything_first_and_cancel(self):
        for choice, mode, saved in (("Download everything", "all", 12),
                                    ("Only the first one", "first", 1), ("Cancel", None, 0)):
            w = World(PLIST)
            self.addCleanup(w.close)
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

    def test_unknown_size_gallery_says_more_than(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario({"ytdlp": {"suitable": False},
                        "gallery": {"found": True, "count": 40, "sample": self.jpg}})
        w.script(("menu", "Cancel"))
        w.share("https://x.com/someone/media")
        self.assertEqual(w.seen("menu")[0][1], "This link has more than 10 items.")

    # ---------------------------------------------------------------- errors

    def failing(self, message):
        return {"ytdlp": {"error": message}, "gallery": {"found": False}}

    def test_error_menu_explains_and_cancels(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Sign in to confirm your age"))
        w.script(("menu", "Cancel"))
        w.share(VIDEO)
        prompt = w.seen("menu")[0][1]
        self.assertIn("Sign in to confirm your age", prompt)
        self.assertIn("needs an account", prompt)
        self.assertEqual(w.photos, [])

    def test_error_then_try_again_succeeds(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("HTTP Error 500"))
        w.script(("menu", "Try again"))
        w.run(VIDEO)
        w.set_scenario(self.one_video())  # the site recovers before the retry
        w.share(w.callbacks.pop(0))
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(w.helper_runs[1][1]["force_update"], "")

    def test_error_then_update_tools_and_retry(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Unable to extract player response"))
        w.script(("menu", "Update tools and retry"), ("menu", "Cancel"))
        w.share(VIDEO)
        self.assertEqual([p["force_update"] for _, p in w.helper_runs], ["", "1"])

    def test_error_then_sign_in_opens_the_site(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("This post is private; log in"))
        w.script(("menu", "Sign in to this site"))
        w.share("https://www.video.test/watch/abc?x=1&y=2")
        self.assertEqual(w.seen("browser"), [("browser", "https://www.video.test")])

    def test_error_details_can_be_copied(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.failing("Unsupported URL: " + VIDEO))
        w.script(("menu", "Copy error details"))
        w.share(VIDEO)
        self.assertIn("unsupported: Unsupported URL", w.clipboard)
        self.assertIn(VIDEO, w.clipboard)

    # ------------------------------------------------------------- recovery

    def test_unsaved_download_is_offered_again(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)                 # helper finishes...
        w.callbacks.clear()          # ...but the hand-back to Shortcuts never happens
        self.assertTrue(os.path.exists(os.path.join(w.workspace, "pending")))
        w.script(("menu", "Save it now"))
        w.share(None)
        self.assertEqual(len(w.photos), 1)
        self.assertEqual(self.jobs_left(), [])
        self.assertEqual(self.notifications(), [("UMDL", "Saved to the Clips album.")])

    def test_unsaved_download_can_be_discarded(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)
        w.callbacks.clear()
        w.script(("menu", "Discard it"), ("list", "About UMDL"), ("menu", "Done"))
        w.share(None)
        self.assertEqual(w.photos, [])
        self.assertEqual(self.jobs_left(), [])
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "pending")))

    def test_saving_pending_then_continues_with_the_new_link(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.run(VIDEO)
        w.callbacks.clear()
        w.script(("menu", "Save it now"))
        w.share("https://video.test/watch/other")
        self.assertEqual(len(w.photos), 2)
        self.assertEqual(w.helper_runs[-1][1]["url"], "https://video.test/watch/other")

    def test_interrupted_download_can_be_resumed_from_the_menu(self):
        w = self.world
        w.install(CONFIG)
        blob = base64.b64encode(json.dumps({
            "v": "1.0.0", "p": "1", "name": "UMDL", "url": VIDEO, "mode": "limit", "limit": "3",
            "force_update": "", "cfg": CONFIG}).encode()).decode()
        with open(os.path.join(w.workspace, "last.b64"), "w") as handle:
            handle.write(blob)
        w.set_scenario(self.one_video())
        w.script(("list", "Resume last download"))
        w.share(None)
        self.assertEqual(w.helper_runs[0], ("run", json.loads(base64.b64decode(blob))))
        self.assertEqual(len(w.photos), 1)
        self.assertFalse(os.path.exists(os.path.join(w.workspace, "last.b64")))

    def test_damaged_settings_file_restarts_setup_instead_of_crashing(self):
        w = self.world
        w.install()
        with open(os.path.join(w.workspace, "config.b64"), "w") as handle:
            handle.write("bm90IGpzb24gYXQgYWxs\n")
        w.script(("menu", "Not now"))
        w.share(VIDEO)
        self.assertIn("Welcome to UMDL", w.seen("menu")[0][1])

    # ------------------------------------------------------------------ menu

    def test_menu_lists_actions_with_subtitles(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "About UMDL"), ("menu", "Done"))
        w.share(None)
        _, prompt, names, _, details = w.seen("list")[0]
        self.assertEqual(names, ["Download from clipboard", "Enter a link", "Settings",
                                 "Sign in to a site", "Update tools", "About UMDL"])
        self.assertTrue(all(details))

    def test_download_from_clipboard(self):
        w = self.world
        w.install(CONFIG)
        w.clipboard = "check " + VIDEO
        w.set_scenario(self.one_video())
        w.script(("list", "Download from clipboard"))
        w.share(None)
        self.assertEqual(w.helper_runs[0][1]["url"], VIDEO)
        self.assertEqual(len(w.photos), 1)

    def test_empty_clipboard_is_explained(self):
        w = self.world
        w.install(CONFIG)
        w.clipboard = "nothing useful"
        w.script(("list", "Download from clipboard"))
        w.share(None)
        self.assertEqual(self.alerts()[0][0], "No link on the clipboard")
        self.assertEqual(w.helper_runs, [])

    def test_enter_a_link(self):
        w = self.world
        w.install(CONFIG)
        w.set_scenario(self.one_video())
        w.script(("list", "Enter a link"), ("ask", VIDEO))
        w.share(None)
        self.assertEqual(len(w.photos), 1)

    def test_settings_change_threshold(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Settings"), ("list", "Ask before big downloads"), ("ask", "25"))
        w.share(None)
        self.assertEqual(w.read_config(), dict(CONFIG, threshold="25"))
        self.assertEqual(self.notifications(), [("UMDL", "Your settings were saved.")])
        details = w.seen("list")[1][4]
        self.assertEqual(details[:4], ["Clips", "When a link has more than 10 items",
                                       "Convert them for Photos", "Show a notification"])

    def test_settings_reject_a_bad_threshold(self):
        for bad in ("0", "abc", "12.5", "-3", ""):
            w = World(PLIST)
            self.addCleanup(w.close)
            w.install(CONFIG)
            w.script(("list", "Settings"), ("list", "Ask before big downloads"), ("ask", bad))
            w.share(None)
            self.assertEqual(w.read_config(), CONFIG, bad)
            self.assertEqual(self.alerts_of(w)[0][0], "Not saved", bad)

    def alerts_of(self, world):
        return [e[1:] for e in world.seen("alert")]

    def test_settings_change_album_conversion_and_finish(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Settings"), ("list", "Save to"), ("menu", "already have"),
                 ("ask", "Holiday"))
        w.share(None)
        w.script(("list", "Settings"), ("list", "Videos Photos cannot play"),
                 ("menu", "Keep the original"))
        w.share(None)
        w.script(("list", "Settings"), ("list", "When a download finishes"), ("menu", "Open Photos"))
        w.share(None)
        self.assertEqual(w.read_config(), {"album": "Holiday", "threshold": "10", "convert": "0",
                                           "after": "photos"})
        self.assertEqual(w.albums, [])  # an existing album is not created again
        self.assertEqual(w.seen("list")[1][2][0], "Save to")

    def test_sign_in_to_a_listed_site_and_a_typed_one(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Sign in to a site"), ("menu", "Instagram"))
        w.share(None)
        w.script(("list", "Sign in to a site"), ("menu", "Another site"),
                 ("ask", "https://forum.example.org/login?next=/a&b=1"))
        w.share(None)
        self.assertEqual([e[1] for e in w.seen("browser")],
                         ["https://www.instagram.com/accounts/login/", "https://forum.example.org"])

    def test_update_tools_and_diagnostics_report_back(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Update tools"))
        w.share(None)
        w.script(("list", "About UMDL"), ("menu", "Run diagnostics"))
        w.share(None)
        self.assertEqual([c for c, _ in w.helper_runs], ["update", "doctor"])
        title, body = self.alerts()[-1]
        self.assertEqual(title, "UMDL diagnostics")
        self.assertIn("yt-dlp  2099.01.01-fake", body)

    def test_forget_logins(self):
        w = self.world
        w.install(CONFIG)
        cookies = os.path.join(w.home, "Library", "Cookies", "Cookies.binarycookies")
        os.makedirs(os.path.dirname(cookies))
        with open(cookies, "wb") as handle:
            handle.write(b"cook")
        w.script(("list", "Settings"), ("list", "Forget saved logins"))
        w.share(None)
        self.assertFalse(os.path.exists(cookies))
        self.assertEqual(self.alerts()[-1][0], "Logins forgotten")

    def test_reset_removes_everything(self):
        w = self.world
        w.install(CONFIG)
        w.script(("list", "Settings"), ("list", "Reset UMDL"), ("menu", "Reset UMDL"))
        w.share(None)
        self.assertFalse(os.path.exists(w.workspace))
        w.script(("menu", "Not now"))
        w.share(None)  # and the next run is a first run again
        self.assertIn("Welcome to UMDL", w.seen("menu")[-1][1])

    def test_check_for_new_version(self):
        current = VERSION
        w = self.world
        w.install(CONFIG)
        w.version_json = json.dumps(current)
        w.script(("list", "About UMDL"), ("menu", "Check for a new version"))
        w.share(None)
        self.assertEqual(self.alerts()[-1][0], "UMDL is up to date")

        w.version_json = json.dumps(dict(current, shortcut="9.9.9", notes="Faster."))
        w.script(("list", "About UMDL"), ("menu", "Check for a new version"),
                 ("menu", "Get the update"))
        w.share(None)
        self.assertIn("UMDL 9.9.9 is available", w.seen("menu")[-1][1])
        self.assertEqual(w.seen("openurl")[-1][1], current["url"])

        w.offline = True
        w.script(("list", "About UMDL"), ("menu", "Check for a new version"))
        w.share(None)
        self.assertEqual(self.alerts()[-1][0], "Update check")

    # --------------------------------------------------------------- hygiene

    def test_every_action_in_the_shortcut_is_modelled(self):
        from shortcut_sim import ASHELL, PREFIX
        known = {"gettext", "setvariable", "nothing", "exit", "number", "math", "count",
                 "dictionary", "detect.dictionary", "getvalueforkey", "text.replace", "text.match",
                 "text.match.getgroup", "base64encode", "detect.link", "getitemfromlist",
                 "geturlcomponent", "setitemname", "choosefromlist", "ask", "alert",
                 "notification", "openurl", "setclipboard", "delay", "openapp",
                 "photos.createalbum", "savetocameraroll", "conditional", "choosefrommenu",
                 "repeat.each"}
        known = {PREFIX + k for k in known} | {ASHELL + "ExecuteCommandIntent",
                                               ASHELL + "GetFileIntent"}
        used = {a["WFWorkflowActionIdentifier"] for a in self.world.plist["WFWorkflowActions"]}
        self.assertEqual(used - known, set())

    def test_shortcut_metadata(self):
        plist = self.world.plist
        self.assertEqual(plist["WFWorkflowTypes"], ["ActionExtension"])
        self.assertEqual(sorted(plist["WFWorkflowInputContentItemClasses"]),
                         ["WFStringContentItem", "WFURLContentItem"])
        self.assertTrue(plist["WFWorkflowIcon"]["WFWorkflowIconGlyphNumber"])

    def test_unscripted_question_fails_loudly(self):
        w = self.world
        with self.assertRaises(SimError):
            w.share(VIDEO)  # not installed, so the welcome menu appears unannounced


if __name__ == "__main__":
    unittest.main()

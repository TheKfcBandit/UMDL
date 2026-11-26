"""Tests for the UMDL helper.

They run on any desktop Python: yt-dlp and gallery-dl are replaced by small
fakes, while ffmpeg (when installed) is used for real so the Photos
compatibility logic is exercised against actual media files.

    python -m unittest discover -s tests -v
"""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="umdl-test-")
os.environ["UMDL_HOME"] = os.path.join(WORK, "UMDL")
os.environ["UMDL_PLATFORM"] = "desktop"
os.environ["UMDL_SKIP_UPDATES"] = "1"
os.environ["UMDL_PIP"] = "pip"   # the stand-in in tests/fakes/bin
os.environ["HOME"] = WORK        # where that stand-in "installs" to
os.environ["NO_COLOR"] = "1"
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests", "fakes"))

import cookiejar  # noqa: E402
import umdl  # noqa: E402

umdl.SAFARI_COOKIES = os.path.join(WORK, "Library", "Cookies", "Cookies.binarycookies")

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def has_encoder(name):
    if not HAVE_FFMPEG:
        return False
    out = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, universal_newlines=True).stdout
    return (" %s " % name) in out


def make_clip(path, vcodec=None, acodec=None, extra=()):
    """Write a one-second test clip with the given codecs."""
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if vcodec == "libx265":
        extra = tuple(extra) + ("-x265-params", "log-level=error")
    if vcodec:
        args += ["-f", "lavfi", "-i", "testsrc=size=160x120:rate=10:duration=1"]
    if acodec:
        args += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1"]
    if vcodec:
        args += ["-c:v", vcodec, "-pix_fmt", "yuv420p"]
    if acodec:
        args += ["-c:a", acodec]
    subprocess.run(args + list(extra) + [path], check=True)
    return path


def payload(url, **extra):
    data = {"v": umdl.HELPER_VERSION, "p": str(umdl.PROTOCOL), "name": "UMDL", "url": url,
            "mode": "auto",
            "cfg": {"album": "UMDL", "threshold": "10", "convert": "1", "after": "notify"}}
    data.update(extra)
    return base64.b64encode(json.dumps(data).encode()).decode()


def read_callback(text):
    """Decode the callback the helper printed in place of opening Shortcuts."""
    lines = [ln for ln in text.splitlines() if ln.startswith("CALLBACK ")]
    assert lines, "no callback in output:\n" + text
    url = lines[-1][len("CALLBACK "):]
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
    blob = query["text"][0]
    assert blob.startswith(umdl.CALLBACK_PREFIX)
    return query["name"][0], json.loads(base64.b64decode(blob[len(umdl.CALLBACK_PREFIX):]))


class FakeDownloadError(Exception):
    pass


def install_fake_ytdlp(behaviour):
    """behaviour: dict with 'raw' (probe result or exception) and 'files'
    (list of (name, source path, title)) to create on download."""
    module = types.ModuleType("yt_dlp")
    utils = types.ModuleType("yt_dlp.utils")
    utils.DownloadError = FakeDownloadError
    version = types.ModuleType("yt_dlp.version")
    version.__version__ = "fake"
    extractor = types.ModuleType("yt_dlp.extractor")

    class FakeIE:
        IE_NAME = behaviour.get("ie", "fake")

        @classmethod
        def suitable(cls, url):
            return behaviour.get("suitable", True)

    extractor.gen_extractor_classes = lambda: [FakeIE]

    class YoutubeDL:
        def __init__(self, opts):
            self.opts = opts
            behaviour.setdefault("opts", []).append(opts)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def extract_info(self, url, download=False, process=False, ie_key=None):
            raw = behaviour["raw"]
            if isinstance(raw, Exception):
                self.opts["logger"].error("ERROR: %s" % raw)
                raise raw
            return raw

        def _produce(self):
            folder = os.path.dirname(self.opts["outtmpl"])
            for name, source, title in behaviour.get("files", []):
                target = os.path.join(folder, name)
                shutil.copy(source, target)
                for hook in self.opts["progress_hooks"]:
                    hook({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 10,
                          "speed": 2048.0, "eta": 3, "info_dict": {"title": title}})
                    hook({"status": "finished", "filename": target, "info_dict": {"title": title}})
            if behaviour.get("download_error"):
                self.opts["logger"].error("ERROR: %s" % behaviour["download_error"])
                raise FakeDownloadError(behaviour["download_error"])

        def process_ie_result(self, raw, download=True):
            self._produce()

        def download(self, urls):
            self._produce()

    module.YoutubeDL = YoutubeDL
    module.utils = utils
    module.version = version
    module.extractor = extractor
    sys.modules.update({"yt_dlp": module, "yt_dlp.utils": utils,
                        "yt_dlp.version": version, "yt_dlp.extractor": extractor})
    return behaviour


def install_fake_gallery(found):
    module = types.ModuleType("gallery_dl")
    extractor = types.ModuleType("gallery_dl.extractor")
    version = types.ModuleType("gallery_dl.version")
    version.__version__ = "fake"

    class Found:
        category = "fakegallery"

    extractor.find = lambda url: Found() if found else None
    module.extractor = extractor
    module.version = version
    sys.modules.update({"gallery_dl": module, "gallery_dl.extractor": extractor,
                        "gallery_dl.version": version})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.media = os.path.join(WORK, "media")
        os.makedirs(cls.media, exist_ok=True)
        cls.bin = os.path.join(ROOT, "tests", "fakes", "bin")
        if cls.bin not in os.environ["PATH"].split(os.pathsep):
            os.environ["PATH"] = cls.bin + os.pathsep + os.environ["PATH"]
        cls.jpg = os.path.join(cls.media, "sample.jpg")
        if HAVE_FFMPEG and not os.path.exists(cls.jpg):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                            "-i", "testsrc=size=64x64:rate=1:duration=1", "-frames:v", "1",
                            cls.jpg], check=True)
        elif not os.path.exists(cls.jpg):
            with open(cls.jpg, "wb") as handle:
                handle.write(b"\xff\xd8\xff\xe0fakejpeg")
        os.environ["FAKE_GALLERY_SAMPLE"] = cls.jpg

    def setUp(self):
        shutil.rmtree(umdl.WORKSPACE, ignore_errors=True)
        os.makedirs(umdl.WORKSPACE)
        self.out = io.StringIO()
        umdl.OUT = self.out
        for key in ("FAKE_GALLERY_FAIL", "FAKE_GALLERY_COUNT"):
            os.environ.pop(key, None)
        for name in list(sys.modules):
            if name.split(".")[0] in ("yt_dlp", "gallery_dl"):
                del sys.modules[name]

    def run_helper(self, command, blob):
        code = umdl.main(["umdl.py", command, blob])
        return code, read_callback(self.out.getvalue())


class PureLogic(unittest.TestCase):
    def test_clean_url(self):
        self.assertEqual(umdl.clean_url("Look: https://x.com/a/status/1?s=20."),
                         "https://x.com/a/status/1?s=20")
        self.assertEqual(umdl.clean_url("https://youtu.be/abc_-1"), "https://youtu.be/abc_-1")
        self.assertEqual(umdl.clean_url("(https://example.com/a)"), "https://example.com/a")
        self.assertEqual(umdl.clean_url("no link here"), "")

    def test_versions(self):
        self.assertTrue(umdl.newer("1.2.0", "1.1.9"))
        self.assertTrue(umdl.newer("v1.10", "1.9.5"))
        self.assertFalse(umdl.newer("1.0.0", "1.0.0"))
        self.assertFalse(umdl.newer("", "1.0.0"))
        self.assertFalse(umdl.newer(None, "1.0.0"))

    def test_classify_error(self):
        cases = {
            "This video is DRM protected": "drm",
            "Sign in to confirm your age": "auth",
            "[instagram][error] HTTP redirect to login page": "auth",
            "Unsupported URL: https://example.com": "unsupported",
            "<urlopen error [Errno 8] getaddrinfo failed>": "network",
            "Video unavailable. This video has been removed": "gone",
            "something odd happened": "unknown",
        }
        for message, kind in cases.items():
            self.assertEqual(umdl.classify_error(message), kind, message)

    def test_tidy_error(self):
        self.assertEqual(umdl.tidy_error("\x1b[0;31mERROR:\x1b[0m [youtube] abc: Private video"),
                         "[youtube] abc: Private video")
        self.assertEqual(umdl.tidy_error("[twitter][error] No results for X"), "No results for X")
        self.assertEqual(umdl.tidy_error(""), "Unknown error")
        self.assertEqual(
            umdl.tidy_error("[generic] x: Unable to download webpage: HTTP Error 404: Not Found "
                            "(caused by <HTTPError 404: Not Found>)"),
            "[generic] x: Unable to download webpage: HTTP Error 404: Not Found")
        self.assertLessEqual(len(umdl.tidy_error("x" * 1000)), 280)

    def test_prefers_gallery(self):
        for host in ("x.com", "www.instagram.com", "old.reddit.com", "i.pinterest.co.uk",
                     "danbooru.donmai.us", "www.pinterest.com"):
            self.assertTrue(umdl.prefers_gallery(host), host)
        for host in ("www.youtube.com", "vimeo.com", "notx.com", "example.com", "max.com"):
            self.assertFalse(umdl.prefers_gallery(host), host)

    def test_decode_payload(self):
        blob = base64.b64encode(b'{"url":"https://a.b","cfg":"oops"}').decode().rstrip("=")
        data = umdl.decode_payload(blob)
        self.assertEqual(data["url"], "https://a.b")
        self.assertEqual(data["cfg"], {})
        with self.assertRaises(Exception):
            umdl.decode_payload("bm90IGpzb24=")

    def test_count_entries(self):
        self.assertEqual(umdl.count_entries([1, 2, 3], 11), (3, True))
        self.assertEqual(umdl.count_entries(iter(range(5)), 11), (5, True))
        self.assertEqual(umdl.count_entries(iter(range(500)), 11), (11, False))
        self.assertEqual(umdl.count_entries(None, 11), (0, True))

        class Paged:
            def getslice(self, start, end):
                return list(range(start, min(end, 40)))

        self.assertEqual(umdl.count_entries(Paged(), 11), (11, False))

    def test_safe_title(self):
        self.assertEqual(umdl.safe_title('a/b:c*?"<>|d', "x"), "a b c d")
        self.assertEqual(umdl.safe_title("", "fallback"), "fallback")
        self.assertEqual(len(umdl.safe_title("y" * 300, "x")), 80)

    def test_format_string_prefers_native(self):
        first = umdl.YTDLP_FORMAT.split("/")[0]
        self.assertIn("avc", first)
        self.assertIn("mp4a", first)
        self.assertEqual(umdl.YTDLP_FORMAT.split("/")[-2:], ["b", "ba"])


class Quality(unittest.TestCase):
    """Settings, format choice and the advanced-mode plan."""

    FORMATS = [
        {"format_id": "18", "vcodec": "avc1.42001E", "acodec": "mp4a.40.2", "width": 640,
         "height": 360, "fps": 30, "tbr": 500, "filesize": 10_000_000},
        {"format_id": "22", "vcodec": "avc1.64001F", "acodec": "mp4a.40.2", "width": 1280,
         "height": 720, "fps": 30, "tbr": 1500},
        {"format_id": "137", "vcodec": "avc1.640028", "acodec": "none", "width": 1920,
         "height": 1080, "fps": 30, "tbr": 4000, "filesize": 80_000_000},
        {"format_id": "299", "vcodec": "avc1.64002a", "acodec": "none", "width": 1920,
         "height": 1080, "fps": 60, "tbr": 6000, "filesize": 120_000_000},
        {"format_id": "315", "vcodec": "vp09.00.51.08", "acodec": "none", "width": 3840,
         "height": 2160, "fps": 60, "tbr": 26000, "filesize": 650_000_000},
        {"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129},
        {"format_id": "251", "vcodec": "none", "acodec": "opus", "abr": 160},
    ]

    def plan(self, **quality):
        settings = umdl.settings_from(dict({"mode": "advanced"}, **quality))
        return umdl.build_plan(self.FORMATS, settings, "A video")

    def test_settings_have_safe_defaults(self):
        best = {"convert": "best", "res": "best", "fps": "best", "advanced": False}
        self.assertEqual(umdl.settings_from({}), best)
        self.assertEqual(umdl.settings_from(None), best)
        self.assertEqual(umdl.settings_from({"res": "999", "fps": "24", "convert": "sometimes"}), best)
        self.assertEqual(umdl.settings_from({"res": "1080", "fps": "30", "convert": "small",
                                             "mode": "advanced"}),
                         {"convert": "small", "res": "1080", "fps": "30", "advanced": True})

    def test_settings_saved_by_earlier_versions_still_mean_the_same(self):
        for old, new in (("1", "best"), ("0", "off"), ("needed", "best"), ("never", "off"),
                         ("best", "best"), ("off", "off")):
            self.assertEqual(umdl.settings_from({"convert": old})["convert"], new, old)

    def test_best_means_size_then_smoothness_then_what_photos_plays(self):
        sort = lambda **q: umdl.ytdlp_sort(umdl.settings_from(q))  # noqa: E731
        self.assertEqual(sort(), ["lang", "res", "fps", "vcodec:h265", "acodec:aac"])
        self.assertEqual(sort(res="1080")[1:3], ["res:1080", "fps"])
        self.assertEqual(sort(fps="30")[1:3], ["res", "fps:30"])
        self.assertEqual(sort(res="720", fps="60")[1:3], ["res:720", "fps:60"])

    def test_the_conversion_setting_has_no_say_in_the_version(self):
        asked = {(umdl.ytdlp_format("best", q), tuple(umdl.ytdlp_sort(q)))
                 for q in (umdl.settings_from({"convert": c}) for c in ("best", "small", "off"))}
        self.assertEqual(asked, {("bv*+ba/b/ba", ("lang", "res", "fps", "vcodec:h265", "acodec:aac"))})

    def test_a_frame_rate_limit_filters_with_a_fallback(self):
        capped = umdl.ytdlp_format("best", umdl.settings_from({"fps": "30"}))
        self.assertEqual(capped, "bv*[fps<=?30]+ba/b[fps<=?30]/bv*+ba/b/ba")
        native = umdl.ytdlp_format("native", umdl.settings_from({"fps": "60"}))
        self.assertTrue(native.endswith("/" + umdl.YTDLP_FORMAT))
        self.assertEqual(native.count("[fps<=?60]"), umdl.YTDLP_FORMAT.count("/"))   # every choice but "ba"
        self.assertEqual(umdl.ytdlp_format("native"), umdl.YTDLP_FORMAT)

    def test_plan_names_the_best_of_each_kind(self):
        plan = self.plan()
        self.assertEqual(plan["info"], "A video\n\nBest video: 2160p60 VP9 · 650 MB\n"
                                       "Best audio: Opus · 160 kbps\nSingle file: 720p H.264 + AAC")
        self.assertEqual([(o["title"], o["detail"], o["format"], o["convert"]) for o in plan["options"]], [
            ("2160p60 · VP9 → HEVC", "Best available", "315+140", True),
            ("1080p60 · H.264", "Best without converting", "299+140", False),
            ("720p · H.264 · single file", "Nothing to merge", "22", False)])

    def test_sound_photos_plays_is_preferred_so_it_can_be_copied(self):
        self.assertTrue(all(o["format"].endswith("+140") for o in self.plan()["options"][:2]))
        only_opus = [f for f in self.FORMATS if f["format_id"] != "140"]
        plan = umdl.build_plan(only_opus, umdl.settings_from({}), "")
        self.assertEqual(plan["options"][0]["format"], "315+251")

    def test_between_equals_the_one_photos_plays_wins(self):
        twin = dict(self.FORMATS[4], format_id="401", vcodec="hev1.2.4.L153", tbr=20000)
        plan = umdl.build_plan(self.FORMATS + [twin], umdl.settings_from({}), "")
        self.assertEqual((plan["options"][0]["title"], plan["options"][0]["format"]),
                         ("2160p60 · HEVC", "401+140"))

    def test_plan_respects_the_limits_and_says_so(self):
        plan = self.plan(res="1080", fps="30")
        self.assertTrue(plan["info"].endswith("\nYour limit: 1080p 30 fps"))
        self.assertEqual([o["format"] for o in plan["options"]], ["137+140", "22"])
        plan = self.plan(res="480")
        self.assertEqual([o["format"] for o in plan["options"]], ["18"])

    def test_a_frame_rate_limit_is_kept_even_at_a_smaller_size(self):
        sixty = [f for f in self.FORMATS if f["format_id"] in ("18", "299", "315", "140")]
        plan = umdl.build_plan(sixty, umdl.settings_from({"fps": "30"}), "")
        self.assertEqual([o["format"] for o in plan["options"]], ["18"])

    def test_nothing_within_the_limit_offers_the_smallest_there_is(self):
        tall = [f for f in self.FORMATS if f["format_id"] in ("137", "299", "315", "140")]
        plan = umdl.build_plan(tall, umdl.settings_from({"res": "720"}), "")
        self.assertEqual([o["format"] for o in plan["options"]], ["299+140"])

    def test_the_conversion_named_is_the_one_this_device_does(self):
        plan = umdl.build_plan(self.FORMATS, umdl.settings_from({}), "", target="H.264")
        self.assertEqual(plan["options"][0]["title"], "2160p60 · VP9 → H.264")

    def test_plan_for_a_site_with_one_file(self):
        plan = umdl.build_plan(self.FORMATS[:1], umdl.settings_from({}), "")
        self.assertEqual([(o["format"], o["convert"]) for o in plan["options"]], [("18", False)])

    def test_titles_are_unique_even_after_a_trip_through_shortcuts(self):
        for quality in ({}, {"res": "1080"}, {"res": "720", "fps": "30"}, {"res": "480"}):
            names = [umdl.plain(o["title"]) for o in self.plan(**quality)["options"]]
            self.assertEqual(len(names), len(set(names)), quality)
        self.assertEqual(umdl.plain("2160p60 · VP9 → HEVC"), umdl.plain(" 2160p60  VP9 -> hevc"))

    def test_rows_are_cards_with_an_icon_marker_each(self):
        cards = umdl.cards_for(self.plan()["options"])
        self.assertEqual(cards.count("BEGIN:VCARD"), 3)
        self.assertEqual(cards.count(umdl.ICON_CONVERT), 1)      # only the version that needs converting
        self.assertEqual(cards.count(umdl.ICON_GET), 2)
        self.assertIn("\nN;CHARSET=utf-8:1080p60 · H.264;;;;\nORG;CHARSET=utf-8:Best without converting", cards)
        odd = umdl.cards_for([{"title": "a;b,c\\d\ne", "detail": "x;y"}])
        self.assertIn("N;CHARSET=utf-8:a b c d e;;;;\nORG;CHARSET=utf-8:x y;", odd)


class ConversionOrder(unittest.TestCase):
    INFO = {"width": 3840, "height": 2160, "fps": 60.0, "vbitrate": 26_000_000, "bitrate": 26_200_000,
            "pix_fmt": "yuv420p", "v": "vp9", "a": "opus"}

    def test_hardware_hevc_at_a_quality_level_comes_first(self):
        attempts = umdl.conversion_attempts(self.INFO, {"hevc_videotoolbox", "h264_videotoolbox",
                                                         "libx264"})
        self.assertEqual([codec for codec, _ in attempts], ["HEVC", "HEVC", "H.264", "H.264"])
        first = attempts[0][1]
        self.assertEqual(first[:4], ["-c:v", "hevc_videotoolbox", "-tag:v", "hvc1"])
        self.assertEqual(first[-2:], ["-q:v", "75"])
        self.assertNotIn("-vf", first)                      # size and frame rate are left alone
        self.assertNotIn("-r", first)

    def test_the_bitrate_fallback_never_goes_below_the_source(self):
        attempts = umdl.conversion_attempts(self.INFO, {"hevc_videotoolbox"})
        rate = int(attempts[1][1][-1])
        self.assertGreaterEqual(rate, self.INFO["vbitrate"])
        self.assertLessEqual(rate, 80_000_000)

    def test_ten_bit_sources_stay_ten_bit(self):
        deep = dict(self.INFO, pix_fmt="yuv420p10le")
        first = umdl.conversion_attempts(deep, {"hevc_videotoolbox"})[0][1]
        self.assertIn("main10", first)
        self.assertIn("p010le", first)

    def test_only_encoders_this_ffmpeg_has_are_tried(self):
        attempts = umdl.conversion_attempts(self.INFO, {"libx264"})
        self.assertEqual([args[1] for _, args in attempts], ["libx264"])
        self.assertIn("17", attempts[0][1])                 # visually lossless, not a fixed bitrate

    def test_smaller_file_asks_for_less_at_every_step(self):
        have = {"hevc_videotoolbox", "h264_videotoolbox", "libx264"}
        best = umdl.conversion_attempts(self.INFO, have)
        small = umdl.conversion_attempts(self.INFO, have, "small")
        self.assertEqual([c for c, _ in small], [c for c, _ in best])        # same encoders, same order
        self.assertEqual((best[0][1][-1], small[0][1][-1]), ("75", "55"))
        self.assertLess(int(small[1][1][-1]), int(best[1][1][-1]))
        self.assertEqual((best[3][1][5], small[3][1][5]), ("17", "23"))
        self.assertNotIn("-vf", small[0][1])                                # still the same size
        self.assertNotIn("-r", small[0][1])

    def test_a_low_bitrate_source_gets_a_sensible_floor(self):
        thin = dict(self.INFO, width=1280, height=720, fps=30.0, vbitrate=300_000, bitrate=350_000)
        rate = int(umdl.conversion_attempts(thin, {"hevc_videotoolbox"})[1][1][-1])
        self.assertGreater(rate, 1_000_000)


class Planning(Base):
    def plan(self, url, ytdlp, gallery):
        install_fake_ytdlp({"suitable": ytdlp})
        install_fake_gallery(gallery)
        return umdl.plan_engines(url)

    def test_orders(self):
        self.assertEqual(self.plan("https://www.youtube.com/watch?v=1", True, False), ["ytdlp"])
        self.assertEqual(self.plan("https://x.com/a/status/1", True, True), ["gallery", "ytdlp"])
        self.assertEqual(self.plan("https://vimeo.com/1", True, True), ["ytdlp", "gallery"])
        self.assertEqual(self.plan("https://somebooru.test/p/1", False, True), ["gallery", "ytdlp"])
        self.assertEqual(self.plan("https://example.com/page", False, False), ["ytdlp"])


@unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
class PhotosReady(Base):
    def stage(self, source):
        folder = tempfile.mkdtemp(dir=WORK)
        target = os.path.join(folder, "001." + source.rsplit(".", 1)[1])
        shutil.copy(source, target)
        return target

    def test_native_mp4_untouched(self):
        clip = make_clip(os.path.join(self.media, "native.mp4"), "libx264", "aac")
        staged = self.stage(clip)
        self.assertEqual(umdl.make_photos_ready(staged, True), staged)

    def test_mkv_is_rewrapped_without_reencoding(self):
        clip = make_clip(os.path.join(self.media, "wrapped.mkv"), "libx264", "aac")
        ready = umdl.make_photos_ready(self.stage(clip), False)
        self.assertTrue(ready.endswith("001.mp4"))           # takes the original's place
        info = umdl.probe_media(ready)
        self.assertEqual((info["v"], info["a"]), ("h264", "aac"))

    @unittest.skipUnless(has_encoder("libopus"), "no libopus")
    def test_wrong_audio_only_reencodes_audio(self):
        clip = make_clip(os.path.join(self.media, "opus.mkv"), "libx264", "libopus")
        ready = umdl.make_photos_ready(self.stage(clip), False)
        info = umdl.probe_media(ready)
        self.assertEqual((info["v"], info["a"]), ("h264", "aac"))

    @unittest.skipUnless(has_encoder("libvpx-vp9"), "no libvpx-vp9")
    def test_vp9_converted_only_when_allowed(self):
        clip = make_clip(os.path.join(self.media, "vp9.webm"), "libvpx-vp9", None)
        self.assertIsNone(umdl.make_photos_ready(self.stage(clip), False))
        ready = umdl.make_photos_ready(self.stage(clip), True)
        self.assertIsNotNone(ready)
        self.assertEqual(umdl.probe_media(ready)["v"], "h264")

    @unittest.skipUnless(has_encoder("libx265"), "no libx265")
    def test_hevc_is_retagged_for_apple(self):
        clip = make_clip(os.path.join(self.media, "hev1.mp4"), "libx265", "aac",
                         extra=("-tag:v", "hev1"))
        self.assertEqual(umdl.probe_media(clip)["tag"], "hev1")
        ready = umdl.make_photos_ready(self.stage(clip), False)
        self.assertEqual(umdl.probe_media(ready)["tag"], "hvc1")

    @unittest.skipUnless(has_encoder("libvpx-vp9"), "no libvpx-vp9")
    def test_verdicts(self):
        native = make_clip(os.path.join(self.media, "native.mp4"), "libx264", "aac")
        wrapped = make_clip(os.path.join(self.media, "wrapped.mkv"), "libx264", "aac")
        vp9 = make_clip(os.path.join(self.media, "vp9.webm"), "libvpx-vp9", None)
        song = make_clip(os.path.join(self.media, "song.m4a"), None, "aac")
        self.assertEqual([umdl.photos_verdict(p)[0] for p in (native, wrapped, vp9, song, self.jpg)],
                         ["ready", "repack", "convert", "files", "ready"])
        self.assertEqual([p for p, _ in umdl.conversions_pending([native, wrapped, vp9, song])], [vp9])

    @unittest.skipUnless(has_encoder("libvpx-vp9"), "no libvpx-vp9")
    def test_conversion_keeps_size_and_frame_rate_and_is_noted(self):
        clip = make_clip(os.path.join(self.media, "vp9.webm"), "libvpx-vp9", None)
        before = umdl.probe_media(clip)
        notes = []
        ready = umdl.make_photos_ready(self.stage(clip), True, notes)
        after = umdl.probe_media(ready)
        self.assertEqual((after["width"], after["height"]), (before["width"], before["height"]))
        self.assertAlmostEqual(after["fps"], before["fps"], places=1)
        self.assertEqual(notes, ["VP9 → H.264"])            # this machine has no VideoToolbox
        self.assertTrue(ready.endswith("001.mp4"))
        self.assertEqual(os.listdir(os.path.dirname(ready)), ["001.mp4"])   # the original is gone

    def test_audio_and_unknown_stay_in_files(self):
        clip = make_clip(os.path.join(self.media, "song.m4a"), None, "aac")
        self.assertIsNone(umdl.make_photos_ready(self.stage(clip), True))
        other = os.path.join(self.media, "archive.zip")
        with open(other, "wb") as handle:
            handle.write(b"PK\x03\x04")
        self.assertIsNone(umdl.make_photos_ready(self.stage(other), True))

    def test_audio_in_video_container_stays_in_files(self):
        clip = make_clip(os.path.join(self.media, "audio_only.mp4"), None, "aac")
        self.assertIsNone(umdl.make_photos_ready(self.stage(clip), True))

    def test_images_pass_through(self):
        staged = self.stage(self.jpg)
        self.assertEqual(umdl.make_photos_ready(staged, True), staged)


class EndToEnd(Base):
    def clip(self):
        if HAVE_FFMPEG:
            return make_clip(os.path.join(self.media, "e2e.mp4"), "libx264", "aac")
        path = os.path.join(self.media, "e2e.mp4")
        with open(path, "wb") as handle:
            handle.write(b"\x00\x00\x00\x18ftypmp42")
        return path

    def test_single_video(self):
        clip = self.clip()
        fake = install_fake_ytdlp({
            "raw": {"_type": "video", "id": "abc", "title": "My clip"},
            "files": [("abc.mp4", clip, "My clip")],
        })
        install_fake_gallery(False)
        code, (name, data) = self.run_helper("run", payload("https://video.test/watch/abc"))
        self.assertEqual(code, 0)
        self.assertEqual(name, "UMDL")
        self.assertEqual(data["t"], "done")
        self.assertEqual((data["np"], data["nk"]), ("1", "0"))
        self.assertEqual(data["title"], "My clip")
        self.assertEqual(data["cfg"]["album"], "UMDL")
        with open(data["m"]) as handle:
            manifest = json.load(handle)
        self.assertEqual(len(manifest["photos"]), 1)
        self.assertTrue(os.path.exists(manifest["photos"][0]))
        self.assertNotIn(" ", manifest["photos"][0].replace(WORK, ""))
        with open(umdl.PENDING_FILE) as handle:
            self.assertEqual(handle.read(), data["m"])
        self.assertFalse(os.path.exists(umdl.LAST_FILE))
        opts = fake["opts"][-1]
        self.assertEqual(opts["format"], "bv*+ba/b/ba")
        self.assertTrue(opts["noplaylist"])
        self.assertNotIn("cookiesfrombrowser", opts)

    def test_big_playlist_asks_first(self):
        install_fake_ytdlp({"raw": {"_type": "playlist", "title": "Mix", "playlist_count": 37,
                                    "entries": iter(())}})
        install_fake_gallery(False)
        code, (_, data) = self.run_helper("run", payload("https://video.test/playlist/1"))
        self.assertEqual(data["t"], "confirm")
        self.assertEqual((data["n"], data["thr"], data["title"]), ("37", "10", "Mix"))
        self.assertFalse(os.path.exists(umdl.PENDING_FILE))

    def test_playlist_with_limit(self):
        clip = self.clip()
        fake = install_fake_ytdlp({
            "raw": {"_type": "playlist", "title": "Mix", "playlist_count": 37, "entries": iter(())},
            "files": [("a.mp4", clip, "One"), ("b.mp4", clip, "Two")],
        })
        install_fake_gallery(False)
        code, (_, data) = self.run_helper(
            "run", payload("https://video.test/playlist/1", mode="limit", limit="10"))
        self.assertEqual((data["t"], data["np"]), ("done", "2"))
        self.assertEqual(fake["opts"][-1]["playlist_items"], "1-10")
        self.assertEqual(fake["opts"][-1]["ignoreerrors"], "only_download")

    def test_small_playlist_just_downloads(self):
        clip = self.clip()
        install_fake_ytdlp({
            "raw": {"_type": "playlist", "title": "Pair", "entries": [1, 2]},
            "files": [("a.mp4", clip, "One"), ("b.mp4", clip, "Two")],
        })
        install_fake_gallery(False)
        code, (_, data) = self.run_helper("run", payload("https://video.test/playlist/2"))
        self.assertEqual((data["t"], data["np"]), ("done", "2"))

    def test_falls_back_to_gallery(self):
        install_fake_ytdlp({"raw": FakeDownloadError("No video could be found in this post")})
        install_fake_gallery(True)
        os.environ["FAKE_GALLERY_COUNT"] = "3"
        code, (_, data) = self.run_helper("run", payload("https://video.test/post/9"))
        self.assertEqual((data["t"], data["np"]), ("done", "3"))
        with open(data["m"]) as handle:
            manifest = json.load(handle)
        self.assertTrue(all(os.path.exists(p) for p in manifest["photos"]))
        self.assertTrue(all(os.path.basename(p)[:3].isdigit() for p in manifest["photos"]))

    def test_gallery_first_and_confirm(self):
        install_fake_ytdlp({"raw": {"_type": "video", "id": "x"}})
        install_fake_gallery(True)
        os.environ["FAKE_GALLERY_COUNT"] = "25"
        code, (_, data) = self.run_helper("run", payload("https://x.com/user/media"))
        self.assertEqual((data["t"], data["n"], data["thr"]), ("confirm", "", "10"))
        self.setUp()
        install_fake_ytdlp({"raw": {"_type": "video", "id": "x"}})
        install_fake_gallery(True)
        os.environ["FAKE_GALLERY_COUNT"] = "25"
        code, (_, data) = self.run_helper(
            "run", payload("https://x.com/user/media", mode="first"))
        self.assertEqual((data["t"], data["np"]), ("done", "1"))

    def test_error_reports_first_tool(self):
        install_fake_ytdlp({"raw": FakeDownloadError("Sign in to confirm your age")})
        install_fake_gallery(True)
        os.environ["FAKE_GALLERY_FAIL"] = "Unsupported URL"
        code, (_, data) = self.run_helper("run", payload("https://video.test/watch/x"))
        self.assertEqual((data["t"], data["kind"]), ("error", "auth"))
        self.assertEqual(data["msg"], "Sign in to confirm your age")
        self.assertEqual(data["url"], "https://video.test/watch/x")

    def test_partial_download_still_delivers(self):
        clip = self.clip()
        install_fake_ytdlp({
            "raw": {"_type": "playlist", "title": "Mix", "entries": [1, 2, 3]},
            "files": [("a.mp4", clip, "One")],
            "download_error": "Video unavailable",
        })
        install_fake_gallery(False)
        code, (_, data) = self.run_helper("run", payload("https://video.test/playlist/3"))
        self.assertEqual((data["t"], data["np"], data["nf"]), ("done", "1", "1"))

    @unittest.skipUnless(HAVE_FFMPEG, "ffmpeg not installed")
    def test_audio_goes_to_files(self):
        song = make_clip(os.path.join(self.media, "track.m4a"), None, "aac")
        install_fake_ytdlp({
            "raw": {"_type": "video", "id": "s1", "title": "A song: live/2024"},
            "files": [("s1.m4a", song, "A song: live/2024")],
        })
        install_fake_gallery(False)
        code, (_, data) = self.run_helper("run", payload("https://audio.test/s1"))
        self.assertEqual((data["t"], data["np"], data["nk"]), ("done", "0", "1"))
        self.assertEqual(os.listdir(umdl.SAVED_DIR), ["A song live 2024.m4a"])
        self.assertFalse(os.path.exists(umdl.PENDING_FILE))

    def test_no_link(self):
        code, (_, data) = self.run_helper("run", payload("just some words"))
        self.assertEqual((data["t"], data["kind"]), ("error", "nolink"))

    def test_other_jobs_are_cleaned_but_pending_kept(self):
        stale = os.path.join(umdl.JOBS_DIR, "stale")
        unsaved = os.path.join(umdl.JOBS_DIR, "unsaved")
        os.makedirs(stale)
        os.makedirs(unsaved)
        with open(umdl.PENDING_FILE, "w") as handle:
            handle.write(os.path.join(unsaved, "manifest.json"))
        install_fake_ytdlp({"raw": FakeDownloadError("Unsupported URL")})
        install_fake_gallery(False)
        self.run_helper("run", payload("https://video.test/none"))
        self.assertFalse(os.path.exists(stale))
        self.assertTrue(os.path.exists(unsaved))

    def test_redownload_drops_its_own_stale_pending_marker(self):
        clip = self.clip()
        install_fake_ytdlp({"raw": {"_type": "video", "id": "abc", "title": "T"},
                            "files": [("abc.mp4", clip, "T")]})
        install_fake_gallery(False)
        url = "https://video.test/watch/again"
        self.run_helper("run", payload(url))
        self.assertTrue(os.path.exists(umdl.PENDING_FILE))
        self.setUp_keep_workspace()
        install_fake_ytdlp({"raw": FakeDownloadError("HTTP Error 500")})
        install_fake_gallery(False)
        code, (_, data) = self.run_helper("run", payload(url))
        self.assertEqual(data["t"], "error")
        self.assertFalse(os.path.exists(umdl.PENDING_FILE))

    def setUp_keep_workspace(self):
        self.out = io.StringIO()
        umdl.OUT = self.out
        for name in list(sys.modules):
            if name.split(".")[0] in ("yt_dlp", "gallery_dl"):
                del sys.modules[name]

    def test_logout(self):
        os.makedirs(os.path.dirname(umdl.SAFARI_COOKIES), exist_ok=True)
        with open(umdl.SAFARI_COOKIES, "wb") as handle:
            handle.write(b"cookies")
        self.addCleanup(lambda: umdl.remove(umdl.SAFARI_COOKIES))
        code, (_, data) = self.run_helper("logout", payload(""))
        self.assertEqual((data["t"], data["title"]), ("info", "Signed out"))
        self.assertFalse(os.path.exists(umdl.SAFARI_COOKIES))

    def test_setup_and_status(self):
        install_fake_ytdlp({"raw": {}})
        install_fake_gallery(True)
        code, (_, data) = self.run_helper("setup", payload(""))
        self.assertEqual((code, data["t"]), (0, "setup"))
        self.assertEqual(data["ver"]["yt-dlp"], "fake")
        self.setUp()
        install_fake_ytdlp({"raw": {}})
        install_fake_gallery(True)
        code, (_, data) = self.run_helper("status", payload(""))
        self.assertEqual(data["t"], "status")
        self.assertIn("gallery-dl fake", data["msg"].split("\n"))
        self.assertIn("Download tools: ready", data["msg"])
        self.assertRegex(data["msg"], r"\nConverts with: [a-z0-9_, ]+\n")

    def test_tools_that_cannot_be_installed_are_reported(self):
        sys.modules["yt_dlp"] = None  # makes "import yt_dlp" raise ImportError
        install_fake_gallery(True)
        flag = os.path.join(WORK, ".fake-pip-fail")
        with open(flag, "w") as handle:
            handle.write("Could not find a version that satisfies the requirement yt-dlp")
        self.addCleanup(os.remove, flag)
        for command in ("setup", "run", "update"):
            self.out.seek(0)
            self.out.truncate()
            code, (_, data) = self.run_helper(command, payload("https://video.test/a"))
            self.assertEqual((data["t"], data["kind"]), ("error", "install"), command)
            self.assertIn("Could not install yt-dlp.", data["msg"])
            self.assertIn("Could not find a version", data["msg"])

    def test_another_protocol_or_command_is_reported_as_out_of_date(self):
        install_fake_ytdlp({"raw": {}})
        install_fake_gallery(True)
        code, (_, data) = self.run_helper("run", payload("https://video.test/a", p="1"))
        self.assertEqual((code, data["t"], data["kind"]), (2, "error", "outdated"))
        self.out.seek(0)
        self.out.truncate()
        code, (_, data) = self.run_helper("installed", payload(""))
        self.assertEqual((code, data["t"], data["kind"]), (2, "error", "outdated"))

    def test_update_notice_is_flat(self):
        clip = self.clip()
        install_fake_ytdlp({"raw": {"_type": "video", "id": "abc", "title": "T"},
                            "files": [("abc.mp4", clip, "T")]})
        install_fake_gallery(False)
        umdl.write_json(umdl.STATE_FILE, {"latest": {"v": "99.0.0", "url": "https://example.test/r",
                                                     "notes": ""},
                                          "meta_checked": 4102444800})
        original = umdl.check_project_updates
        umdl.check_project_updates = lambda state, version, force=False: state.get("latest")
        try:
            code, (_, data) = self.run_helper("run", payload("https://video.test/watch/abc"))
        finally:
            umdl.check_project_updates = original
        self.assertEqual((data["t"], data["upv"], data["upurl"]),
                         ("done", "99.0.0", "https://example.test/r"))

    def test_crash_still_calls_back(self):
        install_fake_ytdlp({"raw": {"_type": "video", "id": "x"}})
        install_fake_gallery(False)
        original = umdl.plan_engines
        umdl.plan_engines = lambda url: 1 / 0
        try:
            code, (_, data) = self.run_helper("run", payload("https://video.test/x"))
        finally:
            umdl.plan_engines = original
        self.assertEqual(code, 1)
        self.assertEqual((data["t"], data["kind"]), ("error", "unknown"))
        self.assertIn("ZeroDivisionError", data["msg"])


class RedditPosts(unittest.TestCase):
    """Where a Reddit post keeps its media, from the fields Reddit's JSON has."""

    def test_hosted_video(self):
        video = {"dash_url": "https://v.redd.it/x/DASHPlaylist.mpd?a=1", "hls_url": "h", "fallback_url": "f"}
        self.assertEqual(umdl.reddit_targets({"is_video": True, "secure_media": {"reddit_video": video}}),
                         ("video", video["dash_url"]))
        self.assertEqual(umdl.reddit_targets({"media": {"reddit_video": {"fallback_url": "f"}}}),
                         ("video", "f"))
        self.assertEqual(umdl.reddit_targets({"url": "https://v.redd.it/x9/"}),
                         ("video", "https://v.redd.it/x9/DASHPlaylist.mpd"))

    def test_gallery_keeps_its_order_and_asks_for_originals(self):
        post = {"is_gallery": True, "url": "https://www.reddit.com/gallery/1abcde",
                "gallery_data": {"items": [{"media_id": "b"}, {"media_id": "a"}, {"media_id": "gone"},
                                           {"media_id": "anim"}]},
                "media_metadata": {
                    "a": {"s": {"u": "https://preview.redd.it/a.png?width=640&s=1"}},
                    "b": {"s": {"u": "https://preview.redd.it/b.jpg?width=640&s=2"}},
                    "gone": {"status": "failed"},
                    "anim": {"s": {"gif": "https://i.redd.it/anim.gif", "mp4": "https://preview.redd.it/anim.mp4"}}}}
        self.assertEqual(umdl.reddit_targets(post),
                         ("files", ["https://i.redd.it/b.jpg", "https://i.redd.it/a.png",
                                    "https://i.redd.it/anim.gif"]))

    def test_single_image_crosspost_and_outside_link(self):
        self.assertEqual(umdl.reddit_targets({"url": "https://i.redd.it/one.jpg"}),
                         ("files", ["https://i.redd.it/one.jpg"]))
        crosspost = {"url": "https://www.reddit.com/r/a/comments/1/x/", "is_self": False,
                     "crosspost_parent_list": [{"url": "https://i.redd.it/orig.png"}]}
        self.assertEqual(umdl.reddit_targets(crosspost), ("files", ["https://i.redd.it/orig.png"]))
        self.assertEqual(umdl.reddit_targets({"url_overridden_by_dest": "https://imgur.com/a/xyz",
                                              "url": "https://imgur.com/a/xyz"}),
                         ("link", "https://imgur.com/a/xyz"))

    def test_text_post_has_nothing_to_download(self):
        for post in ({"is_self": True, "url": "https://www.reddit.com/r/a/comments/1/x/"},
                     {"is_self": True, "url": "https://example.com/mentioned-in-text"}, {}):
            with self.assertRaises(umdl.EngineError):
                umdl.reddit_targets(post)

    def test_which_links_are_reddit(self):
        for link in ("https://www.reddit.com/r/a/s/b", "https://old.reddit.com/x", "https://redd.it/abc"):
            self.assertTrue(umdl.is_reddit(link), link)
        for link in ("https://notreddit.com/x", "https://i.redd.it/a.jpg", "https://reddit.com.evil.test/"):
            self.assertFalse(umdl.is_reddit(link), link)


class SelfUpdate(Base):
    def setUp(self):
        super().setUp()
        with open(os.path.join(ROOT, "src", "umdl.py"), encoding="utf-8") as handle:
            self.published = handle.read()
        self.installed = os.path.join(WORK, "installed-umdl.py")
        with open(self.installed, "w", encoding="utf-8") as handle:
            handle.write("# the copy in a-Shell\n")
        self.addCleanup(setattr, umdl, "__file__", umdl.__file__)
        self.addCleanup(setattr, umdl, "fetch_text", umdl.fetch_text)
        umdl.__file__ = self.installed

    def installed_text(self):
        with open(self.installed, encoding="utf-8") as handle:
            return handle.read()

    def test_published_helper_replaces_the_installed_one(self):
        umdl.fetch_text = lambda url: self.published
        self.assertTrue(umdl.self_update())
        self.assertEqual(self.installed_text(), self.published)

    def test_a_download_cut_short_or_an_error_page_is_not_installed(self):
        cut = self.published[:self.published.index("def main(argv):") + 400]
        for source in ("", "<html>Not found</html>", cut, self.published + "\nthis is not python ("):
            umdl.fetch_text = lambda url, source=source: source
            self.assertFalse(umdl.self_update())
            self.assertEqual(self.installed_text(), "# the copy in a-Shell\n")


class SignIns(Base):
    def setUp(self):
        super().setUp()
        umdl.remove(umdl.SAFARI_COOKIES)
        self.addCleanup(umdl.remove, umdl.SAFARI_COOKIES)
        plan = os.path.join(WORK, ".fake-signin")
        self.addCleanup(lambda: os.path.exists(plan) and os.remove(plan))
        self.plan = plan
        self.wait = umdl.SIGNIN_WAIT
        umdl.SIGNIN_WAIT = 1
        self.addCleanup(setattr, umdl, "SIGNIN_WAIT", self.wait)

    def test_cookie_store_is_read_without_its_values(self):
        cookiejar.write(umdl.SAFARI_COOKIES, [(".Instagram.com", "sessionid", 2000000000),
                                              ("example.org", "théme")])
        self.assertEqual(umdl.read_cookie_store(),
                         [(".instagram.com", "sessionid", 2000000000.0),
                          ("example.org", "théme", 4102444800.0)])

    def test_missing_or_damaged_store_is_no_sign_ins(self):
        self.assertIsNone(umdl.read_cookie_store())
        os.makedirs(os.path.dirname(umdl.SAFARI_COOKIES), exist_ok=True)
        for junk in (b"", b"cook", b"not a cookie file at all", b"cook\x00\x00\x00\x09short"):
            with open(umdl.SAFARI_COOKIES, "wb") as handle:
                handle.write(junk)
            self.assertFalse(umdl.read_cookie_store(), junk)
        self.assertEqual(umdl.sign_in_lines(None), ["No sign-ins are stored."])

    def test_signed_in_needs_the_sites_own_session_cookie(self):
        now = 1900000000
        cookies = [(".instagram.com", "csrftoken", 0), (".x.com", "auth_token", now + 60),
                   (".reddit.com", "reddit_session", now - 60), ("notreddit.com", "reddit_session", 0),
                   ("forum.example.org", "PHPSESSID", 0), ("ads.example.net", "uid", 0)]
        self.assertFalse(umdl.signed_in("www.instagram.com", cookies, now))   # visited only
        self.assertTrue(umdl.signed_in("twitter.com", cookies, now))          # same site as x.com
        self.assertFalse(umdl.signed_in("old.reddit.com", cookies, now))      # expired
        self.assertTrue(umdl.signed_in("example.org", cookies, now))          # generic session cookie
        self.assertFalse(umdl.signed_in("example.net", cookies, now))

    def test_sign_in_waits_for_the_cookie_then_confirms(self):
        with open(self.plan, "w") as handle:
            json.dump([[".tiktok.com", "sid_tt"]], handle)
        code, (_, data) = self.run_helper("signin", payload("https://www.tiktok.com/@someone/video/1"))
        self.assertEqual((data["t"], data["title"]), ("info", "Signed in to TikTok"))
        with open(os.path.join(WORK, "browser.log")) as handle:
            self.assertEqual(handle.read().split()[-1], "https://www.tiktok.com/login")

    def test_sign_in_gives_up_politely(self):
        code, (_, data) = self.run_helper("signin", payload("https://www.facebook.com/x"))
        self.assertEqual((data["t"], data["title"]), ("info", "Sign-in not confirmed"))

    def test_forgetting_sign_ins_shows_in_status(self):
        cookiejar.write(umdl.SAFARI_COOKIES, [(".facebook.com", "c_user")])
        self.assertIn("Facebook: signed in", umdl.sign_in_lines(umdl.read_cookie_store()))
        self.run_helper("logout", payload(""))
        self.assertEqual(umdl.sign_in_lines(umdl.read_cookie_store()), ["No sign-ins are stored."])


def tearDownModule():
    shutil.rmtree(WORK, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

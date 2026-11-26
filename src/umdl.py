#!/usr/bin/env python3
"""UMDL helper.

Runs inside a-Shell on iOS/iPadOS. The UMDL shortcut hands it one base64
JSON payload; it downloads the media with yt-dlp or gallery-dl, makes the
result importable by Photos, and calls the shortcut back with the outcome.

Usage (the shortcut builds these commands, you never need to type them):
    python umdl.py run <payload>        download the link in the payload
    python umdl.py setup <payload>      install the download tools and report
    python umdl.py update <payload>     force-update the download tools
    python umdl.py status <payload>     report versions, sign-ins and storage
    python umdl.py signin <payload>     open a site's sign-in page and confirm the sign-in
    python umdl.py logout <payload>     sign out of every site
    python umdl.py reset <payload>      remove UMDL, the tools and the sign-ins from a-Shell

Project: https://github.com/TheKfcBandit/UMDL   Licence: MIT
"""

import base64
import copy
import hashlib
import importlib
import importlib.util
import itertools
import json
import os
import re
import shlex
import shutil
import site
import struct
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse

HELPER_VERSION = "1.6.0"
# Bumped only when the payload/callback format changes incompatibly.
PROTOCOL = 6

REPO = "TheKfcBandit/UMDL"
RAW_BASE = "https://raw.githubusercontent.com/%s/main" % REPO
RELEASES_URL = "https://github.com/%s/releases/latest" % REPO
CALLBACK_PREFIX = "UMDLCB:"

HOME = os.path.expanduser("~")
WORKSPACE = os.environ.get("UMDL_HOME") or os.path.join(HOME, "Documents", "UMDL")
JOBS_DIR = os.path.join(WORKSPACE, "Working")
SAVED_DIR = os.path.join(WORKSPACE, "Saved")
STATE_FILE = os.path.join(WORKSPACE, "state.json")
LAST_FILE = os.path.join(WORKSPACE, "last.b64")
LOG_FILE = os.path.join(WORKSPACE, "last.log")
SAFARI_COOKIES = os.path.join(HOME, "Library", "Cookies", "Cookies.binarycookies")

# pip package name -> module that proves it is installed.
REQUIRED_TOOLS = {"yt-dlp": "yt_dlp", "gallery-dl": "gallery_dl"}
# Needed by yt-dlp for YouTube on iOS. A failure here must not block other sites.
OPTIONAL_TOOLS = ["yt-dlp-ejs", "yt-dlp-apple-webkit-jsi"]

DAY = 86400

# a-Shell hands files to Shortcuts by loading them into memory (its "as a copy"
# mode, the only one that works on iOS 27.2). Around 2 GB that times out, so
# anything above this size is kept in Files instead of being sent to Photos.

# Sites UMDL can open a sign-in page for: name, domains, the cookies that mean
# "signed in", and the page to sign in on.
SITES = (
    ("Instagram", ("instagram.com",), ("sessionid",), "https://www.instagram.com/accounts/login/"),
    ("X (Twitter)", ("x.com", "twitter.com"), ("auth_token",), "https://x.com/i/flow/login"),
    ("Reddit", ("reddit.com",), ("reddit_session",), "https://www.reddit.com/login/"),
    ("TikTok", ("tiktok.com",), ("sessionid", "sid_tt", "sid_guard"), "https://www.tiktok.com/login"),
    ("Facebook", ("facebook.com",), ("c_user",), "https://m.facebook.com/login/"),
)
# For any other site: cookie names that usually mean a signed-in session.
SESSION_COOKIE = re.compile(r"sess|auth|token|login|logged|(^|[_-])sid($|[_-])|user", re.I)
SIGNIN_WAIT = int(os.environ.get("UMDL_SIGNIN_WAIT") or 600)

# A site turning the request away because of where it comes from, not who is asking.
BLOCKED = re.compile(r"blocked by network security|unable to access the reddit api|403:? blocked", re.I)
# Reddit refuses its website's JSON to many networks, signed in or not, and
# points to its API instead. gallery-dl can use that API with a public token.
# The empty refresh-token keeps gallery-dl 1.32 off a code path that crashes.
REDDIT_API = ["-o", "api=oauth", "-o", "refresh-token="]

IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "heic", "heif", "webp", "tif", "tiff", "bmp", "avif"}
VIDEO_EXTS = {"mp4", "m4v", "mov", "mkv", "webm", "flv", "ts", "avi", "3gp", "wmv", "mpg", "mpeg", "ogv"}
JUNK_EXTS = {"part", "ytdl", "tmp", "temp", "json", "description", "txt", "vtt", "srt", "ass", "lrc"}
PHOTOS_CONTAINERS = {"mp4", "m4v", "mov"}
PHOTOS_VCODECS = {"h264", "hevc"}
PHOTOS_ACODECS = {"aac", "alac", "ac3", "eac3"}

# Hosts where a post is often images (or images and video mixed), so
# gallery-dl goes first and yt-dlp is the fallback.
GALLERY_FIRST = (
    "twitter.com", "x.com", "instagram.com", "threads.net", "threads.com",
    "reddit.com", "redd.it", "tumblr.com", "bsky.app", "imgur.com",
    "pinterest.", "pin.it", "pixiv.net", "flickr.com", "flic.kr",
    "deviantart.com", "artstation.com", "danbooru.", "gelbooru.", "e621.net",
    "kemono.", "coomer.", "fanbox.cc", "patreon.com", "weibo.", "500px.com",
    "unsplash.com", "wallhaven.cc", "imgbb.com", "ibb.co", "postimg.",
    "catbox.moe", "civitai.com", "vsco.co", "mastodon.", "misskey.",
    "newgrounds.com", "furaffinity.net", "behance.net", "lofter.com",
)

RES_CHOICES = ("2160", "1440", "1080", "720", "480")
FPS_CHOICES = ("60", "30")


def settings_from(cfg):
    """The two limits on which version is downloaded, whatever was stored."""
    cfg = cfg if isinstance(cfg, dict) else {}
    res, fps = str(cfg.get("res") or "best"), str(cfg.get("fps") or "best")
    return {"res": res if res in RES_CHOICES else "best",
            "fps": fps if fps in FPS_CHOICES else "best"}


def ytdlp_format(quality):
    """Which formats yt-dlp should take: the best there is. ytdlp_sort() says
    what "best" means.

    A frame rate limit is applied here, as a filter with the unfiltered choice
    as its fallback: versions above the limit are passed over, whatever their
    size, unless the site has nothing else.
    """
    best = "bv*+ba/b/ba"
    if quality["fps"] == "best":
        return best
    return "bv*[fps<=?%(fps)s]+ba/b[fps<=?%(fps)s]/" % quality + best


def hardware_decodes(fourcc):
    """Whether this device reads a codec ("av01") with its own chip."""
    forced = os.environ.get("UMDL_TEST_HARDWARE")
    if forced is not None:
        return fourcc in forced.split(",")
    if not IOS:
        return False
    try:
        import ctypes
        toolbox = ctypes.CDLL("/System/Library/Frameworks/VideoToolbox.framework/VideoToolbox")
        check = toolbox.VTIsHardwareDecodeSupported
        check.restype = ctypes.c_bool
        check.argtypes = [ctypes.c_uint32]
        return bool(check(int.from_bytes(fourcc.encode("ascii"), "big")))
    except Exception:
        return False


def av1_verdict():
    """(whether AV1 is the version to take, why) on this device.

    It is, when the chip reads AV1, so Photos may take the file as it is; when
    this ffmpeg can read it too, so a refusal still ends in Photos; and when
    Photos has not already turned an AV1 file down here."""
    if not hardware_decodes("av01"):
        return False, "not taken, the chip does not read it"
    if not {"libdav1d", "libaom-av1"} & ffmpeg_has("-decoders"):
        return False, "not taken, this ffmpeg could not convert it"
    if read_json(STATE_FILE, {}).get("av1_refused"):
        return False, "not taken, Photos turned it down"
    return True, "taken where a site has it"


def av1_goes_in():
    return av1_verdict()[0]


def choose_formats(formats, quality, av1_in_hardware):
    """Among the versions yt-dlp ranks best in size and frame rate, pick the
    codec that costs least afterwards. `formats` is yt-dlp's list, worst first.

    H.264 and HEVC go into Photos as they are. AV1 does too on a device whose
    chip reads it, and converts quickly there if not. VP9 is always read in
    software, which is slow at 4K. Returns "video+audio" format ids, or "".
    """
    def rank(fmt):
        code = str(fmt.get("vcodec") or "").lower()
        if re.match(r"avc|h264|hev|hvc|h265", code):
            return 3
        if re.match(r"av0?1", code):
            return 2 if av1_in_hardware else 0
        return 1 if re.match(r"vp0?9", code) else 0

    def size(fmt):
        return min(fmt.get("width") or 0, fmt.get("height") or 0) or fmt.get("height") or 0

    formats = [f for f in formats or [] if isinstance(f, dict) and f.get("format_id") and not f.get("has_drm")]
    videos = [f for f in formats if str(f.get("vcodec") or "none") != "none"]
    if not videos:
        return ""
    if quality["fps"] != "best":
        videos = [f for f in videos if (f.get("fps") or 0) <= int(quality["fps"])] or videos
    best = videos[-1]
    equals = [(rank(f), index, f) for index, f in enumerate(videos)
              if size(f) == size(best) and round(f.get("fps") or 0) == round(best.get("fps") or 0)]
    video = max(equals, key=lambda entry: entry[:2])[2]
    if str(video.get("acodec") or "none") != "none":
        return video["format_id"]
    sounds = [f for f in formats if str(f.get("vcodec") or "none") == "none"
              and str(f.get("acodec") or "none") != "none"]
    return video["format_id"] + ("+" + sounds[-1]["format_id"] if sounds else "")


def ytdlp_sort(quality):
    """What "best" means, as yt-dlp sort fields, most important first.

    The largest picture, up to the resolution limit if one is set ("res:1080"
    also means: the smallest above it when nothing fits; "res" is the short
    side, so a tall phone video counts by its width). Then the highest frame
    rate. Between versions equal in both, one Photos plays as it is:
    converting cannot add quality, only lose a little. The same goes for the
    sound.
    """
    return [
        "lang",
        "res" if quality["res"] == "best" else "res:" + quality["res"],
        "fps" if quality["fps"] == "best" else "fps:" + quality["fps"],
        "vcodec:h265",
        "acodec:aac",
    ]


# ---- describing and choosing formats (advanced mode)

CODEC_NAMES = (
    (r"avc|h264", "H.264"), (r"hev|hvc|h265|hevc", "HEVC"), (r"vp0?9", "VP9"), (r"av0?1", "AV1"),
    (r"vp0?8", "VP8"), (r"mp4a|aac", "AAC"), (r"opus", "Opus"), (r"vorbis", "Vorbis"),
    (r"ec-?3|eac3", "E-AC-3"), (r"ac-?3", "AC-3"), (r"alac", "ALAC"), (r"flac", "FLAC"),
    (r"mp3", "MP3"),
)


def codec_name(code):
    code = str(code or "").lower()
    for pattern, name in CODEC_NAMES:
        if re.match(pattern, code):
            return name
    return code.split(".")[0].upper() or "unknown"


def detect_ios():
    forced = os.environ.get("UMDL_PLATFORM")
    if forced:
        return forced == "ios"
    if sys.platform == "ios":
        return True
    # a-Shell's Python reports "darwin"; the app sandbox path gives it away.
    return "/Containers/Data/Application/" in HOME or HOME.startswith("/var/mobile")


IOS = detect_ios()
OUT = sys.stdout


# ---------------------------------------------------------------- terminal UI

class UI:
    """Small status display: steps with a spinner, and a progress bar."""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self):
        self.color = IOS or (hasattr(OUT, "isatty") and OUT.isatty())
        if os.environ.get("NO_COLOR"):
            self.color = False
        self.live = self.color
        self._spin = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._label = ""

    def c(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.color else text

    def write(self, text):
        try:
            OUT.write(text)
            OUT.flush()
        except Exception:
            pass

    def header(self, subtitle):
        if self.live:
            self.write("\033[2J\033[H")
        self.write("\n  %s %s\n" % (self.c("1;94", "UMDL"), self.c("2", HELPER_VERSION)))
        self.write("  %s\n\n" % self.c("2", subtitle))

    def _clear_line(self):
        if self.live:
            self.write("\r\033[2K")

    def start(self, label):
        self.stop_spinner()
        self._label = label
        if not self.live:
            self.write("  - %s\n" % label)
            return
        self._stop.clear()

        def spin():
            for frame in itertools.cycle(self.FRAMES):
                if self._stop.is_set():
                    return
                with self._lock:
                    self.write("\r\033[2K  %s %s" % (self.c("93", frame), self._label))
                time.sleep(0.09)

        self._spin = threading.Thread(target=spin, daemon=True)
        self._spin.start()

    def stop_spinner(self):
        if self._spin is not None:
            self._stop.set()
            self._spin.join(timeout=1)
            self._spin = None
            self._clear_line()

    def done(self, detail=""):
        label = self._label
        self.stop_spinner()
        tail = ("  " + self.c("2", detail)) if detail else ""
        self.write("  %s %s%s\n" % (self.c("92", "✓"), label, tail))

    def fail(self, detail=""):
        label = self._label
        self.stop_spinner()
        tail = ("  " + self.c("2", detail)) if detail else ""
        self.write("  %s %s%s\n" % (self.c("91", "✗"), label, tail))

    def note(self, text):
        self.stop_spinner()
        self.write("    %s\n" % self.c("2", text))

    def progress(self, prefix, fraction, extra=""):
        """Redraw a one-line progress bar. fraction None means unknown size."""
        if not self.live:
            return
        self.stop_spinner()
        width = 18
        if fraction is None:
            bar = self.c("2", "░" * width)
            pct = "  …"
        else:
            fraction = max(0.0, min(1.0, fraction))
            filled = int(round(fraction * width))
            bar = self.c("94", "█" * filled) + self.c("2", "░" * (width - filled))
            pct = "%3d%%" % int(fraction * 100)
        with self._lock:
            self.write("\r\033[2K  %s %s %s %s" % (prefix, bar, pct, self.c("2", extra)))

    def end_progress(self, line):
        self._clear_line()
        self.write("  %s %s\n" % (self.c("92", "✓"), line))


ui = UI()


# ------------------------------------------------------------------- helpers

class EngineError(Exception):
    """One download tool could not handle the link; the next one may."""


class NeedConfirm(Exception):
    """The link holds more items than the ask-first threshold."""

    def __init__(self, count, title):
        Exception.__init__(self, "confirmation needed")
        self.count = count  # exact count, or None when only "more than" is known
        self.title = title


def log(text):
    try:
        if not os.path.isdir(WORKSPACE):
            return  # after a reset there is nowhere to write, and nothing should reappear
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(text.rstrip("\n") + "\n")
    except Exception:
        pass


def strip_ansi(text):
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", text or "")


def run_cmd(args):
    """Run a command and return (exit code, stdout, stderr).

    a-Shell has no fork/exec: its patched subprocess takes a command line,
    so on iOS the arguments are joined into one string.
    """
    cmd = " ".join(shlex.quote(a) for a in args) if IOS else args
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception as exc:
        return 127, "", str(exc)


def read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle)
    os.replace(tmp, path)


def remove(path):
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def to_int(value, default):
    try:
        return int(str(value).strip())
    except Exception:
        return default


def truthy(value):
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def parse_version(text):
    parts = re.findall(r"\d+", str(text or ""))
    return tuple(int(p) for p in parts[:4]) or (0,)


def newer(candidate, current):
    return parse_version(candidate) > parse_version(current)


def decode_payload(blob):
    blob = (blob or "").strip()
    blob += "=" * (-len(blob) % 4)
    data = json.loads(base64.b64decode(blob).decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("payload is not an object")
    cfg = data.get("cfg")
    if not isinstance(cfg, dict):
        data["cfg"] = {}
    return data


def clean_url(text):
    """Pull the first http(s) URL out of whatever was shared."""
    match = re.search(r"https?://[^\s<>\"']+", text or "")
    if not match:
        return ""
    return match.group(0).rstrip(").,;]}>")


def hostname(url):
    try:
        return (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return ""


def prefers_gallery(host):
    for pattern in GALLERY_FIRST:
        if pattern.endswith("."):
            if host.startswith(pattern) or ("." + pattern) in ("." + host):
                return True
        elif host == pattern or host.endswith("." + pattern):
            return True
    return False


def job_id_for(url):
    return hashlib.md5(url.encode("utf-8")).hexdigest()[:16]


def ext_of(path):
    return os.path.splitext(path)[1].lstrip(".").lower()


def safe_title(text, fallback):
    text = re.sub(r"[\x00-\x1f/\\:*?\"<>|]+", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:80] or fallback


def classify_error(message):
    """Map a tool's error text to a kind the shortcut can act on."""
    low = (message or "").lower()
    rules = (
        ("drm", ("drm",)),
        ("auth", ("login", "log in", "sign in", "signed in", "cookies", "private",
                  "age-restricted", "confirm your age", "authenticat", "members-only",
                  "members only", "subscriber", "401", "403", "not authorized",
                  "unauthorized", "requires payment", "premium")),
        ("network", ("timed out", "timeout", "getaddrinfo", "name resolution",
                     "network is unreachable", "connection reset", "connection refused",
                     "connection aborted", "ssl", "temporary failure", "no route to host",
                     "offline", "remote end closed")),
        ("unsupported", ("unsupported url", "no suitable extractor", "no extractor",
                         "not supported")),
        ("gone", ("404", "not found", "unavailable", "removed", "deleted",
                  "does not exist", "no longer available", "geo", "not available in your",
                  "no video formats", "nothing to download", "no media")),
    )
    for kind, needles in rules:
        if any(n in low for n in needles):
            return kind
    return "unknown"


def tidy_error(message):
    text = strip_ansi(str(message or "")).strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    text = lines[-1] if lines else "Unknown error"
    text = re.sub(r"^(ERROR|error):\s*", "", text)
    text = re.sub(r"^\[[^\]]+\]\[error\]\s*", "", text)
    text = re.sub(r";? ?please report this issue.*$", "", text, flags=re.I | re.S)
    text = re.sub(r"\s*\(caused by .*\)\s*$", "", text, flags=re.S)
    return text[:280]


def have_cookies():
    try:
        return os.path.getsize(SAFARI_COOKIES) > 0
    except Exception:
        return False


# ------------------------------------------------------------------ callback

def read_cookie_store(path=None):
    """Read a-Shell's cookie store (Apple's binarycookies format).

    Returns a list of (domain, name, expires) with expires in Unix time, or
    None when there is no readable store. Values are never read.
    """
    try:
        with open(path or SAFARI_COOKIES, "rb") as handle:
            data = handle.read()
    except Exception:
        return None
    if data[:4] != b"cook" or len(data) < 8:
        return None
    cookies = []
    try:
        pages = struct.unpack(">i", data[4:8])[0]
        sizes = struct.unpack(">%di" % pages, data[8:8 + 4 * pages])
        offset = 8 + 4 * pages
        for size in sizes:
            page = data[offset:offset + size]
            offset += size
            if len(page) < 8:
                continue
            count = struct.unpack("<i", page[4:8])[0]
            starts = struct.unpack("<%di" % count, page[8:8 + 4 * count])
            for start in starts:
                try:
                    length = struct.unpack("<i", page[start:start + 4])[0]
                    record = page[start:start + length]
                    domain_at, name_at = struct.unpack("<ii", record[16:24])
                    expires = struct.unpack("<d", record[40:48])[0]

                    def text(at):
                        end = record.index(b"\x00", at)
                        return record[at:end].decode("utf-8", "replace")

                    # Apple counts seconds from 1 January 2001.
                    cookies.append((text(domain_at).lower(), text(name_at),
                                    expires + 978307200 if expires else 0))
                except Exception:
                    continue
    except Exception:
        return cookies or None
    return cookies


def site_for(host):
    """The SITES entry a host belongs to, or None."""
    for entry in SITES:
        if any(host == d or host.endswith("." + d) for d in entry[1]):
            return entry
    return None


def base_domain(host):
    parts = [p for p in host.split(".") if p]
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def signed_in(host, cookies, now=None):
    """Whether the cookie store holds a session for this host."""
    now = now or time.time()
    entry = site_for(host)
    domains = entry[1] if entry else (base_domain(host),)
    for domain, name, expires in cookies or []:
        domain = domain.lstrip(".")
        if not any(domain == d or domain.endswith("." + d) for d in domains):
            continue
        if expires and expires < now:
            continue
        if entry:
            if name in entry[2]:
                return True
        elif SESSION_COOKIE.search(name):
            return True
    return False


def sign_in_lines(cookies):
    """One line per known site, then a count of other sites holding cookies."""
    if cookies is None:
        return ["No sign-ins are stored."]
    lines = ["%s: %s" % (entry[0], "signed in" if signed_in(entry[1][0], cookies) else "not signed in")
             for entry in SITES]
    known = [d for entry in SITES for d in entry[1]]
    others = sorted({base_domain(domain.lstrip(".")) for domain, name, _ in cookies
                     if SESSION_COOKIE.search(name)} - set(known))
    others = [d for d in others if not any(d.endswith("." + k) for k in known)]
    if others:
        shown = ", ".join(others[:6]) + (" and %d more" % (len(others) - 6) if len(others) > 6 else "")
        lines.append("Other sites that may be signed in: " + shown)
    return lines


def callback(payload, data):
    """Hand the result to the shortcut by re-running it through its URL scheme."""
    ui.stop_spinner()
    data.setdefault("cfg", payload.get("cfg") or {})
    data["hv"] = HELPER_VERSION
    raw = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    blob = base64.b64encode(raw.encode("utf-8")).decode("ascii")
    name = str(payload.get("name") or "UMDL")
    url = "shortcuts://run-shortcut?name=%s&input=text&text=%s" % (
        urllib.parse.quote(name, safe=""),
        urllib.parse.quote(CALLBACK_PREFIX + blob, safe=""),
    )
    if data.get("t") in ("done", "error", "confirm"):
        remove(LAST_FILE)  # that download has had its answer; nothing is left to resume
    if data.get("t") != "status":  # the status report would only repeat itself in the log
        log("callback: " + raw[:2000])
        log("handing back to Shortcuts at " + time.strftime("%H:%M:%S"))
    if IOS:
        subprocess.run("open " + url)
    else:
        OUT.write("CALLBACK %s\n" % url)
        OUT.flush()
    return data


# ------------------------------------------------------------------- updates

class InstallError(Exception):
    """The download tools are missing and could not be installed."""


def pip_commands():
    override = os.environ.get("UMDL_PIP")  # tests point this at a stand-in
    if override:
        return [shlex.split(override)]
    return [["pip"], ["python", "-m", "pip"]]


def pip_install(packages):
    """Install or upgrade packages. Returns (ok, last lines of pip's output)."""
    tail = ""
    for command in pip_commands():
        code, out, err = run_cmd(command + ["install", "-q", "--disable-pip-version-check",
                                            "--upgrade"] + packages)
        tail = strip_ansi((err or out).strip())[-400:]
        log("%s install %s -> %s %s" % (" ".join(command), " ".join(packages), code, tail))
        if code == 0:
            return True, tail
    return False, tail


def refresh_import_paths():
    """Let this process see packages pip has just installed. A folder that did
    not exist when Python started is not on sys.path yet."""
    importlib.invalidate_caches()
    candidates = []
    try:
        candidates.append(site.getusersitepackages())
    except Exception:
        pass
    try:
        candidates.extend(site.getsitepackages())
    except Exception:
        pass
    for folder in candidates:
        if folder and os.path.isdir(folder) and folder not in sys.path:
            site.addsitedir(folder)


def use_site_dirs(folders):
    """Search extra folders for Python packages. Returns the ones added."""
    added = []
    for folder in folders or []:
        if isinstance(folder, str) and os.path.isdir(folder) and folder not in sys.path:
            site.addsitedir(folder)
            # Tools started as separate commands (gallery-dl) need it as well.
            current = os.environ.get("PYTHONPATH", "")
            os.environ["PYTHONPATH"] = folder + (os.pathsep + current if current else "")
            added.append(folder)
    if added:
        importlib.invalidate_caches()
    return added


def adopt_install_location(state, packages):
    """pip can install into a folder this Python is not searching. Ask pip
    where the packages went, search there too, and remember it for next time."""
    added = []
    for command in pip_commands():
        code, out, _ = run_cmd(command + ["show"] + list(packages))
        if code == 0:
            added = use_site_dirs(re.findall(r"(?m)^Location:\s*(.+?)\s*$", out))
            break
    if added:
        state["site_dirs"] = sorted(set(list(state.get("site_dirs") or []) + added))
        log("adopted install location: " + ", ".join(added))
    return added


def missing_tools():
    refresh_import_paths()
    missing = []
    for package, module in REQUIRED_TOOLS.items():
        loaded = sys.modules.get(module, False)
        if loaded is not False:
            found = loaded is not None
        else:
            try:
                found = importlib.util.find_spec(module) is not None
            except Exception:
                found = False
        if not found:
            missing.append(package)
    return missing


def ensure_tools(state, force=False):
    """Install the download tools if they are missing, and upgrade them at
    most once a day. Sites change often, so a stale extractor is the most
    common cause of a failed download.

    Returns True when an upgrade ran. Raises InstallError when a required
    tool is missing and cannot be installed.
    """
    now = time.time()
    missing = missing_tools()
    if missing:
        ui.start("Installing download tools (first run only)")
        tail = ""
        # One package at a time: a failure in one must not hold back the rest.
        for package in list(REQUIRED_TOOLS) + OPTIONAL_TOOLS:
            ok, output = pip_install([package])
            if not ok and package in REQUIRED_TOOLS:
                tail = output
        missing = missing_tools()
        if missing and adopt_install_location(state, missing):
            missing = missing_tools()
        if missing:
            ui.fail()
            detail = tidy_error(tail) if tail else (
                "pip reported success, but Python cannot find the packages.")
            raise InstallError("Could not install %s. %s" % (" and ".join(missing), detail))
        state["tools_checked"] = now
        ui.done()
        return True
    if os.environ.get("UMDL_SKIP_UPDATES"):
        return False
    if not force and now - float(state.get("tools_checked", 0)) < DAY:
        return False
    ui.start("Updating download tools")
    ok, _ = pip_install(list(REQUIRED_TOOLS) + OPTIONAL_TOOLS)
    if not ok:
        # One optional package failing should not stop the important ones.
        ok = all([pip_install([package])[0] for package in REQUIRED_TOOLS])
    if ok:
        state["tools_checked"] = now
        ui.done()
    else:
        # Offline or PyPI trouble: carry on with what is installed, retry in an hour.
        state["tools_checked"] = now - DAY + 3600
        ui.fail("skipped, will retry later")
    return ok


def fetch_text(url):
    code, out, _ = run_cmd(["curl", "-fsL", "--max-time", "12", url])
    return out if code == 0 else ""


def check_project_updates(state, shortcut_version, force=False):
    """Once a day: self-update this helper and note any newer shortcut release."""
    if os.environ.get("UMDL_SKIP_UPDATES"):
        return None
    now = time.time()
    if force or now - float(state.get("meta_checked", 0)) >= DAY:
        try:
            meta = json.loads(fetch_text(RAW_BASE + "/version.json") or "{}")
        except Exception:
            meta = {}
        if isinstance(meta, dict) and meta.get("shortcut"):
            state["meta_checked"] = now
            state["latest"] = {
                "v": str(meta.get("shortcut")),
                "url": str(meta.get("url") or RELEASES_URL),
                "notes": str(meta.get("notes") or "")[:300],
            }
            same_protocol = to_int(meta.get("protocol"), PROTOCOL) == PROTOCOL
            if same_protocol and newer(meta.get("helper"), HELPER_VERSION):
                self_update()
    latest = state.get("latest") or {}
    if latest.get("v") and newer(latest["v"], shortcut_version):
        return latest
    return None


def self_update():
    """Replace this script with the published one, if it at least compiles."""
    target = os.path.abspath(__file__)
    source = fetch_text(RAW_BASE + "/src/umdl.py")
    # The last line must be there too: a download cut short can still compile.
    if ("HELPER_VERSION" not in source or "def main" not in source
            or not source.rstrip().endswith("sys.exit(main(sys.argv))")):
        return False
    try:
        compile(source, "umdl.py", "exec")
        tmp = target + ".new"
        with open(tmp, "w", encoding="utf-8") as handle:
            handle.write(source)
        os.replace(tmp, target)
        log("helper updated; takes effect on the next run")
        return True
    except Exception as exc:
        log("helper update failed: %s" % exc)
        return False


def tool_versions():
    versions = {}
    try:
        import yt_dlp
        versions["yt-dlp"] = yt_dlp.version.__version__
    except Exception as exc:
        versions["yt-dlp"] = "missing (%s)" % type(exc).__name__
    try:
        import gallery_dl
        versions["gallery-dl"] = gallery_dl.version.__version__
    except Exception as exc:
        versions["gallery-dl"] = "missing (%s)" % type(exc).__name__
    code, out, err = run_cmd(["ffmpeg", "-version"])
    match = re.search(r"ffmpeg version (\S+)", out + err)
    versions["ffmpeg"] = match.group(1) if match else "missing"
    versions["helper"] = HELPER_VERSION
    versions["python"] = "%d.%d.%d" % sys.version_info[:3]
    return versions


# ------------------------------------------------------------ engine: yt-dlp

class YtLogger:
    def __init__(self):
        self.errors = []

    def debug(self, msg):
        # Which JavaScript runtime solved YouTube's challenges is worth a line.
        if "[jsc" in str(msg):
            log("yt-dlp: " + strip_ansi(str(msg))[:200])

    def info(self, msg):
        pass

    def warning(self, msg):
        log("yt-dlp warning: " + strip_ansi(str(msg)))

    def error(self, msg):
        text = strip_ansi(str(msg))
        self.errors.append(text)
        log("yt-dlp error: " + text)


# yt-dlp solves YouTube's JavaScript challenges with a script that, to look
# like a page of the site, assigns "https://www.youtube.com/watch?v=yt-dlp-wins"
# to the page's location. In the stand-alone runtimes it was written for that
# only sets a variable. In a-Shell the script runs in a real web view, where
# the same line is a navigation, and iOS answers a navigation to a YouTube
# address by opening the YouTube app, on a video that does not exist. a-Shell
# is then no longer in front and cannot hand the result to Shortcuts.
SOLVER_NAVIGATION = re.compile(r"(globalThis(?:\.window)?)\.location(\s*=(?!=))")
_SOLVER = {"hooked": False, "noted": False}


def tame_solver():
    """Make that assignment set an ordinary variable when the runtime is a web
    view. The script works without it there: the page already has a location,
    and the challenges were being solved before the navigation took effect."""
    if _SOLVER["hooked"]:
        return True
    try:
        from yt_dlp.extractor.youtube.jsc._builtin.ejs import EJSBaseJCP
        original = EJSBaseJCP._construct_stdin
    except Exception as exc:
        if not _SOLVER["noted"]:
            _SOLVER["noted"] = True
            log("solver: nothing to adjust in this yt-dlp (%s)" % type(exc).__name__)
        return False

    def construct(self, *args, **kwargs):
        script = original(self, *args, **kwargs)
        name = "%s %s" % (type(self).__name__, getattr(self, "JS_RUNTIME_NAME", ""))
        if "webkit" not in name.lower() or not isinstance(script, str):
            return script
        script, changed = SOLVER_NAVIGATION.subn(r"\1.umdlLocation\2", script)
        if not _SOLVER["noted"]:
            _SOLVER["noted"] = True
            log("solver: runs in a web view; %d page navigation%s removed"
                % (changed, "" if changed == 1 else "s"))
        return script

    EJSBaseJCP._construct_stdin = construct
    _SOLVER["hooked"] = True
    return True


def ytdlp_extractor_name(url):
    """Name of the dedicated yt-dlp extractor for this URL, or None."""
    try:
        from yt_dlp.extractor import gen_extractor_classes
    except Exception:
        return None
    for klass in gen_extractor_classes():
        try:
            if klass.IE_NAME != "generic" and klass.suitable(url):
                return klass.IE_NAME
        except Exception:
            continue
    return None


def human_rate(value):
    if not value:
        return ""
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if value < 1024 or unit == "GB/s":
            return "%.1f %s" % (value, unit)
        value /= 1024.0
    return ""


def human_eta(seconds):
    if seconds is None:
        return ""
    seconds = int(seconds)
    return "%d:%02d" % (seconds // 60, seconds % 60)


def count_entries(entries, cap):
    """Count playlist entries without walking an endless feed.
    Returns (count, exact)."""
    if entries is None:
        return 0, True
    try:
        return len(entries), True
    except Exception:
        pass
    try:
        count = sum(1 for _ in itertools.islice(entries, cap))
        return count, count < cap
    except Exception:
        pass
    try:
        count = len(entries.getslice(0, cap))  # yt-dlp PagedList
        return count, count < cap
    except Exception:
        return cap, False


def ytdlp_engine(ctx):
    try:
        import yt_dlp
    except Exception as exc:
        raise EngineError("yt-dlp is not installed (%s)" % exc)
    tame_solver()

    logger = YtLogger()
    titles = ctx["titles"]
    counter = {"n": 0}

    def on_progress(d):
        info = d.get("info_dict") or {}
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            done = d.get("downloaded_bytes") or 0
            index = info.get("playlist_index") or counter["n"] + 1
            count = info.get("n_entries") or info.get("playlist_count")
            prefix = "%s/%s" % (index, count) if count and count > 1 else "↓"
            extra = "  ".join(x for x in (human_rate(d.get("speed")), human_eta(d.get("eta"))) if x)
            ui.progress(prefix, (float(done) / total) if total else None, extra)
        elif d.get("status") == "finished":
            name = d.get("filename") or ""
            if info.get("title"):
                titles[os.path.basename(name)] = info["title"]
                ctx["title"] = ctx.get("title") or info["title"]

    def on_post(d):
        if d.get("status") == "started" and d.get("postprocessor") in ("Merger", "FFmpegMerger"):
            ui.progress("⧉", None, "joining video and audio")

    skipped = []

    def skip_live(info, *args, **kwargs):
        if info.get("is_live"):
            skipped.append("This is a live stream. Try again once it has ended.")
            return "live stream"
        return None

    quality = ctx["quality"]
    opts = {
        "format": ytdlp_format(quality),
        "format_sort": ytdlp_sort(quality),
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(ctx["dir"], "%(id).64s.%(ext)s"),
        "restrictfilenames": True,
        "noplaylist": True,
        "continuedl": True,
        "retries": 8,
        "fragment_retries": 8,
        "extractor_retries": 3,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 4,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "color": "never",
        "logger": logger,
        "progress_hooks": [on_progress],
        "postprocessor_hooks": [on_post],
        "match_filter": skip_live,
    }
    if have_cookies():
        opts["cookiesfrombrowser"] = ("safari",)

    url = ctx["url"]
    limit = ctx["limit"]

    def describe(exc):
        if logger.errors:
            return tidy_error(logger.errors[-1])
        return skipped[-1] if skipped else tidy_error(str(exc))

    # Look before downloading: how many items does this link hold?
    ui.start("Reading link")
    probe_opts = dict(opts, extract_flat="in_playlist")
    raw = None
    try:
        with yt_dlp.YoutubeDL(probe_opts) as ydl:
            raw = ydl.extract_info(url, download=False, process=False)
            hops = 0
            while raw and raw.get("_type") in ("url", "url_transparent") and hops < 3:
                raw = ydl.extract_info(raw["url"], download=False, process=False,
                                       ie_key=raw.get("ie_key"))
                hops += 1
    except Exception as exc:
        ui.fail()
        raise EngineError(describe(exc))
    if not raw:
        ui.fail()
        raise EngineError(describe("nothing to download"))

    is_playlist = raw.get("_type") in ("playlist", "multi_video")
    title = raw.get("title") or ""
    count = 1
    exact = True
    if is_playlist:
        count = to_int(raw.get("playlist_count"), 0)
        if not count:
            count, exact = count_entries(raw.get("entries"), ctx["threshold"] + 1)
    ui.done(title[:40] if title else "")
    ctx["title"] = ctx.get("title") or title

    if is_playlist and ctx["mode"] == "auto" and count > ctx["threshold"]:
        raise NeedConfirm(count if exact else None, title)

    if not is_playlist:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                listed = ydl.process_ie_result(copy.deepcopy(raw), download=False)
            chosen = choose_formats((listed or {}).get("formats"), quality, av1_goes_in())
            if chosen:
                log("version: %s" % chosen)
                opts["format"] = chosen + "/" + opts["format"]
        except Exception as exc:
            log("could not list the versions (%s); leaving the choice to yt-dlp" % exc)

    ui.start("Starting download")
    try:
        if is_playlist:
            run_opts = dict(opts, ignoreerrors="only_download")
            if limit:
                run_opts["playlist_items"] = "1-%d" % limit
            with yt_dlp.YoutubeDL(run_opts) as ydl:
                ydl.download([url])
        else:
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    # Reuse the probe result instead of extracting twice.
                    ydl.process_ie_result(raw, download=True)
                except yt_dlp.utils.DownloadError:
                    raise
                except Exception as exc:
                    log("reuse of probe failed (%s); downloading from scratch" % exc)
                    ydl.download([url])
    except Exception as exc:
        ui.stop_spinner()
        if not media_files(ctx["dir"], ytdlp=True):
            raise EngineError(describe(exc))
        log("yt-dlp stopped early: %s" % exc)
    ui.stop_spinner()
    ctx["failed"] += len(logger.errors)
    files = media_files(ctx["dir"], ytdlp=True)
    if not files:
        raise EngineError(describe("nothing to download"))
    ui.end_progress("Downloaded %d item%s" % (len(files), "" if len(files) == 1 else "s"))
    return files


# -------------------------------------------------------- engine: gallery-dl

def gallery_extractor_name(url):
    """Category of the gallery-dl extractor for this URL, or None."""
    try:
        from gallery_dl import extractor
        found = extractor.find(url)
    except Exception:
        return None
    if found is None:
        return None
    return str(getattr(found, "category", "") or "unknown")


def gallery_run(args, on_line=None):
    """Run the gallery-dl CLI, streaming stdout lines. Returns (code, lines, stderr)."""
    # The gallery-dl command exists only where pip could place scripts on PATH.
    launcher = ["gallery-dl"] if shutil.which("gallery-dl") else ["python", "-m", "gallery_dl"]
    argv = launcher + args
    cmd = " ".join(shlex.quote(a) for a in argv) if IOS else argv
    lines = []
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                bufsize=1, universal_newlines=True)
    except Exception as exc:
        return 127, lines, str(exc)
    for line in proc.stdout:
        line = line.rstrip("\n")
        if not line:
            continue
        lines.append(line)
        if on_line:
            on_line(line)
    err = ""
    try:
        err = proc.stderr.read() or ""
    except Exception:
        pass
    code = proc.wait()
    for pipe in (proc.stdout, proc.stderr):
        try:
            pipe.close()
        except Exception:
            pass
    return code, lines, strip_ansi(err)


def gallery_variants(url):
    """Extra gallery-dl options to try in turn. Each later entry is used only
    when the one before it was blocked by the site."""
    host = hostname(url)
    if host == "reddit.com" or host.endswith(".reddit.com") or host == "redd.it":
        return [[], REDDIT_API]
    return [[]]


def gallery_engine(ctx):
    variants = gallery_variants(ctx["url"])
    first_error = None
    for index, extra in enumerate(variants):
        try:
            return gallery_attempt(ctx, extra)
        except EngineError as exc:
            first_error = first_error or exc
            if index + 1 == len(variants) or not BLOCKED.search(str(exc)):
                break
            log("gallery-dl was blocked (%s); trying again with %s"
                % (exc, " ".join(variants[index + 1])))
    # The site's own refusal is the message worth showing.
    raise first_error


def gallery_attempt(ctx, extra, links=None):
    """One gallery-dl run. With `links`, those direct file links are fetched as
    they are: the caller has already counted and trimmed them."""
    listing = os.path.join(ctx["dir"], "urls.txt")
    with open(listing, "w", encoding="utf-8") as handle:
        handle.write("\n".join(links or [ctx["url"]]) + "\n")

    common = ["--input-file", listing, "--retries", "4", "--http-timeout", "30"] + list(extra)
    if have_cookies():
        common += ["--cookies-from-browser", "safari"]

    def last_error(err, fallback):
        errors = [ln for ln in err.splitlines() if "[error]" in ln or "Error" in ln]
        return tidy_error(errors[-1] if errors else (err or fallback))

    threshold = ctx["threshold"]
    if ctx["mode"] == "auto" and not links:
        ui.start("Reading link")
        code, lines, err = gallery_run(
            ["--get-urls", "--range", "1-%d" % (threshold + 1)] + common)
        # Lines starting with "|" are alternate URLs for the same file.
        found = [ln for ln in lines if not ln.startswith("|")]
        if not found:
            ui.fail()
            remove(listing)
            log("gallery-dl could not read the link (exit %s)\n%s" % (code, err[-3000:]))
            raise EngineError(last_error(err, "nothing to download"))
        ui.done("%d item%s" % (len(found), "" if len(found) == 1 else "s")
                if len(found) <= threshold else "more than %d items" % threshold)
        if len(found) > threshold:
            remove(listing)
            raise NeedConfirm(None, "")

    args = ["--directory", ctx["dir"]] + common
    if ctx["limit"] and not links:
        args += ["--range", "1-%d" % ctx["limit"]]
    seen = {"n": 0}

    def on_line(line):
        seen["n"] += 1
        ui.progress("↓", None, "%d file%s" % (seen["n"], "" if seen["n"] == 1 else "s"))

    ui.start("Starting download")
    code, lines, err = gallery_run(args, on_line)
    ui.stop_spinner()
    remove(listing)
    log("gallery-dl exit %s\n%s" % (code, err[-3000:]))
    files = media_files(ctx["dir"])
    if not files:
        raise EngineError(last_error(err, "nothing to download"))
    ctx["failed"] += len([ln for ln in err.splitlines() if "[error]" in ln])
    ui.end_progress("Downloaded %d item%s" % (len(files), "" if len(files) == 1 else "s"))
    return files


# ------------------------------------------------ Reddit through the browser
#
# Reddit turns the download tools away on some networks even when they carry a
# signed-in session ("You've been blocked by network security"). The one client
# it does accept there is a real browser, and a-Shell has one: the web view that
# "Sign in to a site" uses. a-Shell's jsc command runs JavaScript in that web
# view, so the helper asks the browser itself for the post's details, then
# hands the media links it finds to the download tools. Cookies never leave
# the browser.

def is_reddit(url):
    host = hostname(url)
    return host in ("reddit.com", "redd.it") or host.endswith(".reddit.com")


# Runs inside a page on www.reddit.com. Leaves its answer in window.__umdl:
#   "OK <json>"            the fields of the post that say where its media is
#   "HTTP <status> <text>" Reddit answered, but not with a post
#   "ERR <message>"        the request could not be made
REDDIT_JS = r"""
window.__umdl = "";
(async function () {
  try {
    var target = new URL(__URL__);
    var link = target.hostname === "redd.it" ? "/comments" + target.pathname
                                             : target.pathname + target.search;
    if (!/\/comments\//.test(link)) {
      // A share link: follow it to the post it stands for.
      var hop;
      try {
        hop = await fetch(link, {method: "HEAD", credentials: "include", redirect: "follow"});
      } catch (e) {
        hop = await fetch(link, {credentials: "include", redirect: "follow"});
      }
      link = hop.url || link;
    }
    var match = link.match(/\/comments\/([A-Za-z0-9]+)/);
    if (!match) { window.__umdl = "ERR no post found at " + link; return; }
    var reply = await fetch("/comments/" + match[1] + "/.json?raw_json=1&limit=1",
                            {credentials: "include", headers: {"Accept": "application/json"}});
    var text = await reply.text();
    var data = null;
    try { data = JSON.parse(text); } catch (e) { data = null; }
    var ascii = function (value) {
      // Plain ASCII, so nothing between here and Python can garble it.
      return JSON.stringify(value).replace(/[\u007f-￿]/g, function (c) {
        return "\\u" + ("0000" + c.charCodeAt(0).toString(16)).slice(-4);
      });
    };
    if (!Array.isArray(data)) {
      // Reddit will not give out the post's data. Read the page a visitor's
      // browser is shown instead: the post element carries what is needed.
      var page = await fetch(link.replace(/^https?:\/\/[^\/]+/, ""),
                             {credentials: "include", headers: {"Accept": "text/html"}});
      var html = await page.text();
      var start = html.indexOf("<shreddit-post");
      if (start >= 0) {
        var end = html.indexOf("</shreddit-post>", start);
        var post = html.slice(start, end > 0 ? end : start + 400000);
        var tag = post.slice(0, post.indexOf(">") + 1);
        var attr = function (name) {
          var m = tag.match(new RegExp("\\s" + name + '="([^"]*)"'));
          return !m ? "" : m[1].replace(/&quot;/g, '"').replace(/&#x27;|&#39;/g, "'")
                               .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
        };
        var seen = {id: attr("id").replace(/^t3_/, ""), title: attr("post-title"), umdl: ["none", ""]};
        var href = attr("content-href");
        var video = post.match(/https:\/\/v\.redd\.it\/([A-Za-z0-9]+)/);
        var files = [], had = {}, each;
        var image = /https:\/\/(?:i|preview)\.redd\.it\/([A-Za-z0-9_-]+\.(?:jpe?g|png|gif|webp))/g;
        while ((each = image.exec(post))) {
          // The preview host serves resized copies, sometimes under a longer name.
          var name = each[1].replace(/^.*-v\d+-/, "");
          if (!had[name]) { had[name] = 1; files.push("https://i.redd.it/" + name); }
        }
        if (video) {
          seen.umdl = ["video", "https://v.redd.it/" + video[1] + "/DASHPlaylist.mpd"];
        } else if (files.length) {
          seen.umdl = ["files", files];
        } else if (/^https?:\/\//.test(href) && !/^https?:\/\/([a-z0-9-]+\.)?(reddit\.com|redd\.it)\//.test(href)) {
          seen.umdl = ["link", href];
        }
        window.__umdl = "OK " + ascii(seen);
        return;
      }
      var said = data && data.message ? String(data.message)
        : html.replace(/<(style|script)[\s\S]*?<\/\1>/g, " ").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
      window.__umdl = "HTTP " + reply.status + ", page " + page.status + ": " + said.slice(0, 140);
      return;
    }
    var keep = ["id", "title", "url", "url_overridden_by_dest", "is_video", "is_gallery",
                "is_self", "media", "secure_media", "gallery_data", "media_metadata"];
    var pick = function (post) {
      var out = {};
      keep.forEach(function (key) { if (post[key] !== undefined) { out[key] = post[key]; } });
      return out;
    };
    var post = data[0].data.children[0].data;
    var found = pick(post);
    if (post.crosspost_parent_list && post.crosspost_parent_list[0]) {
      found.crosspost_parent_list = [pick(post.crosspost_parent_list[0])];
    }
    window.__umdl = "OK " + ascii(found);
  } catch (e) {
    window.__umdl = "ERR " + e;
  }
})();
"""

BROWSER_WAIT = float(os.environ.get("UMDL_BROWSER_WAIT") or 40)


def browser_script(expression, before=""):
    """JavaScript that runs `before`, then reports `expression` as text.

    The value is sent through the channel a-Shell gives page scripts for
    printing, and the script itself evaluates to nothing: on iOS 27.2 jsc
    refuses to hand back even a plain string ("a result of an unsupported
    type").
    """
    return before + '''
(function () {
  var out = "";
  try { out = String(%s); } catch (e) { out = ""; }
  try { window.webkit.messageHandlers.aShell.postMessage("print:" + out + "\\n"); } catch (e) {}
})();
void 0;
''' % expression


def browser_js(name, expression, before=""):
    """Run JavaScript in a-Shell's web view and return one value as text."""
    path = os.path.join(WORKSPACE, "web-%s.js" % name)
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(browser_script(expression, before))
        code, out, err = run_cmd(["jsc", path])
    finally:
        remove(path)
    if err.strip():
        log("browser %s: %s" % (name, err.strip()[:200]))
    lines = [line for line in (out or "").splitlines() if line.strip()]
    return lines[-1].strip() if lines else ""


def reddit_post_from_browser(url):
    """Ask a-Shell's browser for a Reddit post. Returns the post's fields."""
    here = browser_js("where", "location.href")  # the page the web view is on
    if not here:
        raise EngineError("a-Shell's browser did not answer")
    log("browser was at " + here[:80])
    # The request has to come from a page of the site. This one is small and runs
    # no scripts of its own, so nothing else can see what jsc puts in the page.
    quiet_page = "https://www.reddit.com/robots.txt"
    moved = here != quiet_page
    step = max(0.05, min(0.5, BROWSER_WAIT / 40.0))
    answer = ""
    try:
        if moved:
            browser_js("go", '"going"', 'location.href = "%s";' % quiet_page)
            deadline = time.time() + BROWSER_WAIT / 2
            while time.time() < deadline:
                time.sleep(step)
                state = browser_js("ready", 'location.hostname + " " + document.readyState')
                if state.startswith("www.reddit.com ") and not state.endswith("loading"):
                    break
            else:
                raise EngineError("a-Shell's browser could not open reddit.com")
        if browser_js("start", '"started"', REDDIT_JS.replace("__URL__", json.dumps(url))) != "started":
            raise EngineError("a-Shell's browser did not run the request")
        deadline = time.time() + BROWSER_WAIT
        while time.time() < deadline and not answer:
            time.sleep(step)
            answer = browser_js("result", 'window.__umdl || ""')
    finally:
        if moved:
            browser_js("back", '"back"', "history.back();")
    log("browser answered: " + (answer[:200] or "nothing"))
    if answer.startswith("OK "):
        try:
            post = json.loads(answer[3:])
            if isinstance(post, dict):
                return post
        except ValueError:
            pass
        raise EngineError("a-Shell's browser returned something unreadable")
    if answer.startswith("HTTP "):
        raise EngineError("Reddit refused the browser as well: " + answer[5:])
    raise EngineError(answer[4:] if answer.startswith("ERR ") else "Reddit did not answer the browser")


def reddit_targets(post):
    """Where a Reddit post keeps its media.

    Returns ("video", manifest link), ("files", [direct links]) or
    ("link", another site's link).
    """
    seen = post.get("umdl")
    if isinstance(seen, list) and len(seen) == 2:
        # Read off the post's page by the browser, when Reddit withholds its data.
        if seen[0] in ("video", "files", "link") and seen[1]:
            return seen[0], seen[1]
        raise EngineError("This Reddit post has no photo or video.")
    parents = post.get("crosspost_parent_list") or []
    if parents and isinstance(parents[0], dict):
        post = parents[0]  # a crosspost: the media belongs to the original
    for holder in (post.get("secure_media"), post.get("media")):
        video = (holder or {}).get("reddit_video") if isinstance(holder, dict) else None
        if isinstance(video, dict):
            link = video.get("dash_url") or video.get("hls_url") or video.get("fallback_url")
            if link:
                return "video", link
    items = (post.get("gallery_data") or {}).get("items") or []
    described = post.get("media_metadata") or {}
    links = []
    for item in items:
        source = (described.get(item.get("media_id")) or {}).get("s") or {}
        link = source.get("u") or source.get("gif") or source.get("mp4")
        if link:
            # The preview host serves a resized copy; the same name on i.redd.it is the original.
            links.append(link.partition("?")[0].replace("/preview.", "/i.", 1))
    if links:
        return "files", links
    link = clean_url(str(post.get("url_overridden_by_dest") or post.get("url") or ""))
    host = hostname(link)
    if host == "i.redd.it":
        return "files", [link]
    if host == "v.redd.it":
        return "video", link.rstrip("/") + "/DASHPlaylist.mpd"
    if link and not is_reddit(link) and not post.get("is_self"):
        return "link", link
    raise EngineError("This Reddit post has no photo or video.")


def reddit_web_engine(ctx):
    """Last resort for Reddit: get the post from a-Shell's browser, then let the
    download tools fetch the media it points to."""
    ui.start("Asking a-Shell's browser for the post")
    try:
        post = reddit_post_from_browser(ctx["url"])
        kind, target = reddit_targets(post)
    except EngineError:
        ui.fail()
        raise
    ui.done()
    title = str(post.get("title") or "")
    log("reddit post %s: %s" % (post.get("id"), kind))
    if kind == "files":
        if ctx["mode"] == "auto" and len(target) > ctx["threshold"]:
            raise NeedConfirm(len(target), title)
        if ctx["limit"]:
            target = target[:ctx["limit"]]
        files = gallery_attempt(ctx, [], links=target)
    else:
        there = dict(ctx, url=target, titles={}, title="")
        files = []
        last = None
        for engine in (["ytdlp"] if kind == "video" else plan_engines(target)):
            try:
                files = ENGINES[engine](there)
                if files:
                    break
            except EngineError as exc:
                last = exc
        ctx["failed"] = there["failed"]
        if not files:
            raise last or EngineError("nothing to download")
        if kind == "link":
            ctx["titles"].update(there["titles"])
    if title and kind != "link":
        # Name the files after the post, not after the manifest they came from.
        for path in files:
            ctx["titles"][os.path.basename(path)] = title
    ctx["title"] = title or ctx.get("title") or ""
    return files


ENGINES = {"ytdlp": ytdlp_engine, "gallery": gallery_engine, "redditweb": reddit_web_engine}


def plan_engines(url):
    """Order in which to try the tools for this link."""
    gallery = gallery_extractor_name(url)
    ytdlp = ytdlp_extractor_name(url)
    if gallery and (prefers_gallery(hostname(url)) or not ytdlp):
        return ["gallery", "ytdlp"]
    if ytdlp and gallery:
        return ["ytdlp", "gallery"]
    # No dedicated extractor anywhere: yt-dlp's generic one scans the page.
    return ["ytdlp"]


# ------------------------------------------------------- making Photos-ready

_INTERMEDIATE = re.compile(r"\.f[0-9A-Za-z_-]+\.[A-Za-z0-9]+$")


def media_files(folder, ytdlp=False):
    """Finished downloads in a job folder, oldest first (playlist order)."""
    found = []
    try:
        names = os.listdir(folder)
    except Exception:
        return found
    for name in names:
        path = os.path.join(folder, name)
        if not os.path.isfile(path) or name.startswith("."):
            continue
        if name in ("urls.txt", "job.json"):
            continue
        if ext_of(name) in JUNK_EXTS or ".part" in name:
            continue
        # yt-dlp keeps "<id>.f137.mp4" style pieces until it has merged them.
        if ytdlp and _INTERMEDIATE.search(name):
            continue
        try:
            if os.path.getsize(path) == 0:
                continue
        except Exception:
            continue
        found.append(path)
    found.sort(key=lambda p: (os.path.getmtime(p), p))
    return found


def probe_media(path):
    """What a media file holds, via ffprobe: codecs, picture size, frame rate,
    bit depth and bitrates. "ok" is False when the file could not be read."""
    info = {"v": None, "a": None, "tag": "", "bitrate": 0, "vbitrate": 0, "width": 0, "height": 0,
            "fps": 0, "pix_fmt": "", "seconds": 0.0, "ok": False}
    code, out, err = run_cmd(["ffprobe", "-v", "error", "-print_format", "json",
                              "-show_streams", "-show_format", path])
    data = None
    if code == 0 and out.strip().startswith("{"):
        try:
            data = json.loads(out)
        except Exception:
            data = None
    if data is not None:
        info["ok"] = True
        for stream in data.get("streams") or []:
            kind = stream.get("codec_type")
            # Cover art shows up as a video stream; it is not one.
            if kind == "video" and not (stream.get("disposition") or {}).get("attached_pic"):
                if info["v"] is None:
                    info["v"] = (stream.get("codec_name") or "").lower()
                    info["tag"] = (stream.get("codec_tag_string") or "").lower()
                    info["width"] = to_int(stream.get("width"), 0)
                    info["height"] = to_int(stream.get("height"), 0)
                    info["pix_fmt"] = str(stream.get("pix_fmt") or "")
                    info["vbitrate"] = to_int(stream.get("bit_rate"), 0)
                    rate = str(stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "")
                    top, _, bottom = rate.partition("/")
                    try:
                        info["fps"] = float(top) / float(bottom or 1)
                    except (ValueError, ZeroDivisionError):
                        info["fps"] = 0
            elif kind == "audio" and info["a"] is None:
                info["a"] = (stream.get("codec_name") or "").lower()
        info["bitrate"] = to_int((data.get("format") or {}).get("bit_rate"), 0)
        try:
            info["seconds"] = float((data.get("format") or {}).get("duration") or 0)
        except (TypeError, ValueError):
            info["seconds"] = 0.0
        return info
    # No ffprobe: read the stream summary ffmpeg prints for any input.
    code, out, err = run_cmd(["ffmpeg", "-hide_banner", "-i", path])
    text = out + err
    video = re.search(r"Stream #\S+ Video: (\w+)(?: \([^)]*\))? \((\w+) /", text)
    plain = re.search(r"Stream #\S+ Video: (\w+)", text)
    audio = re.search(r"Stream #\S+ Audio: (\w+)", text)
    if plain or audio:
        info["ok"] = True
        info["v"] = plain.group(1).lower() if plain else None
        info["tag"] = video.group(2).lower() if video else ""
        info["a"] = audio.group(1).lower() if audio else None
        rate = re.search(r"bitrate: (\d+) kb/s", text)
        info["bitrate"] = int(rate.group(1)) * 1000 if rate else 0
        size = re.search(r"Video: [^\n]*?(\d{2,5})x(\d{2,5})", text)
        if size:
            info["width"], info["height"] = int(size.group(1)), int(size.group(2))
        fps = re.search(r"([\d.]+) fps", text)
        info["fps"] = float(fps.group(1)) if fps else 0
    return info


def tier(width, height):
    """The resolution's usual name: 3840x1920 is "2160p", as is 3840x2160.
    A picture is named after the 16:9 frame it fills, not its shorter side."""
    short, long = sorted((width or 0, height or 0))
    if not short:
        return ""
    lines = max(short, int(round(long * 9 / 16.0)))
    for standard in (4320, 2160, 1440, 1080, 720, 480, 360, 240, 144):
        if abs(lines - standard) <= standard * 0.04:
            return "%dp" % standard
    return "%dp" % lines


def describe_media(info):
    """"2160p60 VP9 + Opus" for a file that has been probed."""
    size = tier(info["width"], info["height"])
    if size and info["fps"] > 40:
        size += "%d" % round(info["fps"])
    text = " ".join(x for x in (size, codec_name(info["v"])) if x)
    return text + (" + " + codec_name(info["a"]) if info["a"] else "")


_FFMPEG_HAS = {}


def ffmpeg_has(listing):
    """What this ffmpeg was built with: the names under "-encoders",
    "-decoders" or "-hwaccels". Asked once."""
    if listing not in _FFMPEG_HAS:
        code, out, err = run_cmd(["ffmpeg", "-hide_banner", listing])
        _FFMPEG_HAS[listing] = (set(out.split()) if listing == "-hwaccels"
                                else set(re.findall(r"(?m)^\s*[VAS][A-Z.]{5}\s+(\S+)", out)))
    return _FFMPEG_HAS[listing]


def encoders():
    return ffmpeg_has("-encoders")


def decode_args():
    """Options that ask the device's hardware to read the picture, when this
    ffmpeg can ask at all. For a codec the hardware does not read (VP9 on an
    iPhone), ffmpeg carries on with its own decoder."""
    return ["-hwaccel", "videotoolbox"] if "videotoolbox" in ffmpeg_has("-hwaccels") else []


# Bits per second that keep a picture of this height clean at 30 frames a second
# in HEVC. Used only as a floor, and only when the encoder cannot be asked for
# a quality level directly.
BITRATE_FLOOR = ((2160, 24000000), (1440, 14000000), (1080, 8000000), (720, 5000000), (0, 2500000))


def conversion_attempts(info, have):
    """Ways to re-encode a video for Photos, best first. Each is (codec name,
    ffmpeg arguments).

    The picture keeps its size and frame rate. HEVC from the device's own
    encoder comes first: it holds 4K, 60 frames a second and 10-bit colour, and
    Photos plays it everywhere. It is asked for a quality level, not a bitrate,
    so detail is kept wherever the picture needs it. H.264 and the software
    encoder follow for an ffmpeg built without the first choice.
    """
    side = min(info["width"], info["height"]) or info["height"] or info["width"]
    floor = next(rate for height, rate in BITRATE_FLOOR if side >= height)
    if info["fps"] > 40:
        floor = int(floor * 1.5)
    source = info["vbitrate"] or info["bitrate"]
    rate = int(min(80000000, max(floor, source * 1.1)))
    deep = "10" in info["pix_fmt"]
    hevc = ["-c:v", "hevc_videotoolbox", "-tag:v", "hvc1"] + (
        ["-profile:v", "main10", "-pix_fmt", "p010le"] if deep else ["-pix_fmt", "yuv420p"])
    attempts = []
    if not have or "hevc_videotoolbox" in have:
        attempts.append(("HEVC", hevc + ["-q:v", "75"]))
        attempts.append(("HEVC", hevc + ["-b:v", str(rate)]))
    if not have or "h264_videotoolbox" in have:
        attempts.append(("H.264", ["-c:v", "h264_videotoolbox", "-profile:v", "high",
                                   "-b:v", str(int(rate * 1.6)), "-pix_fmt", "yuv420p"]))
    if not have or "libx264" in have:
        attempts.append(("H.264", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "17",
                                   "-pix_fmt", "yuv420p"]))
    return attempts


def ffmpeg(args, target, seconds=0):
    """Run ffmpeg. With the length of the video in `seconds`, the step being
    shown counts up in per cent while it runs."""
    base = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    remove(target)
    notes = target + ".progress"
    code, out, err = 1, "", ""
    if seconds > 0:
        # ffmpeg writes its position to a file, which is read from here. Nothing
        # depends on reading a running command's output, which a-Shell may not allow.
        label, stop = ui._label, threading.Event()

        def watch():
            while not stop.wait(0.5):
                try:
                    with open(notes, "rb") as handle:
                        handle.seek(max(0, os.path.getsize(notes) - 600))
                        found = re.findall(r"out_time_(?:us|ms)=(\d+)", handle.read().decode("ascii", "replace"))
                except OSError:
                    continue
                if found:
                    ui._label = "%s  %d%%" % (label, min(99, int(int(found[-1]) / 1e6 / seconds * 100)))

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            code, out, err = run_cmd(base + ["-progress", notes, "-nostats"] + args + [target])
        finally:
            stop.set()
            watcher.join(timeout=2)
            ui._label = label
            remove(notes)
    if code != 0 or not os.path.exists(target) or os.path.getsize(target) == 0:
        if seconds > 0:
            remove(target)  # once more without the progress file, in case that was the obstacle
        code, out, err = run_cmd(base + args + [target])
    good = code == 0 and os.path.exists(target) and os.path.getsize(target) > 0
    if not good:
        log("ffmpeg failed (%s): %s" % (code, (err or out)[-800:]))
        remove(target)
    return good


def inspect(path):
    """What a download is: ("image", None), ("video", what ffprobe found) or
    ("other", None) for sound, archives and anything else Photos has no place for."""
    ext = ext_of(path)
    if ext in IMAGE_EXTS:
        return "image", None
    if ext not in VIDEO_EXTS:
        return "other", None
    info = probe_media(path)
    if not info["ok"] or not info["v"]:
        return "other", None
    return "video", info


def replace_with(path, made):
    """Put the new file in the original's place: 001.webm becomes 001.mp4."""
    final = os.path.splitext(path)[0] + ".mp4"
    remove(path)
    try:
        os.replace(made, final)
    except OSError:
        return made
    return final


def repack(path, info):
    """The same picture in an MP4 wrapper, without re-encoding it. Sound Photos
    plays is copied too; other sound becomes AAC. Returns the new path or None."""
    target = os.path.splitext(path)[0] + "_photos.mp4"
    audio_ok = info["a"] is None or info["a"] in PHOTOS_ACODECS
    args = ["-i", path, "-c:v", "copy"] + (["-tag:v", "hvc1"] if info["v"] == "hevc" else [])
    args += (["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "256k"])
    args += ["-map", "0:v:0", "-map", "0:a:0?", "-movflags", "+faststart"]
    ui.start("Repacking for Photos")
    if ffmpeg(args, target):
        ui.done()
        return replace_with(path, target)
    ui.fail()
    return None


def convert(path, info, notes):
    """Re-encode the picture for Photos, same size and frame rate. Each
    conversion is noted as "VP9 → HEVC". Returns the new path or None."""
    target = os.path.splitext(path)[0] + "_photos.mp4"
    audio_ok = info["a"] is None or info["a"] in PHOTOS_ACODECS
    tail = (["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "256k"])
    tail += ["-map", "0:v:0", "-map", "0:a:0?", "-movflags", "+faststart"]
    source = describe_media(info)
    ui.start("Converting %s for Photos" % source)
    started = time.time()
    # Hardware reads the picture where it can; the plain way is the second try.
    readers = [decode_args(), []] if decode_args() else [[]]
    for reader in readers:
        for codec, video_args in conversion_attempts(info, encoders()):
            if ffmpeg(reader + ["-i", path] + video_args + tail, target, info.get("seconds") or 0):
                ui.done(codec)
                log("converted %s to %s in %d s with %s"
                    % (source, codec, time.time() - started, " ".join(reader + video_args)))
                notes.append("%s → %s" % (codec_name(info["v"]), codec))
                return replace_with(path, target)
    ui.fail("kept the original in Files")
    return None


# ------------------------------------------------- saving straight to Photos
#
# a-Shell is allowed to add to the Photos library, so the helper can save a
# file itself, from inside a-Shell, through the system's own interface
# (PhotoKit, reached with ctypes). Nothing then has to travel through
# Shortcuts: no size limit, the file keeps a proper name, and its date is the
# day it was downloaded. Photos is also the judge of what it can play: a file
# is offered as it is, and converted only if Photos says no.
#
# None of this can be run anywhere but on a device, so each step's name is
# written to a file before it is taken. If a-Shell stops in the middle, the
# next run finds the name, says so, and keeps files in Files until the helper
# changes or Update tools is run. That is the only other place a file can end.

GUARD_FILE = os.path.join(WORKSPACE, "photos.step")


class Refused(Exception):
    """Photos would not take the file."""


class PhotosLibrary:
    ADD_ONLY, READ_WRITE = 1, 2

    def __init__(self, album):
        import ctypes
        self.c = ctypes
        self.objc = ctypes.CDLL("/usr/lib/libobjc.A.dylib")
        ctypes.CDLL("/System/Library/Frameworks/Photos.framework/Photos")
        self.objc.objc_getClass.restype = ctypes.c_void_p
        self.objc.objc_getClass.argtypes = [ctypes.c_char_p]
        self.objc.sel_registerName.restype = ctypes.c_void_p
        self.objc.sel_registerName.argtypes = [ctypes.c_char_p]
        self.objc.objc_autoreleasePoolPush.restype = ctypes.c_void_p
        self.objc.objc_autoreleasePoolPop.argtypes = [ctypes.c_void_p]
        self.album = album if album and album != "Recents" else ""
        self.level = self.ADD_ONLY
        self.collection = None
        self.keep = []  # blocks and their callbacks must outlive the calls that use them

    # -- talking to Objective-C

    def cls(self, name):
        found = self.objc.objc_getClass(name.encode("ascii"))
        if not found:
            raise RuntimeError("no class " + name)
        return found

    def send(self, target, selector, *args, returns="object", types=()):
        c = self.c
        restype = c.c_void_p if returns == "object" else returns
        call = c.CFUNCTYPE(restype, c.c_void_p, c.c_void_p, *types)(("objc_msgSend", self.objc))
        return call(target, self.objc.sel_registerName(selector.encode("ascii")), *args)

    def text(self, value):
        return self.send(self.cls("NSString"), "stringWithUTF8String:", value.encode("utf-8"),
                         types=(self.c.c_char_p,))

    def python(self, ns_string):
        if not ns_string:
            return ""
        raw = self.send(ns_string, "UTF8String", returns=self.c.c_char_p)
        return raw.decode("utf-8", "replace") if raw else ""

    def block(self, function, *types):
        """An Objective-C block that calls a Python function."""
        c = self.c

        class Descriptor(c.Structure):
            _fields_ = [("reserved", c.c_ulong), ("size", c.c_ulong)]

        class Literal(c.Structure):
            _fields_ = [("isa", c.c_void_p), ("flags", c.c_int), ("reserved", c.c_int),
                        ("invoke", c.c_void_p), ("descriptor", c.c_void_p)]

        invoke = c.CFUNCTYPE(None, c.c_void_p, *types)(function)
        descriptor = Descriptor(0, c.sizeof(Literal))
        isa = c.addressof(c.c_void_p.in_dll(c.CDLL(None), "_NSConcreteGlobalBlock"))
        literal = Literal(isa, 1 << 28, 0, c.cast(invoke, c.c_void_p).value, c.addressof(descriptor))
        self.keep += [invoke, descriptor, literal]
        return c.addressof(literal)

    # -- permission and album

    def status(self):
        return self.send(self.cls("PHPhotoLibrary"), "authorizationStatusForAccessLevel:", self.level,
                         returns=self.c.c_long, types=(self.c.c_long,))

    def ask(self):
        answered = threading.Event()

        def done(_block, _status):
            answered.set()

        self.send(self.cls("PHPhotoLibrary"), "requestAuthorizationForAccessLevel:handler:",
                  self.level, self.block(done, self.c.c_long),
                  returns=None, types=(self.c.c_long, self.c.c_void_p))
        answered.wait(180)
        return self.status()

    def permitted(self):
        """True once the owner has allowed this. 3 is allowed, 4 allowed for chosen photos."""
        state = self.status()
        if state == 0:
            ui.start("Asking for access to Photos")
            state = self.ask()
            ui.done() if state in (3, 4) else ui.fail("not allowed")
        return state in (3, 4)

    def find_album(self):
        if not self.album or self.level != self.READ_WRITE:
            return None
        c = self.c
        found = self.send(self.cls("PHAssetCollection"), "fetchAssetCollectionsWithType:subtype:options:",
                          1, 2, None, types=(c.c_long, c.c_long, c.c_void_p))
        count = self.send(found, "count", returns=c.c_ulong) if found else 0
        for index in range(count):
            album = self.send(found, "objectAtIndex:", index, types=(c.c_ulong,))
            if self.python(self.send(album, "localizedTitle")) == self.album:
                return self.send(album, "retain")
        return None

    def where(self):
        return self.album if self.level == self.READ_WRITE and self.album else ""

    # -- adding a file

    def add(self, path, name):
        """Add one photo or video under `name`, dated now. Raises Refused."""
        guard("add " + name[:60])
        try:
            try:
                self.add_once(path, name)
            except Refused as no:
                if not self.where():
                    raise
                # It may be the album that was refused, not the file.
                log("photos: %s; trying without the album" % no)
                self.album = ""
                self.add_once(path, name)
        finally:
            guard(None)

    def add_once(self, path, name):
        c = self.c
        pool = self.objc.objc_autoreleasePoolPush()
        try:
            kind = 1 if ext_of(path) in IMAGE_EXTS else 2
            link = self.send(self.cls("NSURL"), "fileURLWithPath:", self.text(path), types=(c.c_void_p,))
            original = self.text(name)
            now = self.send(self.cls("NSDate"), "date")
            title = self.text(self.album) if self.where() else None
            trouble = []

            def changes(_block):
                try:
                    request = self.send(self.cls("PHAssetCreationRequest"), "creationRequestForAsset")
                    options = self.send(self.send(self.cls("PHAssetResourceCreationOptions"), "alloc"), "init")
                    self.send(options, "setOriginalFilename:", original, returns=None, types=(c.c_void_p,))
                    self.send(request, "addResourceWithType:fileURL:options:", kind, link, options,
                              returns=None, types=(c.c_long, c.c_void_p, c.c_void_p))
                    self.send(request, "setCreationDate:", now, returns=None, types=(c.c_void_p,))
                    if title:
                        if self.collection:
                            album = self.send(self.cls("PHAssetCollectionChangeRequest"),
                                              "changeRequestForAssetCollection:", self.collection,
                                              types=(c.c_void_p,))
                        else:
                            album = self.send(self.cls("PHAssetCollectionChangeRequest"),
                                              "creationRequestForAssetCollectionWithTitle:", title,
                                              types=(c.c_void_p,))
                        placeholder = self.send(request, "placeholderForCreatedAsset")
                        if album and placeholder:
                            self.send(album, "addAssets:",
                                      self.send(self.cls("NSArray"), "arrayWithObject:", placeholder,
                                                types=(c.c_void_p,)),
                                      returns=None, types=(c.c_void_p,))
                except Exception as exc:  # nothing may escape into the system's thread
                    trouble.append("%s: %s" % (type(exc).__name__, exc))

            error = c.c_void_p()
            library = self.send(self.cls("PHPhotoLibrary"), "sharedPhotoLibrary")
            done = self.send(library, "performChangesAndWait:error:", self.block(changes), c.byref(error),
                             returns=c.c_bool, types=(c.c_void_p, c.c_void_p))
            if trouble:
                raise Refused(trouble[0])
            if not done:
                reason = self.python(self.send(error, "localizedDescription")) if error.value else ""
                raise Refused(reason or "Photos gave no reason")
            if title and not self.collection:
                self.collection = self.find_album()  # just created: use it for the next file
        finally:
            self.objc.objc_autoreleasePoolPop(pool)


class TestLibrary:
    """Stands in for Photos in the tests: a folder, and a list of what it "plays"."""

    def __init__(self, folder, album):
        self.folder = folder
        self.album = album if album and album != "Recents" else ""
        self.plays = set((os.environ.get("UMDL_TEST_PHOTOS_PLAYS") or "h264,hevc").split(","))

    def where(self):
        return self.album

    def add(self, path, name):
        if ext_of(path) not in IMAGE_EXTS:
            info = probe_media(path)
            if ext_of(path) not in PHOTOS_CONTAINERS or info["v"] not in self.plays:
                raise Refused("unsupported format")
        target = os.path.join(self.folder, self.album or "Library")
        os.makedirs(target, exist_ok=True)
        shutil.copyfile(path, os.path.join(target, name))
        with open(os.path.join(self.folder, "added.txt"), "a", encoding="utf-8") as handle:
            handle.write("%s\t%s\t%s\t%d\n" % (self.album or "Library", name, time.strftime("%Y-%m-%d"),
                                                os.path.getsize(path)))


def guard(step):
    """Note the step about to be taken, or clear the note with None."""
    if step is None:
        remove(GUARD_FILE)
        return
    with open(GUARD_FILE, "w", encoding="utf-8") as handle:
        handle.write(step)


def open_library(album):
    """Photos, and if it cannot be used, the reason in a sentence."""
    folder = os.environ.get("UMDL_TEST_PHOTOS")
    if folder:
        if os.environ.get("UMDL_TEST_PHOTOS_REFUSED"):
            return None, "a-Shell is not allowed to add to Photos. Allow it in Settings, a-Shell, Photos."
        return TestLibrary(folder, album), ""
    if not IOS:
        return None, "Photos can only be reached on an iPhone or iPad."
    state = read_json(STATE_FILE, {})
    if os.path.exists(GUARD_FILE):
        with open(GUARD_FILE, "r", encoding="utf-8") as handle:
            state["photos_off"] = {"step": handle.read().strip()[:80], "helper": HELPER_VERSION}
        write_json(STATE_FILE, state)
        guard(None)
    off = state.get("photos_off") or {}
    if off.get("helper") == HELPER_VERSION:
        return None, ("Saving to Photos stopped a-Shell last time (at \"%s\"). "
                      "Run Update tools to try again." % off.get("step"))
    try:
        guard("load")
        library = PhotosLibrary(album)
        pool = library.objc.objc_autoreleasePoolPush()
        try:
            guard("permission")
            bundle = library.send(library.cls("NSBundle"), "mainBundle")

            def declared(key):
                return bool(library.send(bundle, "objectForInfoDictionaryKey:", library.text(key),
                                         types=(library.c.c_void_p,)))

            if not declared("NSPhotoLibraryAddUsageDescription"):
                return None, "This version of a-Shell cannot add to Photos."
            if library.album and declared("NSPhotoLibraryUsageDescription"):
                library.level = library.READ_WRITE  # an album needs more than "add only"
            if not library.permitted():
                library.level = library.ADD_ONLY
                if not library.permitted():
                    return None, "a-Shell is not allowed to add to Photos. Allow it in Settings, a-Shell, Photos."
            guard("album")
            library.collection = library.find_album()
        finally:
            library.objc.objc_autoreleasePoolPop(pool)
        log("photos: %s" % ("album " + library.where() if library.where() else "library, no album"))
        return library, ""
    except Exception as exc:
        log("photos: %s: %s" % (type(exc).__name__, exc))
        return None, "Photos could not be reached (%s)." % type(exc).__name__
    finally:
        guard(None)


def unique_path(folder, name):
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return candidate


def stage(ctx, files):
    """Give each download a working name that is safe for any command, and the
    name it will carry in Photos: its title, or the name it was uploaded under."""
    out_dir = os.path.join(ctx["dir"], "out")
    remove(out_dir)
    os.makedirs(out_dir)
    items, used = [], set()
    for index, original in enumerate(files, 1):
        base = os.path.basename(original)
        title = safe_title(ctx["titles"].get(base) or "", os.path.splitext(base)[0])
        stem, copy_number = title, 1
        while stem.lower() in used:
            copy_number += 1
            stem = "%s %d" % (title, copy_number)
        used.add(stem.lower())
        # Recognisable in the Files app, and nothing for ffmpeg to trip on.
        slug = re.sub(r"[^A-Za-z0-9]+", "-", stem).strip("-")[:40]
        staged = os.path.join(out_dir, "%03d%s.%s" % (index, "-" + slug if slug else "",
                                                     ext_of(original) or "bin"))
        os.replace(original, staged)
        items.append({"path": staged, "stem": stem, "state": "waiting"})
    return items


def place(ctx, item, library):
    """Get one file into Photos: as it is if Photos takes it, converted if it
    does not. Returns "saved", or "kept" when it has to stay in Files."""
    path = item["path"]
    kind, info = inspect(path)
    if kind == "other" or library is None:
        return "kept"

    def named(file_path):
        return "%s.%s" % (item["stem"], ext_of(file_path) or "bin")

    def now_at(new_path):
        item["path"] = new_path
        ctx["checkpoint"]()  # an interrupted run carries on from this file
        return new_path

    mislabelled = kind == "video" and info["v"] == "hevc" and info["tag"] != "hvc1"
    if kind == "video" and (ext_of(path) not in PHOTOS_CONTAINERS or mislabelled):
        path = now_at(repack(path, info) or path)  # the wrapper only; the picture is untouched
    try:
        library.add(path, named(path))
        return "saved"
    except Refused as no:
        log("Photos would not take %s as it is: %s" % (named(path), no))
        if kind == "video" and info["v"] == "av1":
            # Learned once: the next download takes a version that needs no converting.
            write_json(STATE_FILE, dict(read_json(STATE_FILE, {}), av1_refused=True))
    if kind == "video":
        converted = convert(path, info, ctx["converted"])
        if converted:
            path = now_at(converted)
            try:
                library.add(path, named(path))
                return "saved"
            except Refused as no:
                log("Photos would not take %s converted either: %s" % (named(path), no))
    return "kept"


def summary(saved, album, converted, kept, failed, reason=""):
    """The notification."""
    where = "the %s album" % album if album else "Photos"
    lines = ["Nothing was added to Photos." if not saved
             else "Saved to %s." % where if saved == 1
             else "Saved %d items to %s." % (saved, where)]
    if converted:
        lines.append("%d converted (%s)." % (len(converted), converted[0]))
    if kept:
        lines.append("%d kept in Files (a-Shell, UMDL, Saved)." % kept)
    if failed:
        lines.append("%d failed." % failed)
    if reason:
        lines.append(reason)
    return "\n".join(lines)


# ------------------------------------------------------------------ commands

# One download is one job, and a job is in one state at a time. A state does
# one thing, writes what it learned into the job, and names the state that
# follows. The job is saved after every step, in its folder under
# a-Shell > UMDL > Working, so a run that is interrupted, by iOS or by you,
# carries on from the last step and downloads nothing twice.

KEEP_JOBS_FOR = 3 * DAY


class Stop(Exception):
    """The job cannot go on by itself. `reply` is what the shortcut is told."""

    def __init__(self, reply):
        Exception.__init__(self, reply.get("t"))
        self.reply = reply


def clean_jobs(keep):
    """Drop what other downloads left behind long enough ago, and the working
    files of versions before 1.6, which nothing reads any more."""
    for name in ("jobs", "pending"):
        remove(os.path.join(WORKSPACE, name))
    try:
        names = os.listdir(JOBS_DIR)
    except Exception:
        return
    for name in names:
        path = os.path.join(JOBS_DIR, name)
        try:
            stale = time.time() - os.path.getmtime(path) > KEEP_JOBS_FOR
        except OSError:
            stale = True
        if name != keep and stale:
            remove(path)


def load_job(folder, url):
    """The job for this link: the one left unfinished, or a new one."""
    job = read_json(os.path.join(folder, "job.json"), {})
    waiting = [i for i in job.get("items") or [] if i.get("state") == "waiting"]
    if (job.get("url") == url and job.get("state") == "save" and waiting
            and all(os.path.exists(i.get("path") or "") for i in waiting)):
        return job
    return {"url": url, "state": "fetch", "title": "", "failed": 0, "items": [], "converted": []}


def state_fetch(job, ctx):
    """Download. Next: save."""
    remove(os.path.join(ctx["dir"], "out"))
    url = ctx["url"]
    files, errors = [], []
    blocked = False
    # Reddit only: if the site blocks both tools, its own browser is asked instead.
    for engine in plan_engines(url) + (["redditweb"] if is_reddit(url) else []):
        if engine == "redditweb" and not blocked:
            continue
        try:
            files = ENGINES[engine](ctx)
            if files:
                break
        except NeedConfirm as ask:
            raise Stop({"t": "confirm", "url": url, "thr": str(ctx["threshold"]),
                        "n": str(ask.count) if ask.count else "",
                        "title": safe_title(ask.title, "")[:60]})
        except EngineError as exc:
            errors.append(str(exc))
            blocked = blocked or bool(BLOCKED.search(str(exc)))
            log("%s could not do it: %s" % (engine, exc))
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            errors.append(tidy_error(str(exc)))
            log("%s crashed:\n%s" % (engine, traceback.format_exc()))
    if not files:
        # The first tool's message is the relevant one; the fallback's is noise.
        message = errors[0] if errors else "Nothing to download at that link."
        kind = classify_error(" ".join(errors))
        host = hostname(url)
        if BLOCKED.search(" ".join(errors)) and signed_in(host, read_cookie_store()):
            # Signing in is not what is missing, so do not send the user to do it again.
            entry = site_for(host)
            kind = "unknown"
            message = ("%s refused this device or network: %s Being signed in did not help. "
                       "If a VPN is on, turn it off and try again."
                       % (entry[0] if entry else base_domain(host), message.strip()))
        raise Stop({"t": "error", "kind": kind, "msg": message, "url": url})
    job["items"] = stage(ctx, files)
    job["title"] = ctx.get("title") or ""
    job["failed"] = ctx["failed"]
    return "save"


def state_save(job, ctx):
    """Put each file where it belongs: Photos, or Files. Next: done."""
    library, reason = open_library(ctx["album"])
    if reason:
        log("photos: " + reason)
    else:
        ui.start("Saving to Photos")
    for item in job["items"]:
        if item["state"] != "waiting":
            continue
        try:
            outcome = place(ctx, item, library)
        except Exception as exc:
            # Whatever went wrong in there, this file is not lost.
            log("photos: %s: %s" % (type(exc).__name__, exc))
            library, reason, outcome = None, "Photos could not be reached (%s)." % type(exc).__name__, "kept"
        if outcome == "kept":
            os.makedirs(SAVED_DIR, exist_ok=True)
            target = unique_path(SAVED_DIR, "%s.%s" % (item["stem"], ext_of(item["path"]) or "bin"))
            shutil.move(item["path"], target)
        item["state"] = outcome
        ctx["checkpoint"]()
    saved = len([i for i in job["items"] if i["state"] == "saved"])
    if library:
        ui._label = "Saving to Photos"
        ui.done("%d item%s" % (saved, "" if saved == 1 else "s"))
    job["album"] = library.where() if library else ""
    job["reason"] = reason if len(job["items"]) > saved else ""
    return "done"


MACHINE = {"fetch": state_fetch, "save": state_save}


def cmd_run(payload, blob):
    url = clean_url(str(payload.get("url") or ""))
    if not url:
        return callback(payload, {"t": "error", "kind": "nolink", "msg": "No web link.", "url": ""})
    cfg = payload["cfg"]
    mode = str(payload.get("mode") or "auto")
    threshold = max(1, to_int(cfg.get("threshold"), 10))
    limit = 0
    if mode == "first":
        limit = 1
    elif mode == "limit":
        limit = max(1, to_int(payload.get("limit"), threshold))

    os.makedirs(JOBS_DIR, exist_ok=True)
    name = job_id_for(url)
    folder = os.path.join(JOBS_DIR, name)
    clean_jobs(name)
    os.makedirs(folder, exist_ok=True)
    job = load_job(folder, url)
    remove(LOG_FILE)
    log("UMDL %s  %s  mode=%s" % (HELPER_VERSION, url, mode))
    with open(LAST_FILE, "w", encoding="utf-8") as handle:
        handle.write(blob.strip())

    ui.header(hostname(url) or "download")
    state = read_json(STATE_FILE, {})
    latest = None
    if job["state"] == "fetch":
        try:
            ensure_tools(state, force=truthy(payload.get("force_update")))
        except InstallError as exc:
            return callback(payload, {"t": "error", "kind": "install", "msg": str(exc), "url": url})
        latest = check_project_updates(state, str(payload.get("v") or "0"))
        try:
            write_json(STATE_FILE, state)
        except Exception:
            pass
    else:
        log("carrying on: %d file%s already downloaded" % (len(job["items"]), "" if len(job["items"]) == 1 else "s"))
        ui.write("  Carrying on from the last run.\n")

    quality = settings_from(cfg)
    log("limits: resolution %s, frame rate %s" % (quality["res"], quality["fps"]))
    ctx = {
        "url": url, "dir": folder, "mode": mode, "limit": limit, "threshold": threshold,
        "quality": quality, "album": str(cfg.get("album") or "Recents"),
        "titles": {}, "title": job["title"], "failed": job["failed"], "converted": job["converted"],
        "checkpoint": lambda: write_json(os.path.join(folder, "job.json"), job),
    }
    while job["state"] in MACHINE:
        log("state: " + job["state"])
        try:
            job["state"] = MACHINE[job["state"]](job, ctx)
        except Stop as stop:
            if stop.reply.get("t") == "error":
                state = read_json(STATE_FILE, {})
                state["last_run"] = {"at": time.time(), "result": "failed (%s)" % stop.reply.get("kind")}
                write_json(STATE_FILE, state)
            return callback(payload, stop.reply)
        ctx["checkpoint"]()

    saved = len([i for i in job["items"] if i["state"] == "saved"])
    kept = len(job["items"]) - saved
    log("state: done. %d in Photos, %d in Files" % (saved, kept))
    shutil.rmtree(folder, ignore_errors=True)
    state = read_json(STATE_FILE, {})
    state["last_run"] = {"at": time.time(), "result": "saved %d, kept %d" % (saved, kept)}
    write_json(STATE_FILE, state)
    result = {"t": "done", "title": safe_title(job["title"], "")[:60],
              "msg": summary(saved, job.get("album") or "", job["converted"], kept, job["failed"],
                             job.get("reason") or "")}
    if latest:
        result["upv"] = latest["v"]
        result["upurl"] = latest["url"]
    ui.write("\n  %s\n" % ui.c("92", "Finished. Returning to Shortcuts."))
    return callback(payload, result)


def cmd_setup(payload):
    """First run with nothing to download: install the tools and report."""
    ui.header("setting up")
    state = read_json(STATE_FILE, {})
    try:
        ensure_tools(state)
    except InstallError as exc:
        return callback(payload, {"t": "error", "kind": "install", "msg": str(exc), "url": ""})
    write_json(STATE_FILE, state)
    return callback(payload, {"t": "setup", "url": "", "ver": tool_versions()})


def describe_versions(versions):
    order = ("helper", "yt-dlp", "gallery-dl", "ffmpeg", "python")
    return "\n".join("%s  %s" % (key, versions.get(key, "?")) for key in order)


def cmd_update(payload):
    ui.header("updating tools")
    state = read_json(STATE_FILE, {})
    try:
        ok = ensure_tools(state, force=True)
    except InstallError as exc:
        return callback(payload, {"t": "error", "kind": "install", "msg": str(exc), "url": ""})
    check_project_updates(state, str(payload.get("v") or "0"), force=True)
    state.pop("photos_off", None)  # an update is also the way to try saving from a-Shell again
    state.pop("av1_refused", None)
    write_json(STATE_FILE, state)
    versions = tool_versions()
    # This helper keeps running to the end of the update. What will run next
    # time is whatever is in the file now.
    try:
        with open(os.path.abspath(__file__), "r", encoding="utf-8") as handle:
            found = re.search(r'^HELPER_VERSION = "([^"]+)"', handle.read(), re.M)
        versions["helper"] = found.group(1) if found else HELPER_VERSION
    except OSError:
        pass
    title = "Download tools updated" if ok else "The update could not be completed"
    return callback(payload, {"t": "info", "title": title, "msg": describe_versions(versions)})


def folder_size(path):
    total = 0
    for root, _, names in os.walk(path):
        for name in names:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                pass
    return total


def human_size(size):
    for unit in ("bytes", "KB", "MB", "GB"):
        if size < 1000 or unit == "GB":
            return ("%d %s" if unit == "bytes" or size >= 10 else "%.1f %s") % (size, unit)
        size /= 1000.0


def status_text(payload):
    """Everything worth knowing when something is not working, as plain text."""
    versions = tool_versions()
    state = read_json(STATE_FILE, {})
    lines = ["UMDL %s, helper %s" % (payload.get("v") or "?", HELPER_VERSION)]
    app = os.environ.get("APPNAME")
    if app:
        lines.append("%s %s (%s)" % (app, os.environ.get("APPVERSION", "?"),
                                     os.environ.get("APPBUILDNUMBER", "?")))
    lines.append("Python %s" % versions["python"])
    lines.append("yt-dlp %s" % versions["yt-dlp"])
    lines.append("gallery-dl %s" % versions["gallery-dl"])
    lines.append("ffmpeg %s" % versions["ffmpeg"])
    usable = [name for name in ("hevc_videotoolbox", "h264_videotoolbox", "libx264") if name in encoders()]
    lines.append("Converts with: %s" % (", ".join(usable) if usable else "no encoder found"))
    lines.append("AV1: " + av1_verdict()[1])
    checked = float(state.get("tools_checked", 0) or 0)
    lines.append("Tools last updated: %s" % (time.strftime("%d %b %H:%M", time.localtime(checked))
                                             if checked > DAY else "never"))

    lines += ["", "Sign-ins"] + sign_in_lines(read_cookie_store())

    lines += ["", "Storage"]
    lines.append("Working files: %s" % human_size(folder_size(JOBS_DIR)))
    try:
        saved = len(os.listdir(SAVED_DIR))
    except OSError:
        saved = 0
    lines.append("Kept in Files: %d %s" % (saved, "item" if saved == 1 else "items"))
    unfinished = len([n for n in (os.listdir(JOBS_DIR) if os.path.isdir(JOBS_DIR) else [])
                      if os.path.exists(os.path.join(JOBS_DIR, n, "job.json"))])
    lines.append("Unfinished downloads: %s" % (unfinished or "none"))
    try:
        lines.append("Free space: %s" % human_size(shutil.disk_usage(WORKSPACE).free))
    except Exception:
        pass

    lines += ["", "Checks"]
    lines.append("Download tools: %s" % ("ready" if not missing_tools() else "missing"))
    lines.append("GitHub: %s" % ("reachable" if fetch_text(RAW_BASE + "/version.json") else "not reachable"))
    last = state.get("last_run") or {}
    if last.get("at"):
        lines.append("Last download: %s, %s" % (
            time.strftime("%d %b %H:%M", time.localtime(float(last["at"]))), last.get("result", "")))
    else:
        lines.append("Last download: none yet")
    return "\n".join(lines)


def cmd_status(payload):
    ui.header("status")
    ui.start("Checking tools, sign-ins and storage")
    text = status_text(payload)
    ui.done()
    return callback(payload, {"t": "status", "msg": text})


def cmd_signin(payload):
    """Open a site's sign-in page in a-Shell's browser, wait until the sign-in
    is stored, and tell the shortcut. The browser keeps its cookies where both
    download tools read them, so nothing else has to be copied."""
    url = clean_url(str(payload.get("url") or ""))
    host = hostname(url)
    if not host:
        return callback(payload, {"t": "info", "title": "Sign in",
                                  "msg": "That was not a web address."})
    entry = site_for(host)
    label = entry[0] if entry else base_domain(host)
    page = entry[3] if entry else url
    ui.header("sign in to " + label)
    if signed_in(host, read_cookie_store()):
        return callback(payload, {
            "t": "info", "title": "Already signed in to " + label,
            "msg": "To switch accounts, sign out first: Settings, Reset."})
    ui.write("  Sign in on the page that opens.\n"
             "  UMDL returns to Shortcuts once the sign-in is saved.\n\n")
    run_cmd(["internalbrowser", page])
    ui.start("Waiting for the sign-in to %s" % label)
    deadline = time.time() + SIGNIN_WAIT
    found = False
    while time.time() < deadline:
        if signed_in(host, read_cookie_store()):
            found = True
            break
        time.sleep(min(2.0, max(0.05, SIGNIN_WAIT / 20.0)))
    if found:
        ui.done()
        log("signed in to " + label)
        return callback(payload, {
            "t": "info", "title": "Signed in to " + label,
            "msg": "UMDL will use this sign-in for %s links." % label})
    ui.fail("not confirmed")
    return callback(payload, {
        "t": "info", "title": "Sign-in not confirmed",
        "msg": "No sign-in to %s appeared within %d minutes. Status shows whether it was saved. "
               "Some sites block sign-in from in-app browsers." % (label, max(1, SIGNIN_WAIT // 60))})


def forget_sign_ins():
    """Remove what the download tools use to act as the signed-in user: a-Shell's
    cookie store, and the tools' own caches, where gallery-dl keeps tokens."""
    remove(SAFARI_COOKIES)
    for folder in (os.path.join(HOME, ".cache", "gallery-dl"), os.path.join(HOME, ".cache", "yt-dlp"),
                   os.path.join(HOME, "Library", "Caches", "yt-dlp")):
        shutil.rmtree(folder, ignore_errors=True)
    return not os.path.exists(SAFARI_COOKIES)


def cmd_logout(payload):
    """Sign out of every site."""
    ui.header("signing out")
    ui.start("Removing saved sign-ins")
    gone = forget_sign_ins()
    ui.done()
    return callback(payload, {
        "t": "info",
        "title": "Signed out" if gone else "Could not sign out",
        "msg": "All saved sign-ins were removed." if gone else "Open a-Shell, then try again."})


def cmd_reset(payload):
    """Remove everything UMDL put into a-Shell: its folder, the download tools
    and the sign-ins. Files the user keeps in a-Shell for other purposes are
    not touched."""
    ui.header("resetting")
    ui.start("Removing the download tools")
    for command in pip_commands():
        code, out, err = run_cmd(command + ["uninstall", "-y"] + list(REQUIRED_TOOLS) + OPTIONAL_TOOLS)
        if code == 0:
            break
    ui.done()
    ui.start("Removing sign-ins and UMDL's files")
    forget_sign_ins()
    shutil.rmtree(WORKSPACE, ignore_errors=True)
    ui.done()
    return callback(payload, {
        "t": "info", "title": "UMDL was reset",
        "msg": "UMDL's files, the download tools and all sign-ins were removed from a-Shell. "
               "Run UMDL to set it up again."})


def main(argv):
    if len(argv) < 3:
        OUT.write(__doc__ + "\n")
        return 2
    command, blob = argv[1], argv[2]
    try:
        payload = decode_payload(blob)
    except Exception as exc:
        OUT.write("UMDL: unreadable payload (%s)\n" % exc)
        return 2
    os.makedirs(WORKSPACE, exist_ok=True)
    if IOS:
        try:
            subprocess.run("hideKeyboard")
        except Exception:
            pass
    use_site_dirs(read_json(STATE_FILE, {}).get("site_dirs"))
    commands = ("run", "setup", "update", "status", "signin", "logout", "reset")
    if command not in commands or to_int(payload.get("p"), PROTOCOL) != PROTOCOL:
        # A shortcut from another version is talking to this helper.
        callback(payload, {"t": "error", "kind": "outdated", "url": "",
                           "msg": "The shortcut and its helper are different versions."})
        return 2
    try:
        if command == "run":
            cmd_run(payload, blob)
        elif command == "setup":
            cmd_setup(payload)
        elif command == "update":
            cmd_update(payload)
        elif command == "status":
            cmd_status(payload)
        elif command == "reset":
            cmd_reset(payload)
        elif command == "signin":
            cmd_signin(payload)
        elif command == "logout":
            cmd_logout(payload)
    except KeyboardInterrupt:
        ui.stop_spinner()
        OUT.write("\n  Stopped. What is already downloaded is kept in UMDL > Working;\n"
                  "  run UMDL and choose Resume last download to carry on.\n"
                  if command == "run" else "\n  Cancelled.\n")
        return 130
    except Exception as exc:
        # Never strand the user in the terminal: always report back.
        ui.stop_spinner()
        log(traceback.format_exc())
        callback(payload, {"t": "error", "kind": "unknown",
                           "msg": tidy_error("%s: %s" % (type(exc).__name__, exc)),
                           "url": clean_url(str(payload.get("url") or ""))})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

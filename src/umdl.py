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
    python umdl.py logout <payload>     forget saved site sign-ins

Project: https://github.com/TheKfcBandit/UMDL   Licence: MIT
"""

import base64
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

HELPER_VERSION = "1.2.1"
# Bumped only when the payload/callback format changes incompatibly.
PROTOCOL = 2

REPO = "TheKfcBandit/UMDL"
RAW_BASE = "https://raw.githubusercontent.com/%s/main" % REPO
RELEASES_URL = "https://github.com/%s/releases/latest" % REPO
CALLBACK_PREFIX = "UMDLCB:"

HOME = os.path.expanduser("~")
WORKSPACE = os.environ.get("UMDL_HOME") or os.path.join(HOME, "Documents", "UMDL")
JOBS_DIR = os.path.join(WORKSPACE, "jobs")
SAVED_DIR = os.path.join(WORKSPACE, "Saved")
STATE_FILE = os.path.join(WORKSPACE, "state.json")
PENDING_FILE = os.path.join(WORKSPACE, "pending")
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
MAX_PHOTOS_BYTES = int(float(os.environ.get("UMDL_MAX_PHOTOS_MB") or 1000) * 1000 * 1000)

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

_NATIVE_V = "vcodec~='^(avc|h264|hev|hvc|h265)'"
_NATIVE_A = "acodec~='^(mp4a|aac|alac|ac-3|ec-3)'"
# Best stream Photos can import as-is first; anything at all last, in which
# case make_photos_ready() remuxes or converts afterwards.
YTDLP_FORMAT = "/".join([
    "bv*[%s]+ba[%s]" % (_NATIVE_V, _NATIVE_A),
    "b[%s][%s]" % (_NATIVE_V, _NATIVE_A),
    "bv*[%s]+ba" % _NATIVE_V,
    "b[%s]" % _NATIVE_V,
    "b[ext=mp4]",
    "b[ext=mov]",
    "bv*+ba",
    "b",
    "ba",  # audio-only sources such as SoundCloud
])


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
    remove(LAST_FILE)
    if data.get("t") != "status":  # the status report would only repeat itself in the log
        log("callback: " + raw[:2000])
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
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        log("yt-dlp warning: " + strip_ansi(str(msg)))

    def error(self, msg):
        text = strip_ansi(str(msg))
        self.errors.append(text)
        log("yt-dlp error: " + text)


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

    opts = {
        "format": YTDLP_FORMAT,
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


def gallery_attempt(ctx, extra):
    listing = os.path.join(ctx["dir"], "urls.txt")
    with open(listing, "w", encoding="utf-8") as handle:
        handle.write(ctx["url"] + "\n")

    common = ["--input-file", listing, "--retries", "4", "--http-timeout", "30"] + list(extra)
    if have_cookies():
        common += ["--cookies-from-browser", "safari"]

    def last_error(err, fallback):
        errors = [ln for ln in err.splitlines() if "[error]" in ln or "Error" in ln]
        return tidy_error(errors[-1] if errors else (err or fallback))

    threshold = ctx["threshold"]
    if ctx["mode"] == "auto":
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
    if ctx["limit"]:
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


ENGINES = {"ytdlp": ytdlp_engine, "gallery": gallery_engine}


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
        if name in ("manifest.json", "urls.txt"):
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
    """Return {'v': codec, 'a': codec, 'tag': fourcc, 'bitrate': int} via ffprobe."""
    info = {"v": None, "a": None, "tag": "", "bitrate": 0, "ok": False}
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
            elif kind == "audio" and info["a"] is None:
                info["a"] = (stream.get("codec_name") or "").lower()
        info["bitrate"] = to_int((data.get("format") or {}).get("bit_rate"), 0)
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
    return info


def ffmpeg(args, target):
    remove(target)
    code, out, err = run_cmd(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"] + args + [target])
    good = code == 0 and os.path.exists(target) and os.path.getsize(target) > 0
    if not good:
        log("ffmpeg failed (%s): %s" % (code, (err or out)[-800:]))
        remove(target)
    return good


def make_photos_ready(path, convert):
    """Return a path Photos can import, or None to keep the file in Files.

    Cheapest fix first: leave alone, then rewrap without re-encoding, then
    (only if allowed) re-encode with the hardware encoder.
    """
    ext = ext_of(path)
    if ext in IMAGE_EXTS:
        return path
    if ext not in VIDEO_EXTS:
        return None  # audio, archives, documents: Photos has no place for them
    info = probe_media(path)
    if not info["ok"]:
        # Cannot inspect it; trust the container for the usual suspects.
        return path if ext in PHOTOS_CONTAINERS else None
    if not info["v"]:
        return None  # audio-only, whatever the extension says

    video_ok = info["v"] in PHOTOS_VCODECS
    audio_ok = info["a"] is None or info["a"] in PHOTOS_ACODECS
    container_ok = ext in PHOTOS_CONTAINERS
    # Apple players only accept HEVC tagged hvc1, not hev1.
    tag_ok = info["v"] != "hevc" or info["tag"] in ("hvc1", "")
    if video_ok and audio_ok and container_ok and tag_ok:
        return path

    base = os.path.splitext(path)[0]
    target = base + "_photos.mp4"
    audio_args = ["-c:a", "copy"] if audio_ok else ["-c:a", "aac", "-b:a", "192k"]
    tail = ["-map", "0:v:0", "-map", "0:a:0?", "-movflags", "+faststart"]

    if video_ok:
        ui.start("Repacking for Photos")
        tag = ["-tag:v", "hvc1"] if info["v"] == "hevc" else []
        if ffmpeg(["-i", path, "-c:v", "copy"] + tag + audio_args + tail, target):
            ui.done()
            remove(path)
            return target
        ui.fail()
        return None

    if not convert:
        return None

    ui.start("Converting for Photos (this can take a while)")
    rate = info["bitrate"] or 6000000
    rate = int(max(2000000, min(40000000, rate * 1.4)))
    attempts = (
        ["-c:v", "h264_videotoolbox", "-b:v", str(rate), "-pix_fmt", "yuv420p"],
        ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"],
    )
    for video_args in attempts:
        if ffmpeg(["-i", path] + video_args + ["-c:a", "aac", "-b:a", "192k"] + tail, target):
            ui.done()
            remove(path)
            return target
    ui.fail("kept the original in Files")
    return None


def unique_path(folder, name):
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(folder, name)
    n = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return candidate


def finalize(ctx, files):
    """Sort downloads into Photos imports and files kept in the Files app."""
    photos, kept = [], []
    titles = ctx["titles"]
    out_dir = os.path.join(ctx["dir"], "out")
    remove(out_dir)
    os.makedirs(out_dir)
    for index, original in enumerate(files, 1):
        title = titles.get(os.path.basename(original)) or ""
        # Plain sequential names: no spaces or symbols for ffmpeg or Shortcuts to trip on.
        staged = os.path.join(out_dir, "%03d.%s" % (index, ext_of(original) or "bin"))
        os.replace(original, staged)
        ready = make_photos_ready(staged, ctx["convert"])
        if ready:
            try:
                too_big = os.path.getsize(ready) > MAX_PHOTOS_BYTES
            except OSError:
                too_big = False
            if not too_big:
                photos.append(ready)
                continue
            # Too large for a-Shell to hand to Shortcuts: keep it in Files.
            ctx["oversize"] = ctx.get("oversize", 0) + 1
            staged = ready
        os.makedirs(SAVED_DIR, exist_ok=True)
        fallback = os.path.splitext(os.path.basename(original))[0]
        name = "%s.%s" % (safe_title(title, fallback), ext_of(staged) or "bin")
        target = unique_path(SAVED_DIR, name)
        shutil.move(staged, target)
        kept.append(os.path.basename(target))
    return photos, kept


# ------------------------------------------------------------------ commands

def clean_jobs(keep):
    """Drop leftovers from other downloads; keep this job (for resuming) and
    any finished job the shortcut has not saved yet."""
    pending = ""
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as handle:
            pending = handle.read().strip()
    except Exception:
        pass
    try:
        names = os.listdir(JOBS_DIR)
    except Exception:
        return
    for name in names:
        path = os.path.join(JOBS_DIR, name)
        if name == keep or (pending and os.path.dirname(pending) == path):
            continue
        remove(path)


def cmd_run(payload, blob):
    url = clean_url(str(payload.get("url") or ""))
    if not url:
        return callback(payload, {"t": "error", "kind": "nolink",
                                  "msg": "That did not contain a web link.", "url": ""})
    cfg = payload["cfg"]
    mode = str(payload.get("mode") or "auto")
    threshold = max(1, to_int(cfg.get("threshold"), 10))
    limit = 0
    if mode == "first":
        limit = 1
    elif mode == "limit":
        limit = max(1, to_int(payload.get("limit"), threshold))

    os.makedirs(JOBS_DIR, exist_ok=True)
    job = job_id_for(url)
    job_dir = os.path.join(JOBS_DIR, job)
    clean_jobs(job)
    os.makedirs(job_dir, exist_ok=True)
    manifest = os.path.join(job_dir, "manifest.json")
    try:
        with open(PENDING_FILE, "r", encoding="utf-8") as handle:
            if handle.read().strip() == manifest:
                # Downloading the same link again replaces its unsaved result.
                remove(PENDING_FILE)
    except Exception:
        pass
    remove(manifest)
    remove(os.path.join(job_dir, "out"))
    remove(LOG_FILE)
    log("UMDL %s  %s  mode=%s" % (HELPER_VERSION, url, mode))
    with open(LAST_FILE, "w", encoding="utf-8") as handle:
        handle.write(blob.strip())

    ui.header(hostname(url) or "download")
    state = read_json(STATE_FILE, {})
    try:
        updated = ensure_tools(state, force=truthy(payload.get("force_update")))
    except InstallError as exc:
        return callback(payload, {"t": "error", "kind": "install", "msg": str(exc), "url": url})
    latest = check_project_updates(state, str(payload.get("v") or "0"))
    try:
        write_json(STATE_FILE, state)
    except Exception:
        pass

    ctx = {
        "url": url, "dir": job_dir, "mode": mode, "limit": limit,
        "threshold": threshold, "convert": truthy(cfg.get("convert", "1")),
        "titles": {}, "title": "", "failed": 0,
    }
    files, errors = [], []
    for engine in plan_engines(url):
        try:
            files = ENGINES[engine](ctx)
            if files:
                break
        except NeedConfirm as ask:
            return callback(payload, {
                "t": "confirm", "url": url, "thr": str(threshold),
                "n": str(ask.count) if ask.count else "",
                "title": safe_title(ask.title, "")[:60],
            })
        except EngineError as exc:
            errors.append(str(exc))
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
            message = ("%s refused this device or network: %s UMDL is signed in, so the account "
                       "is not the cause. A VPN is a common one: turn it off, then try again."
                       % (entry[0] if entry else base_domain(host), message.strip()))
        state = read_json(STATE_FILE, {})
        state["last_run"] = {"at": time.time(), "result": "failed (%s)" % kind}
        write_json(STATE_FILE, state)
        return callback(payload, {"t": "error", "kind": kind, "msg": message,
                                  "url": url, "updated": "1" if updated else ""})

    photos, kept = finalize(ctx, files)
    write_json(manifest, {"photos": photos, "kept": kept, "url": url})
    result = {
        "t": "done", "m": manifest, "np": str(len(photos)), "nk": str(len(kept)),
        "nf": str(ctx["failed"]) if ctx["failed"] else "",
        "nb": str(ctx["oversize"]) if ctx.get("oversize") else "",
        "title": safe_title(ctx.get("title"), "")[:60],
    }
    state = read_json(STATE_FILE, {})
    state["last_run"] = {"at": time.time(), "result": "saved %d, kept %d" % (len(photos), len(kept))}
    write_json(STATE_FILE, state)
    if photos:
        with open(PENDING_FILE, "w", encoding="utf-8") as handle:
            handle.write(manifest)
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
    write_json(STATE_FILE, state)
    versions = tool_versions()
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
            return ("%d %s" if unit == "bytes" else "%.1f %s") % (size, unit)
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
    lines.append("Unsaved download: %s" % ("yes" if os.path.exists(PENDING_FILE) else "none"))
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


def cmd_status(payload, kind="status"):
    ui.header("status")
    ui.start("Checking tools, sign-ins and storage")
    text = status_text(payload)
    ui.done()
    if kind == "info":  # the "doctor" command of shortcut 1.1.0
        return callback(payload, {"t": "info", "title": "UMDL diagnostics", "msg": text})
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
            "msg": "UMDL already uses this sign-in for %s links.\n\nTo use another account, choose "
                   "Forget saved sign-ins in Settings, then sign in again." % label})
    ui.write("  The sign-in page opens now. Sign in as usual.\n"
             "  UMDL returns to Shortcuts by itself once the sign-in is saved.\n"
             "  If you are back here and nothing happens, check Status in the UMDL menu.\n\n")
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
            "msg": "The sign-in is saved on this device, inside a-Shell. UMDL uses it for %s links "
                   "from now on." % label})
    ui.fail("not confirmed")
    return callback(payload, {
        "t": "info", "title": "Sign-in not confirmed",
        "msg": "No sign-in to %s was found after %d minutes.\n\nIf you did sign in, open Status "
               "from the UMDL menu to check. Some sites do not allow signing in from an app's "
               "built-in browser." % (label, max(1, SIGNIN_WAIT // 60))})


def cmd_logout(payload):
    """Forget site sign-ins: the cookie file both download tools read."""
    ui.header("removing sign-ins")
    ui.start("Removing saved sign-ins")
    remove(SAFARI_COOKIES)
    ui.done()
    gone = not os.path.exists(SAFARI_COOKIES)
    return callback(payload, {
        "t": "info",
        "title": "Sign-ins removed" if gone else "The sign-ins could not be removed",
        "msg": ("The download tools no longer hold any site sign-ins."
                if gone else "Open a-Shell, then try again.")})


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
    commands = ("run", "setup", "update", "status", "doctor", "signin", "logout")
    if command not in commands or to_int(payload.get("p"), PROTOCOL) != PROTOCOL:
        # A shortcut from another version is talking to this helper.
        callback(payload, {"t": "error", "kind": "outdated", "url": "",
                           "msg": "The UMDL shortcut and its helper are different versions. "
                                  "Install the latest UMDL from " + RELEASES_URL})
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
        elif command == "doctor":
            cmd_status(payload, "info")
        elif command == "signin":
            cmd_signin(payload)
        elif command == "logout":
            cmd_logout(payload)
    except KeyboardInterrupt:
        ui.stop_spinner()
        OUT.write("\n  Cancelled.\n")
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

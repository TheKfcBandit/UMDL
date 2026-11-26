"""Stand-in for yt-dlp, used by the shortcut flow tests.

Behaviour comes from the JSON file named in UMDL_FAKE_SCENARIO:
    {"ytdlp": {"suitable": true, "raw": {...}, "error": "message",
               "files": [["name.mp4", "/source/file", "Title"]],
               "download_error": "message",
               "formats": [{"format_id": "137", "vcodec": "avc1", "acodec": "none", ...}],
               "stray_warning": "text yt-dlp writes straight to the terminal",
               "urls": {"part of a link": {...the same keys, for links containing it...}}}}
"""

import json
import os
import shutil
import sys
import types


def _scenario():
    path = os.environ.get("UMDL_FAKE_SCENARIO")
    if not path:
        return {}
    with open(path) as handle:
        return json.load(handle).get("ytdlp") or {}


class DownloadError(Exception):
    pass


utils = types.ModuleType("yt_dlp.utils")
utils.DownloadError = DownloadError
version = types.ModuleType("yt_dlp.version")
version.__version__ = "2099.01.01-fake"


_chosen = [None]


class YoutubeDL:
    def __init__(self, opts):
        self.opts = opts
        self.scenario = _chosen[0] or _scenario()
        record = os.environ.get("UMDL_FAKE_RECORD")
        if record:
            with open(record, "a") as handle:
                plain = {k: v for k, v in opts.items()
                         if isinstance(v, (str, int, bool))
                         or (isinstance(v, list) and all(isinstance(i, str) for i in v))}
                handle.write(json.dumps(plain) + "\n")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False, process=False, ie_key=None):
        for part, special in (self.scenario.get("urls") or {}).items():
            if part in url:
                # Remembered for the download, which is given the result, not the link.
                _chosen[0] = special
                self.scenario = special
        if self.scenario.get("stray_warning"):
            # As yt-dlp's parse_codecs does: past the logger, past "no_warnings".
            sys.stderr.write("WARNING: %s\n" % self.scenario["stray_warning"])
        if self.scenario.get("error"):
            self.opts["logger"].error("ERROR: " + self.scenario["error"])
            raise DownloadError(self.scenario["error"])
        return dict(self.scenario.get("raw") or {"_type": "video", "id": "fake", "title": "Fake"})

    def _produce(self):
        folder = os.path.dirname(self.opts["outtmpl"])
        files = self.scenario.get("files") or []
        items = self.opts.get("playlist_items")
        if items:
            files = files[:int(items.split("-")[-1])]
        # Video and sound that are fetched apart are reported under their own
        # names ("abc.f401.mp4", "abc.f140.m4a"), never under the joined file's.
        parts = self.opts["format"].split("/")[0].split("+")
        for name, source, title in files:
            target = os.path.join(folder, name)
            shutil.copy(source, target)
            stem, ext = os.path.splitext(target)
            reported = ["%s.f%s%s" % (stem, part, ext) for part in parts] if len(parts) > 1 else [target]
            for hook in self.opts["progress_hooks"]:
                for filename in reported:
                    hook({"status": "finished", "filename": filename, "info_dict": {"title": title}})
        if self.scenario.get("download_error"):
            self.opts["logger"].error("ERROR: " + self.scenario["download_error"])
            raise DownloadError(self.scenario["download_error"])

    def sanitize_info(self, info):
        return json.loads(json.dumps(info, default=repr))

    def process_ie_result(self, raw, download=True):
        if not download:
            # Listing what the site offers: the scenario's "formats".
            return dict(raw, formats=self.scenario.get("formats") or raw.get("formats") or [])
        self._produce()

    def download(self, urls):
        self._produce()

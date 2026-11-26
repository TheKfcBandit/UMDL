"""Stand-in for yt-dlp, used by the shortcut flow tests.

Behaviour comes from the JSON file named in UMDL_FAKE_SCENARIO:
    {"ytdlp": {"suitable": true, "raw": {...}, "error": "message",
               "files": [["name.mp4", "/source/file", "Title"]],
               "download_error": "message",
               "formats": [{"format_id": "137", "vcodec": "avc1", "acodec": "none", ...}],
               "urls": {"part of a link": {...the same keys, for links containing it...}}}}
"""

import json
import os
import shutil
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
        for name, source, title in files:
            target = os.path.join(folder, name)
            shutil.copy(source, target)
            for hook in self.opts["progress_hooks"]:
                hook({"status": "finished", "filename": target, "info_dict": {"title": title}})
        if self.scenario.get("download_error"):
            self.opts["logger"].error("ERROR: " + self.scenario["download_error"])
            raise DownloadError(self.scenario["download_error"])

    def process_ie_result(self, raw, download=True):
        if not download:
            # Listing what the site offers: the scenario's "formats".
            return dict(raw, formats=self.scenario.get("formats") or raw.get("formats") or [])
        self._produce()

    def download(self, urls):
        self._produce()

"""The JavaScript the helper runs inside a-Shell's browser, exercised in Node.

The scripts are taken from src/umdl.py exactly as the helper sends them. Node
stands in for the web view: `document` holds a page from tests/reddit_pages.py,
and a-Shell's print channel is replaced by a list. As on iOS 27.2, a script
must report through that channel and leave nothing behind as its own value.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import reddit_pages  # noqa: E402
import umdl  # noqa: E402

HARNESS = r"""
const fs = require("fs");
const page = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
globalThis.window = globalThis;
const printed = [];
window.webkit = {messageHandlers: {aShell: {postMessage: function (text) { printed.push(text); }}}};
globalThis.location = {href: page.href};
const from = page.html.indexOf("<shreddit-post"), to = page.html.indexOf("</shreddit-post>");
globalThis.document = {
  readyState: page.state || "complete", title: page.title || "", body: {innerText: page.words || ""},
  querySelector: (what) => (what === "shreddit-post" && from >= 0 ? {outerHTML: page.html.slice(from, to + 16)} : null),
};
const value = (0, eval)(fs.readFileSync(process.argv[2], "utf8"));
console.log(JSON.stringify({value: typeof value, printed: printed}));
"""


@unittest.skipUnless(shutil.which("node"), "needs Node.js")
class RedditPage(unittest.TestCase):
    def look(self, html, **page):
        """Run the helper's "look" script on a page; returns what it printed."""
        with tempfile.TemporaryDirectory() as folder:
            paths = [os.path.join(folder, name) for name in ("harness.js", "script.js", "page.json")]
            script = umdl.browser_script(umdl.REDDIT_LOOK, umdl.REDDIT_READ)
            page = dict({"href": "https://www.reddit.com/r/me_irl/comments/1abcde/a_post/", "html": html}, **page)
            for path, text in zip(paths, (HARNESS, script, json.dumps(page))):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            done = subprocess.run(["node"] + paths, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  universal_newlines=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertEqual(result["value"], "undefined")           # nothing for jsc to refuse
        self.assertEqual(len(result["printed"]), 1)
        self.assertTrue(result["printed"][0].startswith("print:") and result["printed"][0].endswith("\n"))
        return result["printed"][0][6:-1]

    def post(self, html):
        seen = self.look(html)
        self.assertTrue(seen.startswith("OK "), seen)
        self.assertTrue(seen.isascii())
        return json.loads(seen[3:])

    def test_a_gallery_gives_the_originals_in_order_once_each(self):
        post = self.post(reddit_pages.gallery(3))
        self.assertEqual((post["id"], post["title"], post["type"]), ("1abcde", "Holiday photos", "gallery"))
        self.assertEqual(post["umdl"], ["files", ["https://i.redd.it/img00.jpg", "https://i.redd.it/img01.jpg",
                                                  "https://i.redd.it/img02.jpg"]])

    def test_only_the_post_is_read_not_avatars_or_comments(self):
        post = self.post(reddit_pages.IMAGE)
        self.assertEqual(post["umdl"], ["files", ["https://i.redd.it/qyvi7xrehmwh1.jpeg"]])

    def test_a_video_gives_its_manifest(self):
        post = self.post(reddit_pages.VIDEO)
        self.assertEqual(post["umdl"], ["video", "https://v.redd.it/abc123/DASHPlaylist.mpd"])
        self.assertEqual(post["title"], "Cat falls off shelf")

    def test_a_link_to_another_site_and_a_text_post(self):
        self.assertEqual(self.post(reddit_pages.LINK)["umdl"], ["link", "https://clips.test/watch/9"])
        self.assertEqual(self.post(reddit_pages.TEXT)["umdl"], ["none", ""])

    def test_titles_survive_markup_and_other_alphabets(self):
        post = self.post(reddit_pages.AWKWARD)
        self.assertEqual(post["title"], "Caf&eacute; & \"bar\" – café \U0001f600")

    def test_until_the_post_is_there_the_page_is_described(self):
        seen = self.look("<html><body>Checking your browser</body></html>", title="Reddit - Please wait",
                         words="Checking  your\nbrowser", state="interactive")
        self.assertEqual(seen, "AT https://www.reddit.com/r/me_irl/comments/1abcde/a_post/ | interactive | "
                               "Reddit - Please wait | Checking your browser")

    def test_a_block_page_is_recognised_by_the_helper(self):
        seen = self.look("<html></html>", title="Blocked",
                         words="You've been blocked by network security. If you think you've been blocked by mistake")
        self.assertTrue(umdl.BLOCKED.search(seen))


class RedditLinks(unittest.TestCase):
    def test_every_form_of_link_becomes_the_posts_page_on_the_main_site(self):
        cases = {
            "https://www.reddit.com/r/pcmasterrace/s/nkV2GToMVG": "https://www.reddit.com/r/pcmasterrace/s/nkV2GToMVG",
            "https://reddit.com/r/a/comments/1abcde/title/?utm_source=share&utm_medium=ios":
                "https://www.reddit.com/r/a/comments/1abcde/title/",
            "https://old.reddit.com/r/a/comments/1abcde/": "https://www.reddit.com/r/a/comments/1abcde/",
            "https://redd.it/1abcde": "https://www.reddit.com/comments/1abcde",
        }
        for link, page in cases.items():
            self.assertEqual(umdl.reddit_page(link), page)
            self.assertEqual(umdl.plan_engines(link), ["redditweb"])

    def test_reddits_media_hosts_are_left_to_the_tools(self):
        for link in ("https://i.redd.it/abc.jpg", "https://v.redd.it/abc123/DASHPlaylist.mpd"):
            self.assertFalse(umdl.is_reddit(link))

    def test_what_the_page_said_becomes_what_to_fetch(self):
        self.assertEqual(umdl.reddit_targets({"umdl": ["video", "https://v.redd.it/x/DASHPlaylist.mpd"]}),
                         ("video", "https://v.redd.it/x/DASHPlaylist.mpd"))
        self.assertEqual(umdl.reddit_targets({"umdl": ["files", ["https://i.redd.it/a.jpg"]]}),
                         ("files", ["https://i.redd.it/a.jpg"]))
        for nothing in ({"umdl": ["none", ""]}, {"umdl": ["files", []]}, {}):
            with self.assertRaisesRegex(umdl.EngineError, "No photo or video in this post"):
                umdl.reddit_targets(nothing)


if __name__ == "__main__":
    unittest.main()

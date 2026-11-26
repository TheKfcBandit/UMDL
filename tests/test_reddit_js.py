"""The JavaScript the helper runs inside a-Shell's browser, exercised in Node.

The script is taken from src/umdl.py exactly as the helper would send it. Node
stands in for the web view: `fetch` is replaced by a recording that answers
the way Reddit does in each case, and a-Shell's print channel is replaced by a
list. As on iOS 27.2, the script must report through that channel and leave
nothing behind as its own value.
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

import umdl  # noqa: E402

HARNESS = r"""
const fs = require("fs");
const plan = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const calls = [];
globalThis.window = globalThis;
const printed = [];
window.webkit = {messageHandlers: {aShell: {postMessage: function (text) { printed.push(text); }}}};
globalThis.fetch = async function (link, options) {
  const method = (options && options.method) || "GET";
  calls.push([method, link, (options && options.credentials) || ""]);
  const answer = plan[method + " " + link];
  if (answer === undefined || answer.fail) { throw new TypeError("Load failed"); }
  return {url: answer.url || "", status: answer.status || 200, text: async () => answer.body || ""};
};
const value = (0, eval)(fs.readFileSync(process.argv[2], "utf8"));
setTimeout(function () {
  console.log(JSON.stringify({value: typeof value, printed: printed, answer: window.__umdl,
                              calls: calls}));
}, 50);
"""

POST = {"id": "1abcde", "title": "Café \U0001f600", "url": "https://i.redd.it/pic.jpg",
        "ups": 5, "selftext": "", "is_video": False,
        "media": None, "secure_media": None}
LISTING = [{"data": {"children": [{"data": POST}]}}, {"data": {"children": []}}]
JSON_PATH = "/comments/1abcde/.json?raw_json=1&limit=1"
CANONICAL = "https://www.reddit.com/r/me_irl/comments/1abcde/some_title/?share_id=x"


@unittest.skipUnless(shutil.which("node"), "needs Node.js")
class RedditScript(unittest.TestCase):
    def run_script(self, link, plan):
        with tempfile.TemporaryDirectory() as folder:
            paths = [os.path.join(folder, name) for name in ("harness.js", "script.js", "plan.json")]
            script = umdl.browser_script('"started"',
                                         umdl.REDDIT_JS.replace("__URL__", json.dumps(link)))
            for path, text in zip(paths, (HARNESS, script, json.dumps(plan))):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(text)
            out = subprocess.run(["node"] + paths, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 universal_newlines=True)
            self.assertEqual(out.stderr, "")
            return json.loads(out.stdout)

    def test_share_link_is_followed_to_the_post(self):
        share = "/r/me_irl/s/cUdJnFfPwD"
        result = self.run_script("https://www.reddit.com" + share, {
            "HEAD " + share: {"url": CANONICAL},
            "GET " + JSON_PATH: {"body": json.dumps(LISTING)}})
        self.assertEqual(result["printed"], ["print:started\n"])   # through a-Shell's channel
        self.assertEqual(result["value"], "undefined")              # and nothing as its own value
        self.assertEqual(result["calls"], [["HEAD", share, "include"], ["GET", JSON_PATH, "include"]])
        self.assertTrue(result["answer"].startswith("OK "))
        self.assertTrue(result["answer"].isascii())
        post = json.loads(result["answer"][3:])
        self.assertEqual(post, {"id": "1abcde", "title": POST["title"], "url": POST["url"],
                                "is_video": False, "media": None, "secure_media": None})

    def test_share_link_falls_back_to_get(self):
        share = "/r/me_irl/s/cUdJnFfPwD"
        result = self.run_script("https://reddit.com" + share + "?utm=1", {
            "HEAD " + share + "?utm=1": {"fail": True},
            "GET " + share + "?utm=1": {"url": CANONICAL},
            "GET " + JSON_PATH: {"body": json.dumps(LISTING)}})
        self.assertTrue(result["answer"].startswith("OK "))

    def test_post_links_and_short_links_need_no_hop(self):
        for link in ("https://old.reddit.com/r/pics/comments/1abcde/title/", "https://redd.it/1abcde"):
            result = self.run_script(link, {"GET " + JSON_PATH: {"body": json.dumps(LISTING)}})
            self.assertEqual(result["calls"], [["GET", JSON_PATH, "include"]], link)
            self.assertTrue(result["answer"].startswith("OK "), link)

    def test_crosspost_brings_the_original_along(self):
        listing = json.loads(json.dumps(LISTING))
        parent = {"id": "orig", "is_video": True, "secure_media": {"reddit_video": {"dash_url": "d"}},
                  "author": "someone"}
        listing[0]["data"]["children"][0]["data"]["crosspost_parent_list"] = [parent]
        result = self.run_script(CANONICAL, {"GET " + JSON_PATH: {"body": json.dumps(listing)}})
        post = json.loads(result["answer"][3:])
        self.assertEqual(post["crosspost_parent_list"],
                         [{"id": "orig", "is_video": True,
                           "secure_media": {"reddit_video": {"dash_url": "d"}}}])

    PAGE_PATH = "/r/me_irl/comments/1abcde/some_title/?share_id=x"
    BLOCK = ("<html><head><style>.theme-light,:root{--rem360:22.5rem}</style></head><body>"
             "<h1>\"You've been blocked by network security.\"</h1>\n<p>To continue</p></body></html>")

    def page(self, attributes, inside=""):
        return ("<html><body><shreddit-app><shreddit-post " + attributes + ">" + inside +
                "</shreddit-post><shreddit-comment-tree><img src=\"https://preview.redd.it/not-the-post.jpg\">"
                "</shreddit-comment-tree></body></html>")

    def from_page(self, html):
        return self.run_script(CANONICAL, {"GET " + JSON_PATH: {"status": 403, "body": self.BLOCK},
                                           "GET " + self.PAGE_PATH: {"body": html}})

    def test_when_the_data_is_refused_the_posts_page_is_read(self):
        result = self.from_page(self.page(
            'id="t3_1abcde" post-title="Tom &amp; Jerry&#x27;s &quot;best&quot;" post-type="video" '
            'content-href="https://v.redd.it/abc123xyz"',
            '<shreddit-player-2 src="https://v.redd.it/abc123xyz/HLSPlaylist.m3u8?a=1&amp;v=1"></shreddit-player-2>'))
        self.assertEqual(result["calls"][-1], ["GET", self.PAGE_PATH, "include"])
        post = json.loads(result["answer"][3:])
        self.assertEqual(post, {"id": "1abcde", "title": "Tom & Jerry's \"best\"",
                                "umdl": ["video", "https://v.redd.it/abc123xyz/DASHPlaylist.mpd"]})
        self.assertEqual(umdl.reddit_targets(post), ("video", "https://v.redd.it/abc123xyz/DASHPlaylist.mpd"))

    def test_a_gallery_on_the_page_gives_the_originals_in_order_once_each(self):
        slides = "".join('<li><img src="https://preview.redd.it/%s?width=640&amp;s=x"></li>' % name for name in (
            "first-slide-v0-aaa111.jpg", "bbb222.png", "first-slide-v0-aaa111.jpg"))
        slides += '<li><img data-lazy-src="https://preview.redd.it/ccc333.jpeg?width=640"></li>'
        post = json.loads(self.from_page(self.page('id="t3_1abcde" post-title="Set" post-type="gallery"',
                                                   slides))["answer"][3:])
        self.assertEqual(post["umdl"], ["files", ["https://i.redd.it/aaa111.jpg", "https://i.redd.it/bbb222.png",
                                                  "https://i.redd.it/ccc333.jpeg"]])     # nothing from the comments

    def test_a_single_image_and_a_link_to_another_site(self):
        post = json.loads(self.from_page(self.page(
            'id="t3_1abcde" post-title="Pic" post-type="image" content-href="https://i.redd.it/zzz999.jpeg"',
            '<img src="https://preview.redd.it/zzz999.jpeg?width=320">'))["answer"][3:])
        self.assertEqual(post["umdl"], ["files", ["https://i.redd.it/zzz999.jpeg"]])
        post = json.loads(self.from_page(self.page(
            'id="t3_1abcde" post-title="Clip" post-type="link" content-href="https://streamable.com/abc"'))["answer"][3:])
        self.assertEqual(umdl.reddit_targets(post), ("link", "https://streamable.com/abc"))

    def test_a_text_post_on_the_page_has_nothing_to_download(self):
        post = json.loads(self.from_page(self.page(
            'id="t3_1abcde" post-title="Words" post-type="text" '
            'content-href="https://www.reddit.com/r/me_irl/comments/1abcde/words/"'))["answer"][3:])
        self.assertEqual(post["umdl"], ["none", ""])
        with self.assertRaises(umdl.EngineError):
            umdl.reddit_targets(post)

    def test_a_block_on_both_is_reported_with_what_it_says(self):
        result = self.run_script(CANONICAL, {"GET " + JSON_PATH: {"status": 403, "body": self.BLOCK},
                                             "GET " + self.PAGE_PATH: {"status": 403, "body": self.BLOCK}})
        self.assertEqual(result["answer"], "HTTP 403, page 403: \"You've been blocked by network security.\" To continue")

    def test_no_connection_and_no_post(self):
        result = self.run_script(CANONICAL, {})
        self.assertEqual(result["answer"], "ERR TypeError: Load failed")
        result = self.run_script("https://www.reddit.com/r/pics/s/AbCdEfGhIj", {
            "HEAD /r/pics/s/AbCdEfGhIj": {"url": "https://www.reddit.com/r/pics/"}})
        self.assertEqual(result["answer"], "ERR no post found at https://www.reddit.com/r/pics/")


if __name__ == "__main__":
    unittest.main()

"""The JavaScript the helper runs inside a-Shell's browser, exercised in Node.

The script is taken from src/umdl.py exactly as the helper would send it. Node
stands in for the web view: `fetch` is replaced by a recording that answers
the way Reddit does in each case.
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
globalThis.fetch = async function (link, options) {
  const method = (options && options.method) || "GET";
  calls.push([method, link, (options && options.credentials) || ""]);
  const answer = plan[method + " " + link];
  if (answer === undefined || answer.fail) { throw new TypeError("Load failed"); }
  return {url: answer.url || "", status: answer.status || 200, text: async () => answer.body || ""};
};
const started = (0, eval)(fs.readFileSync(process.argv[2], "utf8"));
setTimeout(function () {
  console.log(JSON.stringify({started: started, answer: window.__umdl, calls: calls}));
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
            for path, text in zip(paths, (HARNESS, umdl.REDDIT_JS.replace("__URL__", json.dumps(link)),
                                          json.dumps(plan))):
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
        self.assertEqual(result["started"], "started")
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

    def test_a_block_page_is_reported_with_what_it_says(self):
        page = "<html><body><h1>\"You've been blocked by network security.\"</h1>\n<p>To continue</p></body></html>"
        result = self.run_script(CANONICAL, {"GET " + JSON_PATH: {"status": 403, "body": page}})
        self.assertEqual(result["answer"],
                         "HTTP 403 \"You've been blocked by network security.\" To continue")

    def test_a_refusal_in_json_is_reported(self):
        body = json.dumps({"reason": "private", "message": "Forbidden", "error": 403})
        result = self.run_script(CANONICAL, {"GET " + JSON_PATH: {"status": 403, "body": body}})
        self.assertEqual(result["answer"], "HTTP 403 Forbidden")

    def test_no_connection_and_no_post(self):
        result = self.run_script(CANONICAL, {})
        self.assertEqual(result["answer"], "ERR TypeError: Load failed")
        result = self.run_script("https://www.reddit.com/r/pics/s/AbCdEfGhIj", {
            "HEAD /r/pics/s/AbCdEfGhIj": {"url": "https://www.reddit.com/r/pics/"}})
        self.assertEqual(result["answer"], "ERR no post found at https://www.reddit.com/r/pics/")


if __name__ == "__main__":
    unittest.main()

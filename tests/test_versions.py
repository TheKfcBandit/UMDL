"""The version is written in three places; they must agree."""

import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class Versions(unittest.TestCase):
    def setUp(self):
        self.meta = json.loads(read("version.json"))
        self.shortcut = read("src", "UMDL.cherri")
        self.helper = read("src", "umdl.py")

    def test_shortcut_version(self):
        found = re.search(r'^@umdlVersion = "([^"]+)"', self.shortcut, flags=re.M).group(1)
        self.assertEqual(found, self.meta["shortcut"])

    def test_helper_version(self):
        found = re.search(r'^HELPER_VERSION = "([^"]+)"', self.helper, flags=re.M).group(1)
        self.assertEqual(found, self.meta["helper"])

    def test_protocol(self):
        shortcut = re.search(r'^@protocol = "(\d+)"', self.shortcut, flags=re.M).group(1)
        helper = re.search(r"^PROTOCOL = (\d+)", self.helper, flags=re.M).group(1)
        self.assertEqual(int(shortcut), self.meta["protocol"])
        self.assertEqual(int(helper), self.meta["protocol"])

    def test_repository_is_named_consistently(self):
        repo = re.search(r'^REPO = "([^"]+)"', self.helper, flags=re.M).group(1)
        self.assertIn("raw.githubusercontent.com/%s/main/src/umdl.py" % repo, self.shortcut)
        self.assertIn("raw.githubusercontent.com/%s/main/version.json" % repo, self.shortcut)
        self.assertIn(repo, self.meta["url"])


class PlaygroundCopy(unittest.TestCase):
    def test_single_file_source_is_current(self):
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import make_playground
        expected, count = make_playground.render()
        self.assertGreater(count, 0)
        self.assertEqual(read("playground", "UMDL.cherri"), expected,
                         "run `make playground` and commit the result")


if __name__ == "__main__":
    unittest.main()

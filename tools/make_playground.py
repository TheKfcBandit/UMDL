#!/usr/bin/env python3
"""Write a single-file copy of the shortcut source with the icons inlined.

The normal source embeds the menu icons from assets/icons at compile time,
which needs the files on disk. This copy carries them as text instead, so
it can be pasted into the Cherri Playground (https://playground.cherrilang.org)
and compiled and signed there, with no Mac and no API key.

    python tools/make_playground.py [output path]     # default: playground/UMDL.cherri

The result is committed, so anyone can copy it straight from GitHub.
tests/test_versions.py fails if it is out of date.
"""

import base64
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def render():
    """Return (single-file source, number of icons inlined)."""
    with open(os.path.join(ROOT, "src", "UMDL.cherri"), encoding="utf-8") as handle:
        source = handle.read()

    def inline(match):
        with open(os.path.join(ROOT, match.group(1)), "rb") as handle:
            return '"%s"' % base64.b64encode(handle.read()).decode("ascii")

    return re.subn(r'embedFile\("([^"]+)"\)', inline, source)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "playground", "UMDL.cherri")
    result, count = render()
    if count == 0 or "embedFile" in result:
        sys.exit("expected embedFile(...) calls to inline; found %d" % count)
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        handle.write(result)
    print("wrote %s (%d icons inlined)" % (target, count))


if __name__ == "__main__":
    main()

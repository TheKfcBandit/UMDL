import json
import os


class _Found:
    category = "fakegallery"


def find(url):
    path = os.environ.get("UMDL_FAKE_SCENARIO")
    if not path:
        return None
    with open(path) as handle:
        scenario = json.load(handle).get("gallery") or {}
    return _Found() if scenario.get("found") else None

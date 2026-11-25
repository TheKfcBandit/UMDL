import json
import os


def gen_extractor_classes():
    path = os.environ.get("UMDL_FAKE_SCENARIO")
    scenario = {}
    if path:
        with open(path) as handle:
            scenario = json.load(handle).get("ytdlp") or {}

    class FakeIE:
        IE_NAME = "fake"

        @classmethod
        def suitable(cls, url):
            return bool(scenario.get("suitable", True))

    return [FakeIE]

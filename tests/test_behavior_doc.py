"""docs/BEHAVIOR.md and the shortcut must describe the same thing.

Two checks. Every label the compiled shortcut can put on screen (menu items,
the first line of each menu, alert titles, the rows of the icon menus) appears
in the document. And every test the document names exists, while every flow
test of a documented section is named in it.
"""

import os
import plistlib
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_shortcut_flow as flows  # noqa: E402

SECTIONS = ("Onboarding", "OneTap", "LargeDownloads", "Errors", "Recovery", "MainMenu", "Settings")
VARIABLE = "\ufffc"  # where Shortcuts inserts a variable into a text


def literal(value):
    """The fixed text of a parameter, with a marker wherever a variable goes."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        inner = value.get("WFValue", value).get("Value", {})
        if isinstance(inner, dict) and "string" in inner:
            return inner["string"]
        return VARIABLE
    return ""


def labels(plist):
    found = set()
    for action in plist["WFWorkflowActions"]:
        kind = action["WFWorkflowActionIdentifier"].rsplit(".", 1)[-1]
        params = action.get("WFWorkflowActionParameters", {})
        if kind == "choosefrommenu" and params.get("WFControlFlowMode") == 0:
            found.update(literal(item) for item in params.get("WFMenuItems", []))
            found.add(literal(params.get("WFMenuPrompt", "")).split("\n")[0])
        elif kind == "alert":
            found.add(literal(params.get("WFAlertActionTitle", "")))
        elif kind == "gettext":
            text = literal(params.get("WFTextActionText", ""))
            if "BEGIN:VCARD" in text:
                found.update(re.findall(r"\nN;CHARSET=utf-8:([^;\n]+);", text))
                found.update(re.findall(r"\nORG;CHARSET=utf-8:([^;\n]+);", text))
    return sorted(label for label in found if label.strip(VARIABLE + " "))


@unittest.skipUnless(flows.PLIST, "compile the shortcut first")
class BehaviourDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "docs", "BEHAVIOR.md"), encoding="utf-8") as handle:
            cls.doc = handle.read()
        with open(flows.PLIST, "rb") as handle:
            cls.plist = plistlib.load(handle)

    def test_every_label_the_shortcut_shows_is_described(self):
        found = labels(self.plist)
        self.assertGreater(len(found), 60)  # the extraction itself still works
        missing = []
        for label in found:
            parts = [part.strip() for part in label.split(VARIABLE)]
            if not all(part in self.doc for part in parts if len(part) > 2):
                missing.append(label.replace(VARIABLE, "{...}"))
        self.assertEqual(missing, [], "describe these in docs/BEHAVIOR.md")

    def test_every_test_the_document_names_exists(self):
        named = set(re.findall(r"`(\w+)\.(test_\w+)`", self.doc))
        self.assertGreater(len(named), 40)
        unknown = sorted("%s.%s" % pair for pair in named
                         if not hasattr(getattr(flows, pair[0], None), pair[1]))
        self.assertEqual(unknown, [])

    def test_every_flow_test_is_named_in_the_document(self):
        named = set(re.findall(r"`(\w+)\.(test_\w+)`", self.doc))
        unnamed = sorted("%s.%s" % (section, name)
                         for section in SECTIONS
                         for name in dir(getattr(flows, section)) if name.startswith("test_")
                         if (section, name) not in named)
        self.assertEqual(unnamed, [], "name these next to the behaviour they pin down")


if __name__ == "__main__":
    unittest.main()

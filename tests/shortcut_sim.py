"""A small interpreter for the compiled UMDL shortcut.

Shortcuts cannot be run off-device, so this executes the actions in the
compiled plist with a model of each action UMDL uses. a-Shell is modelled
too: background commands run in a real `dash` with HOME pointed at a temp
folder, and foreground commands run the real helper (src/umdl.py) with
stand-in download tools. A helper callback becomes the input of the next
shortcut run, exactly as the shortcuts:// URL does on a phone.

This checks the shortcut's logic and its protocol with the helper. It is a
model, not iOS: only a run on a real device proves the real thing.
"""

import base64
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAKES = os.path.join(ROOT, "tests", "fakes")
PREFIX = "is.workflow.actions."
ASHELL = "AsheKube.app.a-Shell."


class SimError(AssertionError):
    pass


class Stop(Exception):
    pass


class File:
    def __init__(self, data=b"", path="", name=""):
        self.data, self.path, self.name = data, path, name


class Contact:
    def __init__(self, name, detail):
        self.name, self.detail = name, detail


class Matches(list):
    """Text matches that remember their regex groups."""


def utf16_len(text):
    return len(text.encode("utf-16-le")) // 2


def as_text(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, dict):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, File):
        return value.data.decode("utf-8", "replace")
    if isinstance(value, Contact):
        return value.name
    if isinstance(value, (list, tuple)):
        return "\n".join(as_text(v) for v in value)
    return str(value)


def as_list(value):
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def has_value(value):
    if value is None:
        return False
    if isinstance(value, (str, list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, File):
        return len(value.data) > 0
    return True


def as_dict(value):
    if isinstance(value, dict):
        return value
    if not has_value(value):
        return None
    text = as_text(value).strip()
    try:
        parsed = json.loads(text)
    except Exception:
        raise SimError("Shortcuts could not convert this to a dictionary: %r" % text[:120])
    if not isinstance(parsed, dict):
        raise SimError("not a dictionary: %r" % text[:120])
    return parsed


def parse_vcards(text):
    cards = []
    for block in re.findall(r"BEGIN:VCARD(.*?)END:VCARD", text, flags=re.S):
        name = re.search(r"^N[^:\n]*:([^;\n]*)", block, flags=re.M)
        detail = re.search(r"^ORG[^:\n]*:([^;\n]*)", block, flags=re.M)
        photo = re.search(r"^PHOTO;ENCODING=b:(\S+)", block, flags=re.M)
        if not name or not photo:
            raise SimError("malformed vCard: %r" % block[:120])
        base64.b64decode(photo.group(1), validate=True)
        cards.append(Contact(name.group(1), detail.group(1) if detail else ""))
    return cards


class World:
    """Everything that outlives a single shortcut run: the phone, in effect."""

    def __init__(self, plist_path):
        with open(plist_path, "rb") as handle:
            self.plist = plistlib.load(handle)
        self.home = tempfile.mkdtemp(prefix="umdl-sim-")
        self.workspace = os.path.join(self.home, "Documents", "UMDL")
        self.scenario_path = os.path.join(self.home, "scenario.json")
        self.record_path = os.path.join(self.home, "ytdlp-opts.jsonl")
        self.set_scenario({})
        self.clipboard = ""
        self.version_json = ""
        self.offline = False
        self.ui = []          # scripted answers: ("menu"|"list"|"ask", text)
        self.events = []      # everything the user would see or that left the shortcut
        self.photos = []      # (file name, album, byte size)
        self.albums = []
        self.commands = []    # (openWindow, command text)
        self.helper_runs = [] # (command, decoded payload)
        self.callbacks = []   # callback texts waiting to re-run the shortcut
        self.helper_output = ""

    def close(self):
        shutil.rmtree(self.home, ignore_errors=True)

    # -- set-up helpers ---------------------------------------------------

    def set_scenario(self, scenario):
        with open(self.scenario_path, "w") as handle:
            json.dump(scenario, handle)

    def install(self, config=None):
        """Pretend setup already happened."""
        os.makedirs(os.path.join(self.workspace, "env"), exist_ok=True)
        shutil.copy(os.path.join(ROOT, "src", "umdl.py"), os.path.join(self.workspace, "umdl.py"))
        if config is not None:
            blob = base64.b64encode(json.dumps(config).encode()).decode()
            with open(os.path.join(self.workspace, "config.b64"), "w") as handle:
                handle.write(blob + "\n")

    def read_config(self):
        with open(os.path.join(self.workspace, "config.b64")) as handle:
            return json.loads(base64.b64decode(handle.read().strip()))

    def script(self, *answers):
        self.ui.extend(answers)

    # -- running ----------------------------------------------------------

    def run(self, shared=None):
        """One run of the shortcut, the way a tap or a callback starts it."""
        Run(self, shared).execute()

    def share(self, shared=None):
        """Run the shortcut, then keep re-running it for every helper callback."""
        self.run(shared)
        guard = 0
        while self.callbacks:
            guard += 1
            if guard > 8:
                raise SimError("callback loop did not settle")
            self.run(self.callbacks.pop(0))
        if self.ui:
            raise SimError("scripted answers were never used: %r" % (self.ui,))

    def seen(self, kind):
        return [e for e in self.events if e[0] == kind]

    # -- a-Shell ----------------------------------------------------------

    def env(self):
        env = dict(os.environ)
        env.update({
            "HOME": self.home,
            "UMDL_PLATFORM": "desktop",
            "UMDL_SKIP_UPDATES": "1",
            "NO_COLOR": "1",
            "UMDL_FAKE_SCENARIO": self.scenario_path,
            "UMDL_FAKE_RECORD": self.record_path,
            "PYTHONPATH": FAKES,
            "PATH": os.path.join(FAKES, "bin") + os.pathsep + env.get("PATH", ""),
        })
        env.pop("UMDL_HOME", None)
        return env

    def background(self, command):
        """An "in extension" command: runs without opening a-Shell, returns stdout."""
        if command.startswith("curl "):
            if "-f" not in command.split()[1]:
                raise SimError("curl without -f would hand an error page to the shortcut")
            return "" if self.offline else self.version_json
        proc = subprocess.run(["dash", "-c", command], env=self.env(), cwd=self.home,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True)
        if proc.returncode != 0:
            raise SimError("background command failed: %s\n%s" % (command, proc.stderr))
        return proc.stdout

    def foreground(self, command):
        """A command typed into the a-Shell window, one line at a time."""
        for line in command.split("\n"):
            line = line.strip()
            words = line.split()
            if not words or line in ("clear", "hideKeyboard", "deactivate", "cd", "clear && cd"):
                continue
            if words[0] == "echo" or words[0] == "source" or line.startswith("cd $HOME"):
                continue
            if words[0] == "mkdir":
                self.background(line)
            elif line.startswith("python -m venv "):
                os.makedirs(os.path.expandvars(words[3].replace("$HOME", self.home)), exist_ok=True)
            elif words[0] == "pip":
                continue
            elif words[0] == "curl":
                target = words[words.index("-o") + 1].replace("$HOME", self.home)
                if not self.offline:
                    if "/main/src/umdl.py" not in line:
                        raise SimError("unexpected download: " + line)
                    shutil.copy(os.path.join(ROOT, "src", "umdl.py"), target)
            elif words[0] == "python":
                self.helper(words)
            elif words[0] == "internalbrowser":
                self.events.append(("browser", words[1]))
            else:
                raise SimError("a-Shell would not understand: %r" % line)

    def helper(self, words):
        script = words[1].replace("$HOME", self.home)
        if not os.path.isabs(script):
            script = os.path.join(self.workspace, script)
        if len(words) != 4:
            raise SimError("helper needs exactly a command and a payload: %r" % (words,))
        command, blob = words[2], words[3]
        if not re.fullmatch(r"[A-Za-z0-9+/=]+", blob):
            raise SimError("payload is not shell-safe base64: %r" % blob[:60])
        self.helper_runs.append((command, json.loads(base64.b64decode(blob))))
        if not os.path.exists(script):
            self.events.append(("helper-missing", script))
            return
        proc = subprocess.run([sys.executable, script, command, blob], env=self.env(),
                              cwd=self.workspace, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, universal_newlines=True)
        self.helper_output = proc.stdout
        for line in proc.stdout.splitlines():
            if line.startswith("CALLBACK "):
                url = urllib.parse.urlsplit(line[len("CALLBACK "):])
                query = urllib.parse.parse_qs(url.query)
                if url.scheme != "shortcuts" or query["name"] != ["UMDL"]:
                    raise SimError("callback would not reach UMDL: " + line)
                self.callbacks.append(query["text"][0])
                return
        raise SimError("helper finished without calling back:\n" + proc.stdout)


class Run:
    def __init__(self, world, shared):
        self.world = world
        self.shared = shared
        self.actions = world.plist["WFWorkflowActions"]
        self.vars = {}
        self.outputs = {}
        self.groups = {}
        for index, action in enumerate(self.actions):
            params = action.get("WFWorkflowActionParameters", {})
            gid = params.get("GroupingIdentifier")
            if gid is None:
                continue
            group = self.groups.setdefault(gid, {"cases": []})
            mode = params.get("WFControlFlowMode")
            if mode == 0:
                group["start"] = index
            elif mode == 2:
                group["end"] = index
            elif action["WFWorkflowActionIdentifier"].endswith("choosefrommenu"):
                group["cases"].append(index)
            else:
                group["else"] = index

    # -- values -----------------------------------------------------------

    def resolve(self, value):
        if isinstance(value, dict) and "WFSerializationType" in value:
            kind, inner = value["WFSerializationType"], value.get("Value")
            if kind == "WFTextTokenString":
                return self.token_string(inner)
            if kind == "WFTextTokenAttachment":
                return self.attachment(inner)
            if kind == "WFDictionaryFieldValue":
                return self.dictionary(inner)
            raise SimError("unmodelled value type " + kind)
        if isinstance(value, dict) and value.get("Type") == "Variable" and "Variable" in value:
            return self.resolve(value["Variable"])
        return value

    def token_string(self, inner):
        text = inner["string"]
        spots = {}
        for key, attachment in (inner.get("attachmentsByRange") or {}).items():
            spots[int(key.strip("{}").split(",")[0])] = attachment
        if not spots:
            return text
        out, offset = [], 0
        for char in text:
            if offset in spots:
                if char != "￼":
                    raise SimError("attachment offset does not land on a placeholder")
                out.append(as_text(self.attachment(spots.pop(offset))))
            else:
                out.append(char)
            offset += utf16_len(char)
        if spots:
            raise SimError("attachment offsets beyond the text: %r" % list(spots))
        return "".join(out)

    def attachment(self, ref):
        kind = ref.get("Type")
        if kind == "ActionOutput":
            if ref["OutputUUID"] not in self.outputs:
                raise SimError("output %r read before its action ran" % ref.get("OutputName"))
            value = self.outputs[ref["OutputUUID"]]
        elif kind == "Variable":
            value = self.vars.get(ref["VariableName"])
        elif kind == "ExtensionInput":
            value = self.shared
        elif kind == "Clipboard":
            value = self.world.clipboard
        else:
            raise SimError("unmodelled reference " + str(kind))
        for extra in ref.get("Aggrandizements") or []:
            if extra["Type"] == "WFDictionaryValueVariableAggrandizement":
                source = as_dict(value)
                value = source.get(extra["DictionaryKey"]) if source else None
            elif extra["Type"] == "WFCoercionVariableAggrandizement":
                target = extra["CoercionItemClass"]
                if target == "WFContactContentItem":
                    value = parse_vcards(as_text(value))
                elif target == "WFDictionaryContentItem":
                    value = as_dict(value)
                elif target == "WFStringContentItem":
                    value = as_text(value)
            else:
                raise SimError("unmodelled aggrandizement " + extra["Type"])
        return value

    def dictionary(self, inner):
        # Nested dictionaries are wrapped twice in a real Shortcuts plist.
        if "WFDictionaryFieldValueItems" not in inner and isinstance(inner.get("Value"), dict):
            inner = inner["Value"]
        result = {}
        for item in inner.get("WFDictionaryFieldValueItems", []):
            key = as_text(self.resolve(item["WFKey"]))
            value = self.resolve(item["WFValue"])
            result[key] = value if isinstance(value, dict) else as_text(value)
        return result

    # -- control flow -----------------------------------------------------

    def condition(self, params):
        value = self.resolve(params.get("WFInput"))
        code = params.get("WFCondition")
        if code == 100:
            return has_value(value)
        if code == 101:
            return not has_value(value)
        if "WFNumberValue" in params:
            left = float(as_text(value) or 0)
            right = float(as_text(self.resolve(params["WFNumberValue"])) or 0)
            return {4: left == right, 5: left != right, 0: left < right, 1: left <= right,
                    2: left > right, 3: left >= right}[code]
        left = as_text(value)
        right = as_text(self.resolve(params.get("WFConditionalActionString", "")))
        if code == 4:
            return left == right
        if code == 5:
            return left != right
        if code == 8:
            return left.startswith(right)
        if code == 9:
            return left.endswith(right)
        if code == 99:
            return right.lower() in left.lower()
        if code == 999:
            return right.lower() not in left.lower()
        raise SimError("unmodelled condition %r" % code)

    def answer(self, kind, describe):
        if not self.world.ui:
            raise SimError("the shortcut asked something the test did not expect: " + describe)
        got, text = self.world.ui.pop(0)
        if got != kind:
            raise SimError("expected a %s answer for %s, test supplied %s %r"
                           % (kind, describe, got, text))
        return text

    def pick(self, kind, prompt, options):
        wanted = self.answer(kind, "%r with %r" % (prompt, options))
        for index, option in enumerate(options):
            if option == wanted or (wanted and wanted in option):
                self.world.events.append((kind, prompt, list(options), option))
                return index
        raise SimError("%r is not among %r (prompt %r)" % (wanted, options, prompt))

    def execute(self):
        pc = 0
        loops = {}
        try:
            while pc < len(self.actions):
                action = self.actions[pc]
                ident = action["WFWorkflowActionIdentifier"]
                params = action.get("WFWorkflowActionParameters", {})
                mode = params.get("WFControlFlowMode")
                group = self.groups.get(params.get("GroupingIdentifier"))
                if ident == PREFIX + "conditional":
                    if mode == 0 and not self.condition(params):
                        pc = group["else"] + 1 if "else" in group else group["end"]
                    elif mode == 1:
                        pc = group["end"]
                    else:
                        pc += 1
                elif ident == PREFIX + "choosefrommenu":
                    if mode == 0:
                        prompt = as_text(self.resolve(params.get("WFMenuPrompt", "")))
                        options = []
                        for item in params["WFMenuItems"]:
                            if isinstance(item, dict):
                                item = self.resolve(item.get("WFValue"))
                            options.append(as_text(item))
                        if len(options) != len(group["cases"]):
                            raise SimError("menu items and cases differ: %r" % options)
                        pc = group["cases"][self.pick("menu", prompt, options)] + 1
                    elif mode == 1:
                        pc = group["end"]
                    else:
                        pc += 1
                elif ident == PREFIX + "repeat.each":
                    gid = params["GroupingIdentifier"]
                    if mode == 0:
                        items = as_list(self.resolve(params.get("WFInput")))
                        if items:
                            loops[gid] = [items, 0]
                            self.vars["Repeat Item"] = items[0]
                            pc += 1
                        else:
                            pc = group["end"] + 1
                    else:
                        items, index = loops[gid]
                        if index + 1 < len(items):
                            loops[gid][1] = index + 1
                            self.vars["Repeat Item"] = items[index + 1]
                            pc = group["start"] + 1
                        else:
                            pc += 1
                else:
                    result = self.act(ident, params)
                    if "UUID" in params:
                        self.outputs[params["UUID"]] = result
                    pc += 1
        except Stop:
            pass

    # -- actions ----------------------------------------------------------

    def act(self, ident, p):
        world = self.world
        get = lambda key, default=None: self.resolve(p.get(key, default))
        name = ident[len(PREFIX):] if ident.startswith(PREFIX) else ident

        if name == "gettext":
            return as_text(get("WFTextActionText", ""))
        if name == "setvariable":
            self.vars[p["WFVariableName"]] = get("WFInput")
            return None
        if name == "nothing":
            return None
        if name == "exit":
            raise Stop()
        if name == "number":
            return float(as_text(get("WFNumberActionNumber", 0)) or 0)
        if name == "math":
            left = float(as_text(get("WFInput")) or 0)
            right = float(as_text(get("WFMathOperand", 0)) or 0)
            return {"+": left + right, "-": left - right}[p.get("WFMathOperation", "+")]
        if name == "count":
            return float(len(as_list(get("Input"))))
        if name == "dictionary":
            return get("WFItems")
        if name == "detect.dictionary":
            return as_dict(get("WFInput"))
        if name == "getvalueforkey":
            source = as_dict(get("WFInput"))
            return source.get(as_text(get("WFDictionaryKey"))) if source else None
        if name == "text.replace":
            subject = as_text(get("WFInput"))
            find, repl = as_text(get("WFReplaceTextFind")), as_text(get("WFReplaceTextReplace", ""))
            if p.get("WFReplaceTextRegularExpression"):
                return re.sub(find, repl.replace("\\", "\\\\"), subject)
            return subject.replace(find, repl)
        if name == "text.match":
            found = Matches()
            for match in re.finditer(as_text(get("WFMatchTextPattern")), as_text(get("text")),
                                     flags=re.M):
                found.append(match.group(0))
                found.groups = getattr(found, "groups", []) + [match]
            return found
        if name == "text.match.getgroup":
            matches = get("matches")
            groups = getattr(matches, "groups", [])
            return groups[0].group(int(p.get("WFGroupIndex", 1))) if groups else None
        if name == "base64encode":
            value = get("WFInput")
            if p.get("WFEncodeMode") == "Decode":
                text = as_text(value).strip()
                if not text:
                    return None
                return File(base64.b64decode(text + "=" * (-len(text) % 4)))
            if p.get("WFBase64LineBreakMode") != "None":
                raise SimError("base64 with line breaks would break the command line")
            return base64.b64encode(as_text(value).encode("utf-8")).decode("ascii")
        if name == "detect.link":
            return re.findall(r"https?://[^\s<>\"']+", as_text(get("WFInput")))
        if name == "getitemfromlist":
            items = as_list(get("WFInput"))
            return items[0] if items else None
        if name == "geturlcomponent":
            if p.get("WFURLComponent") != "Host":
                raise SimError("unmodelled URL component")
            return urllib.parse.urlsplit(as_text(get("WFURL"))).hostname
        if name == "setitemname":
            return File(as_text(get("WFInput")).encode("utf-8"), name=as_text(get("WFName")))
        if name == "choosefromlist":
            items = as_list(get("WFInput"))
            labels = [as_text(i) for i in items]
            prompt = as_text(get("WFChooseFromListActionPrompt", ""))
            index = self.pick("list", prompt, labels)
            world.events[-1] = world.events[-1] + ([getattr(i, "detail", "") for i in items],)
            return labels[index]
        if name == "ask":
            prompt = as_text(get("WFAskActionPrompt", ""))
            default = as_text(get("WFAskActionDefaultAnswer", ""))
            text = self.answer("ask", repr(prompt))
            world.events.append(("ask", prompt, default, text))
            return text
        if name == "alert":
            world.events.append(("alert", as_text(get("WFAlertActionTitle", "")),
                                 as_text(get("WFAlertActionMessage", ""))))
            return None
        if name == "notification":
            world.events.append(("notification", as_text(get("WFNotificationActionTitle", "")),
                                 as_text(get("WFNotificationActionBody", ""))))
            return None
        if name == "openurl":
            world.events.append(("openurl", as_text(get("WFInput"))))
            return None
        if name == "setclipboard":
            world.clipboard = as_text(get("WFInput"))
            world.events.append(("clipboard", world.clipboard))
            return None
        if name == "delay":
            return None
        if name == "openapp":
            app = p.get("WFSelectedApp")
            # A plain plist dictionary, not Shortcuts' dictionary-parameter wrapper.
            if not isinstance(app, dict) or app.get("BundleIdentifier") != p["WFAppIdentifier"]:
                raise SimError("Open App has a malformed app reference: %r" % (app,))
            world.events.append(("openapp", p["WFAppIdentifier"]))
            return None
        if name == "photos.createalbum":
            world.albums.append(as_text(get("AlbumName")))
            return None
        if name == "savetocameraroll":
            item = get("WFInput")
            if not isinstance(item, File) or not item.data:
                raise SimError("Save to Photo Album got no file")
            album = as_text(get("WFCameraRollSelectedGroup", "Recents"))
            world.photos.append((os.path.basename(item.path), album, len(item.data)))
            return None
        if name == ASHELL + "ExecuteCommandIntent":
            command = as_text(get("command"))
            window = p.get("openWindow")
            if p.get("ShowWhenRun") is not False:
                raise SimError("a-Shell action would show itself")
            world.commands.append((window, command))
            if window == "close":
                return world.background(command)
            if window != "open" or p.get("keepGoing") is not False:
                raise SimError("unexpected a-Shell window mode %r" % window)
            if world.events[-1][0] != "openapp":
                raise SimError("a-Shell must be opened before a foreground command")
            world.foreground(command)
            return None
        if name == ASHELL + "GetFileIntent":
            path = as_text(get("fileName"))
            if not os.path.isabs(path) or " " in path:
                raise SimError("Get File needs a clean absolute path, got %r" % path)
            if not os.path.exists(path):
                raise SimError("a-Shell has no file %r" % path)
            with open(path, "rb") as handle:
                return File(handle.read(), path=path)
        raise SimError("the simulator has no model for action %r" % ident)

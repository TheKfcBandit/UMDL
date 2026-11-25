"""Stand-in for the gallery-dl Python package (see ../bin/gallery-dl for the CLI)."""

import types

version = types.ModuleType("gallery_dl.version")
version.__version__ = "9.9.9-fake"

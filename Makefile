# UMDL developer tasks. Run from the repository root.
#   make build   compile the shortcut unsigned, with a plist for inspection
#   make test    build, then run every test
#   make sign    compile and sign (macOS, or anywhere with ROUTINEHUB_API_KEY set)
#   make icons   redraw the menu icons

CHERRI ?= cherri
PYTHON ?= python3

.PHONY: build test sign icons clean

build:
	$(CHERRI) src/UMDL.cherri --skip-sign --debug --no-ansi > /dev/null
	@ls -l src/UMDL_unsigned.shortcut

test: build
	$(PYTHON) -m unittest discover -s tests

sign:
	@mkdir -p dist
	@if [ -n "$$ROUTINEHUB_API_KEY" ]; then \
		$(CHERRI) src/UMDL.cherri --hubsign --routinehub-api-key="$$ROUTINEHUB_API_KEY" --output=dist/UMDL.shortcut; \
	else \
		$(CHERRI) src/UMDL.cherri --share=anyone --output=dist/UMDL.shortcut; \
	fi
	@ls -l dist/UMDL.shortcut

icons:
	$(PYTHON) tools/make_icons.py

clean:
	rm -rf build dist src/UMDL.plist src/UMDL_processed.cherri src/*.shortcut

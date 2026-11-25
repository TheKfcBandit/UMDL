# UMDL developer tasks. Run from the repository root.
#   make build   compile the shortcut unsigned, with a plist for inspection
#   make test    build, then run every test
#   make sign    compile, sign through the Shortcuty service, and verify the result
#   make icons   redraw the menu icons
#   make playground   refresh playground/UMDL.cherri, the single file for the Cherri Playground

CHERRI ?= cherri
PYTHON ?= python3
SIGNING_API ?= https://sign.shortcuty.app/api/v1/sign

.PHONY: build test sign icons playground clean

build:
	$(CHERRI) src/UMDL.cherri --skip-sign --debug --no-ansi > /dev/null
	@ls -l src/UMDL_unsigned.shortcut

test: build
	$(PYTHON) -m unittest discover -s tests

# Signs through the free Shortcuty service, then checks the signed file holds
# exactly what was built. On a Mac signed in to iCloud you can instead run:
#   cherri src/UMDL.cherri --share=anyone
sign: build
	@mkdir -p dist
	curl --fail --show-error --silent --max-time 180 \
		--form 'file=@src/UMDL_unsigned.shortcut;filename=UMDL.shortcut' \
		--output dist/UMDL.shortcut $(SIGNING_API)
	cd tools/verifysigned && go run . ../../src/UMDL_unsigned.shortcut ../../dist/UMDL.shortcut
	@ls -l dist/UMDL.shortcut

icons:
	$(PYTHON) tools/make_icons.py

playground:
	$(PYTHON) tools/make_playground.py

clean:
	rm -rf build dist src/UMDL.plist src/UMDL_processed.cherri src/*.shortcut

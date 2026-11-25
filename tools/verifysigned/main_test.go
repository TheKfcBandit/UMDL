package main

import (
	"bytes"
	"encoding/binary"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"howett.net/plist"
)

// fakeSigned wraps a workflow the way a signed shortcut does, using LZFSE's
// uncompressed block type so no compressor is needed. It tests this tool's
// own reading of the layout; a real signed file is checked in CI.
func fakeSigned(workflow []byte) []byte {
	entry := func(path string, data []byte) []byte {
		var fields bytes.Buffer
		fields.WriteString("TYP1F")
		fields.WriteString("PATP")
		binary.Write(&fields, binary.LittleEndian, uint16(len(path)))
		fields.WriteString(path)
		fields.WriteString("MOD4")
		binary.Write(&fields, binary.LittleEndian, uint32(0o644))
		fields.WriteString("MTMT")
		fields.Write(make([]byte, 12))
		if data != nil {
			fields.WriteString("DATB")
			binary.Write(&fields, binary.LittleEndian, uint32(len(data)))
		}
		var out bytes.Buffer
		out.WriteString(entryMagic)
		binary.Write(&out, binary.LittleEndian, uint16(6+fields.Len()))
		out.Write(fields.Bytes())
		out.Write(data)
		return out.Bytes()
	}
	archive := append(entry("Other.txt", []byte("ignore me")), entry(workflowPath, workflow)...)

	var file bytes.Buffer
	file.WriteString(aeaMagic)
	file.Write([]byte{0, 0, 0, 0})
	authSize := uint32(40)
	binary.Write(&file, binary.LittleEndian, authSize)
	file.Write(make([]byte, int(authSize)+payloadGap-file.Len()))
	file.WriteString("bvx-")
	binary.Write(&file, binary.LittleEndian, uint32(len(archive)))
	file.Write(archive)
	file.WriteString("bvx$")
	return file.Bytes()
}

func sample(t *testing.T, format int, text string) []byte {
	t.Helper()
	workflow := map[string]any{
		"WFWorkflowClientVersion": "1",
		"WFWorkflowIcon":          map[string]any{"WFWorkflowIconGlyphNumber": 59693},
		"WFWorkflowActions": []any{
			map[string]any{
				"WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
				"WFWorkflowActionParameters": map[string]any{"WFTextActionText": text, "Flag": false},
			},
			map[string]any{"WFWorkflowActionIdentifier": "is.workflow.actions.exit"},
		},
	}
	data, err := plist.Marshal(workflow, format)
	if err != nil {
		t.Fatal(err)
	}
	return data
}

func TestSameWorkflowInXMLAndBinaryMatches(t *testing.T) {
	inner, err := workflowFromSigned(fakeSigned(sample(t, plist.BinaryFormat, "hello")))
	if err != nil {
		t.Fatal(err)
	}
	built, _ := decode(sample(t, plist.XMLFormat, "hello"))
	signed, err := decode(inner)
	if err != nil {
		t.Fatal(err)
	}
	if problems := compare(built, signed); len(problems) != 0 {
		t.Fatalf("expected a match, got %v", problems)
	}
}

func TestChangedActionIsReported(t *testing.T) {
	inner, err := workflowFromSigned(fakeSigned(sample(t, plist.BinaryFormat, "tampered")))
	if err != nil {
		t.Fatal(err)
	}
	built, _ := decode(sample(t, plist.XMLFormat, "hello"))
	signed, _ := decode(inner)
	problems := compare(built, signed)
	if len(problems) != 1 || problems[0] != "action 0 (is.workflow.actions.gettext) differs" {
		t.Fatalf("unexpected result %v", problems)
	}
}

func TestAddedAndMissingKeysAreReported(t *testing.T) {
	built, _ := decode(sample(t, plist.XMLFormat, "hello"))
	signed, _ := decode(sample(t, plist.XMLFormat, "hello"))
	delete(signed, "WFWorkflowIcon")
	signed["Extra"] = int64(1)
	if problems := compare(built, signed); len(problems) != 2 {
		t.Fatalf("unexpected result %v", problems)
	}
}

func TestUnsignedFileIsRejected(t *testing.T) {
	if _, err := workflowFromSigned(sample(t, plist.XMLFormat, "hello")); err == nil {
		t.Fatal("an unsigned property list was accepted as signed")
	}
}

func TestRealBuildRoundTrips(t *testing.T) {
	_, here, _, _ := runtime.Caller(0)
	root := filepath.Join(filepath.Dir(here), "..", "..")
	for _, candidate := range []string{"src/UMDL_unsigned.shortcut", "build/UMDL_unsigned.shortcut"} {
		data, err := os.ReadFile(filepath.Join(root, candidate))
		if err != nil {
			continue
		}
		inner, err := workflowFromSigned(fakeSigned(data))
		if err != nil {
			t.Fatal(err)
		}
		built, _ := decode(data)
		signed, _ := decode(inner)
		if problems := compare(built, signed); len(problems) != 0 {
			t.Fatalf("%s: %v", candidate, problems)
		}
		return
	}
	t.Skip("no compiled shortcut found")
}

// verifysigned checks that a signed shortcut holds exactly the workflow that
// was built.
//
// UMDL is signed by a third-party service, because Apple's own signing tool
// needs a Mac that is signed in to iCloud. A signed shortcut is an Apple
// Encrypted Archive that is signed but not encrypted, so the workflow inside
// can be read back and compared with the unsigned build, action for action.
//
//	go run . unsigned.shortcut signed.shortcut
//
// Format notes: https://theapplewiki.com/wiki/Apple_Encrypted_Archive and
// Apple's Apple Archive documentation.
package main

import (
	"bytes"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"os"
	"reflect"
	"sort"

	"github.com/aixiansheng/lzfse"
	"howett.net/plist"
)

const (
	aeaMagic       = "AEA1"
	lzfseMagic     = "bvx"
	entryMagic     = "AA01"
	workflowPath   = "Shortcut.wflow"
	authSizeOffset = 8
	// For a shortcut, the signature and the root and cluster headers that sit
	// between the authentication data and the first compressed block have a
	// fixed total size.
	payloadGap = 0x495c
)

func main() {
	if len(os.Args) != 3 {
		fail("usage: verifysigned <unsigned.shortcut> <signed.shortcut>")
	}
	unsignedBytes := mustRead(os.Args[1])
	signedBytes := mustRead(os.Args[2])

	inner, err := workflowFromSigned(signedBytes)
	if err != nil {
		fail("could not read the signed shortcut: " + err.Error())
	}
	built, err := decode(unsignedBytes)
	if err != nil {
		fail("could not read the unsigned shortcut: " + err.Error())
	}
	signed, err := decode(inner)
	if err != nil {
		fail("the workflow inside the signed shortcut is not a property list: " + err.Error())
	}

	problems := compare(built, signed)
	if len(problems) > 0 {
		for _, p := range problems {
			fmt.Fprintln(os.Stderr, "  "+p)
		}
		fail("the signed shortcut does not match the build")
	}
	actions, _ := built["WFWorkflowActions"].([]any)
	fmt.Printf("OK: the signed shortcut holds the same %d actions and settings as the build.\n", len(actions))
}

func fail(message string) {
	fmt.Fprintln(os.Stderr, "verifysigned: "+message)
	os.Exit(1)
}

func mustRead(path string) []byte {
	data, err := os.ReadFile(path)
	if err != nil {
		fail(err.Error())
	}
	return data
}

// workflowFromSigned returns the bytes of Shortcut.wflow from a signed shortcut.
func workflowFromSigned(signed []byte) ([]byte, error) {
	if len(signed) < authSizeOffset+4 || string(signed[:4]) != aeaMagic {
		return nil, errors.New("not an AEA1 file")
	}
	start := int(binary.LittleEndian.Uint32(signed[authSizeOffset:])) + payloadGap
	if start+len(lzfseMagic) > len(signed) || string(signed[start:start+len(lzfseMagic)]) != lzfseMagic {
		// Unexpected layout: fall back to the first compressed block after the header.
		found := bytes.Index(signed[authSizeOffset+4:], []byte(lzfseMagic))
		if found < 0 {
			return nil, errors.New("no compressed data found")
		}
		start = authSizeOffset + 4 + found
	}

	// The archive is stored as one LZFSE stream per block of up to 1 MiB.
	reader := bytes.NewReader(signed[start:])
	var archive bytes.Buffer
	for reader.Len() > 0 {
		before := reader.Len()
		block, err := io.ReadAll(lzfse.NewReader(reader))
		if err != nil {
			if archive.Len() > 0 {
				break // trailing bytes that are not another block
			}
			return nil, fmt.Errorf("decompression failed: %w", err)
		}
		if reader.Len() == before {
			break
		}
		archive.Write(block)
	}
	return fileFromArchive(archive.Bytes(), workflowPath)
}

// fileFromArchive walks the entries of an Apple Archive and returns one file's data.
// Each entry is "AA01", a 16-bit header size, then fields of a 3-letter key
// and a 1-letter type that says how the value is stored.
func fileFromArchive(archive []byte, wanted string) ([]byte, error) {
	for offset := 0; offset < len(archive); {
		rest := archive[offset:]
		if len(rest) < 6 || string(rest[:4]) != entryMagic {
			return nil, fmt.Errorf("unexpected data at archive offset %d", offset)
		}
		headerSize := int(binary.LittleEndian.Uint16(rest[4:]))
		if headerSize < 6 || headerSize > len(rest) {
			return nil, errors.New("archive entry header is damaged")
		}
		var path string
		var dataSize uint64
		for pos := 6; pos+4 <= headerSize; {
			key, kind := string(rest[pos:pos+3]), rest[pos+3]
			pos += 4
			var width int
			switch kind {
			case '*': // flag, no value
			case '1':
				width = 1
			case '2':
				width = 2
			case '4':
				width = 4
			case '8':
				width = 8
			case 'S':
				width = 8
			case 'T':
				width = 12
			case 'F':
				width = 4
			case 'G':
				width = 20
			case 'H':
				width = 32
			case 'I':
				width = 48
			case 'J':
				width = 64
			case 'P': // string with a 16-bit length
				if pos+2 > headerSize {
					return nil, errors.New("archive entry string is damaged")
				}
				length := int(binary.LittleEndian.Uint16(rest[pos:]))
				pos += 2
				if pos+length > headerSize {
					return nil, errors.New("archive entry string is damaged")
				}
				if key == "PAT" {
					path = string(rest[pos : pos+length])
				}
				pos += length
				continue
			case 'A', 'B', 'C': // blob stored after the header; the field holds its size
				width = map[byte]int{'A': 2, 'B': 4, 'C': 8}[kind]
				if pos+width > headerSize {
					return nil, errors.New("archive entry blob size is damaged")
				}
				var size uint64
				switch width {
				case 2:
					size = uint64(binary.LittleEndian.Uint16(rest[pos:]))
				case 4:
					size = uint64(binary.LittleEndian.Uint32(rest[pos:]))
				default:
					size = binary.LittleEndian.Uint64(rest[pos:])
				}
				dataSize += size
				if key != "DAT" && path == wanted {
					return nil, fmt.Errorf("entry has an unexpected %s blob", key)
				}
			default:
				return nil, fmt.Errorf("unknown archive field type %q in %s", kind, key)
			}
			pos += width
		}
		end := uint64(headerSize) + dataSize
		if end > uint64(len(rest)) {
			return nil, errors.New("archive entry runs past the end of the archive")
		}
		if path == wanted {
			return rest[headerSize:end], nil
		}
		offset += int(end)
	}
	return nil, fmt.Errorf("%s is not in the archive", wanted)
}

func decode(data []byte) (map[string]any, error) {
	var value map[string]any
	if _, err := plist.Unmarshal(data, &value); err != nil {
		return nil, err
	}
	return normalize(value).(map[string]any), nil
}

// normalize makes values from XML and binary property lists comparable:
// every integer becomes int64.
func normalize(value any) any {
	switch v := value.(type) {
	case map[string]any:
		for key, item := range v {
			v[key] = normalize(item)
		}
		return v
	case []any:
		for i, item := range v {
			v[i] = normalize(item)
		}
		return v
	case uint64:
		return int64(v)
	case int:
		return int64(v)
	case uint:
		return int64(v)
	case int32:
		return int64(v)
	case uint32:
		return int64(v)
	default:
		return v
	}
}

// compare lists the differences between the built and the signed workflow.
func compare(built, signed map[string]any) []string {
	var problems []string
	keys := map[string]bool{}
	for key := range built {
		keys[key] = true
	}
	for key := range signed {
		keys[key] = true
	}
	names := make([]string, 0, len(keys))
	for key := range keys {
		names = append(names, key)
	}
	sort.Strings(names)

	for _, key := range names {
		a, inBuilt := built[key]
		b, inSigned := signed[key]
		switch {
		case !inSigned:
			problems = append(problems, key+" is missing from the signed shortcut")
		case !inBuilt:
			problems = append(problems, key+" was added to the signed shortcut")
		case key == "WFWorkflowActions":
			problems = append(problems, compareActions(a, b)...)
		case !reflect.DeepEqual(a, b):
			problems = append(problems, fmt.Sprintf("%s differs: built %v, signed %v", key, a, b))
		}
	}
	return problems
}

func compareActions(a, b any) []string {
	built, _ := a.([]any)
	signed, _ := b.([]any)
	if len(built) != len(signed) {
		return []string{fmt.Sprintf("action count differs: built %d, signed %d", len(built), len(signed))}
	}
	for i := range built {
		if !reflect.DeepEqual(built[i], signed[i]) {
			name := "?"
			if action, ok := built[i].(map[string]any); ok {
				name = fmt.Sprint(action["WFWorkflowActionIdentifier"])
			}
			return []string{fmt.Sprintf("action %d (%s) differs", i, name)}
		}
	}
	return nil
}

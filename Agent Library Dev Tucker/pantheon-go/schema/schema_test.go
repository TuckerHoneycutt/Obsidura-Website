package schema_test

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/schema"
)

// Named mutation table for schema derivation.
//
//	mutation                                        | reddens
//	------------------------------------------------|-----------------------------------------
//	omitempty no longer excludes a field from        | TestOmitemptyAndPointersAreOptional
//	  `required`                                     |
//	pointers are treated as required                 | TestOmitemptyAndPointersAreOptional
//	additionalProperties defaults to true            | TestObjectsAreClosedByDefault
//	json:"-" fields are emitted                      | TestRawEscapeHatchIsExcluded
//	[]byte derives as an array                       | TestByteSliceDerivesAsAString
//	time.Time derives as an object                   | TestTimeDerivesAsADateTimeString
//	recursion is silently accepted                   | TestRecursiveTypeIsRefused
//	Marshal stops sorting keys                       | TestMarshalIsDeterministic

type inner struct {
	Label string `json:"label"`
}

type sample struct {
	Required  string          `json:"required" desc:"Must be present."`
	Optional  string          `json:"optional,omitempty"`
	Pointer   *int            `json:"pointer"`
	Count     int64           `json:"count"`
	Ratio     float64         `json:"ratio"`
	Flag      bool            `json:"flag"`
	Tags      []string        `json:"tags"`
	Lookup    map[string]int  `json:"lookup"`
	Nested    inner           `json:"nested"`
	When      time.Time       `json:"when"`
	Blob      []byte          `json:"blob"`
	Anything  any             `json:"anything"`
	Raw       json.RawMessage `json:"-"`
	unexposed string          //nolint:unused // deliberately unexported
}

func derive(t *testing.T) schema.Doc {
	t.Helper()
	d, err := schema.Of[sample]("test.Sample@1")
	if err != nil {
		t.Fatal(err)
	}
	return d
}

func props(t *testing.T, d schema.Doc) map[string]any {
	t.Helper()
	p, ok := d["properties"].(map[string]any)
	if !ok {
		t.Fatalf("no properties in %v", d)
	}
	return p
}

func TestScalarKindsMapToJSONSchemaTypes(t *testing.T) {
	p := props(t, derive(t))
	want := map[string]string{
		"required": "string",
		"count":    "integer",
		"ratio":    "number",
		"flag":     "boolean",
		"tags":     "array",
		"lookup":   "object",
		"nested":   "object",
	}
	for field, typ := range want {
		got, ok := p[field].(schema.Doc)
		if !ok {
			t.Errorf("field %q missing from schema", field)
			continue
		}
		if got["type"] != typ {
			t.Errorf("field %q derived as %v, want %q", field, got["type"], typ)
		}
	}
}

// A pointer is how a Go author says "absent is meaningful", which is exactly
// optionality. omitempty says the same thing a second way.
func TestOmitemptyAndPointersAreOptional(t *testing.T) {
	d := derive(t)
	required, ok := d["required"].([]string)
	if !ok {
		t.Fatalf("required is %T", d["required"])
	}
	set := map[string]bool{}
	for _, r := range required {
		set[r] = true
	}

	if !set["required"] {
		t.Error("a plain field must be required")
	}
	if set["optional"] {
		t.Error("an omitempty field must not be required")
	}
	if set["pointer"] {
		t.Error("a pointer field must not be required")
	}
}

// An unexpected field is a contract violation worth hearing about. Tenant
// extensions ride in an explicit RawMessage, not in whatever happens to arrive.
func TestObjectsAreClosedByDefault(t *testing.T) {
	d := derive(t)
	if d["additionalProperties"] != false {
		t.Errorf("additionalProperties is %v, want false", d["additionalProperties"])
	}
	nested := props(t, d)["nested"].(schema.Doc)
	if nested["additionalProperties"] != false {
		t.Error("nested objects must be closed too")
	}
}

// The tenant-payload escape hatch is json:"-" and must not appear in the
// contract; it is a Go-side convenience, not a wire field.
func TestRawEscapeHatchIsExcluded(t *testing.T) {
	p := props(t, derive(t))
	if _, present := p["Raw"]; present {
		t.Error(`a json:"-" field leaked into the schema`)
	}
	if _, present := p["unexposed"]; present {
		t.Error("an unexported field leaked into the schema")
	}
}

// []byte marshals as a base64 string, so the schema must say string. Saying
// "array of integers" would be a contract nothing actually satisfies.
func TestByteSliceDerivesAsAString(t *testing.T) {
	blob := props(t, derive(t))["blob"].(schema.Doc)
	if blob["type"] != "string" {
		t.Errorf("[]byte derived as %v, want string", blob["type"])
	}
	if blob["contentEncoding"] != "base64" {
		t.Errorf("[]byte should declare base64 encoding, got %v", blob["contentEncoding"])
	}
}

func TestTimeDerivesAsADateTimeString(t *testing.T) {
	when := props(t, derive(t))["when"].(schema.Doc)
	if when["type"] != "string" || when["format"] != "date-time" {
		t.Errorf("time.Time derived as %v", when)
	}
}

func TestAnyIsUnconstrained(t *testing.T) {
	anything := props(t, derive(t))["anything"].(schema.Doc)
	if len(anything) != 0 {
		t.Errorf("an `any` field should be unconstrained, got %v", anything)
	}
}

func TestDescTagBecomesDescription(t *testing.T) {
	req := props(t, derive(t))["required"].(schema.Doc)
	if req["description"] != "Must be present." {
		t.Errorf("desc tag did not become a description: %v", req)
	}
}

func TestTitleAndSchemaHeaderAreSet(t *testing.T) {
	d := derive(t)
	if d["title"] != "test.Sample@1" {
		t.Errorf("title is %v", d["title"])
	}
	if !strings.Contains(d["$schema"].(string), "2020-12") {
		t.Errorf("$schema is %v", d["$schema"])
	}
}

type recursive struct {
	Next *recursive `json:"next"`
}

// A self-referential business type is nearly always a modelling mistake, and
// supporting it would mean adding $ref/$defs resolution for a case that should
// be pushed back on instead.
func TestRecursiveTypeIsRefused(t *testing.T) {
	_, err := schema.Of[recursive]("test.Recursive@1")
	if err == nil {
		t.Fatal("a recursive type must be refused, not silently truncated")
	}
	if !strings.Contains(err.Error(), "recursive") {
		t.Errorf("the error should say why: %v", err)
	}
}

type badMapKey struct {
	M map[int]string `json:"m"`
}

func TestNonStringMapKeyIsRefused(t *testing.T) {
	if _, err := schema.Of[badMapKey]("test.Bad@1"); err == nil {
		t.Fatal("a non-string map key cannot be expressed in JSON and must be refused")
	}
}

type embeddedBase struct {
	ID string `json:"id"`
}

type withEmbedded struct {
	embeddedBase
	Extra string `json:"extra"`
}

// Embedded structs promote their fields in encoding/json, so the schema must
// promote them too or it describes a shape that never appears on the wire.
func TestEmbeddedFieldsArePromoted(t *testing.T) {
	d, err := schema.Of[withEmbedded]("test.Embedded@1")
	if err != nil {
		t.Fatal(err)
	}
	p := props(t, d)
	if _, ok := p["id"]; !ok {
		t.Errorf("embedded field was not promoted: %v", p)
	}
	if _, ok := p["extra"]; !ok {
		t.Error("own field missing")
	}
}

// The drift gate compares these bytes, so formatting is part of the contract.
func TestMarshalIsDeterministic(t *testing.T) {
	d := derive(t)
	first, err := d.Marshal()
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 20; i++ {
		again, err := d.Marshal()
		if err != nil {
			t.Fatal(err)
		}
		if string(first) != string(again) {
			t.Fatal("Marshal is not deterministic; the drift gate would flap")
		}
	}
	if !strings.HasSuffix(string(first), "\n") {
		t.Error("Marshal should end with a newline so files are POSIX-clean")
	}
	var round map[string]any
	if err := json.Unmarshal(first, &round); err != nil {
		t.Errorf("Marshal produced invalid JSON: %v", err)
	}
}

// The kernel types must themselves be derivable, since the emitter runs over
// action inputs and outputs that embed them.
func TestKernelHandlesDerive(t *testing.T) {
	type carriesHandles struct {
		File  kernel.FileHandle  `json:"file"`
		Table kernel.TableHandle `json:"table"`
	}
	d, err := schema.Of[carriesHandles]("test.Handles@1")
	if err != nil {
		t.Fatal(err)
	}
	p := props(t, d)
	for _, f := range []string{"file", "table"} {
		if _, ok := p[f]; !ok {
			t.Errorf("field %q missing", f)
		}
	}
}

// The behaviour must match encoding/json for an EXPORTED embedded type too,
// not only the unexported case above.
type ExportedBase struct {
	Kind string `json:"kind"`
}

type withExportedEmbedded struct {
	ExportedBase
	Extra string `json:"extra"`
}

func TestExportedEmbeddedFieldsArePromoted(t *testing.T) {
	d, err := schema.Of[withExportedEmbedded]("test.Embedded2@1")
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := props(t, d)["kind"]; !ok {
		t.Errorf("exported embedded field was not promoted: %v", props(t, d))
	}
}

// The strongest check available: the derived property set must equal the field
// set encoding/json actually produces. Anything else means the schema validates
// a different shape than the one on the wire.
func TestDerivedPropertiesMatchEncodingJSON(t *testing.T) {
	for _, tc := range []struct {
		name  string
		value any
		doc   func() (schema.Doc, error)
	}{
		{"unexported embedded", withEmbedded{}, func() (schema.Doc, error) { return schema.Of[withEmbedded]("x@1") }},
		{"exported embedded", withExportedEmbedded{}, func() (schema.Doc, error) { return schema.Of[withExportedEmbedded]("x@1") }},
		{"embedded base", ExportedBase{}, func() (schema.Doc, error) { return schema.Of[ExportedBase]("x@1") }},
	} {
		t.Run(tc.name, func(t *testing.T) {
			b, err := json.Marshal(tc.value)
			if err != nil {
				t.Fatal(err)
			}
			var onWire map[string]any
			if err := json.Unmarshal(b, &onWire); err != nil {
				t.Fatal(err)
			}
			d, err := tc.doc()
			if err != nil {
				t.Fatal(err)
			}
			derived := props(t, d)

			for field := range onWire {
				if _, ok := derived[field]; !ok {
					t.Errorf("field %q appears on the wire but not in the schema", field)
				}
			}
			for field := range derived {
				if _, ok := onWire[field]; !ok {
					t.Errorf("field %q is in the schema but never on the wire", field)
				}
			}
		})
	}
}

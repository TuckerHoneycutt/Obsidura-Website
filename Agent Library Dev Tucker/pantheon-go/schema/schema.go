// Package schema derives JSON Schema (draft 2020-12) from Go types.
//
// The arrow runs backwards here and it is temporary. Spec §6 puts the schema
// registry in Postgres and spec §4 makes Rust the source of truth for the
// kernel; the intended direction is registry -> Go structs, generated. Neither
// the registry nor the Rust crate exists yet, so this package derives schemas
// from the Go structs instead, giving three things today:
//
//   - a concrete document to register once a registry exists,
//   - a document to check the Rust vocabulary types against,
//   - a drift gate now rather than after the types have quietly diverged.
//
// See kernel's package doc. Do not let this become permanent.
package schema

import (
	"encoding/json"
	"fmt"
	"reflect"
	"strings"
	"time"
)

// Doc is a JSON Schema document. It is a plain map so that output is
// deterministic: encoding/json sorts map keys, and the drift gate compares
// bytes.
type Doc map[string]any

var (
	timeType = reflect.TypeOf(time.Time{})
	rawType  = reflect.TypeOf(json.RawMessage{})
)

// Of derives a schema for T, titled with the given type ref.
func Of[T any](title string) (Doc, error) {
	var zero T
	return For(reflect.TypeOf(&zero).Elem(), title)
}

// For derives a schema for t.
func For(t reflect.Type, title string) (Doc, error) {
	d, err := derive(t, map[reflect.Type]bool{})
	if err != nil {
		return nil, err
	}
	d["$schema"] = "https://json-schema.org/draft/2020-12/schema"
	if title != "" {
		d["title"] = title
	}
	return d, nil
}

func derive(t reflect.Type, seen map[reflect.Type]bool) (Doc, error) {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}

	switch t {
	case timeType:
		return Doc{"type": "string", "format": "date-time"}, nil
	case rawType:
		// Deliberately unconstrained: this is the tenant-payload escape hatch
		// described in 02-architecture.md. Constraining it would defeat it.
		return Doc{}, nil
	}

	switch t.Kind() {
	case reflect.String:
		return Doc{"type": "string"}, nil
	case reflect.Bool:
		return Doc{"type": "boolean"}, nil
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64,
		reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		return Doc{"type": "integer"}, nil
	case reflect.Float32, reflect.Float64:
		return Doc{"type": "number"}, nil

	case reflect.Slice, reflect.Array:
		if t.Elem().Kind() == reflect.Uint8 && t != rawType {
			// []byte marshals as a base64 string, so the schema must say string.
			return Doc{"type": "string", "contentEncoding": "base64"}, nil
		}
		items, err := derive(t.Elem(), seen)
		if err != nil {
			return nil, err
		}
		return Doc{"type": "array", "items": items}, nil

	case reflect.Map:
		if t.Key().Kind() != reflect.String {
			return nil, fmt.Errorf("schema: map key must be string, got %s", t.Key())
		}
		vals, err := derive(t.Elem(), seen)
		if err != nil {
			return nil, err
		}
		return Doc{"type": "object", "additionalProperties": vals}, nil

	case reflect.Interface:
		return Doc{}, nil

	case reflect.Struct:
		if seen[t] {
			// A self-referential business type is nearly always a modelling
			// mistake, and emitting $ref/$defs to support it would add a whole
			// resolution machinery for a case that should be pushed back on.
			return nil, fmt.Errorf("schema: recursive type %s is not supported", t)
		}
		seen[t] = true
		defer delete(seen, t)
		return deriveStruct(t, seen)
	}

	return nil, fmt.Errorf("schema: unsupported kind %s (%s)", t.Kind(), t)
}

func deriveStruct(t reflect.Type, seen map[reflect.Type]bool) (Doc, error) {
	props := map[string]any{}
	var required []string

	for i := 0; i < t.NumField(); i++ {
		f := t.Field(i)
		// An embedded struct is traversed even when its TYPE is unexported,
		// because encoding/json promotes its exported fields regardless. Skipping
		// it here would produce a schema describing a shape that never appears on
		// the wire -- which is worse than no schema, since it would validate
		// against the wrong thing.
		embeddedStruct := f.Anonymous && deref(f.Type).Kind() == reflect.Struct
		if !f.IsExported() && !embeddedStruct {
			continue
		}
		name, opts := parseJSONTag(f)
		if name == "-" {
			continue
		}
		if f.Anonymous && name == "" {
			// Embedded struct: promote its fields, matching encoding/json.
			sub, err := deriveStruct(deref(f.Type), seen)
			if err != nil {
				return nil, err
			}
			for k, v := range sub["properties"].(map[string]any) {
				props[k] = v
			}
			if r, ok := sub["required"].([]string); ok {
				required = append(required, r...)
			}
			continue
		}
		if name == "" {
			name = f.Name
		}

		fs, err := derive(f.Type, seen)
		if err != nil {
			return nil, fmt.Errorf("schema: field %s.%s: %w", t.Name(), f.Name, err)
		}
		if d := f.Tag.Get("desc"); d != "" {
			fs["description"] = d
		}
		props[name] = fs

		// Required unless omitempty or a pointer. A pointer is how a Go author
		// says "absent is meaningful", which is precisely optionality.
		if !opts["omitempty"] && f.Type.Kind() != reflect.Pointer {
			required = append(required, name)
		}
	}

	d := Doc{"type": "object", "properties": props}
	if len(required) > 0 {
		d["required"] = required
	}
	// Closed by default: an unexpected field is a contract violation worth
	// hearing about, not a field to ignore. Tenant extensions ride in an
	// explicit json.RawMessage field, not in whatever happens to arrive.
	d["additionalProperties"] = false
	return d, nil
}

func deref(t reflect.Type) reflect.Type {
	for t.Kind() == reflect.Pointer {
		t = t.Elem()
	}
	return t
}

func parseJSONTag(f reflect.StructField) (string, map[string]bool) {
	tag := f.Tag.Get("json")
	opts := map[string]bool{}
	if tag == "" {
		return "", opts
	}
	parts := strings.Split(tag, ",")
	for _, o := range parts[1:] {
		opts[o] = true
	}
	return parts[0], opts
}

// Marshal renders the document with stable, human-diffable formatting. The
// drift gate compares these bytes, so the formatting is part of the contract.
func (d Doc) Marshal() ([]byte, error) {
	b, err := json.MarshalIndent(d, "", "  ")
	if err != nil {
		return nil, err
	}
	return append(b, '\n'), nil
}

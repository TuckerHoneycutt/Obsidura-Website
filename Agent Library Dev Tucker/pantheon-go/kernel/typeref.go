// Package kernel is the Go mirror of Pantheon's kernel vocabulary: the closed
// set of five Value variants, the envelope that carries them across every seam,
// and the handles that keep large data out of the wire.
//
// PROVISIONAL SOURCE OF TRUTH. Spec §4 makes Rust the source of truth for this
// vocabulary, with JSON Schema generated from the Rust types via schemars, and
// these Go types generated from that schema in turn. The Rust vocabulary crate
// does not exist yet, so these types are hand-written and Schema() emits the
// JSON Schema they imply -- the arrow runs backwards, on purpose, temporarily.
//
// When the Rust crate lands, the direction reverses and does not reverse again:
// schemars emits the schema, ptn-gen generates this package from it, and CI
// regenerates and diffs. Until then `ptn-gen schema` produces a document to
// check the Rust types against. Do not let this file become permanent.
package kernel

import (
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
)

// TypeRef names a registered schema as name@version, per spec §6. The zero
// TypeRef is invalid; a Record with no type ref cannot be validated, and an
// unvalidatable Record is exactly what the contract system exists to prevent.
type TypeRef struct {
	Name    string
	Version int
}

// Ref builds a TypeRef. Version must be positive.
func Ref(name string, version int) TypeRef {
	return TypeRef{Name: name, Version: version}
}

// ParseTypeRef parses "name@version". It is strict: a bare name is an error
// rather than an implied version 1, because an implied version is a pin that
// silently moves when a second version is registered.
func ParseTypeRef(s string) (TypeRef, error) {
	at := strings.LastIndex(s, "@")
	if at <= 0 || at == len(s)-1 {
		return TypeRef{}, fmt.Errorf("kernel: type ref %q is not name@version", s)
	}
	v, err := strconv.Atoi(s[at+1:])
	if err != nil || v < 1 {
		return TypeRef{}, fmt.Errorf("kernel: type ref %q has a non-positive-integer version", s)
	}
	return TypeRef{Name: s[:at], Version: v}, nil
}

// MustParseTypeRef panics on a malformed ref. For package-level action
// declarations, where a bad ref is a build-time authoring mistake and failing
// at init is preferable to failing on the first invocation in production.
func MustParseTypeRef(s string) TypeRef {
	r, err := ParseTypeRef(s)
	if err != nil {
		panic(err)
	}
	return r
}

// String renders the ref as name@version, or "" when unset.
func (t TypeRef) String() string {
	if t.Name == "" {
		return ""
	}
	return t.Name + "@" + strconv.Itoa(t.Version)
}

// IsZero reports whether the ref is unset.
func (t TypeRef) IsZero() bool { return t.Name == "" && t.Version == 0 }

// MarshalJSON encodes the ref as a JSON string.
func (t TypeRef) MarshalJSON() ([]byte, error) { return json.Marshal(t.String()) }

// UnmarshalJSON decodes a name@version string, accepting "" as the zero ref.
func (t *TypeRef) UnmarshalJSON(b []byte) error {
	var s string
	if err := json.Unmarshal(b, &s); err != nil {
		return err
	}
	if s == "" {
		// The zero TypeRef marshals as "", so it must unmarshal back. A wire
		// type that cannot round-trip its own zero value turns every optional
		// ref into a decode failure somewhere far from the omission.
		//
		// This is not permission for an unlabelled Record: "a schema is
		// required here" is a validation rule the executor enforces against the
		// registry, and enforcing it during JSON decoding instead would reject
		// well-formed envelopes whose ref is legitimately absent.
		*t = TypeRef{}
		return nil
	}
	p, err := ParseTypeRef(s)
	if err != nil {
		return err
	}
	*t = p
	return nil
}

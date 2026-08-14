package kernel

import (
	"encoding/json"
	"fmt"
)

// Kind is the discriminator of the Value union. Closed set of five, per spec §5.
// Adding a variant here is a change to the kernel and therefore a change to the
// Rust executor -- which is exactly the coupling invariant 1 forbids growing.
// If a new business concept seems to need a variant, it is a Record.
type Kind string

const (
	KindText   Kind = "text"
	KindFile   Kind = "file"
	KindTable  Kind = "table"
	KindRecord Kind = "record"
	KindError  Kind = "error"
)

// Text is a body of prose with an optional language tag.
type Text struct {
	Body string `json:"body"`
	Lang string `json:"lang,omitempty"`
}

// FileHandle is a content-addressed blob reference. Bodies never construct one:
// the hash is the executor's to compute and trust. Obtain handles from
// Ctx.PutBlob, which round-trips through the proxy (PROTOCOL.md, blob.put).
type FileHandle struct {
	Blob       string `json:"blob"`       // "sha256:..."
	MediaType  string `json:"media_type"` // spec §5: Bin folded into File, media type distinguishes
	Size       int64  `json:"size,omitempty"`
	Capability string `json:"capability,omitempty"`
	Filename   string `json:"filename,omitempty"`
}

// Column is one column's metadata in a TableHandle.
type Column struct {
	Name string `json:"name"`
	Type string `json:"type"` // "string" | "int" | "float" | "bool" | "timestamp"
}

// TableHandle points at a row source in the blob store: CSV or JSONL in v0,
// Arrow later (spec §11 defers it). Rows are read in chunks through the proxy
// so access stays metered and memory stays bounded.
type TableHandle struct {
	Blob       string   `json:"blob"`
	Format     string   `json:"format"` // "csv" | "jsonl"
	Columns    []Column `json:"columns"`
	Rows       int64    `json:"rows,omitempty"` // advisory; -1 or 0 when unknown
	Capability string   `json:"capability,omitempty"`
}

// Record carries all business meaning. The executor's entire relationship with
// it is validate(schema, data) -- which is what keeps the amount of Rust in the
// executor constant in the number of business types (invariant 1).
type Record struct {
	TypeRef TypeRef         `json:"type_ref"`
	Data    json.RawMessage `json:"data"`
}

// ErrorValue is a typed failure that flows as a value. A business failure is a
// Value the run log routes; a protocol fault is not (see PROTOCOL.md).
type ErrorValue struct {
	Code    string          `json:"code"`
	Message string          `json:"message"`
	Detail  json.RawMessage `json:"detail,omitempty"`
	Retry   bool            `json:"retry,omitempty"`
}

// Value is the kernel's tagged union, mirroring the Rust
// #[serde(tag = "kind", rename_all = "snake_case")] enum. serde's internally
// tagged representation flattens each variant's fields alongside "kind", so the
// custom marshalling below is not a stylistic choice -- it is what makes a Go
// runner and a Python runner produce byte-compatible envelopes.
type Value struct {
	Kind   Kind
	Text   *Text
	File   *FileHandle
	Table  *TableHandle
	Record *Record
	Error  *ErrorValue
}

// Constructors. Use these rather than building a Value literal: they keep Kind
// and the populated arm in agreement, which nothing else enforces.

// NewText builds a Text value with no language tag.
func NewText(body string) Value { return Value{Kind: KindText, Text: &Text{Body: body}} }

// NewFile wraps a content-addressed blob reference.
func NewFile(h FileHandle) Value { return Value{Kind: KindFile, File: &h} }

// NewTable wraps a row-source reference.
func NewTable(h TableHandle) Value { return Value{Kind: KindTable, Table: &h} }

// NewRecord marshals v as the record's data.
func NewRecord(ref TypeRef, v any) (Value, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return Value{}, fmt.Errorf("kernel: marshalling record %s: %w", ref, err)
	}
	return Value{Kind: KindRecord, Record: &Record{TypeRef: ref, Data: b}}, nil
}

// NewRawRecord wraps already-marshalled data.
func NewRawRecord(ref TypeRef, data json.RawMessage) Value {
	return Value{Kind: KindRecord, Record: &Record{TypeRef: ref, Data: data}}
}

// NewError builds a typed failure value.
func NewError(code, message string) Value {
	return Value{Kind: KindError, Error: &ErrorValue{Code: code, Message: message}}
}

// IsZero reports whether the Value is unset.
func (v Value) IsZero() bool { return v.Kind == "" }

// Valuer lets an action's output type choose its own kernel representation.
// Without it every action output would be a Record; with it, an action can
// return a File or a Table as naturally as a struct. See action.Register.
type Valuer interface {
	KernelValue() Value
}

// UnmarshalData decodes a Record's data into dst. It is an error to call this
// on a non-Record, because silently succeeding on a Text would turn a wiring
// mistake into an empty struct three tasks downstream.
func (v Value) UnmarshalData(dst any) error {
	if v.Kind != KindRecord || v.Record == nil {
		return fmt.Errorf("kernel: cannot unmarshal data from a %q value; expected record", v.Kind)
	}
	return json.Unmarshal(v.Record.Data, dst)
}

// MarshalJSON emits the internally tagged form: the variant's fields sit
// alongside "kind", matching serde's representation on the Rust side.
func (v Value) MarshalJSON() ([]byte, error) {
	var (
		payload any
		err     error
	)
	switch v.Kind {
	case KindText:
		if v.Text == nil {
			return nil, errArmUnset(v.Kind)
		}
		payload = *v.Text
	case KindFile:
		if v.File == nil {
			return nil, errArmUnset(v.Kind)
		}
		payload = *v.File
	case KindTable:
		if v.Table == nil {
			return nil, errArmUnset(v.Kind)
		}
		payload = *v.Table
	case KindRecord:
		if v.Record == nil {
			return nil, errArmUnset(v.Kind)
		}
		payload = *v.Record
	case KindError:
		if v.Error == nil {
			return nil, errArmUnset(v.Kind)
		}
		payload = *v.Error
	case "":
		return nil, fmt.Errorf("kernel: cannot marshal a zero Value")
	default:
		return nil, fmt.Errorf("kernel: unknown value kind %q", v.Kind)
	}

	// Flatten the variant's fields alongside "kind", matching serde's
	// internally tagged representation.
	b, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}
	var m map[string]json.RawMessage
	if err := json.Unmarshal(b, &m); err != nil {
		return nil, err
	}
	m["kind"], _ = json.Marshal(string(v.Kind))
	return json.Marshal(m)
}

// UnmarshalJSON decodes the internally tagged form, refusing any kind outside
// the closed set of five.
func (v *Value) UnmarshalJSON(b []byte) error {
	var probe struct {
		Kind Kind `json:"kind"`
	}
	if err := json.Unmarshal(b, &probe); err != nil {
		return fmt.Errorf("kernel: value is not an object with a kind: %w", err)
	}
	out := Value{Kind: probe.Kind}
	switch probe.Kind {
	case KindText:
		out.Text = &Text{}
		if err := json.Unmarshal(b, out.Text); err != nil {
			return err
		}
	case KindFile:
		out.File = &FileHandle{}
		if err := json.Unmarshal(b, out.File); err != nil {
			return err
		}
	case KindTable:
		out.Table = &TableHandle{}
		if err := json.Unmarshal(b, out.Table); err != nil {
			return err
		}
	case KindRecord:
		out.Record = &Record{}
		if err := json.Unmarshal(b, out.Record); err != nil {
			return err
		}
	case KindError:
		out.Error = &ErrorValue{}
		if err := json.Unmarshal(b, out.Error); err != nil {
			return err
		}
	case "":
		return fmt.Errorf("kernel: value has no kind discriminator")
	default:
		// Refusing an unknown kind is deliberate. A Go runner that skipped a
		// variant it did not recognise would hand downstream tasks a zero
		// Value, and the failure would surface far from its cause.
		return fmt.Errorf("kernel: unknown value kind %q; the kernel is a closed set of five", probe.Kind)
	}
	*v = out
	return nil
}

func errArmUnset(k Kind) error {
	return fmt.Errorf("kernel: value of kind %q has no %s payload set; use the New%s constructor", k, k, k)
}

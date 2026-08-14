// Package action is the authoring model: what an action declares, how it is
// registered, and how a typed Go function becomes an ordinary Pantheon task.
//
// An action is a task body and nothing more. It declares its input and output
// schemas, the resources and verbs it needs, and its policy -- and it declares
// no wiring at all. Which trigger fires it and which task follows it are edges,
// derived from references in hand-authored YAML (spec invariant 3). If you ever
// find yourself wanting a Next field on Spec, that is invariant 3 being broken
// from inside the SDK.
package action

import (
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"time"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/schema"
)

// ResourceUse declares one resource and the verbs the action needs on it. This
// becomes `uses:` in the emitted YAML and is the input to the grant check the
// proxy performs on every call (spec §8).
//
// Declare the minimum. A verb listed here and never used is a permission the
// action carries for no reason, and permissions carried for no reason are how
// scope creeps without anyone deciding to widen it.
type ResourceUse struct {
	Name  string   `json:"name"`
	Verbs []string `json:"verbs"`
}

// Policy is per-task operational policy (spec §4).
type Policy struct {
	Timeout    time.Duration `json:"timeout"`
	Retry      int           `json:"retry"`
	Idempotent bool          `json:"idempotent"`
	// Budget is a token budget and is meaningful only for agent runners. It is
	// carried here so script and agent tasks share one policy shape.
	Budget int64 `json:"budget,omitempty"`
}

// DefaultPolicy is a deliberately short timeout and no retries.
//
// Retry defaults to zero because retrying a non-idempotent action is how one
// failure becomes two ledger entries. An action that is safe to retry says so.
var DefaultPolicy = Policy{Timeout: 60 * time.Second, Retry: 0, Idempotent: false}

// Spec is everything an action declares about itself.
type Spec struct {
	// Name is the action's stable identifier, e.g. "finance.reconcile_ledger".
	// Dotted, lower_snake segments: the first segment is the vertical package.
	Name string

	// Version increments on any incompatible change to input or output. The
	// emitted ref is Name@Version.
	Version int

	// Input and Output are registered schema refs (spec §6).
	Input  kernel.TypeRef
	Output kernel.TypeRef

	// Uses declares resource access. Empty means the action touches nothing
	// outside its input, which is worth stating rather than leaving implied.
	Uses []ResourceUse

	Policy Policy

	// Summary is one line, in plain language, for a non-technical reader. It
	// becomes the label on the GUI deck's button, so the deck and the code have
	// exactly one source (Discussion Context.md:29). Not decoration.
	Summary string
}

// Ref returns the action's own name@version.
func (s Spec) Ref() kernel.TypeRef { return kernel.Ref(s.Name, s.Version) }

// Handler is a registered action with its types erased. Bodies are written
// typed; the registry stores them uniform.
type Handler func(*Ctx, kernel.Value) (kernel.Value, error)

// Entry is one registered action.
type Entry struct {
	Spec    Spec
	Handler Handler

	// InputSchema and OutputSchema are derived from the Go types at
	// registration. Provisional, per package schema's doc: when the registry
	// exists these come from it and the Go types are generated instead.
	InputSchema  schema.Doc
	OutputSchema schema.Doc
}

// Registry holds every action a runner binary serves. One binary, many actions,
// dispatched by name -- which is what spec §8's "one generic runner image"
// requires and what makes per-action images a bonus chunk (B4) rather than a
// prerequisite.
type Registry struct {
	entries map[string]*Entry
}

// NewRegistry builds an empty registry.
func NewRegistry() *Registry { return &Registry{entries: map[string]*Entry{}} }

// Lookup finds an action by name.
func (r *Registry) Lookup(name string) (*Entry, bool) {
	e, ok := r.entries[name]
	return e, ok
}

// Names returns every registered action name, sorted. Sorted because it feeds
// the handshake and the YAML emitter, and both are compared byte-for-byte by a
// CI gate: map iteration order would make the drift gate flap.
func (r *Registry) Names() []string {
	out := make([]string, 0, len(r.entries))
	for n := range r.entries {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

// Entries returns every entry, sorted by name.
func (r *Registry) Entries() []*Entry {
	out := make([]*Entry, 0, len(r.entries))
	for _, n := range r.Names() {
		out = append(out, r.entries[n])
	}
	return out
}

var valueType = reflect.TypeOf(kernel.Value{})

// Register adds a typed action to the registry.
//
// Generic at the call site, erased inside: authors write a fully typed body and
// the registry stores a uniform Handler. This is the resolution of Go's
// heterogeneous-registry problem, and it means adding the 200th action touches
// no dispatch code.
//
// Panics on an invalid declaration. Registration happens at init, so a bad
// declaration is an authoring mistake that should stop the binary starting
// rather than surface on the first invocation in production.
func Register[In, Out any](r *Registry, spec Spec, run func(*Ctx, In) (Out, error)) {
	if err := validateSpec(spec); err != nil {
		panic(fmt.Sprintf("action.Register(%s): %v", spec.Name, err))
	}
	if _, exists := r.entries[spec.Name]; exists {
		panic(fmt.Sprintf("action.Register(%s): already registered", spec.Name))
	}

	inSchema, err := schema.Of[In](spec.Input.String())
	if err != nil {
		panic(fmt.Sprintf("action.Register(%s): deriving input schema: %v", spec.Name, err))
	}
	outSchema, err := schema.Of[Out](spec.Output.String())
	if err != nil {
		panic(fmt.Sprintf("action.Register(%s): deriving output schema: %v", spec.Name, err))
	}

	inIsValue := reflect.TypeOf((*In)(nil)).Elem() == valueType
	outIsValue := reflect.TypeOf((*Out)(nil)).Elem() == valueType

	handler := func(c *Ctx, in kernel.Value) (kernel.Value, error) {
		var typed In

		if inIsValue {
			// The action wants the raw Value: a File or Table input, or an
			// action that legitimately handles more than one kind.
			reflect.ValueOf(&typed).Elem().Set(reflect.ValueOf(in))
		} else {
			if in.Kind != kernel.KindRecord || in.Record == nil {
				return kernel.Value{}, fmt.Errorf(
					"action %s: expected a record input matching %s, got kind %q",
					spec.Name, spec.Input, in.Kind)
			}
			if in.Record.TypeRef != spec.Input {
				// A mismatched pair should be caught at plan time (acceptance
				// test 2). Checking again here costs nothing and turns a
				// wrong-shape bug into a named error instead of zero fields.
				return kernel.Value{}, fmt.Errorf(
					"action %s: declared input %s but received %s",
					spec.Name, spec.Input, in.Record.TypeRef)
			}
			if err := json.Unmarshal(in.Record.Data, &typed); err != nil {
				return kernel.Value{}, fmt.Errorf("action %s: decoding input %s: %w", spec.Name, spec.Input, err)
			}
		}

		out, err := run(c, typed)
		if err != nil {
			return kernel.Value{}, err
		}

		switch {
		case outIsValue:
			return reflect.ValueOf(out).Interface().(kernel.Value), nil
		default:
			// Valuer lets an output type pick its own kernel representation --
			// how an action returns a File or a Table as naturally as a struct.
			if v, ok := any(out).(kernel.Valuer); ok {
				return v.KernelValue(), nil
			}
			return kernel.NewRecord(spec.Output, out)
		}
	}

	r.entries[spec.Name] = &Entry{
		Spec:         spec,
		Handler:      handler,
		InputSchema:  inSchema,
		OutputSchema: outSchema,
	}
}

func validateSpec(s Spec) error {
	if s.Name == "" {
		return fmt.Errorf("Name is required")
	}
	if s.Version < 1 {
		return fmt.Errorf("Version must be >= 1")
	}
	if s.Input.IsZero() {
		return fmt.Errorf("Input schema ref is required")
	}
	if s.Output.IsZero() {
		return fmt.Errorf("Output schema ref is required")
	}
	if s.Summary == "" {
		// Enforced, not encouraged. The deck's buttons are generated from this
		// field; an action with no summary is an unlabelled button.
		return fmt.Errorf("Summary is required: it becomes the deck's button label")
	}
	for _, u := range s.Uses {
		if u.Name == "" {
			return fmt.Errorf("a ResourceUse has no Name")
		}
		if len(u.Verbs) == 0 {
			return fmt.Errorf("resource %q declares no verbs", u.Name)
		}
	}
	if s.Policy.Timeout <= 0 {
		return fmt.Errorf("Policy.Timeout must be positive")
	}
	if s.Policy.Retry > 0 && !s.Policy.Idempotent {
		// Retrying a non-idempotent action is how one failure becomes two
		// ledger entries. Say idempotent, or do not retry.
		return fmt.Errorf("Policy.Retry > 0 requires Policy.Idempotent")
	}
	return nil
}

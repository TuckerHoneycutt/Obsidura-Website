package ptnfake

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// LogLine is one log notification a body streamed while running.
type LogLine struct {
	Level   string
	Message string
	Fields  map[string]any
}

// Event is one run-log event a body emitted.
type Event struct {
	Type    string
	Payload any
}

// Result is everything one invocation produced.
type Result struct {
	Value    kernel.Value
	Envelope kernel.Envelope
	Logs     []LogLine
	Events   []Event
	Err      error
}

// Record decodes the result payload as a Record into dst. It fails loudly if
// the action errored, so a test that forgets to check Err still fails rather
// than asserting against a zero struct.
func (r Result) Record(dst any) error {
	if r.Err != nil {
		return r.Err
	}
	if r.Value.Kind == kernel.KindError && r.Value.Error != nil {
		return fmt.Errorf("action returned an error value: %s: %s", r.Value.Error.Code, r.Value.Error.Message)
	}
	return r.Value.UnmarshalData(dst)
}

type captureSink struct {
	logs   []LogLine
	events []Event
}

// Log captures a log line for later assertion.
func (s *captureSink) Log(level, message string, fields map[string]any) {
	s.logs = append(s.logs, LogLine{Level: level, Message: message, Fields: fields})
}

// Event captures a run-log event for later assertion.
func (s *captureSink) Event(eventType string, payload any) {
	s.events = append(s.events, Event{Type: eventType, Payload: payload})
}

// Invoke runs one registered action against this proxy.
//
// It dials the fake proxy over its real socket with the real res client, so a
// passing unit test exercises the actual wire format, the actual grant checks
// and the actual multiplexing. The only thing not exercised is the stdio shim,
// which InvokeOverStdio covers separately.
//
// in may be a kernel.Value, or any value that will be wrapped as a Record
// carrying the action's declared input ref.
func (p *Proxy) Invoke(reg *action.Registry, name string, in any) Result {
	entry, ok := reg.Lookup(name)
	if !ok {
		return Result{Err: fmt.Errorf("ptnfake: no action %q registered", name)}
	}

	payload, err := toValue(entry.Spec.Input, in)
	if err != nil {
		return Result{Err: err}
	}

	client, err := res.Dial(p.caps)
	if err != nil {
		return Result{Err: err}
	}
	defer client.Close()

	env := kernel.Envelope{
		RunID:    "r-test",
		TaskID:   "t-" + name,
		Attempt:  1,
		Schema:   entry.Spec.Input,
		Producer: "ptnfake",
		TS:       time.Unix(0, 0).UTC(),
	}

	ctx := context.Background()
	var cancel context.CancelFunc
	if entry.Spec.Policy.Timeout > 0 {
		ctx, cancel = context.WithTimeout(ctx, entry.Spec.Policy.Timeout)
		defer cancel()
	}

	sink := &captureSink{}
	c := action.NewCtx(ctx, env, entry.Spec, client, sink)

	out, runErr := entry.Handler(c, payload)

	outEnv := env.Derive(entry.Spec.Output, entry.Spec.Ref().String(), kernel.BudgetSpent{}, time.Unix(0, 0).UTC())
	for _, t := range c.Taints() {
		outEnv = outEnv.WithTaint(t)
	}

	return Result{
		Value:    out,
		Envelope: outEnv,
		Logs:     sink.logs,
		Events:   sink.events,
		Err:      runErr,
	}
}

func toValue(ref kernel.TypeRef, in any) (kernel.Value, error) {
	switch v := in.(type) {
	case kernel.Value:
		return v, nil
	case nil:
		return kernel.NewRecord(ref, map[string]any{})
	case json.RawMessage:
		return kernel.NewRawRecord(ref, v), nil
	default:
		return kernel.NewRecord(ref, in)
	}
}

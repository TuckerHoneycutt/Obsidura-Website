package serve_test

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
	"github.com/obsidura/pantheon-go/res"
	"github.com/obsidura/pantheon-go/serve"
)

// Named mutation table for the shim.
//
//	mutation                                          | reddens
//	--------------------------------------------------|----------------------------------------
//	handleHello stops comparing versions               | TestHandshakeRefusesAVersionMismatch
//	a failing body returns a JSON-RPC error            | TestBusinessFailureIsAValueNotAnRPCError
//	call() drops its panic recovery                    | TestPanickingBodySurvivesAsATypedError
//	handleInvoke labels an Error with the success schema | TestErrorEnvelopeCarriesTheErrorSchema
//	an unknown action returns an Error value            | TestUnknownActionIsAProtocolFault

type echoIn struct {
	Say string `json:"say"`
}

type echoOut struct {
	Heard string `json:"heard"`
}

func testRegistry() *action.Registry {
	r := action.NewRegistry()
	action.Register(r, action.Spec{
		Name: "test.echo", Version: 1,
		Input:   kernel.Ref("test.EchoIn", 1),
		Output:  kernel.Ref("test.EchoOut", 1),
		Policy:  action.Policy{Timeout: 5 * time.Second},
		Summary: "Echo the input back.",
	}, func(c *action.Ctx, in echoIn) (echoOut, error) {
		c.Logf("heard %q", in.Say)
		return echoOut{Heard: in.Say}, nil
	})

	action.Register(r, action.Spec{
		Name: "test.explode", Version: 1,
		Input:   kernel.Ref("test.EchoIn", 1),
		Output:  kernel.Ref("test.EchoOut", 1),
		Policy:  action.Policy{Timeout: 5 * time.Second},
		Summary: "Always fail.",
	}, func(c *action.Ctx, in echoIn) (echoOut, error) {
		return echoOut{}, errBoom
	})

	action.Register(r, action.Spec{
		Name: "test.panic", Version: 1,
		Input:   kernel.Ref("test.EchoIn", 1),
		Output:  kernel.Ref("test.EchoOut", 1),
		Policy:  action.Policy{Timeout: 5 * time.Second},
		Summary: "Always panic.",
	}, func(c *action.Ctx, in echoIn) (echoOut, error) {
		var p *echoOut
		return *p, nil // nil dereference
	})
	return r
}

var errBoom = &boomError{}

type boomError struct{}

func (*boomError) Error() string { return "the ledger was on fire" }

// run drives the shim over a real stdio pair with a real fake proxy behind it.
func run(t *testing.T, requests ...any) []map[string]json.RawMessage {
	t.Helper()

	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()

	var in bytes.Buffer
	for _, r := range requests {
		b, err := json.Marshal(r)
		if err != nil {
			t.Fatal(err)
		}
		in.Write(b)
		in.WriteByte('\n')
	}

	var out bytes.Buffer
	srv := serve.New(testRegistry(), serve.Options{
		In:  &in,
		Out: &out,
		Dial: func(_ res.Capabilities) (*res.Client, error) {
			return res.Dial(p.Capabilities())
		},
		Now: func() time.Time { return time.Unix(0, 0).UTC() },
	})
	if err := srv.Serve(); err != nil {
		t.Fatalf("serve: %v", err)
	}

	var frames []map[string]json.RawMessage
	for _, line := range strings.Split(strings.TrimSpace(out.String()), "\n") {
		if line == "" {
			continue
		}
		var f map[string]json.RawMessage
		if err := json.Unmarshal([]byte(line), &f); err != nil {
			t.Fatalf("unparseable output frame %q: %v", line, err)
		}
		frames = append(frames, f)
	}
	return frames
}

func hello(protocol, kernelV int) map[string]any {
	return map[string]any{
		"jsonrpc": "2.0", "id": 1, "method": "hello",
		"params": map[string]any{"protocol_version": protocol, "kernel_version": kernelV},
	}
}

func invoke(id int, name string, payload kernel.Value) map[string]any {
	return map[string]any{
		"jsonrpc": "2.0", "id": id, "method": "invoke",
		"params": map[string]any{
			"action":       name,
			"envelope":     kernel.Envelope{RunID: "r-1", TaskID: "t-1", Attempt: 1},
			"payload":      payload,
			"capabilities": map[string]any{"socket": "ignored", "token": "t"},
		},
	}
}

func mustRecord(t *testing.T, ref string, v any) kernel.Value {
	t.Helper()
	val, err := kernel.NewRecord(kernel.MustParseTypeRef(ref), v)
	if err != nil {
		t.Fatal(err)
	}
	return val
}

func TestHandshakeAdvertisesEveryAction(t *testing.T) {
	frames := run(t, hello(serve.ProtocolVersion, serve.KernelVersion))
	if len(frames) != 1 {
		t.Fatalf("expected one frame, got %d", len(frames))
	}
	var result struct {
		ProtocolVersion int    `json:"protocol_version"`
		Runner          string `json:"runner"`
		Actions         []struct {
			Name    string `json:"name"`
			Summary string `json:"summary"`
		} `json:"actions"`
	}
	if err := json.Unmarshal(frames[0]["result"], &result); err != nil {
		t.Fatalf("handshake was not a result: %s", frames[0])
	}
	if result.ProtocolVersion != serve.ProtocolVersion {
		t.Errorf("protocol %d", result.ProtocolVersion)
	}
	if len(result.Actions) != 3 {
		t.Errorf("advertised %d actions, want 3", len(result.Actions))
	}
	// The list lets the executor verify at deploy time that every definition
	// referencing this image is actually served by it.
	for _, a := range result.Actions {
		if a.Summary == "" {
			t.Errorf("action %s advertises no summary", a.Name)
		}
	}
}

// The whole reason PROTOCOL.md proposes a handshake. An SDK built for kernel v1
// talking to an executor on kernel v2 would misread an envelope and emit
// plausible wrong output, which is the most expensive failure available.
func TestHandshakeRefusesAVersionMismatch(t *testing.T) {
	frames := run(t, hello(serve.ProtocolVersion, serve.KernelVersion+1))
	if len(frames) != 1 {
		t.Fatalf("expected one frame, got %d", len(frames))
	}
	if _, ok := frames[0]["error"]; !ok {
		t.Fatalf("a kernel version mismatch must be refused, got: %s", frames[0])
	}
	var e struct {
		Message string `json:"message"`
	}
	json.Unmarshal(frames[0]["error"], &e)
	if !strings.Contains(e.Message, "version mismatch") {
		t.Errorf("error should name the mismatch: %q", e.Message)
	}
}

func TestInvokeRoundTripsAValue(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "test.echo", mustRecord(t, "test.EchoIn@1", echoIn{Say: "hello"})),
	)

	var logged, answered bool
	for _, f := range frames {
		if m, ok := f["method"]; ok && string(m) == `"log"` {
			logged = true
			continue
		}
		if _, ok := f["result"]; !ok {
			continue
		}
		var r struct {
			Envelope kernel.Envelope `json:"envelope"`
			Payload  kernel.Value    `json:"payload"`
		}
		if err := json.Unmarshal(f["result"], &r); err != nil {
			continue
		}
		if r.Payload.Kind != kernel.KindRecord {
			continue
		}
		answered = true
		var out echoOut
		if err := r.Payload.UnmarshalData(&out); err != nil {
			t.Fatal(err)
		}
		if out.Heard != "hello" {
			t.Errorf("echoed %q", out.Heard)
		}
		if r.Envelope.RunID != "r-1" || r.Envelope.Attempt != 1 {
			t.Errorf("causal fields lost: %+v", r.Envelope)
		}
		if r.Envelope.Producer != "test.echo@1" {
			t.Errorf("producer is %q", r.Envelope.Producer)
		}
	}
	if !logged {
		t.Error("the body's log line did not reach the executor")
	}
	if !answered {
		t.Error("no invoke result frame")
	}
}

// A business failure is a Value the run log routes (spec §5); a protocol fault
// is not. Collapsing the two would make retry, repair and audit read from two
// different places.
func TestBusinessFailureIsAValueNotAnRPCError(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "test.explode", mustRecord(t, "test.EchoIn@1", echoIn{Say: "x"})),
	)

	for _, f := range frames {
		if _, isErr := f["error"]; isErr {
			t.Fatalf("a failing body must not produce a JSON-RPC error: %s", f)
		}
		res, ok := f["result"]
		if !ok {
			continue
		}
		var r struct {
			Payload kernel.Value `json:"payload"`
		}
		if json.Unmarshal(res, &r) != nil || r.Payload.Kind == "" {
			continue
		}
		if r.Payload.Kind != kernel.KindError {
			t.Fatalf("payload kind is %q, want error", r.Payload.Kind)
		}
		if !strings.Contains(r.Payload.Error.Message, "ledger was on fire") {
			t.Errorf("the cause was lost: %q", r.Payload.Error.Message)
		}
		return
	}
	t.Fatal("no result frame")
}

// A crashed body must produce a typed failure, not take down the container and
// every task the warm pool had queued behind it.
func TestPanickingBodySurvivesAsATypedError(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "test.panic", mustRecord(t, "test.EchoIn@1", echoIn{Say: "x"})),
		invoke(3, "test.echo", mustRecord(t, "test.EchoIn@1", echoIn{Say: "still here"})),
	)

	var sawPanic, sawLater bool
	for _, f := range frames {
		res, ok := f["result"]
		if !ok {
			continue
		}
		var r struct {
			Payload kernel.Value `json:"payload"`
		}
		if json.Unmarshal(res, &r) != nil {
			continue
		}
		if r.Payload.Kind == kernel.KindError && strings.Contains(r.Payload.Error.Message, "panicked") {
			sawPanic = true
		}
		if r.Payload.Kind == kernel.KindRecord {
			var out echoOut
			r.Payload.UnmarshalData(&out)
			if out.Heard == "still here" {
				sawLater = true
			}
		}
	}
	if !sawPanic {
		t.Error("the panic did not become a typed Error value")
	}
	if !sawLater {
		t.Error("the process did not survive the panic to serve the next invocation")
	}
}

// Labelling a failure with the success schema would make the run log lie.
func TestErrorEnvelopeCarriesTheErrorSchema(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "test.explode", mustRecord(t, "test.EchoIn@1", echoIn{Say: "x"})),
	)
	for _, f := range frames {
		res, ok := f["result"]
		if !ok {
			continue
		}
		var r struct {
			Envelope kernel.Envelope `json:"envelope"`
			Payload  kernel.Value    `json:"payload"`
		}
		if json.Unmarshal(res, &r) != nil || r.Payload.Kind != kernel.KindError {
			continue
		}
		if r.Envelope.Schema.Name != "kernel.Error" {
			t.Errorf("an Error payload is labelled %q; the envelope must describe what was actually produced",
				r.Envelope.Schema)
		}
		return
	}
	t.Fatal("no error result frame")
}

// Asking for an action this image does not serve is a deploy mistake, not a
// business outcome.
func TestUnknownActionIsAProtocolFault(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "finance.does_not_exist", mustRecord(t, "test.EchoIn@1", echoIn{})),
	)
	for _, f := range frames {
		if e, ok := f["error"]; ok {
			var msg struct {
				Message string `json:"message"`
			}
			json.Unmarshal(e, &msg)
			if !strings.Contains(msg.Message, "does not serve") {
				t.Errorf("message should say what this runner serves: %q", msg.Message)
			}
			return
		}
	}
	t.Fatal("an unknown action must be a JSON-RPC error")
}

func TestMismatchedInputSchemaIsRefused(t *testing.T) {
	frames := run(t,
		hello(serve.ProtocolVersion, serve.KernelVersion),
		invoke(2, "test.echo", mustRecord(t, "test.SomethingElse@1", echoIn{Say: "x"})),
	)
	for _, f := range frames {
		res, ok := f["result"]
		if !ok {
			continue
		}
		var r struct {
			Payload kernel.Value `json:"payload"`
		}
		if json.Unmarshal(res, &r) != nil || r.Payload.Kind != kernel.KindError {
			continue
		}
		if !strings.Contains(r.Payload.Error.Message, "declared input") {
			t.Errorf("error should name the schema mismatch: %q", r.Payload.Error.Message)
		}
		return
	}
	t.Fatal("a wrong-schema payload must be refused, not decoded into a zero struct")
}

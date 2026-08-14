// Package serve is the stdio shim: it turns a Registry into a runner process
// the executor can invoke.
//
// The whole file exists to implement PROTOCOL.md and nothing else. It contains
// no business logic and must never gain any -- an action's behaviour belongs in
// its body, where it can be unit-tested without a process.
package serve

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"runtime/debug"
	"sync"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// Versions this runner implements. A mismatch is refused at the handshake
// rather than tolerated: an SDK built for kernel v1 talking to an executor on
// kernel v2 would misread an envelope and emit plausible wrong output, and
// plausible wrong output is the most expensive failure this system can have.
const (
	ProtocolVersion = 1
	KernelVersion   = 1
	RunnerName      = "pantheon-go/0.1.0"
)

// JSON-RPC reserved error codes, plus the ones this shim adds.
const (
	codeParseError      = -32700
	codeInvalidRequest  = -32600
	codeMethodNotFound  = -32601
	codeVersionMismatch = -32000
	codeUnknownAction   = -32001
)

// Options configures a Server. The zero value is what Run uses.
type Options struct {
	In  io.Reader // defaults to os.Stdin
	Out io.Writer // defaults to os.Stdout

	// Dial opens the resource proxy connection. Overridden by ptnfake so the
	// shim can be tested end to end without an executor.
	Dial func(res.Capabilities) (*res.Client, error)

	// Now supplies timestamps. Overridden in tests so envelope comparison is
	// deterministic rather than approximately-equal.
	Now func() time.Time
}

// Server serves a registry over one stdio pair.
type Server struct {
	reg  *action.Registry
	opts Options

	wmu sync.Mutex
	enc *json.Encoder

	shookHands bool
}

// Run serves reg on stdin/stdout until stdin closes. This is all a runner
// binary's main needs to call.
func Run(reg *action.Registry) error { return New(reg, Options{}).Serve() }

// New builds a Server.
func New(reg *action.Registry, opts Options) *Server {
	if opts.In == nil {
		opts.In = os.Stdin
	}
	if opts.Out == nil {
		opts.Out = os.Stdout
	}
	if opts.Dial == nil {
		opts.Dial = res.Dial
	}
	if opts.Now == nil {
		opts.Now = time.Now
	}
	return &Server{reg: reg, opts: opts, enc: json.NewEncoder(opts.Out)}
}

type request struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      *int64          `json:"id"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params"`
}

type response struct {
	JSONRPC string    `json:"jsonrpc"`
	ID      int64     `json:"id"`
	Result  any       `json:"result,omitempty"`
	Error   *rpcError `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

type notification struct {
	JSONRPC string `json:"jsonrpc"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
}

// Serve reads requests until the input closes.
func (s *Server) Serve() error {
	sc := bufio.NewScanner(s.opts.In)
	sc.Buffer(make([]byte, 0, 64*1024), 64*1024*1024) // a payload may carry a large inline record

	var wg sync.WaitGroup
	defer wg.Wait()

	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var req request
		if err := json.Unmarshal(line, &req); err != nil {
			s.writeError(0, codeParseError, fmt.Sprintf("unparseable request: %v", err))
			continue
		}
		if req.ID == nil {
			// A notification to the runner. Nothing in PROTOCOL.md sends one;
			// ignoring is correct and forward-compatible.
			continue
		}

		// Invocations run concurrently. The executor may well serialise them --
		// spec §8's warm pool implies one task per container -- but handling
		// concurrent invokes costs one goroutine and removes a constraint the
		// protocol never actually stated.
		body := append([]byte(nil), req.Params...)
		id, method := *req.ID, req.Method
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.dispatch(id, method, body)
		}()
	}
	if err := sc.Err(); err != nil && !errors.Is(err, io.EOF) {
		return fmt.Errorf("serve: reading stdin: %w", err)
	}
	return nil
}

func (s *Server) dispatch(id int64, method string, params []byte) {
	switch method {
	case "hello":
		s.handleHello(id, params)
	case "invoke":
		s.handleInvoke(id, params)
	default:
		s.writeError(id, codeMethodNotFound, fmt.Sprintf("unknown method %q", method))
	}
}

// ---------- hello ----------

type helloParams struct {
	ProtocolVersion int `json:"protocol_version"`
	KernelVersion   int `json:"kernel_version"`
}

type actionDescriptor struct {
	Name    string `json:"name"`
	Version int    `json:"version"`
	Input   string `json:"input"`
	Output  string `json:"output"`
	Summary string `json:"summary"`
}

func (s *Server) handleHello(id int64, params []byte) {
	var p helloParams
	if err := json.Unmarshal(params, &p); err != nil {
		s.writeError(id, codeInvalidRequest, fmt.Sprintf("bad hello params: %v", err))
		return
	}
	if p.ProtocolVersion != ProtocolVersion || p.KernelVersion != KernelVersion {
		s.writeError(id, codeVersionMismatch, fmt.Sprintf(
			"version mismatch: executor speaks protocol %d/kernel %d, %s speaks protocol %d/kernel %d",
			p.ProtocolVersion, p.KernelVersion, RunnerName, ProtocolVersion, KernelVersion))
		return
	}

	descs := make([]actionDescriptor, 0, len(s.reg.Names()))
	for _, e := range s.reg.Entries() {
		descs = append(descs, actionDescriptor{
			Name:    e.Spec.Name,
			Version: e.Spec.Version,
			Input:   e.Spec.Input.String(),
			Output:  e.Spec.Output.String(),
			Summary: e.Spec.Summary,
		})
	}
	s.shookHands = true
	s.writeResult(id, map[string]any{
		"protocol_version": ProtocolVersion,
		"kernel_version":   KernelVersion,
		"runner":           RunnerName,
		"actions":          descs,
	})
}

// ---------- invoke ----------

type invokeParams struct {
	Action       string           `json:"action"`
	Envelope     kernel.Envelope  `json:"envelope"`
	Payload      kernel.Value     `json:"payload"`
	Capabilities res.Capabilities `json:"capabilities"`
}

func (s *Server) handleInvoke(id int64, params []byte) {
	var p invokeParams
	if err := json.Unmarshal(params, &p); err != nil {
		s.writeError(id, codeInvalidRequest, fmt.Sprintf("bad invoke params: %v", err))
		return
	}

	entry, ok := s.reg.Lookup(p.Action)
	if !ok {
		// A protocol fault, not a business failure: the executor asked for
		// something this image does not serve, which is a deploy mistake.
		s.writeError(id, codeUnknownAction, fmt.Sprintf(
			"this runner does not serve action %q; it serves %v", p.Action, s.reg.Names()))
		return
	}

	client, err := s.opts.Dial(p.Capabilities)
	if err != nil {
		s.writeValueResult(id, p.Envelope, entry, kernel.NewError("proxy_unavailable", err.Error()), 0)
		return
	}
	defer client.Close()

	ctx := context.Background()
	var cancel context.CancelFunc
	if entry.Spec.Policy.Timeout > 0 {
		ctx, cancel = context.WithTimeout(ctx, entry.Spec.Policy.Timeout)
		defer cancel()
	}

	sink := &streamSink{srv: s}
	c := action.NewCtx(ctx, p.Envelope, entry.Spec, client, sink)

	started := time.Now()
	out, err := s.call(entry, c, p.Payload)
	elapsed := time.Since(started).Milliseconds()

	if err != nil {
		// A business failure is a value the run log routes, not a JSON-RPC
		// error (PROTOCOL.md). The executor sees a completed invocation whose
		// payload is an Error, which is what lets retry, repair and audit all
		// read from one place.
		code := "action_failed"
		if errors.Is(err, context.DeadlineExceeded) {
			code = "timeout"
		}
		out = kernel.NewError(code, err.Error())
	}

	env := p.Envelope.Derive(
		outputRef(entry, out),
		entry.Spec.Ref().String(),
		kernel.BudgetSpent{Ms: elapsed},
		s.opts.Now(),
	)
	for _, t := range c.Taints() {
		env = env.WithTaint(t)
	}
	s.writeResult(id, map[string]any{"envelope": env, "payload": out})
}

// call runs the body with panic recovery.
//
// A panicking body must produce a typed failure in the run log, not a mystery
// exit code that takes down the container and every other task the warm pool
// had scheduled behind it.
func (s *Server) call(e *action.Entry, c *action.Ctx, in kernel.Value) (out kernel.Value, err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("action %s panicked: %v\n%s", e.Spec.Name, r, debug.Stack())
		}
	}()
	return e.Handler(c, in)
}

// outputRef reports the schema the produced value actually carries. An Error is
// a kernel value, not the declared output type, and labelling a failure with
// the success schema would make the run log lie.
func outputRef(e *action.Entry, v kernel.Value) kernel.TypeRef {
	switch v.Kind {
	case kernel.KindError:
		return kernel.Ref("kernel.Error", KernelVersion)
	case kernel.KindRecord:
		if v.Record != nil && !v.Record.TypeRef.IsZero() {
			return v.Record.TypeRef
		}
	case kernel.KindFile:
		return kernel.Ref("kernel.File", KernelVersion)
	case kernel.KindTable:
		return kernel.Ref("kernel.Table", KernelVersion)
	case kernel.KindText:
		return kernel.Ref("kernel.Text", KernelVersion)
	}
	return e.Spec.Output
}

func (s *Server) writeValueResult(id int64, in kernel.Envelope, e *action.Entry, v kernel.Value, ms int64) {
	env := in.Derive(outputRef(e, v), e.Spec.Ref().String(), kernel.BudgetSpent{Ms: ms}, s.opts.Now())
	s.writeResult(id, map[string]any{"envelope": env, "payload": v})
}

// ---------- writing ----------

func (s *Server) writeResult(id int64, result any) {
	s.write(response{JSONRPC: "2.0", ID: id, Result: result})
}

func (s *Server) writeError(id, code int64, msg string) {
	s.write(response{JSONRPC: "2.0", ID: id, Error: &rpcError{Code: int(code), Message: msg}})
}

func (s *Server) write(v any) {
	s.wmu.Lock()
	defer s.wmu.Unlock()
	if err := s.enc.Encode(v); err != nil {
		// stdout is the only channel to the executor. If it is gone there is
		// nowhere to report that it is gone except stderr, which the executor
		// captures as unstructured logs.
		fmt.Fprintf(os.Stderr, "serve: writing to stdout: %v\n", err)
	}
}

// streamSink forwards log and event notifications up the stdio channel.
type streamSink struct{ srv *Server }

// Log forwards a log line to the executor as a JSON-RPC notification.
func (s *streamSink) Log(level, message string, fields map[string]any) {
	p := map[string]any{"level": level, "message": message}
	if len(fields) > 0 {
		p["fields"] = fields
	}
	s.srv.write(notification{JSONRPC: "2.0", Method: "log", Params: p})
}

// Event forwards a run-log event to the executor as a notification.
func (s *streamSink) Event(eventType string, payload any) {
	s.srv.write(notification{JSONRPC: "2.0", Method: "event",
		Params: map[string]any{"event_type": eventType, "payload": payload}})
}

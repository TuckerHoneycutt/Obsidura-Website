// Package res is the resource proxy client, and the only egress in this
// library.
//
// Spec §8: the per-run Unix domain socket IS the capability. Credentials live
// executor-side and are never shared with the container. An action that opens
// its own database connection or HTTP client has bypassed capability
// enforcement, taint recording, budget metering and the audit log in one line
// of code -- which is why lint/imports_test.go fails the build if anything
// under actions/ imports a network or database package directly.
package res

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"sync"
)

// Capabilities is what the executor hands the body at invocation. It carries a
// socket path and a token -- never a credential. It is deliberately not
// Stringer: the token should not reach a log line by accident.
type Capabilities struct {
	Socket string `json:"socket"`
	Token  string `json:"token"`
}

// Client speaks JSON-RPC 2.0 over the run-scoped socket.
//
// Requests are multiplexed by id and the client is safe for concurrent use. If
// the executor's proxy turns out to serialise requests (open question Q3), every
// call here still returns the right answer -- just without the overlap. No
// correctness depends on concurrency, so Q3 can be settled by measurement later
// without touching a single action.
type Client struct {
	caps Capabilities

	conn net.Conn
	enc  *json.Encoder
	wmu  sync.Mutex // serialises frame writes; a torn frame desyncs the stream

	mu      sync.Mutex
	nextID  int64
	pending map[int64]chan rpcResponse
	closed  bool
	readErr error
}

type rpcRequest struct {
	JSONRPC string `json:"jsonrpc"`
	ID      int64  `json:"id"`
	Method  string `json:"method"`
	Params  any    `json:"params"`
}

type rpcResponse struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      int64           `json:"id"`
	Result  json.RawMessage `json:"result,omitempty"`
	Error   *rpcError       `json:"error,omitempty"`
}

type rpcError struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

// Error is a failure reported by the proxy. It is distinct from a transport
// failure: a refused grant is an answer, not a broken connection, and callers
// that retry should be able to tell the difference.
type Error struct {
	Code    int
	Message string
	Method  string
}

// Error renders the refusal with its method and code.
func (e *Error) Error() string {
	return fmt.Sprintf("res: proxy refused %s: %s (code %d)", e.Method, e.Message, e.Code)
}

// Denied reports whether err is a permission refusal from the proxy. Grants are
// enforced proxy-side on every call (spec §8), so this is how an action
// distinguishes "not allowed to see it" from "not there".
func Denied(err error) bool {
	var e *Error
	return errors.As(err, &e) && e.Code == CodeDenied
}

// Proxy error codes. Outside the JSON-RPC reserved range (-32768..-32000).
const (
	CodeDenied     = 1001 // grant check failed
	CodeNotFound   = 1002
	CodeUpstream   = 1003 // the resource itself failed
	CodeBadRequest = 1004
)

// Dial connects to the run's proxy socket.
func Dial(caps Capabilities) (*Client, error) {
	if caps.Socket == "" {
		return nil, errors.New("res: no proxy socket in capabilities; the body has no way to reach any resource")
	}
	conn, err := net.Dial("unix", caps.Socket)
	if err != nil {
		return nil, fmt.Errorf("res: dialling proxy at %s: %w", caps.Socket, err)
	}
	return NewClient(conn, caps), nil
}

// NewClient wraps an established connection. Exported so ptnfake can hand the
// SDK a real socket in tests rather than a mock -- tests assert on the proxy's
// recorded audit log, which is an artifact, not on mock call counts.
func NewClient(conn net.Conn, caps Capabilities) *Client {
	c := &Client{
		caps:    caps,
		conn:    conn,
		enc:     json.NewEncoder(conn),
		pending: map[int64]chan rpcResponse{},
	}
	go c.readLoop()
	return c
}

func (c *Client) readLoop() {
	sc := bufio.NewScanner(c.conn)
	sc.Buffer(make([]byte, 0, 64*1024), 32*1024*1024) // table.read chunks are large
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var resp rpcResponse
		if err := json.Unmarshal(line, &resp); err != nil {
			c.fail(fmt.Errorf("res: unparseable frame from proxy: %w", err))
			return
		}
		c.mu.Lock()
		ch, ok := c.pending[resp.ID]
		delete(c.pending, resp.ID)
		c.mu.Unlock()
		if ok {
			ch <- resp
		}
		// An unmatched id is dropped. It means the proxy answered a request we
		// already gave up on; there is nobody left to tell.
	}
	err := sc.Err()
	if err == nil {
		err = io.EOF
	}
	c.fail(fmt.Errorf("res: proxy connection ended: %w", err))
}

// fail wakes every in-flight caller. Without this a body whose proxy died mid
// run would block until the task timeout rather than reporting the real cause.
func (c *Client) fail(err error) {
	c.mu.Lock()
	if c.closed {
		c.mu.Unlock()
		return
	}
	c.closed = true
	c.readErr = err
	pending := c.pending
	c.pending = map[int64]chan rpcResponse{}
	c.mu.Unlock()

	for id, ch := range pending {
		ch <- rpcResponse{ID: id, Error: &rpcError{Code: CodeUpstream, Message: err.Error()}}
	}
}

// Close releases the connection.
func (c *Client) Close() error {
	c.fail(errors.New("res: client closed"))
	return c.conn.Close()
}

// call issues one request and waits for its response or ctx cancellation.
func (c *Client) call(ctx context.Context, method string, params any, out any) error {
	c.mu.Lock()
	if c.closed {
		err := c.readErr
		c.mu.Unlock()
		return err
	}
	c.nextID++
	id := c.nextID
	ch := make(chan rpcResponse, 1)
	c.pending[id] = ch
	c.mu.Unlock()

	c.wmu.Lock()
	err := c.enc.Encode(rpcRequest{JSONRPC: "2.0", ID: id, Method: method, Params: params})
	c.wmu.Unlock()
	if err != nil {
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return fmt.Errorf("res: writing %s: %w", method, err)
	}

	select {
	case <-ctx.Done():
		c.mu.Lock()
		delete(c.pending, id)
		c.mu.Unlock()
		return ctx.Err()
	case resp := <-ch:
		if resp.Error != nil {
			return &Error{Code: resp.Error.Code, Message: resp.Error.Message, Method: method}
		}
		if out == nil {
			return nil
		}
		if err := json.Unmarshal(resp.Result, out); err != nil {
			return fmt.Errorf("res: decoding %s result: %w", method, err)
		}
		return nil
	}
}

// Call invokes a verb on a named resource. Typed helpers in connectors.go wrap
// this for the three v0 connector kinds; use those. This stays exported because
// a fourth connector should be usable from an action the day the executor gains
// it, without waiting for an SDK release.
func (c *Client) Call(ctx context.Context, resource, verb string, args any, out any) error {
	return c.call(ctx, "resource.call", map[string]any{
		"token":    c.caps.Token,
		"resource": resource,
		"verb":     verb,
		"args":     args,
	}, out)
}

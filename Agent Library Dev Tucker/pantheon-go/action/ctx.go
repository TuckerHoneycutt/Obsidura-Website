package action

import (
	"context"
	"fmt"
	"time"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// Sink receives the notifications a body streams back to the executor while it
// runs. serve implements it over stdio; ptnfake captures it for assertions.
type Sink interface {
	Log(level, message string, fields map[string]any)
	Event(eventType string, payload any)
}

// Ctx is what a body gets. It carries the deadline, the envelope, capability-
// scoped resource access, and the log and event channels -- and no credentials,
// because there are none to carry.
type Ctx struct {
	context.Context

	// Envelope is the inbound envelope. Read it for run_id, taint and causality;
	// the outbound envelope is derived by serve, not built by the body.
	Envelope kernel.Envelope

	// Action is the spec of the running action, so a body can report its own
	// name without hardcoding a string that will outlive a rename.
	Action Spec

	client *res.Client
	sink   Sink

	started time.Time
	taints  []kernel.Taint
}

// NewCtx builds a Ctx. Called by serve and by ptnfake; bodies never call it.
func NewCtx(parent context.Context, env kernel.Envelope, spec Spec, client *res.Client, sink Sink) *Ctx {
	return &Ctx{
		Context:  parent,
		Envelope: env,
		Action:   spec,
		client:   client,
		sink:     sink,
		started:  time.Now(),
	}
}

// Logf streams a log line to the executor.
func (c *Ctx) Logf(format string, args ...any) {
	c.sink.Log("info", fmt.Sprintf(format, args...), nil)
}

// Log streams a log line with structured fields.
func (c *Ctx) Log(level, message string, fields map[string]any) {
	c.sink.Log(level, message, fields)
}

// Emit appends an event to the run log (run_events, spec §8).
//
// This is the PRODUCT's run log, not the Aurora development journal. See
// 01-constraints.md, "the two-journal trap".
func (c *Ctx) Emit(eventType string, payload any) {
	c.sink.Event(eventType, payload)
}

// Taint records that this action's output was influenced by an untrusted
// source. Recorded and logged, never enforced, in v0 (spec §6) -- nothing in
// this SDK refuses an operation because of a mark.
func (c *Ctx) Taint(source, reason string) {
	t := kernel.Taint{Source: source, Reason: reason}
	for _, existing := range c.taints {
		if existing == t {
			return
		}
	}
	c.taints = append(c.taints, t)
}

// Taints returns what the body recorded, for serve to fold into the outbound
// envelope.
func (c *Ctx) Taints() []kernel.Taint { return c.taints }

// Elapsed reports wall time since the body started, for budget metering.
func (c *Ctx) Elapsed() time.Duration { return time.Since(c.started) }

// ---------- resource access ----------

// checkDeclared verifies the action declared this resource and verb.
//
// The proxy is the real enforcement point and would refuse an undeclared call
// anyway. Checking locally converts "denied by the proxy in production" into a
// clear message the first time the action runs in a unit test -- the failure
// mode being prevented is an action whose `uses:` drifted away from its body,
// which YAML alone cannot notice.
func (c *Ctx) checkDeclared(name, verb string) error {
	for _, u := range c.Action.Uses {
		if u.Name != name {
			continue
		}
		for _, v := range u.Verbs {
			if v == verb {
				return nil
			}
		}
		return fmt.Errorf("action %s uses resource %q but does not declare verb %q; add it to Spec.Uses",
			c.Action.Name, name, verb)
	}
	return fmt.Errorf("action %s does not declare resource %q in Spec.Uses", c.Action.Name, name)
}

// Postgres returns a scoped postgres resource.
func (c *Ctx) Postgres(name string) *PostgresHandle {
	return &PostgresHandle{c: c, name: name}
}

// PostgresHandle wraps res.PostgresResource with the declaration check.
type PostgresHandle struct {
	c    *Ctx
	name string
}

// Query runs parameterised SQL through the proxy. Grant scope -- the SQL row
// filter for this run's user -- is applied proxy-side, so the same query for
// two users legitimately returns different rows.
func (p *PostgresHandle) Query(sql string, params ...any) (*res.Rows, error) {
	if err := p.c.checkDeclared(p.name, "query"); err != nil {
		return nil, err
	}
	rows, err := res.Postgres(p.c.client, p.name).Query(p.c.Context, sql, params...)
	if err != nil {
		return nil, err
	}
	p.c.Taint("resource:"+p.name, "postgres query result")
	return rows, nil
}

// S3 returns a scoped blob store resource.
func (c *Ctx) S3(name string) *S3Handle { return &S3Handle{c: c, name: name} }

// S3Handle wraps res.S3Resource with the declaration check.
type S3Handle struct {
	c    *Ctx
	name string
}

// List enumerates objects under a prefix. Keys outside the run's granted
// prefix are filtered proxy-side and simply do not appear.
func (s *S3Handle) List(prefix string) ([]res.ObjectMeta, error) {
	if err := s.c.checkDeclared(s.name, "list"); err != nil {
		return nil, err
	}
	return res.S3(s.c.client, s.name).List(s.c.Context, prefix)
}

// Get fetches an object's bytes and records taint. A key outside the run's
// granted prefix is refused by the proxy.
func (s *S3Handle) Get(key string) ([]byte, error) {
	if err := s.c.checkDeclared(s.name, "get"); err != nil {
		return nil, err
	}
	b, err := res.S3(s.c.client, s.name).Get(s.c.Context, key)
	if err != nil {
		return nil, err
	}
	s.c.Taint("resource:"+s.name, "object "+key)
	return b, nil
}

// Put stores an object. Writing outside the granted prefix is refused.
func (s *S3Handle) Put(key string, body []byte, mediaType string) error {
	if err := s.c.checkDeclared(s.name, "put"); err != nil {
		return err
	}
	return res.S3(s.c.client, s.name).Put(s.c.Context, key, body, mediaType)
}

// HTTP returns a scoped HTTP resource.
func (c *Ctx) HTTP(name string) *HTTPHandle { return &HTTPHandle{c: c, name: name} }

// HTTPHandle wraps res.HTTPResource with the declaration check.
type HTTPHandle struct {
	c    *Ctx
	name string
}

// Request issues an HTTP request through the proxy and records taint. A URL
// off the resource's allowlist is refused proxy-side.
func (h *HTTPHandle) Request(method, url string, body []byte, headers map[string]string) (*res.Response, error) {
	if err := h.c.checkDeclared(h.name, "request"); err != nil {
		return nil, err
	}
	resp, err := res.HTTP(h.c.client, h.name).Request(h.c.Context, method, url, body, headers)
	if err != nil {
		return nil, err
	}
	h.c.Taint("resource:"+h.name, method+" "+url)
	return resp, nil
}

// GetJSON is the common case: GET a URL and decode JSON. A non-2xx status is
// an error.
func (h *HTTPHandle) GetJSON(url string, dst any) error {
	if err := h.c.checkDeclared(h.name, "request"); err != nil {
		return err
	}
	if err := res.HTTP(h.c.client, h.name).GetJSON(h.c.Context, url, dst); err != nil {
		return err
	}
	h.c.Taint("resource:"+h.name, "GET "+url)
	return nil
}

// ---------- handles ----------

// PutFile stores bytes and returns a content-addressed File handle. Needs no
// declaration: the blob store is the run's own scratch space, not a resource
// with a grant.
func (c *Ctx) PutFile(body []byte, mediaType, filename string) (kernel.FileHandle, error) {
	return c.client.PutBlob(c.Context, body, mediaType, filename)
}

// GetFile fetches a File handle's bytes.
func (c *Ctx) GetFile(h kernel.FileHandle) ([]byte, error) {
	return c.client.GetBlob(c.Context, h)
}

// PutTable stores rows as a Table handle.
func (c *Ctx) PutTable(cols []kernel.Column, rows [][]any, format string) (kernel.TableHandle, error) {
	return c.client.PutTable(c.Context, cols, rows, format)
}

// OpenTable opens a chunked cursor over a Table handle. Prefer package table's
// helpers, which iterate without materialising the whole table.
func (c *Ctx) OpenTable(h kernel.TableHandle) (*res.Cursor, error) {
	return c.client.OpenTable(c.Context, h)
}

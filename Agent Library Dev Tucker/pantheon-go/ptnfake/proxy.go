// Package ptnfake is an in-process stand-in for the executor's resource proxy.
//
// It serves a REAL Unix domain socket speaking the real protocol, so tests
// exercise the actual res client, the actual JSON framing, and the actual grant
// checks. Nothing here is a mock: assertions are made against the proxy's
// recorded audit log, which is an artifact the run produces, not against call
// counts on a spy. That is the output-based-assertions invariant, applied to
// the SDK's own tests.
//
// It also enforces grants the way spec §8 describes -- SQL row filter for
// postgres, key prefix for s3, URL allowlist for http -- which is what lets the
// two-user permission beat (acceptance test 4) be an ordinary unit test that
// runs in milliseconds instead of a demo-day hope.
package ptnfake

import (
	"bufio"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// QueryFunc answers a postgres query. Register one with AddPostgresFunc when a
// fixture needs to vary by parameter; AddPostgresRows covers the common case.
type QueryFunc func(sql string, params []any) (*res.Rows, error)

// HTTPFunc answers an HTTP request.
type HTTPFunc func(method, url string, body []byte, headers map[string]string) (res.Response, error)

// Grant is the run's permission on one resource, mirroring
// grants(user_id, resource, verbs, scope) from spec §8. Scope is per-connector,
// exactly as the spec says.
type Grant struct {
	Verbs []string

	// RowFilter is the postgres scope: a row-level predicate applied to every
	// result. This is what makes user A and user B get different patients from
	// the same query, with the action none the wiser -- which is the correct
	// design, and the reason an action must never filter by user itself.
	RowFilter func(row map[string]any) bool

	// KeyPrefix is the s3 scope. Empty means every key in the resource.
	KeyPrefix string

	// URLAllow is the http scope: a list of prefixes. Empty means nothing is
	// allowed, not everything -- an empty allowlist that permits all traffic is
	// the classic fail-open bug, and the guard SPEC is explicit that only
	// membership in a known-good set fails closed.
	URLAllow []string
}

// AuditEntry is one recorded proxy call. The audit log is the artifact tests
// assert against, and it is also what the demo's governance beat displays.
type AuditEntry struct {
	Resource string
	Verb     string
	Detail   string
	Allowed  bool
	Reason   string
	RowsIn   int // rows the resource produced
	RowsOut  int // rows that survived the scope filter
}

// Proxy is a fake executor-side resource proxy.
type Proxy struct {
	mu sync.Mutex

	dir  string
	ln   net.Listener
	caps res.Capabilities

	grants map[string]Grant
	pg     map[string]QueryFunc
	s3     map[string]map[string][]byte
	http   map[string]HTTPFunc

	blobs  map[string][]byte
	blobMT map[string]string

	tables  map[string]*fakeTable
	cursors map[string]*fakeCursor
	seq     int

	audit []AuditEntry

	conns []net.Conn
	wg    sync.WaitGroup
}

type fakeTable struct {
	cols []kernel.Column
	rows [][]any
}

type fakeCursor struct {
	tbl *fakeTable
	pos int
}

// New starts a proxy on a fresh socket. Close it when done.
func New() (*Proxy, error) {
	dir, err := os.MkdirTemp("", "ptnfake")
	if err != nil {
		return nil, err
	}
	// Short filename on purpose: a Unix socket path is capped near 104 bytes on
	// darwin, and the temp dir already eats most of that.
	sock := filepath.Join(dir, "p.sock")
	ln, err := net.Listen("unix", sock)
	if err != nil {
		os.RemoveAll(dir)
		return nil, err
	}
	p := &Proxy{
		dir:     dir,
		ln:      ln,
		caps:    res.Capabilities{Socket: sock, Token: "fake-token"},
		grants:  map[string]Grant{},
		pg:      map[string]QueryFunc{},
		s3:      map[string]map[string][]byte{},
		http:    map[string]HTTPFunc{},
		blobs:   map[string][]byte{},
		blobMT:  map[string]string{},
		tables:  map[string]*fakeTable{},
		cursors: map[string]*fakeCursor{},
	}
	p.wg.Add(1)
	go p.accept()
	return p, nil
}

// Capabilities returns what an invocation would hand the body.
func (p *Proxy) Capabilities() res.Capabilities { return p.caps }

// Close stops the proxy and removes its socket.
func (p *Proxy) Close() error {
	p.ln.Close()
	p.mu.Lock()
	for _, c := range p.conns {
		c.Close()
	}
	p.mu.Unlock()
	p.wg.Wait()
	return os.RemoveAll(p.dir)
}

func (p *Proxy) accept() {
	defer p.wg.Done()
	for {
		conn, err := p.ln.Accept()
		if err != nil {
			return
		}
		p.mu.Lock()
		p.conns = append(p.conns, conn)
		p.mu.Unlock()
		p.wg.Add(1)
		go func() {
			defer p.wg.Done()
			defer conn.Close()
			p.handle(conn)
		}()
	}
}

// ---------- fixture setup ----------

// Grant permits verbs on a resource with the given scope.
func (p *Proxy) Grant(resource string, g Grant) *Proxy {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.grants[resource] = g
	return p
}

// AddPostgresRows registers a canned result for an exact SQL string.
func (p *Proxy) AddPostgresRows(resource, sql string, cols []kernel.Column, rows [][]any) *Proxy {
	p.mu.Lock()
	prev := p.pg[resource]
	p.mu.Unlock()
	p.AddPostgresFunc(resource, func(q string, params []any) (*res.Rows, error) {
		if normaliseSQL(q) == normaliseSQL(sql) {
			return &res.Rows{Columns: cols, Rows: rows}, nil
		}
		if prev != nil {
			return prev(q, params)
		}
		return nil, fmt.Errorf("ptnfake: no fixture for query %q on resource %q", q, resource)
	})
	return p
}

// AddPostgresFunc registers a programmable query answerer.
func (p *Proxy) AddPostgresFunc(resource string, fn QueryFunc) *Proxy {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.pg[resource] = fn
	return p
}

// AddS3Object stores one object.
func (p *Proxy) AddS3Object(resource, key string, body []byte) *Proxy {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.s3[resource] == nil {
		p.s3[resource] = map[string][]byte{}
	}
	p.s3[resource][key] = body
	return p
}

// AddHTTPFunc registers an HTTP answerer.
func (p *Proxy) AddHTTPFunc(resource string, fn HTTPFunc) *Proxy {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.http[resource] = fn
	return p
}

// AddJSONEndpoint answers one exact URL with a JSON body and status 200.
func (p *Proxy) AddJSONEndpoint(resource, url string, body any) *Proxy {
	raw, err := json.Marshal(body)
	if err != nil {
		panic(fmt.Sprintf("ptnfake: marshalling endpoint fixture for %s: %v", url, err))
	}
	p.mu.Lock()
	prev := p.http[resource]
	p.mu.Unlock()
	return p.AddHTTPFunc(resource, func(method, u string, b []byte, h map[string]string) (res.Response, error) {
		if u == url {
			return res.Response{Status: 200, Body: base64.StdEncoding.EncodeToString(raw)}, nil
		}
		if prev != nil {
			return prev(method, u, b, h)
		}
		return res.Response{Status: 404, Body: ""}, nil
	})
}

// AddTable stores a table and returns its handle, for seeding a Table input.
func (p *Proxy) AddTable(cols []kernel.Column, rows [][]any) kernel.TableHandle {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.seq++
	blob := fmt.Sprintf("sha256:fake-table-%d", p.seq)
	p.tables[blob] = &fakeTable{cols: cols, rows: rows}
	return kernel.TableHandle{Blob: blob, Format: "jsonl", Columns: cols, Rows: int64(len(rows))}
}

// ---------- inspection ----------

// Audit returns the recorded calls, in order.
func (p *Proxy) Audit() []AuditEntry {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]AuditEntry(nil), p.audit...)
}

// AuditLines renders the audit log one line per call. This is the governance
// beat of the demo (acceptance test 4) in text form.
func (p *Proxy) AuditLines() []string {
	out := []string{}
	for _, a := range p.Audit() {
		verdict := "ALLOW"
		if !a.Allowed {
			verdict = "DENY"
		}
		line := fmt.Sprintf("%s %s.%s %s", verdict, a.Resource, a.Verb, a.Detail)
		if a.RowsIn != a.RowsOut {
			line += fmt.Sprintf(" [scope: %d/%d rows]", a.RowsOut, a.RowsIn)
		}
		if a.Reason != "" {
			line += " (" + a.Reason + ")"
		}
		out = append(out, line)
	}
	return out
}

// Blob returns a stored blob's bytes, for asserting on what an action emitted.
func (p *Proxy) Blob(h kernel.FileHandle) ([]byte, bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	b, ok := p.blobs[h.Blob]
	return b, ok
}

// TableRows returns a stored table's rows, for asserting on a Table output.
func (p *Proxy) TableRows(h kernel.TableHandle) ([]kernel.Column, [][]any, bool) {
	p.mu.Lock()
	defer p.mu.Unlock()
	t, ok := p.tables[h.Blob]
	if !ok {
		return nil, nil, false
	}
	return t.cols, t.rows, true
}

func (p *Proxy) record(e AuditEntry) {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.audit = append(p.audit, e)
}

// ---------- protocol ----------

type rpcReq struct {
	ID     int64           `json:"id"`
	Method string          `json:"method"`
	Params json.RawMessage `json:"params"`
}

type rpcResp struct {
	JSONRPC string   `json:"jsonrpc"`
	ID      int64    `json:"id"`
	Result  any      `json:"result,omitempty"`
	Error   *respErr `json:"error,omitempty"`
}

type respErr struct {
	Code    int    `json:"code"`
	Message string `json:"message"`
}

func (p *Proxy) handle(conn net.Conn) {
	sc := bufio.NewScanner(conn)
	sc.Buffer(make([]byte, 0, 64*1024), 64*1024*1024)
	enc := json.NewEncoder(conn)
	var wmu sync.Mutex

	write := func(v any) {
		wmu.Lock()
		defer wmu.Unlock()
		enc.Encode(v)
	}

	for sc.Scan() {
		line := append([]byte(nil), sc.Bytes()...)
		if len(line) == 0 {
			continue
		}
		// Concurrently, so a test that fans out proves the client's
		// multiplexing rather than accidentally proving it can be serialised.
		go func() {
			var req rpcReq
			if err := json.Unmarshal(line, &req); err != nil {
				return
			}
			result, err := p.route(req.Method, req.Params)
			if err != nil {
				var pe *res.Error
				code := res.CodeBadRequest
				if errors.As(err, &pe) {
					code = pe.Code
				}
				write(rpcResp{JSONRPC: "2.0", ID: req.ID, Error: &respErr{Code: code, Message: err.Error()}})
				return
			}
			write(rpcResp{JSONRPC: "2.0", ID: req.ID, Result: result})
		}()
	}
}

func (p *Proxy) route(method string, params json.RawMessage) (any, error) {
	switch method {
	case "resource.call":
		return p.resourceCall(params)
	case "blob.put":
		return p.blobPut(params)
	case "blob.get":
		return p.blobGet(params)
	case "table.put":
		return p.tablePut(params)
	case "table.open":
		return p.tableOpen(params)
	case "table.read":
		return p.tableRead(params)
	default:
		return nil, fmt.Errorf("ptnfake: unknown method %q", method)
	}
}

func denied(msg string) error {
	return &res.Error{Code: res.CodeDenied, Message: msg, Method: "resource.call"}
}

func (p *Proxy) resourceCall(params json.RawMessage) (any, error) {
	var q struct {
		Resource string          `json:"resource"`
		Verb     string          `json:"verb"`
		Args     json.RawMessage `json:"args"`
	}
	if err := json.Unmarshal(params, &q); err != nil {
		return nil, err
	}

	p.mu.Lock()
	g, hasGrant := p.grants[q.Resource]
	p.mu.Unlock()

	if !hasGrant {
		p.record(AuditEntry{Resource: q.Resource, Verb: q.Verb, Allowed: false, Reason: "no grant for resource"})
		return nil, denied(fmt.Sprintf("no grant for resource %q", q.Resource))
	}
	if !contains(g.Verbs, q.Verb) {
		p.record(AuditEntry{Resource: q.Resource, Verb: q.Verb, Allowed: false, Reason: "verb not granted"})
		return nil, denied(fmt.Sprintf("verb %q not granted on %q", q.Verb, q.Resource))
	}

	switch q.Verb {
	case "query":
		return p.doQuery(q.Resource, g, q.Args)
	case "list":
		return p.doList(q.Resource, g, q.Args)
	case "get":
		return p.doGet(q.Resource, g, q.Args)
	case "put":
		return p.doPut(q.Resource, g, q.Args)
	case "request":
		return p.doRequest(q.Resource, g, q.Args)
	default:
		return nil, fmt.Errorf("ptnfake: unsupported verb %q", q.Verb)
	}
}

func (p *Proxy) doQuery(resource string, g Grant, args json.RawMessage) (any, error) {
	var a struct {
		SQL    string `json:"sql"`
		Params []any  `json:"params"`
	}
	if err := json.Unmarshal(args, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	fn := p.pg[resource]
	p.mu.Unlock()
	if fn == nil {
		return nil, fmt.Errorf("ptnfake: resource %q has no postgres fixture", resource)
	}
	rows, err := fn(a.SQL, a.Params)
	if err != nil {
		return nil, err
	}

	in := len(rows.Rows)
	filtered := rows.Rows
	if g.RowFilter != nil {
		filtered = nil
		for _, r := range rows.Rows {
			m := make(map[string]any, len(rows.Columns))
			for i, c := range rows.Columns {
				if i < len(r) {
					m[c.Name] = r[i]
				}
			}
			if g.RowFilter(m) {
				filtered = append(filtered, r)
			}
		}
	}
	p.record(AuditEntry{
		Resource: resource, Verb: "query", Detail: truncate(normaliseSQL(a.SQL), 80),
		Allowed: true, RowsIn: in, RowsOut: len(filtered),
	})
	return res.Rows{Columns: rows.Columns, Rows: filtered}, nil
}

func (p *Proxy) doList(resource string, g Grant, args json.RawMessage) (any, error) {
	var a struct {
		Prefix string `json:"prefix"`
	}
	if err := json.Unmarshal(args, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	objs := p.s3[resource]
	keys := make([]string, 0, len(objs))
	for k := range objs {
		keys = append(keys, k)
	}
	p.mu.Unlock()
	sort.Strings(keys)

	out := []res.ObjectMeta{}
	total := 0
	for _, k := range keys {
		if !strings.HasPrefix(k, a.Prefix) {
			continue
		}
		total++
		if !strings.HasPrefix(k, g.KeyPrefix) {
			continue // outside the grant's scope: filtered, not an error
		}
		out = append(out, res.ObjectMeta{Key: k, Size: int64(len(objs[k]))})
	}
	p.record(AuditEntry{
		Resource: resource, Verb: "list", Detail: "prefix=" + a.Prefix,
		Allowed: true, RowsIn: total, RowsOut: len(out),
	})
	return map[string]any{"objects": out}, nil
}

func (p *Proxy) doGet(resource string, g Grant, args json.RawMessage) (any, error) {
	var a struct {
		Key string `json:"key"`
	}
	if err := json.Unmarshal(args, &a); err != nil {
		return nil, err
	}
	if !strings.HasPrefix(a.Key, g.KeyPrefix) {
		p.record(AuditEntry{Resource: resource, Verb: "get", Detail: a.Key, Allowed: false,
			Reason: "key outside granted prefix " + g.KeyPrefix})
		return nil, denied(fmt.Sprintf("key %q is outside the granted prefix %q", a.Key, g.KeyPrefix))
	}
	p.mu.Lock()
	body, ok := p.s3[resource][a.Key]
	p.mu.Unlock()
	if !ok {
		p.record(AuditEntry{Resource: resource, Verb: "get", Detail: a.Key, Allowed: true, Reason: "not found"})
		return nil, &res.Error{Code: res.CodeNotFound, Message: "no object " + a.Key, Method: "resource.call"}
	}
	p.record(AuditEntry{Resource: resource, Verb: "get", Detail: a.Key, Allowed: true, RowsIn: 1, RowsOut: 1})
	return map[string]any{"body": base64.StdEncoding.EncodeToString(body)}, nil
}

func (p *Proxy) doPut(resource string, g Grant, args json.RawMessage) (any, error) {
	var a struct {
		Key  string `json:"key"`
		Body string `json:"body"`
	}
	if err := json.Unmarshal(args, &a); err != nil {
		return nil, err
	}
	if !strings.HasPrefix(a.Key, g.KeyPrefix) {
		p.record(AuditEntry{Resource: resource, Verb: "put", Detail: a.Key, Allowed: false,
			Reason: "key outside granted prefix " + g.KeyPrefix})
		return nil, denied(fmt.Sprintf("key %q is outside the granted prefix %q", a.Key, g.KeyPrefix))
	}
	body, err := base64.StdEncoding.DecodeString(a.Body)
	if err != nil {
		return nil, err
	}
	p.AddS3Object(resource, a.Key, body)
	p.record(AuditEntry{Resource: resource, Verb: "put", Detail: a.Key, Allowed: true, RowsIn: 1, RowsOut: 1})
	return map[string]any{}, nil
}

func (p *Proxy) doRequest(resource string, g Grant, args json.RawMessage) (any, error) {
	var a struct {
		Method  string            `json:"method"`
		URL     string            `json:"url"`
		Body    string            `json:"body"`
		Headers map[string]string `json:"headers"`
	}
	if err := json.Unmarshal(args, &a); err != nil {
		return nil, err
	}
	allowed := false
	for _, prefix := range g.URLAllow {
		if strings.HasPrefix(a.URL, prefix) {
			allowed = true
			break
		}
	}
	if !allowed {
		p.record(AuditEntry{Resource: resource, Verb: "request", Detail: a.Method + " " + a.URL,
			Allowed: false, Reason: "URL not on allowlist"})
		return nil, denied(fmt.Sprintf("URL %q is not on the allowlist for %q", a.URL, resource))
	}
	p.mu.Lock()
	fn := p.http[resource]
	p.mu.Unlock()
	if fn == nil {
		return nil, fmt.Errorf("ptnfake: resource %q has no http fixture", resource)
	}
	var body []byte
	if a.Body != "" {
		body, _ = base64.StdEncoding.DecodeString(a.Body)
	}
	resp, err := fn(a.Method, a.URL, body, a.Headers)
	if err != nil {
		return nil, err
	}
	p.record(AuditEntry{Resource: resource, Verb: "request", Detail: a.Method + " " + a.URL,
		Allowed: true, RowsIn: 1, RowsOut: 1})
	return resp, nil
}

// ---------- blobs and tables ----------

func (p *Proxy) blobPut(params json.RawMessage) (any, error) {
	var a struct {
		MediaType string `json:"media_type"`
		Filename  string `json:"filename"`
		Body      string `json:"body"`
	}
	if err := json.Unmarshal(params, &a); err != nil {
		return nil, err
	}
	body, err := base64.StdEncoding.DecodeString(a.Body)
	if err != nil {
		return nil, err
	}
	sum := sha256.Sum256(body)
	ref := "sha256:" + hex.EncodeToString(sum[:])
	p.mu.Lock()
	p.blobs[ref] = body
	p.blobMT[ref] = a.MediaType
	p.mu.Unlock()
	return kernel.FileHandle{
		Blob: ref, MediaType: a.MediaType, Size: int64(len(body)),
		Filename: a.Filename, Capability: "fake",
	}, nil
}

func (p *Proxy) blobGet(params json.RawMessage) (any, error) {
	var a struct {
		Handle kernel.FileHandle `json:"handle"`
	}
	if err := json.Unmarshal(params, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	body, ok := p.blobs[a.Handle.Blob]
	p.mu.Unlock()
	if !ok {
		return nil, &res.Error{Code: res.CodeNotFound, Message: "no blob " + a.Handle.Blob, Method: "blob.get"}
	}
	return map[string]any{"body": base64.StdEncoding.EncodeToString(body)}, nil
}

func (p *Proxy) tablePut(params json.RawMessage) (any, error) {
	var a struct {
		Columns []kernel.Column `json:"columns"`
		Rows    [][]any         `json:"rows"`
		Format  string          `json:"format"`
	}
	if err := json.Unmarshal(params, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	p.seq++
	blob := fmt.Sprintf("sha256:fake-table-%d", p.seq)
	p.tables[blob] = &fakeTable{cols: a.Columns, rows: a.Rows}
	p.mu.Unlock()
	return kernel.TableHandle{
		Blob: blob, Format: a.Format, Columns: a.Columns, Rows: int64(len(a.Rows)), Capability: "fake",
	}, nil
}

func (p *Proxy) tableOpen(params json.RawMessage) (any, error) {
	var a struct {
		Handle kernel.TableHandle `json:"handle"`
	}
	if err := json.Unmarshal(params, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	t, ok := p.tables[a.Handle.Blob]
	if !ok {
		return nil, &res.Error{Code: res.CodeNotFound, Message: "no table " + a.Handle.Blob, Method: "table.open"}
	}
	p.seq++
	id := fmt.Sprintf("c-%d", p.seq)
	p.cursors[id] = &fakeCursor{tbl: t}
	return map[string]any{"cursor": id, "columns": t.cols}, nil
}

func (p *Proxy) tableRead(params json.RawMessage) (any, error) {
	var a struct {
		Cursor string `json:"cursor"`
		Max    int    `json:"max"`
	}
	if err := json.Unmarshal(params, &a); err != nil {
		return nil, err
	}
	p.mu.Lock()
	defer p.mu.Unlock()
	cu, ok := p.cursors[a.Cursor]
	if !ok {
		return nil, &res.Error{Code: res.CodeNotFound, Message: "no cursor " + a.Cursor, Method: "table.read"}
	}
	if a.Max <= 0 {
		a.Max = 1000
	}
	end := cu.pos + a.Max
	if end > len(cu.tbl.rows) {
		end = len(cu.tbl.rows)
	}
	rows := cu.tbl.rows[cu.pos:end]
	cu.pos = end
	return map[string]any{"rows": rows, "eof": cu.pos >= len(cu.tbl.rows)}, nil
}

// ---------- helpers ----------

func contains(hay []string, needle string) bool {
	for _, h := range hay {
		if h == needle {
			return true
		}
	}
	return false
}

// normaliseSQL collapses whitespace so a fixture keyed on a query still matches
// when the action's SQL is reformatted. Fixtures that break on indentation are
// fixtures people stop writing.
func normaliseSQL(s string) string { return strings.Join(strings.Fields(s), " ") }

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}

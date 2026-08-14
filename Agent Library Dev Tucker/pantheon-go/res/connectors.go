package res

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"fmt"

	"github.com/obsidura/pantheon-go/kernel"
)

// The three v0 connector kinds (spec §4). imap, mcp and memory are deferred
// (§11) and deliberately absent -- Client.Call is the escape hatch for a fourth
// kind the day the executor gains one.

// ---------- postgres ----------

// PostgresResource is a named postgres resource, scoped by the run's grants.
// The SQL row-filter in grants(user_id, resource, verbs, scope) is applied
// proxy-side, so the same query issued for two users legitimately returns
// different rows. That is the mechanism behind acceptance test 4, and an action
// must never try to "help" by filtering by user itself.
type PostgresResource struct {
	c    *Client
	name string
}

// Postgres names a postgres resource. It does not connect or validate; the
// grant check happens on the first call, proxy-side.
func Postgres(c *Client, name string) *PostgresResource {
	return &PostgresResource{c: c, name: name}
}

// Rows is a result set: column metadata plus positional row values.
type Rows struct {
	Columns []kernel.Column `json:"columns"`
	Rows    [][]any         `json:"rows"`
}

// Query runs parameterised SQL. Parameters are passed separately and are never
// interpolated into the statement, here or proxy-side.
func (p *PostgresResource) Query(ctx context.Context, sql string, params ...any) (*Rows, error) {
	if params == nil {
		params = []any{}
	}
	var out Rows
	err := p.c.Call(ctx, p.name, "query", map[string]any{"sql": sql, "params": params}, &out)
	if err != nil {
		return nil, err
	}
	return &out, nil
}

// Decode unmarshals the result set into dst, which must be a pointer to a slice
// of structs. Columns map to fields by json tag; a column with no matching
// field is ignored, and a field with no matching column is left zero.
//
// Tolerating both directions is deliberate: it is what lets one action written
// against a vertical type run over a tenant table that has extra columns, which
// is the whole compounding argument (02-architecture.md, Layer D).
func (r *Rows) Decode(dst any) error {
	objs := make([]map[string]any, 0, len(r.Rows))
	for i, row := range r.Rows {
		if len(row) != len(r.Columns) {
			return fmt.Errorf("res: row %d has %d values but %d columns", i, len(row), len(r.Columns))
		}
		m := make(map[string]any, len(row))
		for j, col := range r.Columns {
			m[col.Name] = row[j]
		}
		objs = append(objs, m)
	}
	b, err := json.Marshal(objs)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}

// Map returns row i keyed by column name.
//
// By name, never by index: a tenant that adds a column to its view shifts every
// position, and an action reading position 4 would then read the wrong column
// while continuing to look like it worked.
func (r *Rows) Map(i int) (map[string]any, error) {
	if i < 0 || i >= len(r.Rows) {
		return nil, fmt.Errorf("res: row %d is out of range (%d rows)", i, len(r.Rows))
	}
	row := r.Rows[i]
	if len(row) != len(r.Columns) {
		return nil, fmt.Errorf("res: row %d has %d values but %d columns", i, len(row), len(r.Columns))
	}
	m := make(map[string]any, len(row))
	for j, c := range r.Columns {
		m[c.Name] = row[j]
	}
	return m, nil
}

// Column returns one column's values by name.
func (r *Rows) Column(name string) ([]any, error) {
	idx := -1
	for i, c := range r.Columns {
		if c.Name == name {
			idx = i
			break
		}
	}
	if idx < 0 {
		return nil, fmt.Errorf("res: no column %q in result set", name)
	}
	out := make([]any, 0, len(r.Rows))
	for _, row := range r.Rows {
		out = append(out, row[idx])
	}
	return out, nil
}

// ---------- s3 ----------

// S3Resource is a named blob store, scoped by a key prefix in the run's grants.
type S3Resource struct {
	c    *Client
	name string
}

// S3 names a blob-store resource. It does not connect or validate; the grant
// check happens on the first call, proxy-side.
func S3(c *Client, name string) *S3Resource { return &S3Resource{c: c, name: name} }

// ObjectMeta describes one stored object.
type ObjectMeta struct {
	Key       string `json:"key"`
	Size      int64  `json:"size"`
	MediaType string `json:"media_type,omitempty"`
}

// List enumerates objects under a prefix. Keys outside the run's granted
// prefix are filtered proxy-side and simply do not appear.
func (s *S3Resource) List(ctx context.Context, prefix string) ([]ObjectMeta, error) {
	var out struct {
		Objects []ObjectMeta `json:"objects"`
	}
	if err := s.c.Call(ctx, s.name, "list", map[string]any{"prefix": prefix}, &out); err != nil {
		return nil, err
	}
	return out.Objects, nil
}

// Get fetches an object's bytes.
func (s *S3Resource) Get(ctx context.Context, key string) ([]byte, error) {
	var out struct {
		Body      string `json:"body"` // base64
		MediaType string `json:"media_type"`
	}
	if err := s.c.Call(ctx, s.name, "get", map[string]any{"key": key}, &out); err != nil {
		return nil, err
	}
	b, err := base64.StdEncoding.DecodeString(out.Body)
	if err != nil {
		return nil, fmt.Errorf("res: object %s body is not valid base64: %w", key, err)
	}
	return b, nil
}

// Put stores an object.
func (s *S3Resource) Put(ctx context.Context, key string, body []byte, mediaType string) error {
	return s.c.Call(ctx, s.name, "put", map[string]any{
		"key":        key,
		"body":       base64.StdEncoding.EncodeToString(body),
		"media_type": mediaType,
	}, nil)
}

// ---------- http ----------

// HTTPResource is a named HTTP resource, scoped by a URL allowlist in the run's
// grants. Requests off the allowlist are refused proxy-side; there is no way to
// reach an arbitrary URL from an action, which is the point.
type HTTPResource struct {
	c    *Client
	name string
}

// HTTP names an HTTP resource. It does not connect or validate; the grant
// check happens on the first call, proxy-side.
func HTTP(c *Client, name string) *HTTPResource { return &HTTPResource{c: c, name: name} }

// Response is an HTTP reply relayed by the proxy.
type Response struct {
	Status  int               `json:"status"`
	Headers map[string]string `json:"headers,omitempty"`
	Body    string            `json:"body"` // base64
}

// Bytes decodes the response body.
func (r *Response) Bytes() ([]byte, error) {
	return base64.StdEncoding.DecodeString(r.Body)
}

// JSON decodes the response body as JSON into dst.
func (r *Response) JSON(dst any) error {
	b, err := r.Bytes()
	if err != nil {
		return err
	}
	return json.Unmarshal(b, dst)
}

// Request issues an HTTP request through the proxy. body may be nil.
func (h *HTTPResource) Request(ctx context.Context, method, url string, body []byte, headers map[string]string) (*Response, error) {
	args := map[string]any{"method": method, "url": url}
	if body != nil {
		args["body"] = base64.StdEncoding.EncodeToString(body)
	}
	if len(headers) > 0 {
		args["headers"] = headers
	}
	var out Response
	if err := h.c.Call(ctx, h.name, "request", args, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

// GetJSON is the common case: GET a URL and decode JSON. A non-2xx status is an
// error, because every caller of a JSON API wants that and forgetting the check
// is the standard way a nil field becomes a wrong number in a report.
func (h *HTTPResource) GetJSON(ctx context.Context, url string, dst any) error {
	resp, err := h.Request(ctx, "GET", url, nil, nil)
	if err != nil {
		return err
	}
	if resp.Status < 200 || resp.Status > 299 {
		return fmt.Errorf("res: GET %s returned status %d", url, resp.Status)
	}
	return resp.JSON(dst)
}

// ---------- blobs and tables ----------

// PutBlob stores bytes and returns a content-addressed File handle. Bodies
// never construct a handle themselves: the hash is the executor's to compute
// and trust (PROTOCOL.md, blob.put).
func (c *Client) PutBlob(ctx context.Context, body []byte, mediaType, filename string) (kernel.FileHandle, error) {
	var out kernel.FileHandle
	err := c.call(ctx, "blob.put", map[string]any{
		"token":      c.caps.Token,
		"media_type": mediaType,
		"filename":   filename,
		"body":       base64.StdEncoding.EncodeToString(body),
	}, &out)
	return out, err
}

// GetBlob fetches a File handle's bytes.
func (c *Client) GetBlob(ctx context.Context, h kernel.FileHandle) ([]byte, error) {
	var out struct {
		Body string `json:"body"`
	}
	if err := c.call(ctx, "blob.get", map[string]any{"token": c.caps.Token, "handle": h}, &out); err != nil {
		return nil, err
	}
	return base64.StdEncoding.DecodeString(out.Body)
}

// PutTable stores rows as a Table handle. Columns are declared, not inferred:
// inferring a column type from the first row is how a table of integers becomes
// a table of strings the moment row one happens to be null.
func (c *Client) PutTable(ctx context.Context, cols []kernel.Column, rows [][]any, format string) (kernel.TableHandle, error) {
	if format == "" {
		format = "jsonl"
	}
	var out kernel.TableHandle
	err := c.call(ctx, "table.put", map[string]any{
		"token":   c.caps.Token,
		"columns": cols,
		"rows":    rows,
		"format":  format,
	}, &out)
	return out, err
}

// OpenTable opens a cursor over a Table handle.
func (c *Client) OpenTable(ctx context.Context, h kernel.TableHandle) (*Cursor, error) {
	var out struct {
		Cursor  string          `json:"cursor"`
		Columns []kernel.Column `json:"columns"`
	}
	if err := c.call(ctx, "table.open", map[string]any{"token": c.caps.Token, "handle": h}, &out); err != nil {
		return nil, err
	}
	return &Cursor{c: c, id: out.Cursor, columns: out.Columns}, nil
}

// Cursor reads a table in chunks. See package table for iteration helpers.
type Cursor struct {
	c       *Client
	id      string
	columns []kernel.Column
}

// Columns returns the cursor's column metadata.
func (cu *Cursor) Columns() []kernel.Column { return cu.columns }

// Read returns up to max rows. eof reports that the table is exhausted; a chunk
// may be empty with eof false, so callers must check eof rather than len(rows).
func (cu *Cursor) Read(ctx context.Context, max int) (rows [][]any, eof bool, err error) {
	var out struct {
		Rows [][]any `json:"rows"`
		EOF  bool    `json:"eof"`
	}
	err = cu.c.call(ctx, "table.read", map[string]any{
		"token": cu.c.caps.Token, "cursor": cu.id, "max": max,
	}, &out)
	return out.Rows, out.EOF, err
}

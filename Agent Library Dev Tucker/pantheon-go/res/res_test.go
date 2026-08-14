package res_test

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// Direct tests for the proxy client — the SOLE EGRESS in this library, and so
// the package where a quiet defect costs the most.
//
// The happy paths are exercised end to end through ptnfake; what is tested here
// is the behaviour ptnfake cannot easily produce: a proxy that dies mid-call,
// one that answers out of order, one that returns garbage, and the accessors
// nothing else happens to touch.
//
// Named mutation table:
//
//	mutation                                      | reddens
//	----------------------------------------------|--------------------------------------
//	fail() stops waking in-flight callers          | TestCallersWakeWhenTheProxyDies
//	responses are matched positionally not by id   | TestResponsesAreMatchedByID
//	Denied classifies any error as denial          | TestDeniedOnlyMatchesRefusals
//	Dial accepts an empty socket path              | TestDialRefusesAnEmptySocket
//	Rows.Map reads positionally                    | TestRowsMapKeysByColumnName
//	GetJSON ignores the status code                | TestGetJSONRejectsNon2xx

// script drives a fake proxy from a table of canned responses, so a test can
// stage orderings and failures a real proxy would not reproduce on demand.
type script struct {
	ln   net.Listener
	path string
	dir  string
	// respond receives each request frame and returns raw response bytes plus
	// whether to hang up afterwards. Returning nil bytes sends nothing, which is
	// how a hang is staged; hangUp closes the CONNECTION, which is what a dead
	// proxy actually looks like to a client (closing only the listener leaves an
	// accepted connection open and the client legitimately waiting).
	respond func(id int64, method string, params json.RawMessage) (out []byte, hangUp bool)
}

func newScript(t *testing.T, respond func(int64, string, json.RawMessage) ([]byte, bool)) *script {
	t.Helper()
	// os.MkdirTemp, not t.TempDir: a Unix socket path is capped near 104 bytes
	// on darwin and t.TempDir embeds the test name, which overruns it.
	dir, err := os.MkdirTemp("", "ptnres")
	if err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(dir, "s.sock")
	ln, err := net.Listen("unix", path)
	if err != nil {
		t.Fatal(err)
	}
	s := &script{ln: ln, path: path, dir: dir, respond: respond}
	go s.serve()
	t.Cleanup(func() { ln.Close(); os.RemoveAll(dir) })
	return s
}

func (s *script) serve() {
	for {
		conn, err := s.ln.Accept()
		if err != nil {
			return
		}
		go func() {
			defer conn.Close()
			dec := json.NewDecoder(conn)
			for {
				var req struct {
					ID     int64           `json:"id"`
					Method string          `json:"method"`
					Params json.RawMessage `json:"params"`
				}
				if err := dec.Decode(&req); err != nil {
					return
				}
				out, hangUp := s.respond(req.ID, req.Method, req.Params)
				if out != nil {
					conn.Write(append(out, '\n'))
				}
				if hangUp {
					return
				}
			}
		}()
	}
}

func (s *script) client(t *testing.T) *res.Client {
	t.Helper()
	c, err := res.Dial(res.Capabilities{Socket: s.path, Token: "tok"})
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Close() })
	return c
}

func ok(id int64, result string) []byte {
	return []byte(fmt.Sprintf(`{"jsonrpc":"2.0","id":%d,"result":%s}`, id, result))
}

// ---------- transport ----------

func TestDialRefusesAnEmptySocket(t *testing.T) {
	_, err := res.Dial(res.Capabilities{})
	if err == nil {
		t.Fatal("dialling with no socket path must fail")
	}
	// A body with no proxy has no way to reach any resource, and saying so is
	// more useful than a connection refused on "".
	if !strings.Contains(err.Error(), "no proxy socket") {
		t.Errorf("error should explain what is missing: %v", err)
	}
}

func TestDialRefusesAMissingSocket(t *testing.T) {
	if _, err := res.Dial(res.Capabilities{Socket: t.TempDir() + "/absent.sock"}); err == nil {
		t.Fatal("dialling a socket that does not exist must fail")
	}
}

// A body whose proxy dies must report the real cause, not block until the task
// timeout and report a timeout instead.
func TestCallersWakeWhenTheProxyDies(t *testing.T) {
	s := newScript(t, func(int64, string, json.RawMessage) ([]byte, bool) {
		return nil, true // hang up instead of answering
	})
	c := s.client(t)

	done := make(chan error, 1)
	go func() {
		var out map[string]any
		done <- c.Call(context.Background(), "ledger", "query", map[string]any{}, &out)
	}()

	select {
	case err := <-done:
		if err == nil {
			t.Fatal("expected an error when the proxy vanished")
		}
	case <-time.After(3 * time.Second):
		t.Fatal("caller blocked after the proxy died instead of being woken")
	}
}

func TestCallRespectsContextCancellation(t *testing.T) {
	s := newScript(t, func(int64, string, json.RawMessage) ([]byte, bool) { return nil, false }) // never answers
	c := s.client(t)

	ctx, cancel := context.WithTimeout(context.Background(), 150*time.Millisecond)
	defer cancel()

	var out map[string]any
	err := c.Call(ctx, "ledger", "query", map[string]any{}, &out)
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("expected the deadline to be honoured, got %v", err)
	}
}

// Requests are multiplexed by id; responses may arrive in any order. Matching
// positionally would cross callers' answers, which is the worst possible bug
// here because both callers succeed with the wrong data.
func TestResponsesAreMatchedByID(t *testing.T) {
	var held []byte
	s := newScript(t, func(id int64, _ string, params json.RawMessage) ([]byte, bool) {
		var p struct {
			Args struct {
				SQL string `json:"sql"`
			} `json:"args"`
		}
		json.Unmarshal(params, &p)
		body := ok(id, fmt.Sprintf(`{"columns":[{"name":"echo","type":"string"}],"rows":[[%q]]}`, p.Args.SQL))
		if p.Args.SQL == "first" {
			held = body // answer this one LAST
			return nil, false
		}
		out := body
		if held != nil {
			// Deliberately reversed: the second request is answered first.
			out = append(append([]byte{}, body...), append([]byte("\n"), held...)...)
			held = nil
		}
		return out, false
	})
	c := s.client(t)
	pg := res.Postgres(c, "ledger")

	type result struct {
		want string
		got  string
		err  error
	}
	results := make(chan result, 2)
	go func() {
		rows, err := pg.Query(context.Background(), "first")
		r := result{want: "first", err: err}
		if err == nil {
			r.got, _ = rows.Rows[0][0].(string)
		}
		results <- r
	}()
	time.Sleep(50 * time.Millisecond) // ensure "first" is in flight
	go func() {
		rows, err := pg.Query(context.Background(), "second")
		r := result{want: "second", err: err}
		if err == nil {
			r.got, _ = rows.Rows[0][0].(string)
		}
		results <- r
	}()

	for i := 0; i < 2; i++ {
		select {
		case r := <-results:
			if r.err != nil {
				t.Fatalf("query %q failed: %v", r.want, r.err)
			}
			if r.got != r.want {
				t.Fatalf("query %q received %q — responses were crossed between callers", r.want, r.got)
			}
		case <-time.After(3 * time.Second):
			t.Fatal("timed out waiting for multiplexed responses")
		}
	}
}

func TestUnparseableFrameFailsTheClient(t *testing.T) {
	s := newScript(t, func(int64, string, json.RawMessage) ([]byte, bool) {
		return []byte(`{this is not json`), false
	})
	c := s.client(t)

	var out map[string]any
	if err := c.Call(context.Background(), "ledger", "query", map[string]any{}, &out); err == nil {
		t.Fatal("a malformed frame must fail the call, not be skipped")
	}
}

func TestDecodeFailureIsReported(t *testing.T) {
	s := newScript(t, func(id int64, _ string, _ json.RawMessage) ([]byte, bool) {
		return ok(id, `{"columns":"not-an-array"}`), false
	})
	c := s.client(t)

	if _, err := res.Postgres(c, "ledger").Query(context.Background(), "select 1"); err == nil {
		t.Fatal("a result that does not fit the expected shape must be an error")
	}
}

// ---------- error classification ----------

func TestDeniedOnlyMatchesRefusals(t *testing.T) {
	denial := &res.Error{Code: res.CodeDenied, Message: "nope", Method: "resource.call"}
	if !res.Denied(denial) {
		t.Error("a denial must be classified as one")
	}
	// A refused grant is an ANSWER; a broken connection is not. Callers that
	// retry need to tell them apart.
	for _, other := range []error{
		&res.Error{Code: res.CodeNotFound, Method: "resource.call"},
		&res.Error{Code: res.CodeUpstream, Method: "resource.call"},
		errors.New("connection reset"),
		nil,
	} {
		if res.Denied(other) {
			t.Errorf("%v must not be classified as a denial", other)
		}
	}
}

func TestErrorMessageNamesMethodAndCode(t *testing.T) {
	e := &res.Error{Code: res.CodeDenied, Message: "verb not granted", Method: "resource.call"}
	msg := e.Error()
	for _, want := range []string{"resource.call", "verb not granted", "1001"} {
		if !strings.Contains(msg, want) {
			t.Errorf("error message %q is missing %q", msg, want)
		}
	}
}

// ---------- result-set accessors ----------

func rowsFixture() res.Rows {
	return res.Rows{
		Columns: []kernel.Column{
			{Name: "id", Type: "string"},
			{Name: "amount", Type: "float"},
		},
		Rows: [][]any{{"a", 1.5}, {"b", 2.5}},
	}
}

func TestRowsMapKeysByColumnName(t *testing.T) {
	r := rowsFixture()
	m, err := r.Map(1)
	if err != nil {
		t.Fatal(err)
	}
	if m["id"] != "b" || m["amount"] != 2.5 {
		t.Errorf("row 1 mapped to %v", m)
	}
}

func TestRowsMapRejectsOutOfRangeAndRaggedRows(t *testing.T) {
	r := rowsFixture()
	if _, err := r.Map(9); err == nil {
		t.Error("an out-of-range row index must be an error")
	}
	if _, err := r.Map(-1); err == nil {
		t.Error("a negative row index must be an error")
	}

	ragged := res.Rows{Columns: r.Columns, Rows: [][]any{{"only-one"}}}
	if _, err := ragged.Map(0); err == nil {
		t.Error("a short row must be an error, not a silently partial map")
	}
}

func TestRowsColumnExtractsByName(t *testing.T) {
	r := rowsFixture()
	got, err := r.Column("amount")
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 2 || got[0] != 1.5 || got[1] != 2.5 {
		t.Errorf("Column returned %v", got)
	}
	if _, err := r.Column("nope"); err == nil {
		t.Error("an unknown column must be an error")
	}
}

// ---------- response helpers ----------

func TestResponseBytesAndJSON(t *testing.T) {
	body := map[string]any{"base": "USD"}
	raw, _ := json.Marshal(body)
	resp := res.Response{Status: 200, Body: base64.StdEncoding.EncodeToString(raw)}

	b, err := resp.Bytes()
	if err != nil {
		t.Fatal(err)
	}
	if string(b) != string(raw) {
		t.Errorf("Bytes returned %q", b)
	}

	var out map[string]any
	if err := resp.JSON(&out); err != nil {
		t.Fatal(err)
	}
	if out["base"] != "USD" {
		t.Errorf("JSON decoded to %v", out)
	}

	bad := res.Response{Body: "not-base64!!"}
	if _, err := bad.Bytes(); err == nil {
		t.Error("a non-base64 body must be an error")
	}
}

// Forgetting the status check is the standard way a nil field becomes a wrong
// number in a report.
func TestGetJSONRejectsNon2xx(t *testing.T) {
	s := newScript(t, func(id int64, _ string, _ json.RawMessage) ([]byte, bool) {
		return ok(id, `{"status":503,"body":""}`), false
	})
	c := s.client(t)

	var out map[string]any
	err := res.HTTP(c, "fx").GetJSON(context.Background(), "https://fx.example/rates", &out)
	if err == nil {
		t.Fatal("a 503 must be an error")
	}
	if !strings.Contains(err.Error(), "503") {
		t.Errorf("the error should name the status: %v", err)
	}
}

// Capabilities carry a token. It must not be rendered by accident into a log
// line, so the type deliberately has no String method.
func TestCapabilitiesHasNoStringerThatCouldLeakTheToken(t *testing.T) {
	var c any = res.Capabilities{Socket: "/tmp/x.sock", Token: "super-secret"}
	if s, ok := c.(fmt.Stringer); ok {
		t.Fatalf("Capabilities implements Stringer (%q); a token must not be one %%v away from a log line", s.String())
	}
}

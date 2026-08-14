package ptnfake_test

import (
	"context"
	"strings"
	"sync"
	"testing"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
	"github.com/obsidura/pantheon-go/res"
)

func newProxy(t *testing.T) *ptnfake.Proxy {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatalf("starting fake proxy: %v", err)
	}
	t.Cleanup(func() { p.Close() })
	return p
}

func dial(t *testing.T, p *ptnfake.Proxy) *res.Client {
	t.Helper()
	c, err := res.Dial(p.Capabilities())
	if err != nil {
		t.Fatalf("dialling proxy: %v", err)
	}
	t.Cleanup(func() { c.Close() })
	return c
}

var patientCols = []kernel.Column{
	{Name: "id", Type: "string"},
	{Name: "ward", Type: "string"},
}

var patientRows = [][]any{
	{"p1", "cardiology"},
	{"p2", "oncology"},
	{"p3", "cardiology"},
	{"p4", "neurology"},
}

// The permission beat (acceptance test 4) as an ordinary unit test: same query,
// two users, different rows, and an audit log that shows the scope decision.
// The action issues an identical query in both cases and never sees the filter.
func TestRowFilterScopesResultsPerUser(t *testing.T) {
	const q = "select id, ward from patients"

	forUser := func(t *testing.T, allowedWard string) (*res.Rows, []string) {
		p := newProxy(t)
		p.AddPostgresRows("records", q, patientCols, patientRows)
		p.Grant("records", ptnfake.Grant{
			Verbs: []string{"query"},
			RowFilter: func(row map[string]any) bool {
				return row["ward"] == allowedWard
			},
		})
		rows, err := res.Postgres(dial(t, p), "records").Query(context.Background(), q)
		if err != nil {
			t.Fatalf("query: %v", err)
		}
		return rows, p.AuditLines()
	}

	cardio, cardioAudit := forUser(t, "cardiology")
	onco, oncoAudit := forUser(t, "oncology")

	if len(cardio.Rows) != 2 {
		t.Errorf("cardiology user should see 2 patients, saw %d", len(cardio.Rows))
	}
	if len(onco.Rows) != 1 {
		t.Errorf("oncology user should see 1 patient, saw %d", len(onco.Rows))
	}

	// The governance beat is the audit line, not the row count.
	if len(cardioAudit) != 1 || !strings.Contains(cardioAudit[0], "[scope: 2/4 rows]") {
		t.Errorf("audit should show the scope decision, got %q", cardioAudit)
	}
	if len(oncoAudit) != 1 || !strings.Contains(oncoAudit[0], "[scope: 1/4 rows]") {
		t.Errorf("audit should show the scope decision, got %q", oncoAudit)
	}
}

func TestUngrantedResourceIsDenied(t *testing.T) {
	p := newProxy(t)
	p.AddPostgresRows("records", "select 1", patientCols, nil)
	// No Grant call at all.

	_, err := res.Postgres(dial(t, p), "records").Query(context.Background(), "select 1")
	if err == nil {
		t.Fatal("expected a denial for an ungranted resource")
	}
	if !res.Denied(err) {
		t.Errorf("expected res.Denied to classify it, got %v", err)
	}
	audit := p.Audit()
	if len(audit) != 1 || audit[0].Allowed {
		t.Fatalf("the denial must be recorded in the audit log, got %+v", audit)
	}
}

func TestUngrantedVerbIsDenied(t *testing.T) {
	p := newProxy(t)
	p.AddS3Object("scans", "a/1.png", []byte("x"))
	p.Grant("scans", ptnfake.Grant{Verbs: []string{"get"}}) // no "put"

	err := res.S3(dial(t, p), "scans").Put(context.Background(), "a/2.png", []byte("y"), "image/png")
	if !res.Denied(err) {
		t.Fatalf("expected a denial for an ungranted verb, got %v", err)
	}
}

func TestKeyPrefixScopesS3(t *testing.T) {
	p := newProxy(t)
	p.AddS3Object("scans", "ward/cardiology/1.png", []byte("a"))
	p.AddS3Object("scans", "ward/oncology/2.png", []byte("b"))
	p.Grant("scans", ptnfake.Grant{Verbs: []string{"get", "list"}, KeyPrefix: "ward/cardiology/"})

	s3 := res.S3(dial(t, p), "scans")

	objs, err := s3.List(context.Background(), "ward/")
	if err != nil {
		t.Fatal(err)
	}
	if len(objs) != 1 || objs[0].Key != "ward/cardiology/1.png" {
		t.Errorf("list should be filtered to the granted prefix, got %+v", objs)
	}

	if _, err := s3.Get(context.Background(), "ward/oncology/2.png"); !res.Denied(err) {
		t.Errorf("a key outside the granted prefix must be denied, got %v", err)
	}
}

// An empty allowlist must permit nothing. An empty allowlist that permits
// everything is the classic fail-open bug the guard SPEC is explicit about:
// only membership in a known-good set fails closed.
func TestEmptyURLAllowlistDeniesEverything(t *testing.T) {
	p := newProxy(t)
	p.AddJSONEndpoint("fx", "https://fx.example/rates", map[string]any{"USD": 1})
	p.Grant("fx", ptnfake.Grant{Verbs: []string{"request"}}) // URLAllow deliberately empty

	var out map[string]any
	err := res.HTTP(dial(t, p), "fx").GetJSON(context.Background(), "https://fx.example/rates", &out)
	if !res.Denied(err) {
		t.Fatalf("an empty allowlist must deny, got %v", err)
	}
}

func TestURLAllowlistPermitsListedPrefix(t *testing.T) {
	p := newProxy(t)
	p.AddJSONEndpoint("fx", "https://fx.example/rates", map[string]any{"USD": 1.0})
	p.Grant("fx", ptnfake.Grant{Verbs: []string{"request"}, URLAllow: []string{"https://fx.example/"}})

	var out map[string]float64
	if err := res.HTTP(dial(t, p), "fx").GetJSON(context.Background(), "https://fx.example/rates", &out); err != nil {
		t.Fatal(err)
	}
	if out["USD"] != 1.0 {
		t.Errorf("got %+v", out)
	}
}

// Q3 is open: the real proxy may or may not serve concurrent requests. The
// client must be correct either way, so this asserts correctness under overlap
// rather than asserting a speedup that is not ours to promise.
func TestClientMultiplexesConcurrentCalls(t *testing.T) {
	p := newProxy(t)
	p.AddPostgresFunc("ledger", func(sql string, params []any) (*res.Rows, error) {
		return &res.Rows{
			Columns: []kernel.Column{{Name: "echo", Type: "string"}},
			Rows:    [][]any{{params[0]}},
		}, nil
	})
	p.Grant("ledger", ptnfake.Grant{Verbs: []string{"query"}})

	c := dial(t, p)
	pg := res.Postgres(c, "ledger")

	const n = 64
	var wg sync.WaitGroup
	got := make([]string, n)
	errs := make([]error, n)
	for i := 0; i < n; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			want := string(rune('a' + i%26))
			rows, err := pg.Query(context.Background(), "select $1", want)
			if err != nil {
				errs[i] = err
				return
			}
			got[i], _ = rows.Rows[0][0].(string)
		}(i)
	}
	wg.Wait()

	for i := 0; i < n; i++ {
		if errs[i] != nil {
			t.Fatalf("call %d failed: %v", i, errs[i])
		}
		want := string(rune('a' + i%26))
		if got[i] != want {
			t.Fatalf("call %d got response %q, wanted %q -- responses were crossed between callers", i, got[i], want)
		}
	}
}

func TestRowsDecodeIgnoresExtraColumns(t *testing.T) {
	// One action written against a vertical type must run over a tenant table
	// that has extra columns. That tolerance is the compounding argument.
	rows := res.Rows{
		Columns: []kernel.Column{
			{Name: "id", Type: "string"},
			{Name: "acme_internal_code", Type: "string"},
			{Name: "total", Type: "float"},
		},
		Rows: [][]any{{"i1", "XYZ", 42.5}},
	}
	var out []struct {
		ID    string  `json:"id"`
		Total float64 `json:"total"`
	}
	if err := rows.Decode(&out); err != nil {
		t.Fatal(err)
	}
	if len(out) != 1 || out[0].ID != "i1" || out[0].Total != 42.5 {
		t.Errorf("got %+v", out)
	}
}

func TestRowsDecodeRejectsRaggedRows(t *testing.T) {
	rows := res.Rows{
		Columns: []kernel.Column{{Name: "a"}, {Name: "b"}},
		Rows:    [][]any{{1}},
	}
	var out []map[string]any
	if err := rows.Decode(&out); err == nil {
		t.Fatal("a row with fewer values than columns must be an error, not a silently short record")
	}
}

func TestBlobPutIsContentAddressed(t *testing.T) {
	p := newProxy(t)
	c := dial(t, p)

	h1, err := c.PutBlob(context.Background(), []byte("report"), "text/html", "r.html")
	if err != nil {
		t.Fatal(err)
	}
	h2, err := c.PutBlob(context.Background(), []byte("report"), "text/html", "other.html")
	if err != nil {
		t.Fatal(err)
	}
	if h1.Blob != h2.Blob {
		t.Errorf("identical bytes must produce identical handles: %s vs %s", h1.Blob, h2.Blob)
	}
	if !strings.HasPrefix(h1.Blob, "sha256:") {
		t.Errorf("handle is not content-addressed: %s", h1.Blob)
	}
	got, err := c.GetBlob(context.Background(), h1)
	if err != nil {
		t.Fatal(err)
	}
	if string(got) != "report" {
		t.Errorf("round trip gave %q", got)
	}
}

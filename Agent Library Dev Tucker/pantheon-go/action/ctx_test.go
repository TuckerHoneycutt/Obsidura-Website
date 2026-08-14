package action_test

import (
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
	"github.com/obsidura/pantheon-go/res"
)

// The Ctx surface a body actually touches: writing objects, calling HTTP,
// storing and fetching files, and timing itself.
//
// Named mutation table:
//
//	mutation                                        | reddens
//	------------------------------------------------|------------------------------------
//	S3Handle.Put skips its declaration check         | TestPutRequiresADeclaredVerb
//	HTTPHandle.Request skips its declaration check   | TestRequestRequiresADeclaredVerb
//	PutFile stops content-addressing                 | TestPutFileIsContentAddressed
//	S3Handle.Get stops recording taint               | TestObjectReadsRecordTaint
//	HTTPHandle.Request stops recording taint         | TestHTTPCallsRecordTaint

type ctxIn struct {
	Key string `json:"key"`
}

type ctxOut struct {
	Note string `json:"note"`
}

func ctxSpec(name string, uses ...action.ResourceUse) action.Spec {
	return action.Spec{
		Name: name, Version: 1,
		Input:   kernel.Ref("test.CtxIn", 1),
		Output:  kernel.Ref("test.CtxOut", 1),
		Uses:    uses,
		Policy:  action.Policy{Timeout: 5 * time.Second},
		Summary: "Exercises the Ctx surface.",
	}
}

func withProxy(t *testing.T) *ptnfake.Proxy {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Close() })
	return p
}

func TestPutStoresAnObjectThroughTheProxy(t *testing.T) {
	p := withProxy(t)
	p.Grant("archive", ptnfake.Grant{Verbs: []string{"put", "get"}, KeyPrefix: "out/"})

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.put", action.ResourceUse{
		Name: "archive", Verbs: []string{"put", "get"},
	}), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		if err := c.S3("archive").Put(in.Key, []byte("<html>report</html>"), "text/html"); err != nil {
			return ctxOut{}, err
		}
		back, err := c.S3("archive").Get(in.Key)
		return ctxOut{Note: string(back)}, err
	})

	var got ctxOut
	if err := p.Invoke(r, "test.put", ctxIn{Key: "out/report.html"}).Record(&got); err != nil {
		t.Fatal(err)
	}
	if got.Note != "<html>report</html>" {
		t.Errorf("round trip returned %q", got.Note)
	}

	var sawPut bool
	for _, a := range p.Audit() {
		if a.Verb == "put" && a.Allowed {
			sawPut = true
		}
	}
	if !sawPut {
		t.Errorf("the write is not in the audit log: %v", p.AuditLines())
	}
}

func TestPutRequiresADeclaredVerb(t *testing.T) {
	p := withProxy(t)
	p.Grant("archive", ptnfake.Grant{Verbs: []string{"put"}, KeyPrefix: "out/"})

	r := action.NewRegistry()
	// Declares only "get", then tries to write.
	action.Register(r, ctxSpec("test.sneakyput", action.ResourceUse{
		Name: "archive", Verbs: []string{"get"},
	}), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		return ctxOut{}, c.S3("archive").Put("out/x", []byte("x"), "text/plain")
	})

	res := p.Invoke(r, "test.sneakyput", ctxIn{})
	if res.Err == nil {
		t.Fatal("writing with an undeclared verb must be refused before it reaches the socket")
	}
	if !strings.Contains(res.Err.Error(), "Spec.Uses") {
		t.Errorf("the error should point at the declaration: %v", res.Err)
	}
	if len(p.Audit()) != 0 {
		t.Errorf("the call must not reach the proxy at all, but the audit log has %d entries", len(p.Audit()))
	}
}

func TestRequestIssuesAnHTTPCall(t *testing.T) {
	p := withProxy(t)
	p.Grant("api", ptnfake.Grant{Verbs: []string{"request"}, URLAllow: []string{"https://api.example/"}})
	p.AddHTTPFunc("api", func(method, url string, body []byte, h map[string]string) (res.Response, error) {
		if method != "POST" || h["X-Trace"] != "abc" {
			return res.Response{Status: 400}, nil
		}
		return res.Response{Status: 201, Body: ""}, nil
	})

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.request", action.ResourceUse{
		Name: "api", Verbs: []string{"request"},
	}), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		resp, err := c.HTTP("api").Request("POST", "https://api.example/v1/x",
			[]byte(`{"a":1}`), map[string]string{"X-Trace": "abc"})
		if err != nil {
			return ctxOut{}, err
		}
		if resp.Status != 201 {
			return ctxOut{}, nil
		}
		return ctxOut{Note: "created"}, nil
	})

	var got ctxOut
	if err := p.Invoke(r, "test.request", ctxIn{}).Record(&got); err != nil {
		t.Fatal(err)
	}
	if got.Note != "created" {
		t.Errorf("method, body or headers did not survive the proxy hop: %+v", got)
	}
}

func TestRequestRequiresADeclaredVerb(t *testing.T) {
	p := withProxy(t)
	p.Grant("api", ptnfake.Grant{Verbs: []string{"request"}, URLAllow: []string{"https://api.example/"}})

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.undeclaredhttp"), // no Uses at all
		func(c *action.Ctx, in ctxIn) (ctxOut, error) {
			_, err := c.HTTP("api").Request("GET", "https://api.example/x", nil, nil)
			return ctxOut{}, err
		})

	res := p.Invoke(r, "test.undeclaredhttp", ctxIn{})
	if res.Err == nil {
		t.Fatal("an undeclared HTTP resource must be refused")
	}
}

// A body never computes a hash the executor would have to trust, so identical
// bytes must come back as one handle regardless of filename.
func TestPutFileIsContentAddressed(t *testing.T) {
	p := withProxy(t)

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.files"), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		h1, err := c.PutFile([]byte("same bytes"), "text/plain", "a.txt")
		if err != nil {
			return ctxOut{}, err
		}
		h2, err := c.PutFile([]byte("same bytes"), "text/plain", "b.txt")
		if err != nil {
			return ctxOut{}, err
		}
		if h1.Blob != h2.Blob {
			return ctxOut{Note: "handles differ: " + h1.Blob + " vs " + h2.Blob}, nil
		}
		back, err := c.GetFile(h1)
		if err != nil {
			return ctxOut{}, err
		}
		return ctxOut{Note: string(back)}, nil
	})

	var got ctxOut
	if err := p.Invoke(r, "test.files", ctxIn{}).Record(&got); err != nil {
		t.Fatal(err)
	}
	if got.Note != "same bytes" {
		t.Errorf("PutFile/GetFile round trip gave %q", got.Note)
	}
}

// Blob storage is the run's own scratch space, not a resource with a grant, so
// it needs no declaration.
func TestFileHandlesNeedNoDeclaration(t *testing.T) {
	p := withProxy(t)

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.nodecl"), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		h, err := c.PutFile([]byte("x"), "text/plain", "x.txt")
		if err != nil {
			return ctxOut{}, err
		}
		return ctxOut{Note: h.Blob}, nil
	})

	var got ctxOut
	if err := p.Invoke(r, "test.nodecl", ctxIn{}).Record(&got); err != nil {
		t.Fatalf("storing a file must not require a resource declaration: %v", err)
	}
	if !strings.HasPrefix(got.Note, "sha256:") {
		t.Errorf("handle is not content-addressed: %q", got.Note)
	}
}

func TestObjectReadsRecordTaint(t *testing.T) {
	p := withProxy(t)
	p.AddS3Object("docs", "d/1.txt", []byte("hello"))
	p.Grant("docs", ptnfake.Grant{Verbs: []string{"get"}, KeyPrefix: "d/"})

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.taintget", action.ResourceUse{
		Name: "docs", Verbs: []string{"get"},
	}), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		_, err := c.S3("docs").Get("d/1.txt")
		return ctxOut{}, err
	})

	out := p.Invoke(r, "test.taintget", ctxIn{})
	if out.Err != nil {
		t.Fatal(out.Err)
	}
	if len(out.Envelope.Taint) != 1 || out.Envelope.Taint[0].Source != "resource:docs" {
		t.Errorf("reading an object must record taint, got %+v", out.Envelope.Taint)
	}
}

func TestHTTPCallsRecordTaint(t *testing.T) {
	p := withProxy(t)
	p.Grant("api", ptnfake.Grant{Verbs: []string{"request"}, URLAllow: []string{"https://api.example/"}})
	p.AddJSONEndpoint("api", "https://api.example/v1/rates", map[string]any{"USD": 1})

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.tainthttp", action.ResourceUse{
		Name: "api", Verbs: []string{"request"},
	}), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		var body map[string]any
		return ctxOut{}, c.HTTP("api").GetJSON("https://api.example/v1/rates", &body)
	})

	out := p.Invoke(r, "test.tainthttp", ctxIn{})
	if out.Err != nil {
		t.Fatal(out.Err)
	}
	if len(out.Envelope.Taint) != 1 || out.Envelope.Taint[0].Source != "resource:api" {
		t.Errorf("an HTTP call must record taint, got %+v", out.Envelope.Taint)
	}
}

func TestElapsedMeasuresBodyTime(t *testing.T) {
	p := withProxy(t)

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.elapsed"), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		time.Sleep(10 * time.Millisecond)
		if c.Elapsed() < 5*time.Millisecond {
			return ctxOut{Note: "too small: " + c.Elapsed().String()}, nil
		}
		return ctxOut{Note: "ok"}, nil
	})

	var got ctxOut
	if err := p.Invoke(r, "test.elapsed", ctxIn{}).Record(&got); err != nil {
		t.Fatal(err)
	}
	if got.Note != "ok" {
		t.Errorf("Elapsed reported %s", got.Note)
	}
}

func TestLogAndEmitReachTheSink(t *testing.T) {
	p := withProxy(t)

	r := action.NewRegistry()
	action.Register(r, ctxSpec("test.streams"), func(c *action.Ctx, in ctxIn) (ctxOut, error) {
		c.Logf("processed %d rows", 7)
		c.Log("warn", "something looked odd", map[string]any{"count": 1})
		c.Emit("test.progress", map[string]any{"pct": 50})
		return ctxOut{Note: "done"}, nil
	})

	out := p.Invoke(r, "test.streams", ctxIn{})
	if out.Err != nil {
		t.Fatal(out.Err)
	}
	if len(out.Logs) != 2 {
		t.Fatalf("expected 2 log lines, got %d", len(out.Logs))
	}
	if out.Logs[0].Message != "processed 7 rows" {
		t.Errorf("Logf did not format: %q", out.Logs[0].Message)
	}
	if out.Logs[1].Level != "warn" || out.Logs[1].Fields["count"] != 1 {
		t.Errorf("structured fields were lost: %+v", out.Logs[1])
	}
	if len(out.Events) != 1 || out.Events[0].Type != "test.progress" {
		t.Errorf("events did not reach the run log: %+v", out.Events)
	}
}

package table_test

import (
	"context"
	"strings"
	"testing"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
	"github.com/obsidura/pantheon-go/res"
	"github.com/obsidura/pantheon-go/table"
)

// Named mutation table for table iteration.
//
//	mutation                                   | reddens
//	-------------------------------------------|---------------------------------------------
//	Each stops on len(rows)==0 instead of eof   | TestEachStopsOnEOFNotOnAnEmptyChunk
//	Each ignores fn's error                     | TestEachStopsWhenTheCallbackFails
//	Row.Float errors on a null                  | TestFloatTreatsNullAsAbsentNotAnError
//	Row accessors index positionally            | TestAccessorsAreByNameNotPosition
//	Builder drops its row cap                    | TestBuilderRefusesToBufferUnbounded
//	Builder infers column types                  | (design; see NewBuilder's doc comment)

func proxy(t *testing.T) *ptnfake.Proxy {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Close() })
	return p
}

func cursor(t *testing.T, p *ptnfake.Proxy, cols []kernel.Column, rows [][]any) *res.Cursor {
	t.Helper()
	h := p.AddTable(cols, rows)
	c, err := res.Dial(p.Capabilities())
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { c.Close() })
	cur, err := c.OpenTable(context.Background(), h)
	if err != nil {
		t.Fatal(err)
	}
	return cur
}

var cols = []kernel.Column{
	{Name: "id", Type: "string"},
	{Name: "value", Type: "float"},
	{Name: "at", Type: "timestamp"},
}

// The reason Each checks eof rather than len(rows): a chunk may legitimately be
// empty while more rows remain, and stopping on an empty chunk silently
// truncates the table.
func TestEachStopsOnEOFNotOnAnEmptyChunk(t *testing.T) {
	p := proxy(t)
	rows := make([][]any, 0, 5000)
	for i := 0; i < 5000; i++ {
		rows = append(rows, []any{"r", float64(i), ""})
	}
	cur := cursor(t, p, cols, rows)

	var seen int
	// A chunk size that divides the row count exactly is the case where a
	// len(rows)==0 stop condition and an eof stop condition differ.
	if err := table.Each(context.Background(), cur, 1000, func(r table.Row) error {
		seen++
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if seen != 5000 {
		t.Errorf("iterated %d of 5000 rows", seen)
	}
}

func TestEachStopsWhenTheCallbackFails(t *testing.T) {
	p := proxy(t)
	rows := make([][]any, 0, 100)
	for i := 0; i < 100; i++ {
		rows = append(rows, []any{"r", float64(i), ""})
	}
	cur := cursor(t, p, cols, rows)

	var seen int
	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		seen++
		if seen == 5 {
			return errStop
		}
		return nil
	})
	if err != errStop {
		t.Fatalf("Each returned %v, want the callback's error", err)
	}
	if seen != 5 {
		t.Errorf("iteration continued past the failure: %d rows", seen)
	}
}

var errStop = &stopErr{}

type stopErr struct{}

func (*stopErr) Error() string { return "stop" }

func TestFoldAccumulates(t *testing.T) {
	p := proxy(t)
	rows := [][]any{{"a", 1.0, ""}, {"b", 2.0, ""}, {"c", 3.0, ""}}
	cur := cursor(t, p, cols, rows)

	sum, err := table.Fold(context.Background(), cur, 2, 0.0, func(acc float64, r table.Row) (float64, error) {
		v, ok, err := r.Float("value")
		if err != nil || !ok {
			return acc, err
		}
		return acc + v, nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if sum != 6 {
		t.Errorf("folded to %v, want 6", sum)
	}
}

// Nulls are ordinary in real telemetry and ledger data. Forcing every caller
// into error handling for the normal case produces code that ignores errors.
func TestFloatTreatsNullAsAbsentNotAnError(t *testing.T) {
	p := proxy(t)
	cur := cursor(t, p, cols, [][]any{{"a", nil, ""}})

	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		v, ok, err := r.Float("value")
		if err != nil {
			t.Errorf("a null must not be an error, got %v", err)
		}
		if ok {
			t.Errorf("a null must report ok=false, got value %v", v)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestFloatRejectsGenuineGarbage(t *testing.T) {
	p := proxy(t)
	cur := cursor(t, p, cols, [][]any{{"a", "not-a-number", ""}})

	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		_, _, err := r.Float("value")
		return err
	})
	if err == nil {
		t.Fatal("a non-numeric string must be an error, not a silent zero")
	}
	if !strings.Contains(err.Error(), "value") {
		t.Errorf("error should name the column: %v", err)
	}
}

// A tenant that adds a column shifts every position. Reading by name is what
// keeps one action working across all of them.
func TestAccessorsAreByNameNotPosition(t *testing.T) {
	p := proxy(t)
	shifted := []kernel.Column{
		{Name: "tenant_extra", Type: "string"},
		{Name: "id", Type: "string"},
		{Name: "value", Type: "float"},
	}
	cur := cursor(t, p, shifted, [][]any{{"XX", "row-1", 42.0}})

	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		id, err := r.String("id")
		if err != nil {
			return err
		}
		if id != "row-1" {
			t.Errorf("id read as %q; columns were read positionally", id)
		}
		v, ok, err := r.Float("value")
		if err != nil {
			return err
		}
		if !ok || v != 42 {
			t.Errorf("value read as %v (ok=%v)", v, ok)
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
}

func TestUnknownColumnIsNamedInTheError(t *testing.T) {
	p := proxy(t)
	cur := cursor(t, p, cols, [][]any{{"a", 1.0, ""}})
	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		_, err := r.String("altitude_m")
		return err
	})
	if err == nil || !strings.Contains(err.Error(), "altitude_m") {
		t.Errorf("error should name the missing column, got %v", err)
	}
}

func TestTimeParsesRFC3339(t *testing.T) {
	p := proxy(t)
	cur := cursor(t, p, cols, [][]any{{"a", 1.0, "2026-06-13T19:45:00Z"}, {"b", 2.0, ""}})

	var parsed, absent int
	err := table.Each(context.Background(), cur, 10, func(r table.Row) error {
		ts, ok, err := r.Time("at")
		if err != nil {
			return err
		}
		if ok {
			parsed++
			if ts.Year() != 2026 {
				t.Errorf("parsed year %d", ts.Year())
			}
		} else {
			absent++
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if parsed != 1 || absent != 1 {
		t.Errorf("parsed=%d absent=%d", parsed, absent)
	}
}

func TestBuilderRejectsWrongWidthRows(t *testing.T) {
	b := table.NewBuilder(table.Col("a", "string"), table.Col("b", "int"))
	if err := b.Append("only-one"); err == nil {
		t.Fatal("appending 1 value to a 2-column table must be an error")
	}
	if err := b.Append("a", 1); err != nil {
		t.Fatal(err)
	}
	if b.Len() != 1 {
		t.Errorf("len=%d", b.Len())
	}
}

// The cap is how "this action should be streaming" announces itself, rather
// than being discovered as an out-of-memory kill in production.
func TestBuilderRefusesToBufferUnbounded(t *testing.T) {
	if testing.Short() {
		t.Skip("skipped in -short")
	}
	b := table.NewBuilder(table.Col("n", "int"))
	var err error
	for i := 0; i <= table.MaxBuilderRows; i++ {
		if err = b.Append(i); err != nil {
			break
		}
	}
	if err == nil {
		t.Fatalf("builder accepted more than %d rows without complaint", table.MaxBuilderRows)
	}
	if !strings.Contains(err.Error(), "stream") {
		t.Errorf("the error should say what to do instead: %v", err)
	}
}

package finance_test

import (
	"fmt"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/obsidura/pantheon-go/actions/finance"
	"github.com/obsidura/pantheon-go/kernel"
)

// kernelColumn is a local alias so table fixtures in tests read less noisily.
type kernelColumn = kernel.Column

// ledgerCols is the column set the ledger fixture query returns. Kept beside
// the tests that override the fixture, so an override cannot silently disagree
// with the shape fetch_ledger expects.
func ledgerCols() []kernelColumn {
	return []kernelColumn{
		{Name: "entry_id", Type: "string"},
		{Name: "posted_at", Type: "timestamp"},
		{Name: "account", Type: "string"},
		{Name: "description", Type: "string"},
		{Name: "amount", Type: "string"},
		{Name: "currency", Type: "string"},
		{Name: "receipt_key", Type: "string"},
	}
}

func kernelRef(name string, v int) kernel.TypeRef { return kernel.Ref(name, v) }

// toInt64 reads a table cell that crossed JSON. Every number arrives as
// float64; minor units stay exact well past 2^53, so this is a conversion, not
// a rounding.
func toInt64(t testingT, v any) int64 {
	t.Helper()
	switch n := v.(type) {
	case int64:
		return n
	case int:
		return int64(n)
	case float64:
		return int64(n)
	default:
		t.Fatalf("cell %v (%T) is not numeric", v, v)
		return 0
	}
}

type testingT interface {
	Helper()
	Fatalf(string, ...any)
}

func mustSeconds(n int) time.Duration { return time.Duration(n) * time.Second }

// parseMinor reads a two-decimal string back into minor units, so a test can
// check the report's own arithmetic without importing the production parser and
// thereby testing it against itself.
func parseMinor(s string) (int64, error) {
	s = strings.TrimSpace(s)
	neg := strings.HasPrefix(s, "-")
	s = strings.TrimPrefix(s, "-")
	whole, frac, ok := strings.Cut(s, ".")
	if !ok {
		frac = "00"
	}
	for len(frac) < 2 {
		frac += "0"
	}
	if len(frac) > 2 {
		return 0, fmt.Errorf("more than two decimal places in %q", s)
	}
	w, err := strconv.ParseInt(whole, 10, 64)
	if err != nil {
		return 0, err
	}
	f, err := strconv.ParseInt(frac, 10, 64)
	if err != nil {
		return 0, err
	}
	out := w*100 + f
	if neg {
		out = -out
	}
	return out, nil
}

// ledgerQueryFields lists LedgerQuery's field names via reflection.
//
// Reflection over the type, not marshalling of a value: an omitempty field is
// absent from a marshalled zero value, so a marshal-based check would pass no
// matter what fields existed.
func ledgerQueryFields(t *testing.T) string {
	t.Helper()
	rt := reflect.TypeOf(finance.LedgerQuery{})
	var names []string
	for i := 0; i < rt.NumField(); i++ {
		f := rt.Field(i)
		name := f.Name
		if tag := f.Tag.Get("json"); tag != "" {
			if n, _, _ := strings.Cut(tag, ","); n != "" {
				name = n
			}
		}
		names = append(names, strings.ToLower(name))
	}
	if len(names) == 0 {
		t.Fatal("LedgerQuery has no fields; the caller's assertion would be vacuous")
	}
	return strings.Join(names, ",")
}

// Package table iterates Table handles without materialising them.
//
// Spec §6: large data always travels by handle, never inline. An action that
// reads tens of thousands of telemetry rows into a slice to pass them onward
// has defeated the handle system while appearing to work -- it will appear to
// work right up until the row count grows. Everything here is chunked.
package table

import (
	"context"
	"fmt"
	"strconv"
	"time"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/res"
)

// DefaultChunk is how many rows a read requests at a time. Large enough that
// per-call overhead is irrelevant, small enough that one chunk is not itself
// the memory problem.
const DefaultChunk = 2000

// Row is one row with its column metadata attached, so accessors can be by name
// rather than by a positional index that silently shifts when a column is added
// upstream.
type Row struct {
	cols []kernel.Column
	vals []any
}

// Len reports the number of values.
func (r Row) Len() int { return len(r.vals) }

// Raw returns a value by column name.
func (r Row) Raw(name string) (any, error) {
	for i, c := range r.cols {
		if c.Name == name {
			if i >= len(r.vals) {
				return nil, fmt.Errorf("table: row is short: no value for column %q", name)
			}
			return r.vals[i], nil
		}
	}
	return nil, fmt.Errorf("table: no column %q", name)
}

// String returns a value as a string.
func (r Row) String(name string) (string, error) {
	v, err := r.Raw(name)
	if err != nil {
		return "", err
	}
	switch t := v.(type) {
	case nil:
		return "", nil
	case string:
		return t, nil
	default:
		return fmt.Sprint(t), nil
	}
}

// Float returns a value as a float64. JSON decoding gives float64 for every
// number, and CSV gives strings, so both are accepted.
//
// A null is 0 with ok=false rather than an error: nulls are ordinary in real
// telemetry and ledger data, and forcing every caller into error handling for
// the normal case produces code that ignores errors.
func (r Row) Float(name string) (val float64, ok bool, err error) {
	v, err := r.Raw(name)
	if err != nil {
		return 0, false, err
	}
	switch t := v.(type) {
	case nil:
		return 0, false, nil
	case float64:
		return t, true, nil
	case float32:
		return float64(t), true, nil
	case int:
		return float64(t), true, nil
	case int64:
		return float64(t), true, nil
	case string:
		if t == "" {
			return 0, false, nil
		}
		f, perr := strconv.ParseFloat(t, 64)
		if perr != nil {
			return 0, false, fmt.Errorf("table: column %q value %q is not a number", name, t)
		}
		return f, true, nil
	default:
		return 0, false, fmt.Errorf("table: column %q has non-numeric type %T", name, v)
	}
}

// Int returns a value as an int64.
func (r Row) Int(name string) (int64, bool, error) {
	f, ok, err := r.Float(name)
	if err != nil || !ok {
		return 0, ok, err
	}
	return int64(f), true, nil
}

// Time parses a value as RFC 3339.
func (r Row) Time(name string) (time.Time, bool, error) {
	s, err := r.String(name)
	if err != nil {
		return time.Time{}, false, err
	}
	if s == "" {
		return time.Time{}, false, nil
	}
	t, perr := time.Parse(time.RFC3339, s)
	if perr != nil {
		return time.Time{}, false, fmt.Errorf("table: column %q value %q is not RFC 3339", name, s)
	}
	return t, true, nil
}

// Each streams every row through fn, one chunk at a time. Memory is bounded by
// chunk regardless of table size.
//
// Returning an error from fn stops iteration and returns it -- that is how an
// action aborts early without reading the rest of a large table.
func Each(ctx context.Context, cur *res.Cursor, chunk int, fn func(Row) error) error {
	if chunk <= 0 {
		chunk = DefaultChunk
	}
	cols := cur.Columns()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		default:
		}
		rows, eof, err := cur.Read(ctx, chunk)
		if err != nil {
			return err
		}
		for _, vals := range rows {
			if err := fn(Row{cols: cols, vals: vals}); err != nil {
				return err
			}
		}
		// eof, not len(rows): a chunk may legitimately be empty while more
		// rows remain, and stopping on an empty chunk would silently truncate.
		if eof {
			return nil
		}
	}
}

// Fold accumulates over every row. The common shape for statistics that must
// not hold the table in memory.
func Fold[T any](ctx context.Context, cur *res.Cursor, chunk int, init T, fn func(T, Row) (T, error)) (T, error) {
	acc := init
	err := Each(ctx, cur, chunk, func(r Row) error {
		var err error
		acc, err = fn(acc, r)
		return err
	})
	return acc, err
}

// Builder accumulates rows for a table an action produces.
//
// Deliberately in-memory and deliberately capped: an action that emits a
// genuinely large table should stream it to the blob store instead, and the cap
// is how that need announces itself rather than being discovered as an OOM.
type Builder struct {
	cols  []kernel.Column
	rows  [][]any
	limit int
}

// MaxBuilderRows caps Builder. Chosen to be comfortably larger than any report
// output and far smaller than a telemetry ingest.
const MaxBuilderRows = 100_000

// NewBuilder starts a table with declared columns. Columns are declared, never
// inferred: inferring a type from row one is how a column of integers becomes a
// column of strings the day row one happens to be null.
func NewBuilder(cols ...kernel.Column) *Builder {
	return &Builder{cols: cols, limit: MaxBuilderRows}
}

// Col is shorthand for a column declaration.
func Col(name, typ string) kernel.Column { return kernel.Column{Name: name, Type: typ} }

// Append adds one row. The value count must match the column count.
func (b *Builder) Append(vals ...any) error {
	if len(vals) != len(b.cols) {
		return fmt.Errorf("table: appended %d values to a %d-column table", len(vals), len(b.cols))
	}
	if len(b.rows) >= b.limit {
		return fmt.Errorf("table: builder exceeded %d rows; stream to the blob store instead of buffering", b.limit)
	}
	b.rows = append(b.rows, vals)
	return nil
}

// Len reports rows appended so far.
func (b *Builder) Len() int { return len(b.rows) }

// Columns returns the declared columns.
func (b *Builder) Columns() []kernel.Column { return b.cols }

// Rows returns the accumulated rows.
func (b *Builder) Rows() [][]any { return b.rows }

package telemetry

import (
	"encoding/csv"
	"fmt"
	"io"
	"strconv"
	"strings"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/table"
)

// DefaultTimeColumn is the axis every telemetry action assumes unless told
// otherwise.
const DefaultTimeColumn = "t"

// ingestCSV parses a downlink capture into a typed Table handle.
//
// Column types are inferred once from the header scan, not per row: a column
// that parses as a number in every sampled row is numeric, and one that does
// not is a string. Per-row inference would let a single null flip a column's
// type midway through, which downstream actions have no way to notice.
func ingestCSV(c *action.Ctx, in TelemetryIngestRequest) (TelemetryExtract, error) {
	if in.ObjectKey == "" {
		return TelemetryExtract{}, fmt.Errorf("object_key is required")
	}
	timeCol := in.TimeColumn
	if timeCol == "" {
		timeCol = DefaultTimeColumn
	}

	body, err := c.S3(ResTelemetry).Get(in.ObjectKey)
	if err != nil {
		return TelemetryExtract{}, fmt.Errorf("fetching capture %s: %w", in.ObjectKey, err)
	}

	r := csv.NewReader(strings.NewReader(string(body)))
	r.FieldsPerRecord = -1 // ragged rows are counted and skipped, not fatal
	r.ReuseRecord = true

	header, err := r.Read()
	if err != nil {
		return TelemetryExtract{}, fmt.Errorf("reading header of %s: %w", in.ObjectKey, err)
	}
	names := make([]string, len(header))
	copy(names, header)
	for i := range names {
		names[i] = strings.TrimSpace(names[i])
	}

	timeIdx := -1
	for i, n := range names {
		if n == timeCol {
			timeIdx = i
			break
		}
	}
	if timeIdx < 0 {
		return TelemetryExtract{}, fmt.Errorf(
			"capture %s has no time column %q; it has %v", in.ObjectKey, timeCol, names)
	}

	// First pass over the values decides each column's type. The whole file is
	// already in memory here (S3 get is not chunked), so this costs one extra
	// walk of the parsed cells and buys a stable schema.
	numeric := make([]bool, len(names))
	for i := range numeric {
		numeric[i] = true
	}

	type rawRow []string
	var raws []rawRow
	skipped := 0

	for {
		rec, err := r.Read()
		if err == io.EOF {
			break
		}
		if err != nil {
			skipped++
			continue
		}
		if len(rec) != len(names) {
			skipped++
			continue
		}
		row := make(rawRow, len(rec))
		copy(row, rec)
		raws = append(raws, row)

		for i, cell := range row {
			cell = strings.TrimSpace(cell)
			if cell == "" {
				continue // a null says nothing about the column's type
			}
			if _, err := strconv.ParseFloat(cell, 64); err != nil {
				numeric[i] = false
			}
		}
	}

	cols := make([]kernel.Column, len(names))
	for i, n := range names {
		typ := "string"
		if numeric[i] {
			typ = "float"
		}
		cols[i] = table.Col(n, typ)
	}

	b := table.NewBuilder(cols...)
	for _, row := range raws {
		vals := make([]any, len(row))
		for i, cell := range row {
			cell = strings.TrimSpace(cell)
			if numeric[i] {
				if cell == "" {
					vals[i] = nil
					continue
				}
				f, _ := strconv.ParseFloat(cell, 64)
				vals[i] = f
				continue
			}
			vals[i] = cell
		}
		if err := b.Append(vals...); err != nil {
			return TelemetryExtract{}, err
		}
	}

	h, err := c.PutTable(b.Columns(), b.Rows(), "jsonl")
	if err != nil {
		return TelemetryExtract{}, fmt.Errorf("storing series table: %w", err)
	}

	if skipped > 0 {
		// Surfaced, not swallowed. Malformed rows in a downlink capture are a
		// signal about the downlink, and a parser that hides them is hiding
		// the finding.
		c.Log("warn", "skipped malformed rows during ingest", map[string]any{
			"object_key": in.ObjectKey, "skipped": skipped,
		})
	}
	c.Logf("ingested %d samples from %s (%d columns)", b.Len(), in.ObjectKey, len(cols))
	c.Emit("telemetry.ingested", map[string]any{
		"object_key": in.ObjectKey, "rows": b.Len(), "skipped": skipped,
	})

	return TelemetryExtract{
		Series:      h,
		RowCount:    b.Len(),
		Columns:     names,
		TimeColumn:  timeCol,
		SkippedRows: skipped,
	}, nil
}

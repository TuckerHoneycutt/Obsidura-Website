package telemetry

import (
	"context"
	"fmt"
	"math"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/core"
	"github.com/obsidura/pantheon-go/table"
)

// windowStats computes rolling statistics over one numeric column.
//
// Fully streaming: one Welford accumulator for the current window, one for the
// whole series, and nothing else retained. The output windows are bounded by
// series duration divided by window size, not by sample count, which is what
// makes this safe on a capture with a hundred thousand rows.
func windowStats(c *action.Ctx, in WindowStatsRequest) (WindowStats, error) {
	if in.Column == "" {
		return WindowStats{}, fmt.Errorf("column is required")
	}
	if in.WindowSize <= 0 {
		return WindowStats{}, fmt.Errorf("window_size must be positive, got %v", in.WindowSize)
	}
	timeCol := in.TimeColumn
	if timeCol == "" {
		timeCol = DefaultTimeColumn
	}

	cur, err := c.OpenTable(in.Series)
	if err != nil {
		return WindowStats{}, fmt.Errorf("opening series: %w", err)
	}

	var (
		series   core.Welford
		window   core.Welford
		windows  []Window
		winStart float64
		started  bool
	)

	flush := func(end float64) {
		if window.N() == 0 {
			return
		}
		windows = append(windows, Window{
			Start: winStart, End: end, Count: window.N(),
			Mean: round6(window.Mean()), StdDev: round6(window.StdDev()),
			Min: window.Min(), Max: window.Max(),
		})
		window = core.Welford{}
	}

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		t, okT, err := row.Float(timeCol)
		if err != nil {
			return err
		}
		v, okV, err := row.Float(in.Column)
		if err != nil {
			return err
		}
		// A sample with no time has no window, and a sample with no value has
		// nothing to contribute. Skipping is right; erroring would make one
		// dropout kill an otherwise good flight's analysis.
		if !okT || !okV {
			return nil
		}

		if !started {
			winStart, started = t, true
		}
		for t >= winStart+in.WindowSize {
			flush(winStart + in.WindowSize)
			winStart += in.WindowSize
		}

		window.Push(v)
		series.Push(v)
		return nil
	})
	if err != nil {
		return WindowStats{}, err
	}
	flush(winStart + in.WindowSize)

	if windows == nil {
		windows = []Window{}
	}

	c.Logf("summarised %d samples of %s into %d windows of %v",
		series.N(), in.Column, len(windows), in.WindowSize)

	return WindowStats{
		Column:      in.Column,
		WindowSize:  in.WindowSize,
		Windows:     windows,
		SeriesCount: series.N(),
		SeriesMean:  round6(series.Mean()),
		SeriesStd:   round6(series.StdDev()),
		SeriesMin:   series.Min(),
		SeriesMax:   series.Max(),
	}, nil
}

// round6 trims floating-point dust so two runs over identical input produce
// byte-identical JSON. Without it the last bits of a mean vary with chunk
// boundaries and every report diff is noise.
func round6(f float64) float64 {
	if math.IsNaN(f) || math.IsInf(f, 0) {
		return 0
	}
	return math.Round(f*1e6) / 1e6
}

package telemetry

import (
	"context"
	"fmt"
	"math"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/table"
)

// DefaultMaxExcursions caps the reported list. A stuck sensor produces one
// excursion per sample, and a 40,000-row report is a report nobody opens.
const DefaultMaxExcursions = 500

// detectAnomalies applies declared limits to a series.
//
// The limits are structured data -- a column, a bound, a rate -- never an
// expression. Spec invariant 2 forbids an expression language in definitions,
// and accepting "altitude_m > 300 && v < 0" here would smuggle one in through
// the payload instead: the same prohibition evaded rather than obeyed. A new
// rule SHAPE is a new field on Limit, reviewed once. A new rule VALUE is data.
//
// Counts are always complete even when the excursion LIST is truncated. A
// report that silently caps both would say "3 excursions" about a flight that
// had four thousand, and a truncated count is worse than no count.
func detectAnomalies(c *action.Ctx, in TelemetryAnomalyRequest) (TelemetryAnomalyReport, error) {
	if len(in.Limits) == 0 {
		return TelemetryAnomalyReport{}, fmt.Errorf("at least one limit is required")
	}
	timeCol := in.TimeColumn
	if timeCol == "" {
		timeCol = DefaultTimeColumn
	}
	cap := in.MaxExcursions
	if cap == 0 {
		cap = DefaultMaxExcursions
	}

	for i, l := range in.Limits {
		if l.Column == "" {
			return TelemetryAnomalyReport{}, fmt.Errorf("limit %d has no column", i)
		}
		if l.Max == nil && l.Min == nil && l.MaxRate == nil {
			return TelemetryAnomalyReport{}, fmt.Errorf(
				"limit %d on column %q declares no bound; a limit that bounds nothing would pass silently",
				i, l.Column)
		}
	}

	cur, err := c.OpenTable(in.Series)
	if err != nil {
		return TelemetryAnomalyReport{}, fmt.Errorf("opening series: %w", err)
	}

	type prevSample struct {
		t, v  float64
		valid bool
	}
	prev := make([]prevSample, len(in.Limits))

	excursions := []Excursion{}
	counts := map[string]int{}
	var samples int64
	truncated := false

	add := func(e Excursion) {
		counts[e.Column]++
		if len(excursions) < cap {
			excursions = append(excursions, e)
			return
		}
		truncated = true
	}

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		t, okT, err := row.Float(timeCol)
		if err != nil {
			return err
		}
		if !okT {
			return nil
		}
		samples++

		for i, l := range in.Limits {
			v, ok, err := row.Float(l.Column)
			if err != nil {
				return err
			}
			if !ok {
				continue
			}

			if l.Max != nil && v > *l.Max {
				add(Excursion{Time: t, Column: l.Column, Value: v, Rule: "max", Limit: *l.Max,
					Detail: fmt.Sprintf("%g exceeds max %g", v, *l.Max)})
			}
			if l.Min != nil && v < *l.Min {
				add(Excursion{Time: t, Column: l.Column, Value: v, Rule: "min", Limit: *l.Min,
					Detail: fmt.Sprintf("%g is below min %g", v, *l.Min)})
			}
			if l.MaxRate != nil && prev[i].valid {
				dt := t - prev[i].t
				if dt > 0 {
					rate := math.Abs(v-prev[i].v) / dt
					if rate > *l.MaxRate {
						add(Excursion{Time: t, Column: l.Column, Value: rate, Rule: "max_rate", Limit: *l.MaxRate,
							Detail: fmt.Sprintf("changed at %g/unit, above max rate %g", rate, *l.MaxRate)})
					}
				}
			}
			prev[i] = prevSample{t: t, v: v, valid: true}
		}
		return nil
	})
	if err != nil {
		return TelemetryAnomalyReport{}, err
	}

	total := 0
	for _, n := range counts {
		total += n
	}
	if truncated {
		c.Log("warn", "excursion list truncated", map[string]any{
			"reported": len(excursions), "total": total,
		})
	}
	c.Logf("checked %d samples against %d limits; %d excursions", samples, len(in.Limits), total)
	c.Emit("telemetry.limits_checked", map[string]any{
		"samples": samples, "excursions": total, "truncated": truncated,
	})

	return TelemetryAnomalyReport{
		SamplesChecked: samples,
		Excursions:     excursions,
		CountByColumn:  counts,
		Truncated:      truncated,
	}, nil
}

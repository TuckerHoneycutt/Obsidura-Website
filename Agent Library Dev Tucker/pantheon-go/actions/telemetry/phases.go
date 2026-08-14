package telemetry

import (
	"context"
	"fmt"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/table"
)

// Phase names.
const (
	PhasePrelaunch = "prelaunch"
	PhaseAscent    = "ascent"
	PhaseCoast     = "coast"
	PhaseDescent   = "descent"
	PhaseLanded    = "landed"
)

// GroundLevel is the altitude below which the vehicle counts as on the ground.
// Not zero: a barometric altimeter at rest reads a metre either side of it, and
// a strict zero would flicker between landed and coast for the whole recording.
const GroundLevel = 1.0

// DefaultAltitudeColumn is the altitude channel assumed unless told otherwise.
const DefaultAltitudeColumn = "altitude_m"

// DefaultAscentRate separates ascent from coast, in altitude units per time
// unit.
const DefaultAscentRate = 5.0

// segmentPhases splits a flight into contiguous phases by vertical rate.
//
// Streaming, holding only the previous sample and the open phase. The rate is
// computed between consecutive samples rather than over a window, which is
// noisier but has no lag -- and phase boundaries are what this action exists to
// locate, so a boundary reported late is the failure that matters.
func segmentPhases(c *action.Ctx, in PhaseRequest) (FlightPhases, error) {
	timeCol := in.TimeColumn
	if timeCol == "" {
		timeCol = DefaultTimeColumn
	}
	altCol := in.AltitudeColumn
	if altCol == "" {
		altCol = DefaultAltitudeColumn
	}
	threshold := in.AscentRate
	if threshold == 0 {
		threshold = DefaultAscentRate
	}

	cur, err := c.OpenTable(in.Series)
	if err != nil {
		return FlightPhases{}, fmt.Errorf("opening series: %w", err)
	}

	var (
		phases             []Phase
		open               *Phase
		prevT, prevAlt     float64
		havePrev           bool
		apogee, apogeeTime float64
		haveApogee         bool
		airborne           bool
		samples            int64
	)

	closePhase := func(t, alt float64) {
		if open == nil {
			return
		}
		open.EndTime = t
		open.EndAlt = alt
		phases = append(phases, *open)
		open = nil
	}

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		t, okT, err := row.Float(timeCol)
		if err != nil {
			return err
		}
		alt, okA, err := row.Float(altCol)
		if err != nil {
			return err
		}
		if !okT || !okA {
			return nil
		}
		samples++

		if !haveApogee || alt > apogee {
			apogee, apogeeTime, haveApogee = alt, t, true
		}

		if !havePrev {
			prevT, prevAlt, havePrev = t, alt, true
			open = &Phase{Name: PhasePrelaunch, StartTime: t, StartAlt: alt, PeakAlt: alt, Samples: 1}
			return nil
		}

		dt := t - prevT
		rate := 0.0
		if dt > 0 {
			rate = (alt - prevAlt) / dt
		}

		if alt > GroundLevel {
			airborne = true
		}

		name := PhaseCoast
		switch {
		case rate > threshold:
			name = PhaseAscent
		case rate < -threshold:
			name = PhaseDescent
		}
		switch {
		case !airborne && name == PhaseCoast:
			// Prelaunch persists until something actually moves. Without this
			// the first noisy sample on the pad opens a "coast" and every
			// flight report starts with a phase that did not happen.
			name = PhasePrelaunch
		case airborne && alt <= GroundLevel:
			// Back on the ground. Deliberately regardless of apparent rate: at
			// touchdown the altimeter settles through a metre or two in a
			// single sample, which computes as a vertical speed no vehicle
			// achieved. Trusting that rate produces a one-sample "ascent" after
			// landing -- a phase that did not happen, in a report an engineer
			// is meant to read.
			//
			// Without the airborne guard this would swallow prelaunch too,
			// which is why the two conditions are separate.
			name = PhaseLanded
		}

		if open == nil || open.Name != name {
			closePhase(prevT, prevAlt)
			open = &Phase{Name: name, StartTime: prevT, StartAlt: prevAlt, PeakAlt: alt}
		}
		open.Samples++
		if alt > open.PeakAlt {
			open.PeakAlt = alt
		}

		prevT, prevAlt = t, alt
		return nil
	})
	if err != nil {
		return FlightPhases{}, err
	}
	closePhase(prevT, prevAlt)

	if phases == nil {
		phases = []Phase{}
	}

	c.Logf("segmented %d samples into %d phases; apogee %.1f at t=%.1f",
		samples, len(phases), apogee, apogeeTime)
	c.Emit("telemetry.phases_segmented", map[string]any{
		"phases": len(phases), "apogee": apogee, "apogee_time": apogeeTime,
	})

	return FlightPhases{
		Phases:      phases,
		Apogee:      apogee,
		ApogeeTime:  apogeeTime,
		SampleCount: samples,
	}, nil
}

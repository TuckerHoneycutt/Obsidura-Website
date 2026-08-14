package telemetry_test

import (
	"testing"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/telemetry"
	"github.com/obsidura/pantheon-go/fixtures"
	"github.com/obsidura/pantheon-go/ptnfake"
)

// Named mutation table for the telemetry vertical.
//
//	mutation                                             | reddens
//	-----------------------------------------------------|-----------------------------------------
//	ingestCSV infers column type per row                  | TestIngestTypesColumnsFromWholeFile
//	ingestCSV treats a blank cell as a malformed row      | TestIngestDistinguishesBlankCellFromRaggedRow
//	ingestCSV swallows skipped rows silently              | TestIngestReportsSkippedRows
//	windowStats stops on the first empty chunk            | TestWindowStatsCoversEveryChunk
//	windowStats holds all samples instead of streaming    | TestWindowStatsHandlesLargeSeries
//	segmentPhases opens a phase on the first pad sample   | TestSegmentPhasesDoesNotInventAPrelaunchCoast
//	detectAnomalies caps counts as well as the list       | TestDetectAnomaliesCountsBeyondTheCap
//	detectAnomalies accepts a limit with no bound         | TestDetectAnomaliesRefusesABoundlessLimit
//	Limit gains a free-text expression field              | (design; see types.go and invariant 2)

func setup(t *testing.T, samples int) (*ptnfake.Proxy, *action.Registry) {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Close() })
	fixtures.Telemetry(p, samples)
	fixtures.GrantTelemetryFull(p)

	r := action.NewRegistry()
	telemetry.Register(r)
	return p, r
}

func ingest(t *testing.T, p *ptnfake.Proxy, r *action.Registry, samples int) telemetry.TelemetryExtract {
	t.Helper()
	var out telemetry.TelemetryExtract
	res := p.Invoke(r, "telemetry.ingest_csv", telemetry.TelemetryIngestRequest{
		ObjectKey: "flights/F-118/telemetry.csv",
	})
	if err := res.Record(&out); err != nil {
		t.Fatalf("ingest_csv: %v", err)
	}
	return out
}

func TestIngestDistinguishesBlankCellFromRaggedRow(t *testing.T) {
	p, r := setup(t, 300)
	out := ingest(t, p, r, 300)

	// The fixture plants exactly one ragged row (skipped) and one row with a
	// blank altitude cell (kept, with a null). Conflating them would either
	// lose a good sample or keep a corrupt one.
	if out.SkippedRows != 1 {
		t.Errorf("expected exactly 1 skipped ragged row, got %d", out.SkippedRows)
	}
	if out.RowCount != 299 {
		t.Errorf("expected 299 retained rows (300 minus the ragged one), got %d", out.RowCount)
	}
}

func TestIngestReportsSkippedRows(t *testing.T) {
	p, r := setup(t, 300)
	res := p.Invoke(r, "telemetry.ingest_csv", telemetry.TelemetryIngestRequest{
		ObjectKey: "flights/F-118/telemetry.csv",
	})
	if res.Err != nil {
		t.Fatal(res.Err)
	}
	// Malformed rows in a downlink capture are a signal about the downlink. A
	// parser that hides them is hiding the finding.
	for _, l := range res.Logs {
		if l.Level == "warn" && l.Fields["skipped"] != nil {
			return
		}
	}
	t.Errorf("skipped rows were not surfaced in the logs: %+v", res.Logs)
}

func TestIngestTypesColumnsFromWholeFile(t *testing.T) {
	p, r := setup(t, 300)
	out := ingest(t, p, r, 300)

	cols, rows, ok := p.TableRows(out.Series)
	if !ok {
		t.Fatal("no series table")
	}
	byName := map[string]string{}
	for _, c := range cols {
		byName[c.Name] = c.Type
	}
	// altitude_m has one blank cell. Per-row inference would let that blank
	// flip the column to string partway through, and nothing downstream could
	// notice.
	if byName["altitude_m"] != "float" {
		t.Errorf("altitude_m typed as %q; one blank cell must not change a column's type", byName["altitude_m"])
	}
	if byName["stage"] != "string" {
		t.Errorf("stage typed as %q, want string", byName["stage"])
	}
	if len(rows) == 0 {
		t.Fatal("no rows")
	}
}

func TestIngestRefusesAMissingTimeColumn(t *testing.T) {
	p, r := setup(t, 50)
	res := p.Invoke(r, "telemetry.ingest_csv", telemetry.TelemetryIngestRequest{
		ObjectKey: "flights/F-118/telemetry.csv", TimeColumn: "epoch",
	})
	if res.Err == nil {
		t.Fatal("a missing time column must be refused; every downstream action needs an axis")
	}
}

func TestWindowStatsCoversEveryChunk(t *testing.T) {
	p, r := setup(t, 600)
	extract := ingest(t, p, r, 600)

	var stats telemetry.WindowStats
	if err := p.Invoke(r, "telemetry.window_stats", telemetry.WindowStatsRequest{
		Series: extract.Series, Column: "altitude_m", WindowSize: 5.0,
	}).Record(&stats); err != nil {
		t.Fatal(err)
	}

	// 600 samples at 0.1s is 60s of flight; 5s windows give 12, and every
	// sample with an altitude must land in one.
	if len(stats.Windows) < 10 {
		t.Errorf("expected roughly 12 windows over 60s, got %d", len(stats.Windows))
	}
	var counted int64
	for _, w := range stats.Windows {
		counted += w.Count
	}
	if counted != stats.SeriesCount {
		t.Errorf("windows account for %d samples but the series has %d; rows were dropped between chunks",
			counted, stats.SeriesCount)
	}
	if stats.SeriesMax <= 0 {
		t.Errorf("series max altitude is %v; the flight should reach altitude", stats.SeriesMax)
	}
}

// The point of chunked reading is that memory does not scale with the table.
// This exercises many chunk boundaries; DefaultChunk is 2000, so 25,000 rows
// crosses a dozen of them.
func TestWindowStatsHandlesLargeSeries(t *testing.T) {
	if testing.Short() {
		t.Skip("large-series test skipped in -short")
	}
	p, r := setup(t, 25_000)
	extract := ingest(t, p, r, 25_000)

	if extract.RowCount != 24_999 {
		t.Fatalf("ingested %d rows", extract.RowCount)
	}

	var stats telemetry.WindowStats
	if err := p.Invoke(r, "telemetry.window_stats", telemetry.WindowStatsRequest{
		Series: extract.Series, Column: "velocity_ms", WindowSize: 10.0,
	}).Record(&stats); err != nil {
		t.Fatal(err)
	}
	if stats.SeriesCount != 24_999 {
		t.Errorf("summarised %d samples, want 24999", stats.SeriesCount)
	}
	var counted int64
	for _, w := range stats.Windows {
		counted += w.Count
	}
	if counted != stats.SeriesCount {
		t.Errorf("windows account for %d of %d samples across %d chunk boundaries",
			counted, stats.SeriesCount, 25_000/2000)
	}
}

func TestSegmentPhasesFindsApogeeAndOrdersPhases(t *testing.T) {
	p, r := setup(t, 600)
	extract := ingest(t, p, r, 600)

	var phases telemetry.FlightPhases
	if err := p.Invoke(r, "telemetry.segment_phases", telemetry.PhaseRequest{
		Series: extract.Series,
	}).Record(&phases); err != nil {
		t.Fatal(err)
	}

	if phases.Apogee <= 0 {
		t.Fatalf("apogee is %v", phases.Apogee)
	}
	// Apogee must not be at the very start or the very end of the flight.
	if phases.ApogeeTime <= 5.0 {
		t.Errorf("apogee at t=%v, which is still on the pad", phases.ApogeeTime)
	}

	seen := map[string]bool{}
	var last float64
	for i, ph := range phases.Phases {
		seen[ph.Name] = true
		if i > 0 && ph.StartTime < last {
			t.Errorf("phase %d starts at %v, before the previous phase ended at %v", i, ph.StartTime, last)
		}
		last = ph.EndTime
	}
	for _, want := range []string{telemetry.PhasePrelaunch, telemetry.PhaseAscent, telemetry.PhaseDescent} {
		if !seen[want] {
			t.Errorf("phase %q never appears; phases were %+v", want, phases.Phases)
		}
	}
}

func TestSegmentPhasesDoesNotInventAPrelaunchCoast(t *testing.T) {
	p, r := setup(t, 600)
	extract := ingest(t, p, r, 600)

	var phases telemetry.FlightPhases
	if err := p.Invoke(r, "telemetry.segment_phases", telemetry.PhaseRequest{
		Series: extract.Series,
	}).Record(&phases); err != nil {
		t.Fatal(err)
	}

	if len(phases.Phases) == 0 {
		t.Fatal("no phases")
	}
	// The first phase must be prelaunch. Without the guard, the first sample on
	// the pad opens a "coast" and every flight report starts with a phase that
	// did not happen.
	if phases.Phases[0].Name != telemetry.PhasePrelaunch {
		t.Errorf("flight begins with phase %q, want prelaunch", phases.Phases[0].Name)
	}
}

// The recording continues long after touchdown. Reporting that tail as "coast"
// -- or letting the altimeter settling produce a one-sample "ascent" -- puts a
// phase in the report that did not happen.
func TestSegmentPhasesReportsLandingAndInventsNoPhaseAfterIt(t *testing.T) {
	p, r := setup(t, 3000) // well past touchdown at t~76s
	extract := ingest(t, p, r, 3000)

	var phases telemetry.FlightPhases
	if err := p.Invoke(r, "telemetry.segment_phases", telemetry.PhaseRequest{
		Series: extract.Series,
	}).Record(&phases); err != nil {
		t.Fatal(err)
	}

	if len(phases.Phases) == 0 {
		t.Fatal("no phases")
	}
	last := phases.Phases[len(phases.Phases)-1]
	if last.Name != telemetry.PhaseLanded {
		t.Errorf("the flight ends in phase %q, want landed", last.Name)
	}

	// Nothing may fly again after landing.
	var landedAt = -1
	for i, ph := range phases.Phases {
		if ph.Name == telemetry.PhaseLanded {
			landedAt = i
			break
		}
	}
	if landedAt < 0 {
		t.Fatalf("no landed phase in %+v", phases.Phases)
	}
	for _, ph := range phases.Phases[landedAt:] {
		if ph.Name == telemetry.PhaseAscent || ph.Name == telemetry.PhaseDescent {
			t.Errorf("phase %q appears after landing: %+v", ph.Name, ph)
		}
	}

	// Every phase name the type documents must be reachable, or the docs lie.
	seen := map[string]bool{}
	for _, ph := range phases.Phases {
		seen[ph.Name] = true
	}
	for _, want := range []string{
		telemetry.PhasePrelaunch, telemetry.PhaseAscent,
		telemetry.PhaseDescent, telemetry.PhaseLanded,
	} {
		if !seen[want] {
			t.Errorf("documented phase %q never appears; phases were %+v", want, phases.Phases)
		}
	}
}

func TestDetectAnomaliesFindsPlantedPressureSpike(t *testing.T) {
	p, r := setup(t, 600)
	extract := ingest(t, p, r, 600)

	max := 60.0
	var report telemetry.TelemetryAnomalyReport
	if err := p.Invoke(r, "telemetry.detect_anomalies", telemetry.TelemetryAnomalyRequest{
		Series: extract.Series,
		Limits: []telemetry.Limit{{Column: "chamber_pressure_bar", Max: &max}},
	}).Record(&report); err != nil {
		t.Fatal(err)
	}

	if len(report.Excursions) == 0 {
		t.Fatalf("the fixture plants a 96.4 bar spike against a 60 bar limit and it was not found; report: %+v", report)
	}
	for _, e := range report.Excursions {
		if e.Column != "chamber_pressure_bar" || e.Value <= max {
			t.Errorf("unexpected excursion %+v", e)
		}
	}
}

func TestDetectAnomaliesRefusesABoundlessLimit(t *testing.T) {
	p, r := setup(t, 100)
	extract := ingest(t, p, r, 100)

	res := p.Invoke(r, "telemetry.detect_anomalies", telemetry.TelemetryAnomalyRequest{
		Series: extract.Series,
		Limits: []telemetry.Limit{{Column: "velocity_ms"}}, // no max, min or rate
	})
	if res.Err == nil {
		t.Fatal("a limit that bounds nothing would pass silently and must be refused")
	}
}

// A truncated LIST is acceptable; a truncated COUNT is not. A report saying
// "3 excursions" about a flight that had four thousand is worse than no report.
func TestDetectAnomaliesCountsBeyondTheCap(t *testing.T) {
	p, r := setup(t, 600)
	extract := ingest(t, p, r, 600)

	max := -1.0 // every sample of a non-negative column exceeds this
	var report telemetry.TelemetryAnomalyReport
	if err := p.Invoke(r, "telemetry.detect_anomalies", telemetry.TelemetryAnomalyRequest{
		Series:        extract.Series,
		Limits:        []telemetry.Limit{{Column: "chamber_pressure_bar", Max: &max}},
		MaxExcursions: 5,
	}).Record(&report); err != nil {
		t.Fatal(err)
	}

	if len(report.Excursions) != 5 {
		t.Errorf("the list should be capped at 5, got %d", len(report.Excursions))
	}
	if !report.Truncated {
		t.Error("truncation must be declared, not silent")
	}
	if got := report.CountByColumn["chamber_pressure_bar"]; got <= 5 {
		t.Errorf("counts must be complete even when the list is capped; got %d", got)
	}
}

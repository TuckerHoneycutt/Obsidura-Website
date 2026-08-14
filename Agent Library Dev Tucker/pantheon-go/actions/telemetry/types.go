// Package telemetry is the rocket flight-diagnostics vertical of the deck.
//
// The vertical exists to stress one property the others do not: tens of
// thousands of rows, never resident. Every action here reads through a chunked
// cursor and holds only its accumulator. An action that works because the
// fixture was small is an action that fails on a real flight.
package telemetry

import "github.com/obsidura/pantheon-go/kernel"

// Logical resource names. See finance's note on why these are constants and not
// input fields.
const (
	ResTelemetry = "telemetry"   // s3: raw CSV downlink captures
	ResFlightLog = "flight_logs" // postgres: test and anomaly logs
)

// TelemetryIngestRequest reads one downlink capture.
type TelemetryIngestRequest struct {
	ObjectKey  string `json:"object_key" desc:"S3 key of the CSV capture, e.g. flights/F-118/telemetry.csv"`
	TimeColumn string `json:"time_column" desc:"Name of the timestamp column; defaults to t"`
}

// TelemetryExtract is a parsed capture as a Table handle.
type TelemetryExtract struct {
	Series      kernel.TableHandle `json:"series"`
	RowCount    int                `json:"row_count"`
	Columns     []string           `json:"columns"`
	TimeColumn  string             `json:"time_column"`
	SkippedRows int                `json:"skipped_rows" desc:"Malformed rows dropped during parse; non-zero deserves a look"`
}

// WindowStatsRequest asks for rolling statistics over one numeric column.
type WindowStatsRequest struct {
	Series     kernel.TableHandle `json:"series"`
	Column     string             `json:"column" desc:"Numeric column to summarise"`
	TimeColumn string             `json:"time_column" desc:"Column supplying the window axis; defaults to t"`
	WindowSize float64            `json:"window_size" desc:"Window width in the time column's own units"`
}

// Window is one window's summary.
type Window struct {
	Start  float64 `json:"start"`
	End    float64 `json:"end"`
	Count  int64   `json:"count"`
	Mean   float64 `json:"mean"`
	StdDev float64 `json:"stddev"`
	Min    float64 `json:"min"`
	Max    float64 `json:"max"`
}

// WindowStats is the rolling summary plus a whole-series baseline.
type WindowStats struct {
	Column      string   `json:"column"`
	WindowSize  float64  `json:"window_size"`
	Windows     []Window `json:"windows"`
	SeriesCount int64    `json:"series_count"`
	SeriesMean  float64  `json:"series_mean"`
	SeriesStd   float64  `json:"series_stddev"`
	SeriesMin   float64  `json:"series_min"`
	SeriesMax   float64  `json:"series_max"`
}

// PhaseRequest asks for flight-phase segmentation.
type PhaseRequest struct {
	Series         kernel.TableHandle `json:"series"`
	TimeColumn     string             `json:"time_column" desc:"Defaults to t"`
	AltitudeColumn string             `json:"altitude_column" desc:"Defaults to altitude_m"`

	// AscentRate is the vertical speed, in altitude units per time unit, above
	// which the vehicle counts as ascending. Zero means the default.
	AscentRate float64 `json:"ascent_rate,omitempty" desc:"Vertical rate threshold separating ascent from coast; default 5"`
}

// Phase is one contiguous segment of flight.
type Phase struct {
	Name      string  `json:"name" desc:"prelaunch | ascent | coast | descent | landed"`
	StartTime float64 `json:"start_time"`
	EndTime   float64 `json:"end_time"`
	Samples   int64   `json:"samples"`
	StartAlt  float64 `json:"start_altitude"`
	EndAlt    float64 `json:"end_altitude"`
	PeakAlt   float64 `json:"peak_altitude"`
}

// FlightPhases is the segmentation result.
type FlightPhases struct {
	Phases      []Phase `json:"phases"`
	Apogee      float64 `json:"apogee" desc:"Highest altitude observed"`
	ApogeeTime  float64 `json:"apogee_time"`
	SampleCount int64   `json:"sample_count"`
}

// Limit is one declared bound on one column.
//
// Deliberately structured data, never an expression string. Spec invariant 2
// forbids an expression language in definitions, and a rule field that accepted
// "altitude_m > 300 && velocity < 0" would smuggle one in through the input
// payload -- the same prohibition, evaded rather than obeyed. A new rule SHAPE
// is a new field here, reviewed once; a new rule VALUE is data.
type Limit struct {
	Column string `json:"column"`

	// Max and Min are absolute bounds. Pointers so that "no bound" and "a bound
	// of zero" are distinguishable, which for a velocity column they must be.
	Max *float64 `json:"max,omitempty"`
	Min *float64 `json:"min,omitempty"`

	// MaxRate bounds the absolute change per unit of the time column, catching
	// discontinuities a static bound cannot -- a sensor that jumps from 40 to
	// 4000 and back stays inside its limits at every individual sample.
	MaxRate *float64 `json:"max_rate,omitempty"`
}

// TelemetryAnomalyRequest applies declared limits to a series.
type TelemetryAnomalyRequest struct {
	Series     kernel.TableHandle `json:"series"`
	TimeColumn string             `json:"time_column" desc:"Defaults to t"`
	Limits     []Limit            `json:"limits"`

	// MaxExcursions caps the reported list. A stuck sensor produces one
	// excursion per sample, and a report with 40,000 identical rows is a report
	// nobody opens. Zero means the default.
	MaxExcursions int `json:"max_excursions,omitempty" desc:"Cap on reported excursions; default 500"`
}

// Excursion is one limit violation.
type Excursion struct {
	Time   float64 `json:"time"`
	Column string  `json:"column"`
	Value  float64 `json:"value"`
	Rule   string  `json:"rule" desc:"max | min | max_rate"`
	Limit  float64 `json:"limit"`
	Detail string  `json:"detail"`
}

// TelemetryAnomalyReport is what the limits found.
type TelemetryAnomalyReport struct {
	SamplesChecked int64          `json:"samples_checked"`
	Excursions     []Excursion    `json:"excursions"`
	CountByColumn  map[string]int `json:"count_by_column" desc:"Full counts, even when the excursion list was truncated"`
	Truncated      bool           `json:"truncated" desc:"True when more excursions occurred than were reported"`
}

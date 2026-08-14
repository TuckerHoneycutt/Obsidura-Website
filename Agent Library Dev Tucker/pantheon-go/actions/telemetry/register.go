package telemetry

import (
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
)

// Register adds the telemetry vertical to a registry.
func Register(r *action.Registry) {
	action.Register(r, action.Spec{
		Name:    "telemetry.ingest_csv",
		Version: 1,
		Input:   kernel.Ref("telemetry.TelemetryIngestRequest", 1),
		Output:  kernel.Ref("telemetry.TelemetryExtract", 1),
		Uses:    []action.ResourceUse{{Name: ResTelemetry, Verbs: []string{"get"}}},
		// Longer than the finance default: a downlink capture is the largest
		// single object anything in the deck fetches.
		Policy:  action.Policy{Timeout: 300 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Parse a raw telemetry capture into a typed series table.",
	}, ingestCSV)

	action.Register(r, action.Spec{
		Name:    "telemetry.window_stats",
		Version: 1,
		Input:   kernel.Ref("telemetry.WindowStatsRequest", 1),
		Output:  kernel.Ref("telemetry.WindowStats", 1),
		Policy:  action.Policy{Timeout: 120 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Compute rolling statistics for one telemetry channel.",
	}, windowStats)

	action.Register(r, action.Spec{
		Name:    "telemetry.segment_phases",
		Version: 1,
		Input:   kernel.Ref("telemetry.PhaseRequest", 1),
		Output:  kernel.Ref("telemetry.FlightPhases", 1),
		Policy:  action.Policy{Timeout: 120 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Split a flight into prelaunch, ascent, coast and descent phases.",
	}, segmentPhases)

	action.Register(r, action.Spec{
		Name:    "telemetry.detect_anomalies",
		Version: 1,
		Input:   kernel.Ref("telemetry.TelemetryAnomalyRequest", 1),
		Output:  kernel.Ref("telemetry.TelemetryAnomalyReport", 1),
		Policy:  action.Policy{Timeout: 120 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Check telemetry channels against declared limits and rate bounds.",
	}, detectAnomalies)
}

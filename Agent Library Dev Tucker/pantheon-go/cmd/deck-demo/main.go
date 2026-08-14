// Command deck-demo runs the three verticals against the synthetic fixtures and
// prints what they produce.
//
// It exists because passing tests are not the same as a result a human has
// looked at. Acceptance test 8 in the spec is explicitly a human test, and the
// same principle applies at this scale: the reports below are meant to be read,
// and if they read wrongly the tests were asserting the wrong things.
//
//	go run ./cmd/deck-demo
package main

import (
	"fmt"
	"os"
	"strings"

	"github.com/obsidura/pantheon-go/actions/clinical"
	"github.com/obsidura/pantheon-go/actions/finance"
	"github.com/obsidura/pantheon-go/actions/telemetry"
	"github.com/obsidura/pantheon-go/deck"
	"github.com/obsidura/pantheon-go/fixtures"
	"github.com/obsidura/pantheon-go/ptnfake"
)

func main() {
	reg := deck.All()

	financeDemo(reg)
	telemetryDemo(reg)
	clinicalDemo(reg)

	fmt.Printf("\n%s\n", rule("deck catalog"))
	for _, c := range deck.Catalog(reg) {
		res := ""
		if len(c.Resources) > 0 {
			res = "  [needs: " + strings.Join(c.Resources, ", ") + "]"
		}
		fmt.Printf("  %-28s %s%s\n", c.Name, c.Summary, res)
	}
}

func financeDemo(reg *deckRegistry) {
	fmt.Printf("%s\n", rule("financial audit — 2026-Q2"))

	p := newProxy()
	defer p.Close()
	fixtures.Finance(p)
	fixtures.GrantFinanceFull(p)

	var extract finance.LedgerExtract
	must(p.Invoke(reg, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&extract))
	fmt.Printf("fetched %d entries in %v\n", extract.RowCount, extract.Currencies)

	var norm finance.NormalizedLedger
	must(p.Invoke(reg, "finance.normalize_fx", finance.FXNormalizeRequest{
		Ledger:       extract.Ledger,
		BaseCurrency: "USD",
		RatesURL:     "https://fx.example/v1/latest?base=USD",
	}).Record(&norm))
	fmt.Printf("normalised %d rows to USD using %v\n\n", norm.ConvertedRows, norm.RatesUsed)

	var rec finance.ReconciliationReport
	must(p.Invoke(reg, "finance.reconcile_ledger", finance.ReconcileRequest{
		Ledger: norm.Ledger, BaseCurrency: "USD", Period: "2026-Q2",
	}).Record(&rec))
	fmt.Printf("  debits %14s   credits %14s   imbalance %10s   balanced=%v\n",
		rec.Debits, rec.Credits, rec.Imbalance, rec.Balanced)
	for _, a := range rec.ByAccount {
		fmt.Printf("    %-16s %3d entries   net %14s\n", a.Account, a.EntryCount, a.Net)
	}

	var match finance.ReceiptMatchReport
	must(p.Invoke(reg, "finance.match_receipts", finance.ReceiptMatchRequest{
		Ledger: norm.Ledger, ReceiptPrefix: "receipts/2026-Q2/",
	}).Record(&match))
	fmt.Printf("\n  receipts: %d matched of %d entries, %d receipts on file\n",
		match.Matched, match.EntriesChecked, match.ReceiptsFound)
	for _, u := range match.UnmatchedEntries {
		fmt.Printf("    %-6s %-24s %12s   %s\n", u.EntryID, trunc(u.Description, 24), u.Amount, u.Reason)
	}
	for _, o := range match.OrphanReceipts {
		fmt.Printf("    orphan receipt with no ledger entry: %s\n", o)
	}

	var anom finance.AnomalyReport
	must(p.Invoke(reg, "finance.flag_anomalies", finance.AnomalyRequest{Ledger: norm.Ledger}).Record(&anom))
	fmt.Printf("\n  anomalies: %d flagged across %d entries (median %s)\n",
		len(anom.Anomalies), anom.EntriesChecked, anom.Median)
	for _, a := range anom.Anomalies {
		fmt.Printf("    [%-13s] %-6s %12s  %s\n", a.Rule, a.EntryID, a.Amount, a.Detail)
	}
}

func telemetryDemo(reg *deckRegistry) {
	fmt.Printf("\n%s\n", rule("flight diagnostics — F-118"))

	p := newProxy()
	defer p.Close()
	const samples = 25_000
	fixtures.Telemetry(p, samples)
	fixtures.GrantTelemetryFull(p)

	var extract telemetry.TelemetryExtract
	must(p.Invoke(reg, "telemetry.ingest_csv", telemetry.TelemetryIngestRequest{
		ObjectKey: "flights/F-118/telemetry.csv",
	}).Record(&extract))
	fmt.Printf("ingested %d samples (%d skipped) across %v\n\n",
		extract.RowCount, extract.SkippedRows, extract.Columns)

	var phases telemetry.FlightPhases
	must(p.Invoke(reg, "telemetry.segment_phases", telemetry.PhaseRequest{Series: extract.Series}).Record(&phases))
	fmt.Printf("  apogee %.1f m at t=%.1f s\n", phases.Apogee, phases.ApogeeTime)
	for _, ph := range phases.Phases {
		fmt.Printf("    %-10s t=%7.1f .. %7.1f  %6d samples  peak %8.1f m\n",
			ph.Name, ph.StartTime, ph.EndTime, ph.Samples, ph.PeakAlt)
	}

	var stats telemetry.WindowStats
	must(p.Invoke(reg, "telemetry.window_stats", telemetry.WindowStatsRequest{
		Series: extract.Series, Column: "velocity_ms", WindowSize: 60,
	}).Record(&stats))
	fmt.Printf("\n  velocity_ms over %d samples: mean %.2f  sd %.2f  range [%.1f, %.1f]  in %d windows\n",
		stats.SeriesCount, stats.SeriesMean, stats.SeriesStd, stats.SeriesMin, stats.SeriesMax, len(stats.Windows))

	maxP := 60.0
	var limits telemetry.TelemetryAnomalyReport
	must(p.Invoke(reg, "telemetry.detect_anomalies", telemetry.TelemetryAnomalyRequest{
		Series: extract.Series,
		Limits: []telemetry.Limit{{Column: "chamber_pressure_bar", Max: &maxP}},
	}).Record(&limits))
	fmt.Printf("\n  limit checks over %d samples: %d excursions\n", limits.SamplesChecked, len(limits.Excursions))
	for _, e := range limits.Excursions {
		fmt.Printf("    t=%6.1f  %-22s %s\n", e.Time, e.Column, e.Detail)
	}
}

func clinicalDemo(reg *deckRegistry) {
	fmt.Printf("\n%s\n", rule("clinical summary — the permission beat"))

	// The SAME request object for both users. Nothing about it changes.
	request := clinical.CohortQuery{Status: "admitted"}

	for _, user := range []struct {
		name  string
		grant func(*ptnfake.Proxy)
	}{
		{"user A (full access)", fixtures.GrantClinicalAll},
		{"user B (cardiology only)", func(p *ptnfake.Proxy) { fixtures.GrantClinicalWard(p, "cardiology", "scans/p-001/") }},
	} {
		p := newProxy()
		fixtures.Clinical(p)
		user.grant(p)

		var cohort clinical.Cohort
		must(p.Invoke(reg, "clinical.filter_cohort", request).Record(&cohort))

		ids := make([]string, 0, len(cohort.Patients))
		for _, pat := range cohort.Patients {
			ids = append(ids, pat.PatientID)
		}

		var manifest clinical.ScanManifest
		must(p.Invoke(reg, "clinical.manifest_scans", clinical.ScanManifestRequest{
			PatientIDs: ids, Prefix: "scans/",
		}).Record(&manifest))

		fmt.Printf("\n  %-26s %d patients %v, %d scans visible\n",
			user.name, cohort.Count, ids, manifest.Found)
		for _, line := range p.AuditLines() {
			fmt.Printf("      audit: %s\n", line)
		}
		p.Close()
	}

	fmt.Printf("\n  Same request, different results. filter_cohort has no requester field\n")
	fmt.Printf("  and issues one identical query; the proxy applies the scope.\n")
}

// ---------- plumbing ----------

type deckRegistry = actionRegistry

func newProxy() *ptnfake.Proxy {
	p, err := ptnfake.New()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	return p
}

func must(err error) {
	if err != nil {
		fmt.Fprintf(os.Stderr, "deck-demo: %v\n", err)
		os.Exit(1)
	}
}

func rule(title string) string {
	return "── " + title + " " + strings.Repeat("─", max(0, 68-len(title)))
}

func trunc(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n-1] + "…"
}

func max(a, b int) int {
	if a > b {
		return a
	}
	return b
}

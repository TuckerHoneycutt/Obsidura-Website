// Package fixtures seeds a ptnfake proxy with the three synthetic datasets.
//
// ONE corpus, shared by every vertical's tests. The build plan says not to
// build a second fixture corpus, and the reason is that divergent fixtures are
// worse than no fixtures: two datasets that are almost the same produce two
// tests that are almost testing the same thing, and neither is trusted.
//
// The data is deliberately small and deliberately WRONG in specific, named ways
// -- a deliberate imbalance, a missing receipt, an orphan receipt, a duplicate
// posting, a sensor excursion, a ward the requester may not see. Every defect
// here exists because some action is supposed to find it. A clean fixture tests
// only the happy path, which is the path that was never going to break.
package fixtures

import (
	"fmt"
	"strings"

	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/ptnfake"
	"github.com/obsidura/pantheon-go/res"
)

// ---------- finance ----------

// Finance seeds the financial-audit dataset: a 2026-Q2 ledger in three
// currencies, receipt documents, and an FX endpoint.
//
// Planted defects, each with an owner:
//
//	e-004 / e-005  identical amount, account, day and description -> duplicate
//	e-006          references receipts/2026-Q2/e-006.pdf, which does not exist
//	e-007          no receipt referenced at all
//	e-008          80,000.00 EUR, far above the median -> outlier
//	e-003/9/10     posted on a Saturday, Saturday and Sunday -> weekend x3
//	(orphan)       receipts/2026-Q2/e-999.pdf belongs to no entry
//	imbalance      debits and credits do not net to zero, deliberately
//
// Note that e-008 is round in EUR but not after conversion to USD, so the
// round_number rule does not fire on this dataset. That rule is exercised
// directly in the finance tests rather than by planting an amount here, because
// an amount that survives conversion as a round number would have to be chosen
// against a specific FX rate and would silently stop testing anything the day
// the rate fixture changed.
func Finance(p *ptnfake.Proxy) {
	cols := []kernel.Column{
		{Name: "entry_id", Type: "string"},
		{Name: "posted_at", Type: "timestamp"},
		{Name: "account", Type: "string"},
		{Name: "description", Type: "string"},
		{Name: "amount", Type: "string"},
		{Name: "currency", Type: "string"},
		{Name: "receipt_key", Type: "string"},
	}

	rows := [][]any{
		{"e-001", "2026-04-02T09:15:00Z", "4000-revenue", "Consulting fee", "-12500.00", "USD", "receipts/2026-Q2/e-001.pdf"},
		{"e-002", "2026-04-02T09:20:00Z", "1000-cash", "Consulting fee received", "12500.00", "USD", "receipts/2026-Q2/e-002.pdf"},
		{"e-003", "2026-04-11T14:02:00Z", "6000-travel", "Flight to client site", "1842.30", "USD", "receipts/2026-Q2/e-003.pdf"},

		// Duplicate pair: same account, amount, day and description.
		{"e-004", "2026-05-06T11:00:00Z", "6100-software", "Annual CRM licence", "4800.00", "USD", "receipts/2026-Q2/e-004.pdf"},
		{"e-005", "2026-05-06T16:41:00Z", "6100-software", "Annual CRM licence", "4800.00", "USD", "receipts/2026-Q2/e-005.pdf"},

		// Claims a receipt that is not in the bucket.
		{"e-006", "2026-05-14T08:30:00Z", "6000-travel", "Hotel, three nights", "1120.55", "USD", "receipts/2026-Q2/e-006.pdf"},

		// Claims no receipt at all.
		{"e-007", "2026-05-21T13:12:00Z", "6200-office", "Desk chairs", "2310.00", "USD", ""},

		// Large, round, and in another currency.
		{"e-008", "2026-06-02T10:00:00Z", "6300-capex", "Server cluster", "80000.00", "EUR", "receipts/2026-Q2/e-008.pdf"},

		// Saturday.
		{"e-009", "2026-06-13T19:45:00Z", "6000-travel", "Weekend site visit", "640.00", "GBP", "receipts/2026-Q2/e-009.pdf"},

		// Credits, not quite balancing the debits.
		{"e-010", "2026-06-28T23:59:00Z", "1000-cash", "Quarter settlements", "-95262.85", "USD", "receipts/2026-Q2/e-010.pdf"},
	}

	p.AddPostgresFunc("ledger", func(sql string, params []any) (*res.Rows, error) {
		if !strings.Contains(strings.ToLower(sql), "ledger_entries") {
			return nil, fmt.Errorf("fixtures: unexpected ledger query: %s", sql)
		}
		if len(params) > 0 {
			if period, ok := params[0].(string); ok && period != "2026-Q2" {
				return &res.Rows{Columns: cols, Rows: [][]any{}}, nil
			}
		}
		return &res.Rows{Columns: cols, Rows: rows}, nil
	})

	for _, key := range []string{
		"receipts/2026-Q2/e-001.pdf", "receipts/2026-Q2/e-002.pdf", "receipts/2026-Q2/e-003.pdf",
		"receipts/2026-Q2/e-004.pdf", "receipts/2026-Q2/e-005.pdf",
		"receipts/2026-Q2/e-008.pdf", "receipts/2026-Q2/e-009.pdf", "receipts/2026-Q2/e-010.pdf",
		"receipts/2026-Q2/e-999.pdf", // orphan: no entry references it
	} {
		p.AddS3Object("receipts", key, []byte("%PDF-1.4 "+key))
	}

	// rates[X] is X per one USD.
	p.AddJSONEndpoint("fx", "https://fx.example/v1/latest?base=USD", map[string]any{
		"base":  "USD",
		"rates": map[string]float64{"EUR": 0.90, "GBP": 0.80, "JPY": 150.0},
	})
}

// GrantFinanceFull grants everything the finance pipeline needs.
func GrantFinanceFull(p *ptnfake.Proxy) {
	p.Grant("ledger", ptnfake.Grant{Verbs: []string{"query"}})
	p.Grant("receipts", ptnfake.Grant{Verbs: []string{"get", "list"}, KeyPrefix: "receipts/"})
	p.Grant("fx", ptnfake.Grant{Verbs: []string{"request"}, URLAllow: []string{"https://fx.example/"}})
}

// ---------- telemetry ----------

// FlightCSV renders a synthetic flight as CSV.
//
// Generated rather than stored so a test can ask for 200 samples or 60,000
// without a 60,000-row file in the repo, and so the shape of the flight is
// stated as arithmetic anyone can check rather than as data nobody will.
//
// Profile: 5s on the pad, powered ascent to burnout, ballistic coast to apogee,
// descent under drogue. Planted defects:
//
//	a chamber-pressure spike at t=8 -> a max excursion
//	a single blank altitude cell    -> a skipped-value path, not a skipped row
//	one ragged row                  -> a skipped row
func FlightCSV(samples int) []byte {
	var b strings.Builder
	b.WriteString("t,altitude_m,velocity_ms,chamber_pressure_bar,stage\n")

	const (
		dt       = 0.1
		burnout  = 12.0
		accel    = 32.0
		gravity  = 9.81
		nominalP = 42.0
	)

	alt, vel := 0.0, 0.0
	for i := 0; i < samples; i++ {
		t := float64(i) * dt
		pressure := 0.0

		switch {
		case t < 5.0: // on the pad
			alt, vel = 0, 0
		case t < 5.0+burnout: // powered
			vel += (accel - gravity) * dt
			alt += vel * dt
			pressure = nominalP
		default: // unpowered
			vel -= gravity * dt
			alt += vel * dt
			if alt < 0 {
				// Clamp AFTER integrating, not before. Clamping first lets the
				// altitude sit negative for one sample and then jump to zero,
				// which reads downstream as a vertical speed no vehicle
				// achieved -- a fixture artifact masquerading as data.
				alt, vel = 0, 0
			}
		}

		// Planted: a pressure spike well above any plausible limit.
		if t >= 7.9 && t < 8.1 {
			pressure = 96.4
		}

		stage := "coast"
		switch {
		case t < 5.0:
			stage = "prelaunch"
		case t < 5.0+burnout:
			stage = "powered"
		case vel < 0:
			stage = "descent"
		}

		switch {
		case i == 40: // planted: a blank altitude cell, not a blank row
			fmt.Fprintf(&b, "%.1f,,%.3f,%.2f,%s\n", t, vel, pressure, stage)
		case i == 41: // planted: a ragged row the parser must skip
			fmt.Fprintf(&b, "%.1f,%.3f\n", t, alt)
		default:
			fmt.Fprintf(&b, "%.1f,%.3f,%.3f,%.2f,%s\n", t, alt, vel, pressure, stage)
		}
	}
	return []byte(b.String())
}

// Telemetry seeds the flight-diagnostics dataset.
func Telemetry(p *ptnfake.Proxy, samples int) {
	p.AddS3Object("telemetry", "flights/F-118/telemetry.csv", FlightCSV(samples))
}

// GrantTelemetryFull grants what the telemetry pipeline needs.
func GrantTelemetryFull(p *ptnfake.Proxy) {
	p.Grant("telemetry", ptnfake.Grant{Verbs: []string{"get", "list"}, KeyPrefix: "flights/"})
}

// ---------- clinical ----------

var clinicalCols = []kernel.Column{
	{Name: "patient_id", Type: "string"},
	{Name: "ward", Type: "string"},
	{Name: "status", Type: "string"},
	{Name: "admitted_on", Type: "string"},
	{Name: "diagnosis", Type: "string"},
}

var clinicalRows = [][]any{
	{"p-001", "cardiology", "admitted", "2026-06-01", "Atrial fibrillation"},
	{"p-002", "cardiology", "discharged", "2026-05-18", "Stable angina"},
	{"p-003", "oncology", "admitted", "2026-06-11", "Stage II carcinoma"},
	{"p-004", "oncology", "admitted", "2026-06-14", "Lymphoma, follow-up"},
	{"p-005", "neurology", "admitted", "2026-06-02", "Post-ictal observation"},
	{"p-006", "cardiology", "admitted", "2026-06-20", "Heart failure, NYHA II"},
}

// Clinical seeds the clinical-summary dataset: six patients across three wards,
// with scans for four of them.
func Clinical(p *ptnfake.Proxy) {
	p.AddPostgresFunc("records", func(sql string, params []any) (*res.Rows, error) {
		if !strings.Contains(strings.ToLower(sql), "patients") {
			return nil, fmt.Errorf("fixtures: unexpected records query: %s", sql)
		}
		ward, status := "", ""
		if len(params) > 0 {
			ward, _ = params[0].(string)
		}
		if len(params) > 1 {
			status, _ = params[1].(string)
		}
		out := [][]any{}
		for _, r := range clinicalRows {
			if ward != "" && r[1] != ward {
				continue
			}
			if status != "" && r[2] != status {
				continue
			}
			out = append(out, r)
		}
		return &res.Rows{Columns: clinicalCols, Rows: out}, nil
	})

	// p-004 and p-005 deliberately have no scans.
	for _, key := range []string{
		"scans/p-001/chest-01.png",
		"scans/p-002/chest-01.png",
		"scans/p-003/abdomen-01.png",
		"scans/p-003/abdomen-02.png",
		"scans/p-006/chest-01.png",
	} {
		p.AddS3Object("scans", key, []byte("\x89PNG "+key))
	}
}

// GrantClinicalAll is the unrestricted clinician: every ward.
func GrantClinicalAll(p *ptnfake.Proxy) {
	p.Grant("records", ptnfake.Grant{Verbs: []string{"query"}})
	p.Grant("scans", ptnfake.Grant{Verbs: []string{"get", "list"}, KeyPrefix: "scans/"})
}

// GrantClinicalWard is the scoped clinician: one ward's patients, and only the
// scans belonging to them.
//
// This is the other half of the permission beat. Both grants are applied
// proxy-side and neither action knows which one is in force.
func GrantClinicalWard(p *ptnfake.Proxy, ward string, scanPrefix string) {
	p.Grant("records", ptnfake.Grant{
		Verbs:     []string{"query"},
		RowFilter: func(row map[string]any) bool { return row["ward"] == ward },
	})
	p.Grant("scans", ptnfake.Grant{Verbs: []string{"get", "list"}, KeyPrefix: scanPrefix})
}

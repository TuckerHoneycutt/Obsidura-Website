package finance_test

import (
	"strings"
	"testing"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/finance"
	"github.com/obsidura/pantheon-go/fixtures"
	"github.com/obsidura/pantheon-go/ptnfake"
)

// Named mutation table for the finance vertical.
//
// A fix is not pinned until a named mutation reddens it (aurora/AGENTS.md #6).
// Each row names a change to production code and the test that must fail when
// it is made. A mutation that stays green fails spec review and is never
// suppressible.
//
//	mutation                                              | reddens
//	------------------------------------------------------|-------------------------------------------
//	Money.Add drops the currency-mismatch check            | TestReconcileRefusesUnnormalisedLedger
//	ParseMoney multiplies a parsed float instead of        | TestPennyExactArithmetic
//	  parsing the string                                   |
//	normalizeFX uses rates[X] instead of 1/rates[X]        | TestNormalizeFXConvertsAtPublishedRate
//	normalizeFX skips the base-currency mismatch check     | TestNormalizeFXRefusesRebasing
//	reconcileLedger sorts nothing                          | TestReconcileIsStableAcrossRuns
//	reconcileLedger tests imbalance with a float epsilon   | TestReconcileDetectsPlantedImbalance
//	matchReceipts reports only unmatched entries           | TestMatchReceiptsFindsOrphanReceipt
//	matchReceipts treats "" and missing key the same       | TestMatchReceiptsDistinguishesNoReceiptFromMissing
//	flagAnomalies uses StdDev instead of MAD               | TestFlagAnomaliesFindsPlantedOutlier
//	flagAnomalies keys duplicates on entry_id              | TestFlagAnomaliesFindsPlantedDuplicate
//	fetchLedger reads columns by index                     | TestFetchLedgerToleratesExtraColumns
//	any action adds a user predicate to its SQL            | TestFinanceActionsTakeNoUserIdentity

func setup(t *testing.T) (*ptnfake.Proxy, *action.Registry) {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Close() })
	fixtures.Finance(p)
	fixtures.GrantFinanceFull(p)

	r := action.NewRegistry()
	finance.Register(r)
	return p, r
}

// fullPipeline runs fetch -> normalise, returning the normalised handle.
func fullPipeline(t *testing.T, p *ptnfake.Proxy, r *action.Registry) finance.NormalizedLedger {
	t.Helper()

	var extract finance.LedgerExtract
	res := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"})
	if err := res.Record(&extract); err != nil {
		t.Fatalf("fetch_ledger: %v", err)
	}

	var norm finance.NormalizedLedger
	res = p.Invoke(r, "finance.normalize_fx", finance.FXNormalizeRequest{
		Ledger:       extract.Ledger,
		BaseCurrency: "USD",
		RatesURL:     "https://fx.example/v1/latest?base=USD",
	})
	if err := res.Record(&norm); err != nil {
		t.Fatalf("normalize_fx: %v", err)
	}
	return norm
}

func TestFetchLedgerProducesATableHandle(t *testing.T) {
	p, r := setup(t)

	var out finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&out); err != nil {
		t.Fatal(err)
	}

	if out.RowCount != 10 {
		t.Errorf("expected 10 ledger entries, got %d", out.RowCount)
	}
	if got := strings.Join(out.Currencies, ","); got != "EUR,GBP,USD" {
		t.Errorf("currencies should be sorted and distinct, got %q", got)
	}
	if out.Ledger.Blob == "" {
		t.Error("no table handle was produced; rows must travel by handle, not inline")
	}
	// The rows must be IN the handle, not just counted.
	_, rows, ok := p.TableRows(out.Ledger)
	if !ok || len(rows) != 10 {
		t.Errorf("table handle holds %d rows (found=%v)", len(rows), ok)
	}
}

func TestFetchLedgerRefusesAnAmountWithNoCurrency(t *testing.T) {
	p, r := setup(t)
	// Override the fixture with a row missing its currency.
	p.AddPostgresRows("ledger", `select entry_id, posted_at, account, description, amount, currency, receipt_key
from ledger_entries
where period = $1
order by posted_at, entry_id`,
		ledgerCols(), [][]any{
			{"e-x", "2026-04-01T00:00:00Z", "1000-cash", "Mystery", "10.00", "", ""},
		})

	res := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"})
	if res.Err == nil {
		t.Fatal("an amount with no currency must be refused; it cannot be summed with anything")
	}
	if !strings.Contains(res.Err.Error(), "currency") {
		t.Errorf("error should name the missing currency, got: %v", res.Err)
	}
}

// A tenant's ledger view carries columns this vertical type does not model.
// Reading by name rather than by index is what lets one action serve them all.
func TestFetchLedgerToleratesExtraColumns(t *testing.T) {
	p, r := setup(t)
	cols := ledgerCols()
	// Insert a tenant-specific column in the MIDDLE, where positional reads break.
	cols = append(cols[:2:2], append([]kernelColumn{{Name: "acme_cost_centre", Type: "string"}}, cols[2:]...)...)

	p.AddPostgresRows("ledger", `select entry_id, posted_at, account, description, amount, currency, receipt_key
from ledger_entries
where period = $1
order by posted_at, entry_id`,
		cols, [][]any{
			{"e-1", "2026-04-01T00:00:00Z", "CC-42", "1000-cash", "Opening", "100.00", "USD", ""},
		})

	var out finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&out); err != nil {
		t.Fatalf("an extra tenant column must not break the action: %v", err)
	}
	_, rows, _ := p.TableRows(out.Ledger)
	if len(rows) != 1 || rows[0][0] != "e-1" || rows[0][2] != "1000-cash" {
		t.Errorf("columns were read positionally, not by name: %+v", rows)
	}
}

func TestNormalizeFXConvertsAtPublishedRate(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	if norm.BaseCurrency != "USD" {
		t.Errorf("base currency is %q", norm.BaseCurrency)
	}
	// e-008 (EUR) and e-009 (GBP) are the only non-USD entries.
	if norm.ConvertedRows != 2 {
		t.Errorf("expected 2 converted rows, got %d", norm.ConvertedRows)
	}

	_, rows, ok := p.TableRows(norm.Ledger)
	if !ok {
		t.Fatal("no normalised table")
	}
	// rates[EUR] = 0.90 EUR per USD, so 80,000.00 EUR is 80000/0.90 = 88,888.89 USD.
	// If the code multiplied instead of dividing it would be 72,000.00.
	var found bool
	for _, row := range rows {
		if row[0] == "e-008" {
			found = true
			// Values arrive as float64 because they crossed JSON, exactly as
			// they would through the real proxy. Minor units stay exact well
			// past 2^53, so the comparison is still an equality, not an epsilon.
			got := toInt64(t, row[4])
			if got != 8888889 {
				t.Errorf("e-008 converted to %d minor units, want 8888889 (80000 EUR / 0.90); "+
					"a multiplied rate would give 7200000", got)
			}
			if row[5] != "USD" {
				t.Errorf("e-008 currency is %v after conversion", row[5])
			}
		}
	}
	if !found {
		t.Error("e-008 is missing from the normalised ledger")
	}
}

func TestNormalizeFXRefusesRebasing(t *testing.T) {
	p, r := setup(t)
	var extract finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&extract); err != nil {
		t.Fatal(err)
	}

	// The endpoint publishes USD-based rates; ask for EUR.
	res := p.Invoke(r, "finance.normalize_fx", finance.FXNormalizeRequest{
		Ledger:       extract.Ledger,
		BaseCurrency: "EUR",
		RatesURL:     "https://fx.example/v1/latest?base=USD",
	})
	if res.Err == nil {
		t.Fatal("silently re-basing someone else's rate table must be refused")
	}
}

func TestNormalizeFXIsDeniedOffAllowlist(t *testing.T) {
	p, r := setup(t)
	var extract finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&extract); err != nil {
		t.Fatal(err)
	}

	res := p.Invoke(r, "finance.normalize_fx", finance.FXNormalizeRequest{
		Ledger:       extract.Ledger,
		BaseCurrency: "USD",
		RatesURL:     "https://evil.example/rates",
	})
	if res.Err == nil {
		t.Fatal("a URL off the allowlist must be refused by the proxy")
	}
	// The refusal must be visible in the audit log, not only in the error.
	var sawDeny bool
	for _, a := range p.Audit() {
		if !a.Allowed && strings.Contains(a.Detail, "evil.example") {
			sawDeny = true
		}
	}
	if !sawDeny {
		t.Errorf("the denial is not in the audit log: %v", p.AuditLines())
	}
}

func TestReconcileDetectsPlantedImbalance(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.ReconciliationReport
	if err := p.Invoke(r, "finance.reconcile_ledger", finance.ReconcileRequest{
		Ledger: norm.Ledger, BaseCurrency: "USD", Period: "2026-Q2",
	}).Record(&report); err != nil {
		t.Fatal(err)
	}

	if report.Balanced {
		t.Errorf("the fixture ledger is deliberately imbalanced; the report says it balances (imbalance %q)",
			report.Imbalance)
	}
	if report.EntryCount != 10 {
		t.Errorf("reconciled %d entries, want 10", report.EntryCount)
	}
	if len(report.ByAccount) == 0 {
		t.Fatal("no per-account totals")
	}
	// Per-account nets must sum to the reported imbalance, exactly.
	var sum int64
	for _, a := range report.ByAccount {
		sum += a.NetMinor
	}
	wantImbalance, err := parseMinor(report.Imbalance)
	if err != nil {
		t.Fatal(err)
	}
	if sum != wantImbalance {
		t.Errorf("per-account nets sum to %d but the report's imbalance is %d", sum, wantImbalance)
	}
}

func TestReconcileRefusesUnnormalisedLedger(t *testing.T) {
	p, r := setup(t)

	var extract finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&extract); err != nil {
		t.Fatal(err)
	}

	// The raw ledger has EUR and GBP in it. Reconciling it as USD would produce
	// a number that looks like money and is not.
	res := p.Invoke(r, "finance.reconcile_ledger", finance.ReconcileRequest{
		Ledger: extract.Ledger, BaseCurrency: "USD", Period: "2026-Q2",
	})
	if res.Err == nil {
		t.Fatal("reconciling a mixed-currency ledger must be refused, not silently summed")
	}
	if !strings.Contains(res.Err.Error(), "normalise") {
		t.Errorf("the error should tell the caller what to do; got: %v", res.Err)
	}
}

func TestReconcileIsStableAcrossRuns(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	req := finance.ReconcileRequest{Ledger: norm.Ledger, BaseCurrency: "USD", Period: "2026-Q2"}
	first := p.Invoke(r, "finance.reconcile_ledger", req)
	second := p.Invoke(r, "finance.reconcile_ledger", req)
	if first.Err != nil || second.Err != nil {
		t.Fatalf("%v / %v", first.Err, second.Err)
	}

	a, _ := first.Value.Record.Data.MarshalJSON()
	b, _ := second.Value.Record.Data.MarshalJSON()
	if string(a) != string(b) {
		t.Errorf("two runs over identical data produced different reports;\nfirst:  %s\nsecond: %s", a, b)
	}
}

func TestMatchReceiptsDistinguishesNoReceiptFromMissing(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.ReceiptMatchReport
	if err := p.Invoke(r, "finance.match_receipts", finance.ReceiptMatchRequest{
		Ledger: norm.Ledger, ReceiptPrefix: "receipts/2026-Q2/",
	}).Record(&report); err != nil {
		t.Fatal(err)
	}

	reasons := map[string]string{}
	for _, u := range report.UnmatchedEntries {
		reasons[u.EntryID] = u.Reason
	}

	// e-006 claims a receipt that is absent; e-007 claims none at all. A
	// reviewer chases those two findings differently, so they must not collapse.
	if !strings.Contains(reasons["e-006"], "not found") {
		t.Errorf("e-006 claims a missing receipt; reason was %q", reasons["e-006"])
	}
	if !strings.Contains(reasons["e-007"], "no receipt referenced") {
		t.Errorf("e-007 references no receipt; reason was %q", reasons["e-007"])
	}
	if reasons["e-006"] == reasons["e-007"] {
		t.Error("the two unmatched cases must be distinguishable")
	}
}

func TestMatchReceiptsFindsOrphanReceipt(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.ReceiptMatchReport
	if err := p.Invoke(r, "finance.match_receipts", finance.ReceiptMatchRequest{
		Ledger: norm.Ledger, ReceiptPrefix: "receipts/2026-Q2/",
	}).Record(&report); err != nil {
		t.Fatal(err)
	}

	// A payment nobody recorded is at least as interesting as a missing receipt,
	// and is the half most tools omit.
	if len(report.OrphanReceipts) != 1 || !strings.Contains(report.OrphanReceipts[0], "e-999") {
		t.Errorf("expected exactly the planted orphan receipt, got %v", report.OrphanReceipts)
	}
	if report.Matched != 8 {
		t.Errorf("matched %d entries, want 8", report.Matched)
	}
}

func TestFlagAnomaliesFindsPlantedOutlier(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.AnomalyReport
	if err := p.Invoke(r, "finance.flag_anomalies", finance.AnomalyRequest{Ledger: norm.Ledger}).Record(&report); err != nil {
		t.Fatal(err)
	}

	byRule := map[string][]string{}
	for _, a := range report.Anomalies {
		byRule[a.Rule] = append(byRule[a.Rule], a.EntryID)
	}

	// e-008 (88,888.89 USD after conversion) and e-010 (-95,262.85) are far
	// above the median. Standard deviation would be inflated by them and might
	// flag neither -- the masking effect MAD exists to avoid.
	if len(byRule[finance.RuleOutlier]) == 0 {
		t.Errorf("no outlier flagged; the fixture contains two entries an order of magnitude above the median.\nfull report: %+v", report)
	}
}

func TestFlagAnomaliesFindsPlantedDuplicate(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.AnomalyReport
	if err := p.Invoke(r, "finance.flag_anomalies", finance.AnomalyRequest{Ledger: norm.Ledger}).Record(&report); err != nil {
		t.Fatal(err)
	}

	dupes := map[string]bool{}
	for _, a := range report.Anomalies {
		if a.Rule == finance.RuleDuplicate {
			dupes[a.EntryID] = true
		}
	}
	// Both halves of the pair are reported: a reviewer needs to see both to
	// decide which is the erroneous one.
	if !dupes["e-004"] || !dupes["e-005"] {
		t.Errorf("the planted duplicate pair e-004/e-005 was not flagged; got %v", dupes)
	}
}

func TestFlagAnomaliesFindsWeekendPosting(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.AnomalyReport
	if err := p.Invoke(r, "finance.flag_anomalies", finance.AnomalyRequest{Ledger: norm.Ledger}).Record(&report); err != nil {
		t.Fatal(err)
	}
	for _, a := range report.Anomalies {
		if a.Rule == finance.RuleWeekend && a.EntryID == "e-009" {
			if !strings.Contains(a.Detail, "Saturday") {
				t.Errorf("detail should name the day, got %q", a.Detail)
			}
			return
		}
	}
	t.Errorf("e-009 is posted on 2026-06-13, a Saturday, and was not flagged: %+v", report.CountByRule)
}

func TestFlagAnomaliesIsStableAcrossRuns(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	req := finance.AnomalyRequest{Ledger: norm.Ledger}
	a := p.Invoke(r, "finance.flag_anomalies", req)
	b := p.Invoke(r, "finance.flag_anomalies", req)
	if a.Err != nil || b.Err != nil {
		t.Fatalf("%v / %v", a.Err, b.Err)
	}
	x, _ := a.Value.Record.Data.MarshalJSON()
	y, _ := b.Value.Record.Data.MarshalJSON()
	if string(x) != string(y) {
		t.Error("anomaly reports must be byte-identical across runs, or they cannot be reviewed by diff")
	}
}

// An action that reached a resource it did not declare would be refused by the
// proxy in production. The declaration check turns that into a clear local
// error the first time a unit test runs.
func TestUndeclaredResourceIsRefusedLocally(t *testing.T) {
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	defer p.Close()
	fixtures.Finance(p)
	fixtures.GrantFinanceFull(p)

	r := action.NewRegistry()
	// reconcile_ledger declares no resources at all, so any proxy call from it
	// must fail the declaration check before it reaches the socket.
	action.Register(r, action.Spec{
		Name: "test.undeclared", Version: 1,
		Input:   kernelRef("finance.LedgerQuery", 1),
		Output:  kernelRef("finance.LedgerExtract", 1),
		Policy:  action.Policy{Timeout: mustSeconds(5)},
		Summary: "Reaches a resource it never declared.",
	}, func(c *action.Ctx, in finance.LedgerQuery) (finance.LedgerExtract, error) {
		_, err := c.Postgres("ledger").Query("select 1")
		return finance.LedgerExtract{}, err
	})

	res := p.Invoke(r, "test.undeclared", finance.LedgerQuery{Period: "2026-Q2"})
	if res.Err == nil {
		t.Fatal("an undeclared resource must be refused")
	}
	if !strings.Contains(res.Err.Error(), "Spec.Uses") {
		t.Errorf("the error should point at the declaration, got: %v", res.Err)
	}
}

// The round_number and missing_account rules do not fire on the shared fixture
// (see fixtures.Finance's note), so they are exercised directly. A rule with no
// test is a rule that quietly stopped working.
func TestFlagAnomaliesFindsRoundNumbersAndMissingAccounts(t *testing.T) {
	p, r := setup(t)
	p.AddPostgresRows("ledger", `select entry_id, posted_at, account, description, amount, currency, receipt_key
from ledger_entries
where period = $1
order by posted_at, entry_id`,
		ledgerCols(), [][]any{
			// Exactly 25,000.00 USD: above the round-number floor and an exact
			// multiple of 1000.00.
			{"r-001", "2026-04-07T10:00:00Z", "6300-capex", "Round payment", "25000.00", "USD", ""},
			// Above the floor but not round.
			{"r-002", "2026-04-08T10:00:00Z", "6300-capex", "Odd payment", "25000.01", "USD", ""},
			// Round but below the floor.
			{"r-003", "2026-04-09T10:00:00Z", "6300-capex", "Small round", "2000.00", "USD", ""},
			// No account assigned.
			{"r-004", "2026-04-10T10:00:00Z", "", "Unassigned", "17.50", "USD", ""},
		})

	var extract finance.LedgerExtract
	if err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Record(&extract); err != nil {
		t.Fatal(err)
	}

	var report finance.AnomalyReport
	if err := p.Invoke(r, "finance.flag_anomalies", finance.AnomalyRequest{Ledger: extract.Ledger}).Record(&report); err != nil {
		t.Fatal(err)
	}

	byRule := map[string][]string{}
	for _, a := range report.Anomalies {
		byRule[a.Rule] = append(byRule[a.Rule], a.EntryID)
	}

	round := strings.Join(byRule[finance.RuleRoundNumber], ",")
	if round != "r-001" {
		t.Errorf("round_number flagged %q; want exactly r-001 "+
			"(r-002 is not round, r-003 is below the floor)", round)
	}
	if got := strings.Join(byRule[finance.RuleNoAccount], ","); got != "r-004" {
		t.Errorf("missing_account flagged %q, want r-004", got)
	}
}

// The deliberately-imbalanced fixture is what makes the reconciliation test
// meaningful. If someone "fixes" the fixture, this says so rather than letting
// TestReconcileDetectsPlantedImbalance quietly start passing for a new reason.
func TestFixtureLedgerIsDeliberatelyImbalanced(t *testing.T) {
	p, r := setup(t)
	norm := fullPipeline(t, p, r)

	var report finance.ReconciliationReport
	if err := p.Invoke(r, "finance.reconcile_ledger", finance.ReconcileRequest{
		Ledger: norm.Ledger, BaseCurrency: "USD", Period: "2026-Q2",
	}).Record(&report); err != nil {
		t.Fatal(err)
	}
	imbalance, err := parseMinor(report.Imbalance)
	if err != nil {
		t.Fatal(err)
	}
	if imbalance == 0 {
		t.Fatal("the fixture must not balance, or the imbalance test proves nothing")
	}
	t.Logf("fixture imbalance is %s USD, as intended", report.Imbalance)
}

// Scope is the proxy's job in every vertical, not only the clinical one. This
// reads the SQL out of the audit log -- the artifact the run actually produced
// -- rather than inspecting a string constant the action might not use.
func TestFinanceActionsTakeNoUserIdentity(t *testing.T) {
	p, r := setup(t)
	if _, err := p.Invoke(r, "finance.fetch_ledger", finance.LedgerQuery{Period: "2026-Q2"}).Value.MarshalJSON(); err != nil {
		t.Fatal(err)
	}

	audit := p.Audit()
	if len(audit) == 0 {
		t.Fatal("no proxy calls recorded; the assertion below would be vacuous")
	}
	for _, a := range audit {
		sql := strings.ToLower(a.Detail)
		for _, needle := range []string{"user_id", "requester", "current_user", "role =", "owner ="} {
			if strings.Contains(sql, needle) {
				t.Errorf("query contains %q: %s\nAuthorisation belongs in the grant, not the action's SQL",
					needle, a.Detail)
			}
		}
	}

	// And the input type must not offer a place to put one.
	blob := ledgerQueryFields(t)
	for _, f := range []string{"requester", "user", "user_id", "role"} {
		if strings.Contains(blob, f) {
			t.Errorf("LedgerQuery carries a %q field", f)
		}
	}
}

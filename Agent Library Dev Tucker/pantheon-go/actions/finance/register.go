package finance

import (
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
)

// Register adds the finance vertical to a registry.
//
// A function rather than an init(): a test can build a registry holding only
// this vertical, and the runner binary decides what it serves rather than
// inheriting whatever happened to be linked in.
func Register(r *action.Registry) {
	action.Register(r, action.Spec{
		Name:    "finance.fetch_ledger",
		Version: 1,
		Input:   kernel.Ref("finance.LedgerQuery", 1),
		Output:  kernel.Ref("finance.LedgerExtract", 1),
		Uses:    []action.ResourceUse{{Name: ResLedger, Verbs: []string{"query"}}},
		// Idempotent: a pure read that writes only a content-addressed table,
		// so a retry produces the same handle rather than a second copy.
		Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Pull one accounting period's ledger entries into a table.",
	}, fetchLedger)

	action.Register(r, action.Spec{
		Name:    "finance.normalize_fx",
		Version: 1,
		Input:   kernel.Ref("finance.FXNormalizeRequest", 1),
		Output:  kernel.Ref("finance.NormalizedLedger", 1),
		Uses:    []action.ResourceUse{{Name: ResFX, Verbs: []string{"request"}}},
		Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Convert every ledger amount into a single base currency.",
	}, normalizeFX)

	action.Register(r, action.Spec{
		Name:    "finance.reconcile_ledger",
		Version: 1,
		Input:   kernel.Ref("finance.ReconcileRequest", 1),
		Output:  kernel.Ref("finance.ReconciliationReport", 1),
		// No Uses at all: it reads the table handed to it and nothing else.
		// Worth stating rather than leaving implied.
		Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Total the ledger by account and report whether it balances.",
	}, reconcileLedger)

	action.Register(r, action.Spec{
		Name:    "finance.match_receipts",
		Version: 1,
		Input:   kernel.Ref("finance.ReceiptMatchRequest", 1),
		Output:  kernel.Ref("finance.ReceiptMatchReport", 1),
		Uses:    []action.ResourceUse{{Name: ResReceipts, Verbs: []string{"get", "list"}}},
		Policy:  action.Policy{Timeout: 120 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Find ledger entries with no receipt, and receipts with no ledger entry.",
	}, matchReceipts)

	action.Register(r, action.Spec{
		Name:    "finance.flag_anomalies",
		Version: 1,
		Input:   kernel.Ref("finance.AnomalyRequest", 1),
		Output:  kernel.Ref("finance.AnomalyReport", 1),
		Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Flag unusual ledger entries: outliers, duplicates, round numbers, weekend postings.",
	}, flagAnomalies)
}

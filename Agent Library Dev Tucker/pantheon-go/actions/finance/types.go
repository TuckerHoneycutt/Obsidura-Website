// Package finance is the financial-audit vertical of the deck.
//
// Five actions covering one real pipeline: pull the ledger, normalise its
// currencies, reconcile it, match its receipts, and flag what looks wrong.
// Every one is deterministic (runner: script). Judgement -- deciding what a
// flagged anomaly MEANS -- belongs to an agent task wired downstream, not here.
//
// These are VERTICAL types. A tenant's own type may add fields and narrow
// constraints but never contradict, so an action written once against Entry
// runs on AcmeEntry. Refinement checking itself is deferred (spec §11); the Go
// approximation is the Raw field, which preserves what the vertical type does
// not model. See 02-architecture.md, Layer D.
package finance

import (
	"encoding/json"

	"github.com/obsidura/pantheon-go/kernel"
)

// Ledger table columns, in the order fetch_ledger emits them. Downstream
// actions address them by name, never by index.
const (
	ColEntryID     = "entry_id"
	ColPostedAt    = "posted_at"
	ColAccount     = "account"
	ColDescription = "description"
	ColAmountMinor = "amount_minor"
	ColCurrency    = "currency"
	ColReceiptKey  = "receipt_key"
)

// LedgerQuery asks for one period's ledger.
type LedgerQuery struct {
	Period string `json:"period" desc:"Accounting period identifier, e.g. 2026-Q2"`
}

// LedgerExtract is a ledger as a Table handle plus what a downstream action
// needs in order to decide what to do with it.
//
// The rows travel by handle, never inline (spec §6). A quarter's ledger is
// small; a year's for a large tenant is not, and an action that works only
// because the fixture was small is an action that fails on the real data.
type LedgerExtract struct {
	Ledger     kernel.TableHandle `json:"ledger"`
	Period     string             `json:"period"`
	RowCount   int                `json:"row_count"`
	Currencies []string           `json:"currencies" desc:"Distinct currencies present, sorted"`
}

// FXNormalizeRequest converts a ledger to a single base currency.
type FXNormalizeRequest struct {
	Ledger       kernel.TableHandle `json:"ledger"`
	BaseCurrency string             `json:"base_currency" desc:"ISO 4217 code every amount is converted to"`
	RatesURL     string             `json:"rates_url" desc:"Absolute URL of the rates endpoint; must be on the fx resource's allowlist"`
}

// NormalizedLedger is a ledger whose amounts share one currency.
type NormalizedLedger struct {
	Ledger        kernel.TableHandle `json:"ledger"`
	BaseCurrency  string             `json:"base_currency"`
	RowCount      int                `json:"row_count"`
	ConvertedRows int                `json:"converted_rows" desc:"Rows whose currency differed from the base"`
	RatesUsed     map[string]float64 `json:"rates_used" desc:"Every rate applied, for audit"`
}

// ReconcileRequest asks for a per-account reconciliation.
type ReconcileRequest struct {
	Ledger       kernel.TableHandle `json:"ledger"`
	BaseCurrency string             `json:"base_currency"`
	Period       string             `json:"period"`
}

// AccountTotal is one account's debits, credits and net.
//
// Amounts are decimal STRINGS, not numbers. A report consumer that parses
// "1234.56" into a float has made its own choice; a report that emits 1234.56
// as JSON has already lost the guarantee, because the number is re-encoded by
// every hop and JSON has no decimal type.
type AccountTotal struct {
	Account    string `json:"account"`
	EntryCount int    `json:"entry_count"`
	Debits     string `json:"debits"`
	Credits    string `json:"credits"`
	Net        string `json:"net"`
	NetMinor   int64  `json:"net_minor" desc:"Net in minor units, for exact downstream arithmetic"`
}

// ReconciliationReport is what a human signs.
type ReconciliationReport struct {
	Period       string         `json:"period"`
	BaseCurrency string         `json:"base_currency"`
	EntryCount   int            `json:"entry_count"`
	Debits       string         `json:"debits"`
	Credits      string         `json:"credits"`
	Imbalance    string         `json:"imbalance" desc:"Debits plus credits; non-zero means the ledger does not balance"`
	Balanced     bool           `json:"balanced"`
	ByAccount    []AccountTotal `json:"by_account" desc:"Sorted by account name"`
}

// ReceiptMatchRequest pairs ledger entries with stored receipt documents.
type ReceiptMatchRequest struct {
	Ledger        kernel.TableHandle `json:"ledger"`
	ReceiptPrefix string             `json:"receipt_prefix" desc:"Key prefix to enumerate, e.g. receipts/2026-Q2/"`
}

// UnmatchedEntry is a ledger entry with no receipt behind it.
type UnmatchedEntry struct {
	EntryID     string `json:"entry_id"`
	PostedAt    string `json:"posted_at"`
	Account     string `json:"account"`
	Description string `json:"description"`
	Amount      string `json:"amount"`
	ReceiptKey  string `json:"receipt_key" desc:"Empty when the entry claims no receipt; set when it claims one that is absent"`
	Reason      string `json:"reason"`
}

// ReceiptMatchReport is the two-sided result: entries with no document, and
// documents with no entry. Both directions matter -- an orphan receipt is a
// payment nobody recorded, which is at least as interesting as the reverse.
type ReceiptMatchReport struct {
	EntriesChecked   int              `json:"entries_checked"`
	ReceiptsFound    int              `json:"receipts_found"`
	Matched          int              `json:"matched"`
	UnmatchedEntries []UnmatchedEntry `json:"unmatched_entries"`
	OrphanReceipts   []string         `json:"orphan_receipts" desc:"Receipt keys no ledger entry references"`
}

// AnomalyRequest configures the heuristics.
type AnomalyRequest struct {
	Ledger kernel.TableHandle `json:"ledger"`

	// ZThreshold is the robust z-score past which an amount is unusual.
	// Zero means the default; see DefaultZThreshold.
	ZThreshold float64 `json:"z_threshold,omitempty" desc:"Robust z-score threshold for unusual amounts; default 3.5"`

	// RoundNumberMinor flags suspiciously round amounts at or above this size.
	// Zero means the default.
	RoundNumberMinor int64 `json:"round_number_minor,omitempty" desc:"Flag round amounts at or above this many minor units; default 1000000"`
}

// Anomaly is one flagged entry.
//
// Severity is advisory and deliberately coarse. A finance action's job is to
// surface candidates with the evidence; deciding which matter is judgement, and
// judgement belongs to an agent task or a human, not to a threshold in Go.
type Anomaly struct {
	EntryID     string  `json:"entry_id"`
	PostedAt    string  `json:"posted_at"`
	Account     string  `json:"account"`
	Description string  `json:"description"`
	Amount      string  `json:"amount"`
	Rule        string  `json:"rule" desc:"Which heuristic fired: outlier | duplicate | round_number | weekend | missing_account"`
	Detail      string  `json:"detail"`
	Score       float64 `json:"score,omitempty" desc:"Rule-specific magnitude; robust z-score for outlier"`
}

// AnomalyReport summarises what fired.
type AnomalyReport struct {
	EntriesChecked int            `json:"entries_checked"`
	Anomalies      []Anomaly      `json:"anomalies" desc:"Sorted by rule then entry id, for stable diffs between runs"`
	CountByRule    map[string]int `json:"count_by_rule"`
	Median         string         `json:"median" desc:"Median absolute amount, the baseline outlier detection used"`
}

// Entry is the vertical ledger-entry type, for actions that work with decoded
// rows rather than a streamed table.
type Entry struct {
	EntryID     string `json:"entry_id"`
	PostedAt    string `json:"posted_at"`
	Account     string `json:"account"`
	Description string `json:"description"`
	AmountMinor int64  `json:"amount_minor"`
	Currency    string `json:"currency"`
	ReceiptKey  string `json:"receipt_key"`

	// Raw preserves the tenant's full payload, including fields this vertical
	// type does not model. It is how one action serves every tenant without
	// forking, and it is deliberately excluded from the schema (json:"-").
	Raw json.RawMessage `json:"-"`
}

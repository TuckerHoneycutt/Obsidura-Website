package finance

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/core"
	"github.com/obsidura/pantheon-go/table"
)

type accountAcc struct {
	entries int
	debits  int64
	credits int64
}

// reconcileLedger totals a normalised ledger per account and reports whether it
// balances.
//
// Convention: a positive amount is a debit, a negative amount is a credit, and
// a balanced double-entry ledger sums to exactly zero. "Exactly" is meant
// literally -- the arithmetic is in integer minor units, so a zero imbalance is
// a real zero rather than 1e-9, and a one-cent imbalance is visible rather than
// lost in floating-point noise.
func reconcileLedger(c *action.Ctx, in ReconcileRequest) (ReconciliationReport, error) {
	base := strings.ToUpper(strings.TrimSpace(in.BaseCurrency))
	if base == "" {
		return ReconciliationReport{}, fmt.Errorf("base_currency is required")
	}

	cur, err := c.OpenTable(in.Ledger)
	if err != nil {
		return ReconciliationReport{}, fmt.Errorf("opening ledger table: %w", err)
	}

	accounts := map[string]*accountAcc{}
	var totalDebits, totalCredits int64
	count := 0

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		currency, err := row.String(ColCurrency)
		if err != nil {
			return err
		}
		if !strings.EqualFold(currency, base) {
			// Reconciling across currencies would produce a number that looks
			// like money and is not. Run finance.normalize_fx first.
			entryID, _ := row.String(ColEntryID)
			return fmt.Errorf("entry %s is in %s, not the base currency %s; normalise before reconciling",
				entryID, currency, base)
		}
		minor, _, err := row.Int(ColAmountMinor)
		if err != nil {
			return err
		}
		account, _ := row.String(ColAccount)
		if account == "" {
			account = "(unassigned)"
		}

		a := accounts[account]
		if a == nil {
			a = &accountAcc{}
			accounts[account] = a
		}
		a.entries++
		count++
		if minor >= 0 {
			a.debits += minor
			totalDebits += minor
		} else {
			a.credits += minor
			totalCredits += minor
		}
		return nil
	})
	if err != nil {
		return ReconciliationReport{}, err
	}

	names := make([]string, 0, len(accounts))
	for n := range accounts {
		names = append(names, n)
	}
	// Sorted so two runs over the same data produce byte-identical reports.
	// A report that reorders itself between runs cannot be diffed, and a report
	// nobody can diff stops being checked.
	sort.Strings(names)

	byAccount := make([]AccountTotal, 0, len(names))
	for _, n := range names {
		a := accounts[n]
		byAccount = append(byAccount, AccountTotal{
			Account:    n,
			EntryCount: a.entries,
			Debits:     core.Money{Minor: a.debits, Currency: base}.Major(),
			Credits:    core.Money{Minor: a.credits, Currency: base}.Major(),
			Net:        core.Money{Minor: a.debits + a.credits, Currency: base}.Major(),
			NetMinor:   a.debits + a.credits,
		})
	}

	imbalance := core.Money{Minor: totalDebits + totalCredits, Currency: base}
	report := ReconciliationReport{
		Period:       in.Period,
		BaseCurrency: base,
		EntryCount:   count,
		Debits:       core.Money{Minor: totalDebits, Currency: base}.Major(),
		Credits:      core.Money{Minor: totalCredits, Currency: base}.Major(),
		Imbalance:    imbalance.Major(),
		Balanced:     imbalance.IsZero(),
		ByAccount:    byAccount,
	}

	if !report.Balanced {
		c.Log("warn", "ledger does not balance", map[string]any{
			"imbalance": report.Imbalance, "period": in.Period,
		})
	}
	c.Emit("finance.reconciled", map[string]any{
		"period": in.Period, "entries": count, "balanced": report.Balanced,
		"imbalance_minor": imbalance.Minor,
	})

	return report, nil
}

package finance

import (
	"fmt"
	"sort"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/core"
	"github.com/obsidura/pantheon-go/kernel"
	"github.com/obsidura/pantheon-go/table"
)

// Logical resource names. An action names the resource it needs; which physical
// database that maps to is the definition's business, not the body's.
//
// This is why the names are constants rather than input fields. Spec §4 makes
// `uses:` a static declaration, and a resource name that arrives at runtime
// cannot be checked against a static declaration -- an action that chose its own
// resource could ask for one it never declared, which is precisely the check the
// declaration exists to make possible.
const (
	ResLedger   = "ledger"   // postgres
	ResReceipts = "receipts" // s3
	ResFX       = "fx"       // http
)

// ledgerColumns is the shape every finance action agrees on.
func ledgerColumns() []kernel.Column {
	return []kernel.Column{
		table.Col(ColEntryID, "string"),
		table.Col(ColPostedAt, "timestamp"),
		table.Col(ColAccount, "string"),
		table.Col(ColDescription, "string"),
		table.Col(ColAmountMinor, "int"),
		table.Col(ColCurrency, "string"),
		table.Col(ColReceiptKey, "string"),
	}
}

const fetchLedgerSQL = `select entry_id, posted_at, account, description, amount, currency, receipt_key
from ledger_entries
where period = $1
order by posted_at, entry_id`

// fetchLedger pulls one period's ledger into a Table handle.
//
// Amounts are converted to minor units here, once, at the edge. Every
// downstream action then works in exact integers and no one has to remember
// which representation they are holding.
func fetchLedger(c *action.Ctx, in LedgerQuery) (LedgerExtract, error) {
	if in.Period == "" {
		return LedgerExtract{}, fmt.Errorf("period is required")
	}

	// The grant's SQL row filter is applied proxy-side. This action must not
	// add a user predicate of its own: doing so would put an authorisation
	// decision in a place nobody audits.
	rows, err := c.Postgres(ResLedger).Query(fetchLedgerSQL, in.Period)
	if err != nil {
		return LedgerExtract{}, fmt.Errorf("querying ledger for %s: %w", in.Period, err)
	}

	b := table.NewBuilder(ledgerColumns()...)
	currencies := map[string]bool{}

	for i := range rows.Rows {
		r, err := rows.Map(i)
		if err != nil {
			return LedgerExtract{}, fmt.Errorf("ledger row %d: %w", i, err)
		}
		currency := str(r["currency"])
		if currency == "" {
			return LedgerExtract{}, fmt.Errorf("ledger row %d (entry %s) has no currency; an amount without a currency cannot be summed",
				i, str(r["entry_id"]))
		}
		amount, err := core.MoneyFromAny(r["amount"], currency)
		if err != nil {
			return LedgerExtract{}, fmt.Errorf("ledger row %d (entry %s): %w", i, str(r["entry_id"]), err)
		}
		currencies[amount.Currency] = true

		if err := b.Append(
			str(r["entry_id"]),
			str(r["posted_at"]),
			str(r["account"]),
			str(r["description"]),
			amount.Minor,
			amount.Currency,
			str(r["receipt_key"]),
		); err != nil {
			return LedgerExtract{}, err
		}
	}

	h, err := c.PutTable(b.Columns(), b.Rows(), "jsonl")
	if err != nil {
		return LedgerExtract{}, fmt.Errorf("storing ledger table: %w", err)
	}

	list := make([]string, 0, len(currencies))
	for cur := range currencies {
		list = append(list, cur)
	}
	sort.Strings(list)

	c.Logf("fetched %d ledger entries for %s in %v", b.Len(), in.Period, list)
	c.Emit("finance.ledger_fetched", map[string]any{
		"period": in.Period, "rows": b.Len(), "currencies": list,
	})

	return LedgerExtract{
		Ledger:     h,
		Period:     in.Period,
		RowCount:   b.Len(),
		Currencies: list,
	}, nil
}

func str(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprint(v)
}

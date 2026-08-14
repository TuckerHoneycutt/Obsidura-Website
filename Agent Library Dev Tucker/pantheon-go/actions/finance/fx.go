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

// ratesResponse is the shape of the FX endpoint's reply: rates[X] is how many
// units of X buy one unit of base.
type ratesResponse struct {
	Base  string             `json:"base"`
	Rates map[string]float64 `json:"rates"`
}

// normalizeFX converts every ledger amount into one base currency.
//
// Mixed-currency ledgers are the normal case, and every downstream action here
// refuses to add across currencies (core.Money.Add). That refusal is only
// useful if something converts first -- this is that something, and it is a
// separate action so the conversion is visible in the graph and its rates are
// visible in the audit trail, rather than hidden inside a reconciliation.
func normalizeFX(c *action.Ctx, in FXNormalizeRequest) (NormalizedLedger, error) {
	base := strings.ToUpper(strings.TrimSpace(in.BaseCurrency))
	if base == "" {
		return NormalizedLedger{}, fmt.Errorf("base_currency is required")
	}
	if in.RatesURL == "" {
		return NormalizedLedger{}, fmt.Errorf("rates_url is required")
	}

	var rates ratesResponse
	if err := c.HTTP(ResFX).GetJSON(in.RatesURL, &rates); err != nil {
		return NormalizedLedger{}, fmt.Errorf("fetching rates from %s: %w", in.RatesURL, err)
	}
	if !strings.EqualFold(rates.Base, base) {
		// Silently re-basing someone else's rate table is how a report ends up
		// off by a factor nobody can reconstruct six months later.
		return NormalizedLedger{}, fmt.Errorf(
			"rates endpoint is based on %s but %s was requested; re-basing is not done implicitly",
			rates.Base, base)
	}

	cur, err := c.OpenTable(in.Ledger)
	if err != nil {
		return NormalizedLedger{}, fmt.Errorf("opening ledger table: %w", err)
	}

	b := table.NewBuilder(ledgerColumns()...)
	used := map[string]float64{}
	converted := 0

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		currency, err := row.String(ColCurrency)
		if err != nil {
			return err
		}
		minor, _, err := row.Int(ColAmountMinor)
		if err != nil {
			return err
		}
		entryID, _ := row.String(ColEntryID)
		amount := core.Money{Minor: minor, Currency: strings.ToUpper(currency)}

		if amount.Currency != base {
			perBase, ok := rates.Rates[amount.Currency]
			if !ok {
				return fmt.Errorf("entry %s is in %s but the rates endpoint published no %s rate",
					entryID, amount.Currency, amount.Currency)
			}
			if perBase <= 0 {
				return fmt.Errorf("entry %s: rate for %s is %v, which cannot be inverted",
					entryID, amount.Currency, perBase)
			}
			// rates[X] is X per base, so base per X is its reciprocal.
			amount, err = amount.Convert(1/perBase, base)
			if err != nil {
				return fmt.Errorf("entry %s: %w", entryID, err)
			}
			used[strings.ToUpper(currency)] = perBase
			converted++
		}

		postedAt, _ := row.String(ColPostedAt)
		account, _ := row.String(ColAccount)
		desc, _ := row.String(ColDescription)
		receipt, _ := row.String(ColReceiptKey)
		return b.Append(entryID, postedAt, account, desc, amount.Minor, amount.Currency, receipt)
	})
	if err != nil {
		return NormalizedLedger{}, err
	}

	h, err := c.PutTable(b.Columns(), b.Rows(), "jsonl")
	if err != nil {
		return NormalizedLedger{}, fmt.Errorf("storing normalised ledger: %w", err)
	}

	names := make([]string, 0, len(used))
	for k := range used {
		names = append(names, k)
	}
	sort.Strings(names)

	c.Logf("normalised %d/%d rows to %s using rates for %v", converted, b.Len(), base, names)
	c.Emit("finance.fx_normalised", map[string]any{
		"base": base, "converted_rows": converted, "rates_used": used,
	})

	return NormalizedLedger{
		Ledger:        h,
		BaseCurrency:  base,
		RowCount:      b.Len(),
		ConvertedRows: converted,
		RatesUsed:     used,
	}, nil
}

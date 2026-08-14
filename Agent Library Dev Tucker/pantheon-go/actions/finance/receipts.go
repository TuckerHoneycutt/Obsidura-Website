package finance

import (
	"context"
	"fmt"
	"sort"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/core"
	"github.com/obsidura/pantheon-go/table"
)

// matchReceipts pairs ledger entries with the receipt documents behind them.
//
// Both directions are reported. An entry with no receipt is the obvious finding;
// a receipt with no entry is a payment nobody recorded, which is at least as
// interesting and is the half most tools omit.
//
// Objects outside the run's granted key prefix are filtered proxy-side and never
// appear in the listing. That means a scoped user's "orphan receipts" list is
// scoped too -- correct, and worth stating, because the alternative would be
// leaking the existence of documents the user may not see.
func matchReceipts(c *action.Ctx, in ReceiptMatchRequest) (ReceiptMatchReport, error) {
	if in.ReceiptPrefix == "" {
		return ReceiptMatchReport{}, fmt.Errorf("receipt_prefix is required")
	}

	objects, err := c.S3(ResReceipts).List(in.ReceiptPrefix)
	if err != nil {
		return ReceiptMatchReport{}, fmt.Errorf("listing receipts under %s: %w", in.ReceiptPrefix, err)
	}
	available := make(map[string]bool, len(objects))
	for _, o := range objects {
		available[o.Key] = true
	}

	cur, err := c.OpenTable(in.Ledger)
	if err != nil {
		return ReceiptMatchReport{}, fmt.Errorf("opening ledger table: %w", err)
	}

	claimed := map[string]bool{}
	unmatched := []UnmatchedEntry{}
	checked, matched := 0, 0

	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		checked++
		entryID, _ := row.String(ColEntryID)
		key, _ := row.String(ColReceiptKey)
		minor, _, err := row.Int(ColAmountMinor)
		if err != nil {
			return err
		}
		currency, _ := row.String(ColCurrency)
		postedAt, _ := row.String(ColPostedAt)
		account, _ := row.String(ColAccount)
		desc, _ := row.String(ColDescription)

		entry := UnmatchedEntry{
			EntryID:     entryID,
			PostedAt:    postedAt,
			Account:     account,
			Description: desc,
			Amount:      core.Money{Minor: minor, Currency: currency}.Major(),
			ReceiptKey:  key,
		}

		switch {
		case key == "":
			// Distinguished from a broken reference on purpose: "no receipt was
			// ever claimed" and "a receipt was claimed and is missing" are
			// different findings and a reviewer chases them differently.
			entry.Reason = "no receipt referenced"
			unmatched = append(unmatched, entry)
		case !available[key]:
			entry.Reason = "referenced receipt not found under " + in.ReceiptPrefix
			unmatched = append(unmatched, entry)
		default:
			claimed[key] = true
			matched++
		}
		return nil
	})
	if err != nil {
		return ReceiptMatchReport{}, err
	}

	orphans := []string{}
	for _, o := range objects {
		if !claimed[o.Key] {
			orphans = append(orphans, o.Key)
		}
	}
	sort.Strings(orphans)
	sort.Slice(unmatched, func(i, j int) bool { return unmatched[i].EntryID < unmatched[j].EntryID })

	c.Logf("matched %d/%d entries against %d receipts; %d orphan receipts",
		matched, checked, len(objects), len(orphans))
	c.Emit("finance.receipts_matched", map[string]any{
		"checked": checked, "matched": matched,
		"unmatched": len(unmatched), "orphans": len(orphans),
	})

	return ReceiptMatchReport{
		EntriesChecked:   checked,
		ReceiptsFound:    len(objects),
		Matched:          matched,
		UnmatchedEntries: unmatched,
		OrphanReceipts:   orphans,
	}, nil
}

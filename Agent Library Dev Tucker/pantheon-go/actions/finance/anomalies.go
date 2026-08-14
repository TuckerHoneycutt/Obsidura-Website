package finance

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/core"
	"github.com/obsidura/pantheon-go/table"
)

// Defaults for the heuristics. Named constants rather than literals because
// these are the numbers a reviewer will argue about, and they should be
// findable.
const (
	// DefaultZThreshold is deliberately above the conventional 3. Ledgers are
	// heavy-tailed -- a quarter legitimately contains a few very large entries --
	// and a detector that flags forty rows gets switched off in a week.
	DefaultZThreshold = 3.5

	// DefaultRoundNumberMinor is 10,000.00 in a two-digit currency. Round
	// numbers below that are ordinary; above it they are worth a look.
	DefaultRoundNumberMinor = 1_000_000

	// roundTo is the granularity at which an amount counts as "round".
	roundTo = 100_000 // 1000.00 in a two-digit currency
)

// Rule names, so the report's counts and a downstream filter agree on spelling.
const (
	RuleOutlier     = "outlier"
	RuleDuplicate   = "duplicate"
	RuleRoundNumber = "round_number"
	RuleWeekend     = "weekend"
	RuleNoAccount   = "missing_account"
)

type entryRow struct {
	id       string
	postedAt string
	account  string
	desc     string
	minor    int64
	currency string
}

// flagAnomalies surfaces candidate entries with the evidence for each.
//
// It decides nothing. Every rule here is a heuristic that produces candidates;
// which of them actually matter is judgement, and judgement belongs to an agent
// task wired downstream or to the human reading the report. An action that
// silently dropped "unimportant" findings would be making an audit decision
// nobody could review.
//
// Outlier detection uses median absolute deviation rather than standard
// deviation, because the outliers being hunted inflate the standard deviation
// and then fail to exceed it -- the masking effect, which is exactly the
// situation an anomaly detector is in by definition.
func flagAnomalies(c *action.Ctx, in AnomalyRequest) (AnomalyReport, error) {
	zThreshold := in.ZThreshold
	if zThreshold == 0 {
		zThreshold = DefaultZThreshold
	}
	roundFloor := in.RoundNumberMinor
	if roundFloor == 0 {
		roundFloor = DefaultRoundNumberMinor
	}

	cur, err := c.OpenTable(in.Ledger)
	if err != nil {
		return AnomalyReport{}, fmt.Errorf("opening ledger table: %w", err)
	}

	// Two passes' worth of data is needed (a median cannot be streamed), so the
	// rows are held. This is bounded by the ledger's size, which for one period
	// is report-scale; telemetry, which is not, streams instead.
	var entries []entryRow
	err = table.Each(context.Background(), cur, table.DefaultChunk, func(row table.Row) error {
		minor, _, err := row.Int(ColAmountMinor)
		if err != nil {
			return err
		}
		id, _ := row.String(ColEntryID)
		postedAt, _ := row.String(ColPostedAt)
		account, _ := row.String(ColAccount)
		desc, _ := row.String(ColDescription)
		currency, _ := row.String(ColCurrency)
		entries = append(entries, entryRow{id, postedAt, account, desc, minor, currency})
		return nil
	})
	if err != nil {
		return AnomalyReport{}, err
	}

	magnitudes := make([]float64, 0, len(entries))
	for _, e := range entries {
		m := float64(e.minor)
		if m < 0 {
			m = -m
		}
		magnitudes = append(magnitudes, m)
	}
	median, mad := core.MedianAbsDev(magnitudes)

	var found []Anomaly
	add := func(a Anomaly) { found = append(found, a) }

	// Duplicate detection keys on the fields a genuine double-posting shares.
	// Not the entry id, which is unique by construction and would never match.
	seen := map[string][]string{}

	for i, e := range entries {
		amountStr := core.Money{Minor: e.minor, Currency: e.currency}.Major()
		base := Anomaly{
			EntryID: e.id, PostedAt: e.postedAt, Account: e.account,
			Description: e.desc, Amount: amountStr,
		}

		if mad > 0 {
			z := core.RobustZ(magnitudes[i], median, mad)
			if z >= zThreshold {
				a := base
				a.Rule = RuleOutlier
				a.Score = z
				a.Detail = fmt.Sprintf("amount is %.1f robust deviations above the median of %s",
					z, core.Money{Minor: int64(median), Currency: e.currency}.Major())
				add(a)
			}
		}

		if e.account == "" {
			a := base
			a.Rule = RuleNoAccount
			a.Detail = "entry has no account assigned"
			add(a)
		}

		abs := e.minor
		if abs < 0 {
			abs = -abs
		}
		if abs >= roundFloor && abs%roundTo == 0 {
			a := base
			a.Rule = RuleRoundNumber
			a.Detail = fmt.Sprintf("large amount is an exact multiple of %s",
				core.Money{Minor: roundTo, Currency: e.currency}.Major())
			add(a)
		}

		if t, err := time.Parse(time.RFC3339, e.postedAt); err == nil {
			if wd := t.Weekday(); wd == time.Saturday || wd == time.Sunday {
				a := base
				a.Rule = RuleWeekend
				a.Detail = "posted on a " + wd.String()
				add(a)
			}
		}

		key := strings.Join([]string{e.account, amountStr, dayOf(e.postedAt), strings.ToLower(strings.TrimSpace(e.desc))}, "|")
		seen[key] = append(seen[key], e.id)
	}

	for _, e := range entries {
		amountStr := core.Money{Minor: e.minor, Currency: e.currency}.Major()
		key := strings.Join([]string{e.account, amountStr, dayOf(e.postedAt), strings.ToLower(strings.TrimSpace(e.desc))}, "|")
		ids := seen[key]
		if len(ids) < 2 {
			continue
		}
		others := make([]string, 0, len(ids)-1)
		for _, id := range ids {
			if id != e.id {
				others = append(others, id)
			}
		}
		add(Anomaly{
			EntryID: e.id, PostedAt: e.postedAt, Account: e.account,
			Description: e.desc, Amount: amountStr,
			Rule:   RuleDuplicate,
			Detail: "same account, amount, day and description as " + strings.Join(others, ", "),
			Score:  float64(len(ids)),
		})
	}

	// Stable order so two runs over the same ledger diff cleanly. An audit
	// report that reshuffles itself between runs cannot be reviewed by diff,
	// and one that cannot be diffed stops being reviewed.
	sort.Slice(found, func(i, j int) bool {
		if found[i].Rule != found[j].Rule {
			return found[i].Rule < found[j].Rule
		}
		return found[i].EntryID < found[j].EntryID
	})

	counts := map[string]int{}
	for _, a := range found {
		counts[a.Rule]++
	}
	if found == nil {
		found = []Anomaly{}
	}

	c.Logf("checked %d entries, flagged %d (%v)", len(entries), len(found), counts)
	c.Emit("finance.anomalies_flagged", map[string]any{
		"checked": len(entries), "flagged": len(found), "by_rule": counts,
	})

	return AnomalyReport{
		EntriesChecked: len(entries),
		Anomalies:      found,
		CountByRule:    counts,
		Median:         core.Money{Minor: int64(median), Currency: currencyOf(entries)}.Major(),
	}, nil
}

// dayOf truncates a timestamp to its date. Two postings of the same amount to
// the same account on the same day are a duplicate candidate even when their
// clock times differ, which is the usual shape of a double-submitted invoice.
func dayOf(ts string) string {
	if len(ts) >= 10 {
		return ts[:10]
	}
	return ts
}

func currencyOf(entries []entryRow) string {
	if len(entries) == 0 {
		return ""
	}
	return entries[0].currency
}

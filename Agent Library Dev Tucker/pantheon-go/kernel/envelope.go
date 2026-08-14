package kernel

import (
	"encoding/json"
	"time"
)

// BudgetSpent meters what an attempt cost. Tokens is always zero for a script
// runner and non-zero only for an agent runner; it is carried regardless so the
// two runner kinds produce the same envelope shape and downstream readers need
// no special case.
type BudgetSpent struct {
	Tokens int64 `json:"tokens"`
	Ms     int64 `json:"ms"`
}

// Taint marks a value as having been influenced by an untrusted source.
//
// Spec §6: taint is RECORDED AND LOGGED, NOT ENFORCED in v0. Nothing in this
// SDK refuses an operation because of a taint mark, and nothing should start
// doing so without the enforcement design that spec §11 defers. Recording it
// now is what makes enforcing it later a change of policy rather than a
// retrofit of provenance no one kept.
type Taint struct {
	Source string `json:"source"` // e.g. "resource:crm" or "agent:triage@2"
	Reason string `json:"reason,omitempty"`
}

// Envelope accompanies every value crossing a seam (spec §6).
type Envelope struct {
	RunID       string      `json:"run_id"`
	TaskID      string      `json:"task_id"`
	Attempt     int         `json:"attempt"`
	Schema      TypeRef     `json:"schema"`
	Producer    string      `json:"producer"`
	CausedBy    int64       `json:"caused_by"` // run_events.seq of the causing event
	Taint       []Taint     `json:"taint"`
	BudgetSpent BudgetSpent `json:"budget_spent"`
	TS          time.Time   `json:"ts"`
}

// MarshalJSON emits taint as [] rather than null when empty.
//
// A nil slice is null in Go and [] in Rust, and spec §6 shows `taint: []`.
// Without this the two runners produce envelopes that differ on the wire for
// the commonest case of all -- a task that recorded no taint -- and a reader
// forced to handle both null and [] for "nothing here" is a reader that will
// eventually handle one of them wrong.
//
// Caught by the shared wire corpus, not by review.
func (e Envelope) MarshalJSON() ([]byte, error) {
	// The alias sheds the method set, so this does not recurse.
	type alias Envelope
	a := alias(e)
	if a.Taint == nil {
		a.Taint = []Taint{}
	}
	return json.Marshal(a)
}

// Derive builds the outbound envelope for a result produced from this inbound
// one: same run, same task, same attempt, same causal parent, taint carried
// forward, with the schema and producer of what was actually produced.
//
// Taint is carried, never dropped. An action that filters or aggregates tainted
// input produces tainted output -- laundering provenance through an aggregation
// is the exact failure mode recording taint exists to make visible.
func (e Envelope) Derive(schema TypeRef, producer string, spent BudgetSpent, now time.Time) Envelope {
	out := e
	out.Schema = schema
	out.Producer = producer
	out.BudgetSpent = spent
	out.TS = now
	out.Taint = append([]Taint(nil), e.Taint...)
	return out
}

// WithTaint returns a copy carrying one more taint mark, skipping exact
// duplicates so a loop over 10,000 rows from one tainted resource does not
// produce 10,000 identical marks.
func (e Envelope) WithTaint(t Taint) Envelope {
	for _, existing := range e.Taint {
		if existing == t {
			return e
		}
	}
	out := e
	out.Taint = append(append([]Taint(nil), e.Taint...), t)
	return out
}

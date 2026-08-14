// Package core holds what more than one vertical turned out to need.
//
// It was EMPTY until two verticals existed, on purpose (03-build-plan.md,
// Phase 3): a core designed before any vertical is a guess, and guesses in a
// shared package are expensive to unwind. Every item here names where it was
// extracted from, so the next reader can judge whether the generalisation was
// earned or merely convenient:
//
//	Money   -- finance.reconcile_ledger, finance.normalize_fx, finance.match_receipts
//	Stats   -- finance.flag_anomalies (outliers), telemetry.window_stats (rolling)
//	Welford -- telemetry.window_stats, then adopted by finance.flag_anomalies
//
// If something here has exactly one caller, it was extracted too early and
// belongs back in that vertical.
package core

import (
	"fmt"
	"math"
	"strconv"
	"strings"
)

// Money is an amount in minor units (cents, pence, sen) plus a currency.
//
// Never float64. A ledger reconciled in binary floating point produces
// imbalances of 0.000000001 that are not real and hides imbalances of 0.01 that
// are -- and a financial audit whose imbalance column is noise is worse than no
// audit, because someone will trust it.
type Money struct {
	Minor    int64  `json:"minor"`
	Currency string `json:"currency"`
}

// Exponent is how many minor units make one major unit. Currencies with a zero
// or three digit exponent are handled explicitly rather than assumed to be two:
// JPY has no minor unit and treating 1000 JPY as 10.00 JPY is a factor-of-100
// error in a report a human will sign.
func Exponent(currency string) int {
	switch strings.ToUpper(currency) {
	case "JPY", "KRW", "VND", "CLP", "ISK":
		return 0
	case "BHD", "IQD", "JOD", "KWD", "OMR", "TND":
		return 3
	default:
		return 2
	}
}

// ParseMoney reads a decimal string like "-1234.56" into minor units.
//
// String parsing, not float arithmetic: multiplying a parsed float by 100 turns
// 1.15 into 114.99999999999999, which truncates to 114.
func ParseMoney(s, currency string) (Money, error) {
	s = strings.TrimSpace(s)
	if s == "" {
		return Money{Currency: currency}, nil
	}
	neg := false
	switch s[0] {
	case '-':
		neg, s = true, s[1:]
	case '+':
		s = s[1:]
	}
	s = strings.ReplaceAll(s, ",", "")

	exp := Exponent(currency)
	intPart, fracPart, hasFrac := strings.Cut(s, ".")
	if intPart == "" {
		intPart = "0"
	}
	whole, err := strconv.ParseInt(intPart, 10, 64)
	if err != nil {
		return Money{}, fmt.Errorf("core: %q is not a decimal amount", s)
	}

	var frac int64
	if hasFrac {
		if len(fracPart) > exp {
			// Truncate rather than round. A ledger that rounds sub-minor-unit
			// digits invents money; truncation at least loses it consistently,
			// and the imbalance column then shows a real discrepancy.
			fracPart = fracPart[:exp]
		}
		for len(fracPart) < exp {
			fracPart += "0"
		}
		if fracPart != "" {
			frac, err = strconv.ParseInt(fracPart, 10, 64)
			if err != nil {
				return Money{}, fmt.Errorf("core: %q has a non-numeric fraction", s)
			}
		}
	}

	scale := int64(1)
	for i := 0; i < exp; i++ {
		scale *= 10
	}
	minor := whole*scale + frac
	if neg {
		minor = -minor
	}
	return Money{Minor: minor, Currency: strings.ToUpper(currency)}, nil
}

// MoneyFromAny converts a value that arrived over JSON. Numbers arrive as
// float64 and are routed back through the string path rather than multiplied,
// for the reason in ParseMoney.
func MoneyFromAny(v any, currency string) (Money, error) {
	switch t := v.(type) {
	case nil:
		return Money{Currency: strings.ToUpper(currency)}, nil
	case string:
		return ParseMoney(t, currency)
	case float64:
		return ParseMoney(strconv.FormatFloat(t, 'f', Exponent(currency), 64), currency)
	case int64:
		return ParseMoney(strconv.FormatInt(t, 10), currency)
	case int:
		return ParseMoney(strconv.Itoa(t), currency)
	default:
		return Money{}, fmt.Errorf("core: cannot read %T as an amount", v)
	}
}

// Add sums two amounts. Mixing currencies is an error, not a silent sum: a
// total of "USD 100 + EUR 50 = 150" is the single most expensive bug a finance
// action can have, because the number looks entirely reasonable.
func (m Money) Add(o Money) (Money, error) {
	if m.Currency == "" {
		return Money{Minor: o.Minor, Currency: o.Currency}, nil
	}
	if o.Currency == "" && o.Minor == 0 {
		return m, nil
	}
	if m.Currency != o.Currency {
		return Money{}, fmt.Errorf("core: cannot add %s to %s without converting", o.Currency, m.Currency)
	}
	return Money{Minor: m.Minor + o.Minor, Currency: m.Currency}, nil
}

// Neg returns the negated amount.
func (m Money) Neg() Money { return Money{Minor: -m.Minor, Currency: m.Currency} }

// Abs returns the magnitude.
func (m Money) Abs() Money {
	if m.Minor < 0 {
		return m.Neg()
	}
	return m
}

// IsZero reports an exactly zero amount.
func (m Money) IsZero() bool { return m.Minor == 0 }

// Convert applies an exchange rate, returning the amount in `to`.
//
// Rounds half away from zero, which is the convention a human checking the
// arithmetic by hand will use.
func (m Money) Convert(rate float64, to string) (Money, error) {
	if rate <= 0 || math.IsNaN(rate) || math.IsInf(rate, 0) {
		return Money{}, fmt.Errorf("core: exchange rate %v is not usable", rate)
	}
	fromExp, toExp := Exponent(m.Currency), Exponent(to)
	major := float64(m.Minor) / math.Pow10(fromExp)
	converted := major * rate
	scaled := converted * math.Pow10(toExp)

	rounded := math.Floor(math.Abs(scaled) + 0.5)
	if scaled < 0 {
		rounded = -rounded
	}
	return Money{Minor: int64(rounded), Currency: strings.ToUpper(to)}, nil
}

// String renders the amount with its currency, e.g. "-1234.56 USD".
func (m Money) String() string {
	exp := Exponent(m.Currency)
	neg := m.Minor < 0
	v := m.Minor
	if neg {
		v = -v
	}
	scale := int64(1)
	for i := 0; i < exp; i++ {
		scale *= 10
	}
	whole, frac := v/scale, v%scale
	sign := ""
	if neg {
		sign = "-"
	}
	if exp == 0 {
		return fmt.Sprintf("%s%d %s", sign, whole, m.Currency)
	}
	return fmt.Sprintf("%s%d.%0*d %s", sign, whole, exp, frac, m.Currency)
}

// Major returns the amount as a decimal string with no currency, for report
// rendering. Still not a float: the string is the presentation.
func (m Money) Major() string {
	s := m.String()
	if i := strings.LastIndex(s, " "); i > 0 {
		return s[:i]
	}
	return s
}

// SumMoney totals a slice, failing on mixed currencies.
func SumMoney(ms []Money) (Money, error) {
	var acc Money
	for i, m := range ms {
		var err error
		acc, err = acc.Add(m)
		if err != nil {
			return Money{}, fmt.Errorf("core: summing element %d: %w", i, err)
		}
	}
	return acc, nil
}

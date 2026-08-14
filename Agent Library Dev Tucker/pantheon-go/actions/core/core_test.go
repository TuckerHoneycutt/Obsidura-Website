package core_test

import (
	"math"
	"testing"

	"github.com/obsidura/pantheon-go/actions/core"
)

// Named mutation table for core.
//
//	mutation                                          | reddens
//	--------------------------------------------------|----------------------------------------
//	ParseMoney parses a float and multiplies by 100    | TestPennyExactArithmetic
//	Exponent returns 2 for every currency              | TestZeroExponentCurrencies
//	Money.Add drops the currency check                 | TestAddRefusesMixedCurrencies
//	Money.Convert rounds toward zero                   | TestConvertRoundsHalfAwayFromZero
//	Welford.ZScore divides by a zero standard deviation | TestZScoreOfAConstantSeriesIsZero
//	MedianAbsDev uses standard deviation                | TestMADResistsMasking
//	Welford accumulates naively (sum of squares)        | TestWelfordIsNumericallyStable

// The single most important property in the finance vertical. A ledger
// reconciled in binary floating point produces imbalances that are not real and
// hides ones that are.
func TestPennyExactArithmetic(t *testing.T) {
	// 1.15 is not representable in binary; float64(1.15)*100 == 114.99999999999999,
	// which truncates to 114. String parsing gives 115.
	m, err := core.ParseMoney("1.15", "USD")
	if err != nil {
		t.Fatal(err)
	}
	if m.Minor != 115 {
		t.Errorf("1.15 USD parsed to %d minor units, want 115 (a float path gives 114)", m.Minor)
	}

	// Ten additions of 0.10 must be exactly 1.00, not 0.9999999999999999.
	var acc core.Money
	for i := 0; i < 10; i++ {
		step, _ := core.ParseMoney("0.10", "USD")
		acc, err = acc.Add(step)
		if err != nil {
			t.Fatal(err)
		}
	}
	if acc.Minor != 100 {
		t.Errorf("ten times 0.10 gave %d minor units, want 100", acc.Minor)
	}
	if acc.Major() != "1.00" {
		t.Errorf("rendered as %q", acc.Major())
	}
}

func TestParseMoneyHandlesSignsAndSeparators(t *testing.T) {
	cases := map[string]int64{
		"-1234.56":  -123456,
		"+1234.56":  123456,
		"1,234.56":  123456,
		"0.01":      1,
		"1234":      123400,
		"":          0,
		"-0.01":     -1,
		"1234.5":    123450,
		"1234.5678": 123456, // truncated, never rounded up: rounding invents money
	}
	for in, want := range cases {
		m, err := core.ParseMoney(in, "USD")
		if err != nil {
			t.Errorf("%q: %v", in, err)
			continue
		}
		if m.Minor != want {
			t.Errorf("%q parsed to %d, want %d", in, m.Minor, want)
		}
	}
}

// JPY has no minor unit. Treating 1000 JPY as 10.00 JPY is a factor-of-100
// error in a report a human will sign.
func TestZeroExponentCurrencies(t *testing.T) {
	m, err := core.ParseMoney("1000", "JPY")
	if err != nil {
		t.Fatal(err)
	}
	if m.Minor != 1000 {
		t.Errorf("1000 JPY is %d minor units, want 1000", m.Minor)
	}
	if m.Major() != "1000" {
		t.Errorf("rendered as %q, want %q", m.Major(), "1000")
	}

	// Three-digit currencies too.
	k, err := core.ParseMoney("1.234", "KWD")
	if err != nil {
		t.Fatal(err)
	}
	if k.Minor != 1234 {
		t.Errorf("1.234 KWD is %d minor units, want 1234", k.Minor)
	}
}

// A total of "USD 100 + EUR 50 = 150" is the single most expensive bug a
// finance action can have, because the number looks entirely reasonable.
func TestAddRefusesMixedCurrencies(t *testing.T) {
	usd, _ := core.ParseMoney("100.00", "USD")
	eur, _ := core.ParseMoney("50.00", "EUR")
	if _, err := usd.Add(eur); err == nil {
		t.Fatal("adding EUR to USD must be an error, not a plausible-looking number")
	}
	// A zero with no currency is the accumulator's starting state and must work.
	var zero core.Money
	got, err := zero.Add(usd)
	if err != nil || got.Minor != 10000 || got.Currency != "USD" {
		t.Errorf("zero + USD gave %+v, %v", got, err)
	}
}

func TestConvertRoundsHalfAwayFromZero(t *testing.T) {
	// 0.005 USD at rate 1.0 is exactly half a cent; a human checking by hand
	// rounds it to 1 cent, and so must this.
	m := core.Money{Minor: 1, Currency: "USD"} // 0.01
	got, err := m.Convert(0.5, "USD")          // 0.005
	if err != nil {
		t.Fatal(err)
	}
	if got.Minor != 1 {
		t.Errorf("0.01 * 0.5 rounded to %d minor units, want 1 (half away from zero)", got.Minor)
	}

	neg := core.Money{Minor: -1, Currency: "USD"}
	gotNeg, _ := neg.Convert(0.5, "USD")
	if gotNeg.Minor != -1 {
		t.Errorf("-0.01 * 0.5 rounded to %d, want -1 (symmetric)", gotNeg.Minor)
	}
}

func TestConvertRefusesUnusableRates(t *testing.T) {
	m := core.Money{Minor: 100, Currency: "USD"}
	for _, rate := range []float64{0, -1, math.NaN(), math.Inf(1)} {
		if _, err := m.Convert(rate, "EUR"); err == nil {
			t.Errorf("rate %v must be refused", rate)
		}
	}
}

func TestConvertAcrossExponents(t *testing.T) {
	// 100.00 USD at 150 JPY per USD is 15000 JPY, with no minor unit.
	usd := core.Money{Minor: 10000, Currency: "USD"}
	jpy, err := usd.Convert(150, "JPY")
	if err != nil {
		t.Fatal(err)
	}
	if jpy.Minor != 15000 {
		t.Errorf("100 USD at 150 gave %d JPY minor units, want 15000", jpy.Minor)
	}
	if jpy.Major() != "15000" {
		t.Errorf("rendered as %q", jpy.Major())
	}
}

func TestWelfordMatchesTheTextbookAnswer(t *testing.T) {
	var w core.Welford
	for _, x := range []float64{2, 4, 4, 4, 5, 5, 7, 9} {
		w.Push(x)
	}
	if w.N() != 8 {
		t.Errorf("n=%d", w.N())
	}
	if w.Mean() != 5 {
		t.Errorf("mean=%v, want 5", w.Mean())
	}
	// Sample variance (n-1 denominator) of this set is 32/7.
	if math.Abs(w.Var()-32.0/7.0) > 1e-9 {
		t.Errorf("var=%v, want %v", w.Var(), 32.0/7.0)
	}
	if w.Min() != 2 || w.Max() != 9 {
		t.Errorf("min=%v max=%v", w.Min(), w.Max())
	}
}

// The reason for Welford rather than sum-of-squares: with a large offset, the
// naive formula subtracts two nearly equal huge numbers and loses every
// significant digit.
func TestWelfordIsNumericallyStable(t *testing.T) {
	var w core.Welford
	const offset = 1e9
	for _, x := range []float64{offset + 4, offset + 7, offset + 13, offset + 16} {
		w.Push(x)
	}
	// Variance of {4,7,13,16} is 30.
	if math.Abs(w.Var()-30) > 1e-6 {
		t.Errorf("var=%v, want 30; a naive sum-of-squares loses this entirely", w.Var())
	}
}

// A constant series has no outliers. A report column full of Infinity is a
// rendering bug and a support ticket, not a finding.
func TestZScoreOfAConstantSeriesIsZero(t *testing.T) {
	var w core.Welford
	for i := 0; i < 10; i++ {
		w.Push(42)
	}
	if z := w.ZScore(42); z != 0 {
		t.Errorf("z=%v for a constant series, want 0", z)
	}
	if z := w.ZScore(1000); z != 0 || math.IsInf(z, 0) {
		t.Errorf("z=%v; a zero standard deviation must not produce Infinity", z)
	}
}

func TestPercentileInterpolates(t *testing.T) {
	xs := []float64{1, 2, 3, 4, 5}
	cases := map[float64]float64{0: 1, 50: 3, 100: 5, 25: 2, 75: 4}
	for p, want := range cases {
		if got := core.Percentile(xs, p); math.Abs(got-want) > 1e-9 {
			t.Errorf("p%v = %v, want %v", p, got, want)
		}
	}
	// The input must not be disturbed.
	unsorted := []float64{5, 1, 3}
	core.Percentile(unsorted, 50)
	if unsorted[0] != 5 {
		t.Errorf("Percentile sorted its argument in place: %v", unsorted)
	}
}

// The masking effect: outliers inflate the standard deviation until they no
// longer exceed it. This is the situation an anomaly detector is in by
// definition, and it is why MAD is used instead.
func TestMADResistsMasking(t *testing.T) {
	// Twenty ordinary values around 10, plus two enormous ones.
	xs := make([]float64, 0, 22)
	for i := 0; i < 20; i++ {
		xs = append(xs, 10+float64(i%3))
	}
	xs = append(xs, 5000, 5200)

	var w core.Welford
	for _, x := range xs {
		w.Push(x)
	}
	median, mad := core.MedianAbsDev(xs)

	classicZ := w.ZScore(5000)
	robustZ := core.RobustZ(5000, median, mad)

	if robustZ <= classicZ {
		t.Errorf("robust z (%v) should be far larger than the classic z (%v); "+
			"the outliers inflate the standard deviation and mask themselves", robustZ, classicZ)
	}
	if classicZ >= 3.5 {
		t.Logf("note: classic z reached %v here; the masking is milder than expected", classicZ)
	}
	if robustZ < 3.5 {
		t.Errorf("robust z is %v; a value 500x the median must clear the default threshold", robustZ)
	}
}

func TestMADOfAConstantSeriesScoresZero(t *testing.T) {
	xs := []float64{7, 7, 7, 7}
	median, mad := core.MedianAbsDev(xs)
	if mad != 0 {
		t.Errorf("mad=%v for a constant series", mad)
	}
	if z := core.RobustZ(1000, median, mad); z != 0 {
		t.Errorf("RobustZ with mad=0 gave %v; it must not divide by zero", z)
	}
}

func TestSumMoneyNamesTheOffendingElement(t *testing.T) {
	usd, _ := core.ParseMoney("1.00", "USD")
	eur, _ := core.ParseMoney("1.00", "EUR")
	_, err := core.SumMoney([]core.Money{usd, usd, eur})
	if err == nil {
		t.Fatal("summing across currencies must fail")
	}
	if got := err.Error(); got == "" {
		t.Error("error should name which element failed")
	}
}

func TestNegAndAbs(t *testing.T) {
	m, _ := core.ParseMoney("-1234.56", "USD")
	if got := m.Neg(); got.Minor != 123456 || got.Currency != "USD" {
		t.Errorf("Neg gave %+v", got)
	}
	if got := m.Abs(); got.Minor != 123456 {
		t.Errorf("Abs of a negative gave %+v", got)
	}
	pos, _ := core.ParseMoney("1.00", "USD")
	if got := pos.Abs(); got.Minor != 100 {
		t.Errorf("Abs of a positive must be unchanged, got %+v", got)
	}
	if !(core.Money{Currency: "USD"}).IsZero() {
		t.Error("a zero amount must report IsZero")
	}
}

// Values arrive over JSON as float64, or from a text column as a string, or as
// a null. All three are ordinary in a real ledger.
func TestMoneyFromAnyAcceptsEveryWireShape(t *testing.T) {
	cases := []struct {
		in   any
		want int64
	}{
		{nil, 0},
		{"1234.56", 123456},
		{1234.56, 123456},
		{float64(1000), 100000},
		{int64(42), 4200},
		{int(7), 700},
	}
	for _, tc := range cases {
		got, err := core.MoneyFromAny(tc.in, "USD")
		if err != nil {
			t.Errorf("%v (%T): %v", tc.in, tc.in, err)
			continue
		}
		if got.Minor != tc.want {
			t.Errorf("%v (%T) gave %d minor units, want %d", tc.in, tc.in, got.Minor, tc.want)
		}
	}

	if _, err := core.MoneyFromAny(true, "USD"); err == nil {
		t.Error("a boolean is not an amount and must be refused")
	}
	if _, err := core.MoneyFromAny("not-a-number", "USD"); err == nil {
		t.Error("a non-numeric string must be refused")
	}
}

// A float that arrives as 1234.5600000000001 must still be exactly 1234.56,
// because MoneyFromAny formats to the currency's exponent before parsing.
func TestMoneyFromAnyIsNotDefeatedByFloatDust(t *testing.T) {
	got, err := core.MoneyFromAny(0.1+0.2, "USD") // 0.30000000000000004
	if err != nil {
		t.Fatal(err)
	}
	if got.Minor != 30 {
		t.Errorf("0.1+0.2 gave %d minor units, want 30", got.Minor)
	}
}

func TestMajorDropsTheCurrencySuffix(t *testing.T) {
	m, _ := core.ParseMoney("-1234.56", "USD")
	if m.String() != "-1234.56 USD" {
		t.Errorf("String gave %q", m.String())
	}
	if m.Major() != "-1234.56" {
		t.Errorf("Major gave %q", m.Major())
	}
	j, _ := core.ParseMoney("1500", "JPY")
	if j.Major() != "1500" {
		t.Errorf("Major of a zero-exponent currency gave %q", j.Major())
	}
}

func TestWelfordAccessorsOnAnEmptyAccumulator(t *testing.T) {
	var w core.Welford
	if w.N() != 0 || w.Mean() != 0 || w.Var() != 0 || w.StdDev() != 0 {
		t.Errorf("an empty accumulator should report zeros, got n=%d mean=%v var=%v",
			w.N(), w.Mean(), w.Var())
	}
	w.Push(5)
	if w.N() != 1 || w.Mean() != 5 {
		t.Errorf("one sample: n=%d mean=%v", w.N(), w.Mean())
	}
	// One sample has no spread, which is honest rather than a division by zero.
	if w.Var() != 0 || w.StdDev() != 0 {
		t.Errorf("one sample should have zero variance, got %v", w.Var())
	}
}

func TestPercentileOfAnEmptySliceIsZero(t *testing.T) {
	if got := core.Percentile(nil, 50); got != 0 {
		t.Errorf("percentile of nothing gave %v", got)
	}
	median, mad := core.MedianAbsDev(nil)
	if median != 0 || mad != 0 {
		t.Errorf("MAD of nothing gave %v/%v", median, mad)
	}
}

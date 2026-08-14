package core

import (
	"math"
	"sort"
)

// Welford accumulates count, mean and variance in one pass, without holding the
// samples.
//
// Extracted from telemetry.window_stats, then adopted by finance.flag_anomalies
// -- the second caller is what earned it a place in core. The streaming
// property is not an optimisation here: a telemetry table has tens of thousands
// of rows and package table iterates in chunks precisely so they are never all
// resident. A statistic that needs the whole slice would defeat that.
type Welford struct {
	n    int64
	mean float64
	m2   float64
	min  float64
	max  float64
}

// Push adds one sample.
func (w *Welford) Push(x float64) {
	if w.n == 0 || x < w.min {
		w.min = x
	}
	if w.n == 0 || x > w.max {
		w.max = x
	}
	w.n++
	delta := x - w.mean
	w.mean += delta / float64(w.n)
	w.m2 += delta * (x - w.mean)
}

// N returns the sample count.
func (w *Welford) N() int64 { return w.n }

// Mean returns the arithmetic mean, or 0 for no samples.
func (w *Welford) Mean() float64 {
	if w.n == 0 {
		return 0
	}
	return w.mean
}

// Var returns the sample variance (n-1 denominator). Zero for fewer than two
// samples, which is honest: one sample has no spread.
func (w *Welford) Var() float64 {
	if w.n < 2 {
		return 0
	}
	return w.m2 / float64(w.n-1)
}

// StdDev returns the sample standard deviation.
func (w *Welford) StdDev() float64 { return math.Sqrt(w.Var()) }

// Min returns the smallest sample.
func (w *Welford) Min() float64 { return w.min }

// Max returns the largest sample.
func (w *Welford) Max() float64 { return w.max }

// ZScore reports how many standard deviations x sits from the mean.
//
// Returns 0 when the deviation is zero rather than ±Inf. A constant series has
// no outliers, and a report column full of Infinity is a rendering bug and a
// support ticket rather than a finding.
func (w *Welford) ZScore(x float64) float64 {
	sd := w.StdDev()
	if sd == 0 {
		return 0
	}
	return (x - w.Mean()) / sd
}

// Percentile returns the linearly interpolated p-th percentile of xs, where p
// is in [0,100]. It sorts a copy, so xs is not disturbed.
//
// Unlike Welford this needs every sample, so callers hold the slice knowingly.
// Used on per-window aggregates (thousands of values), never on raw rows.
func Percentile(xs []float64, p float64) float64 {
	if len(xs) == 0 {
		return 0
	}
	s := append([]float64(nil), xs...)
	sort.Float64s(s)
	if p <= 0 {
		return s[0]
	}
	if p >= 100 {
		return s[len(s)-1]
	}
	pos := (p / 100) * float64(len(s)-1)
	lo := int(math.Floor(pos))
	hi := int(math.Ceil(pos))
	if lo == hi {
		return s[lo]
	}
	frac := pos - float64(lo)
	return s[lo] + (s[hi]-s[lo])*frac
}

// MedianAbsDev returns the median absolute deviation from the median.
//
// Preferred over standard deviation for outlier detection on data that already
// contains outliers: the outliers inflate the standard deviation, which then
// fails to flag them. This is the "masking" effect, and it is exactly the
// situation an anomaly detector is in by definition.
func MedianAbsDev(xs []float64) (median, mad float64) {
	if len(xs) == 0 {
		return 0, 0
	}
	median = Percentile(xs, 50)
	devs := make([]float64, len(xs))
	for i, x := range xs {
		devs[i] = math.Abs(x - median)
	}
	return median, Percentile(devs, 50)
}

// RobustZ scores x against a median and MAD.
//
// The 0.6745 factor makes the result comparable to a standard z-score for
// normally distributed data, so a threshold of 3 means roughly what it means
// for a conventional z-score and reviewers do not have to learn a new scale.
func RobustZ(x, median, mad float64) float64 {
	if mad == 0 {
		return 0
	}
	return 0.6745 * (x - median) / mad
}

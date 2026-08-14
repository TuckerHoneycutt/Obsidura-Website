package clinical_test

import (
	"strings"
	"testing"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/clinical"
	"github.com/obsidura/pantheon-go/fixtures"
	"github.com/obsidura/pantheon-go/ptnfake"
)

// Named mutation table for the clinical vertical.
//
//	mutation                                            | reddens
//	----------------------------------------------------|------------------------------------------
//	filterCohort adds `and requester = $3` to its SQL    | TestSameRequestTwoUsersDifferentCohorts
//	CohortQuery gains a requester field                  | TestCohortQueryCarriesNoIdentity
//	Cohort drops ScopeNote                               | TestCohortDeclaresThatItIsScoped
//	checkPHIScope treats an empty allowlist as "all"     | TestEmptyAllowlistPermitsNothing
//	checkPHIScope runs after render instead of before    | (design; see checkPHIScope's doc comment)
//	manifestScans reports scans for out-of-scope keys    | TestScanManifestIsScopedToo
//	manifestScans fails the run on a denied list          | TestScanManifestTreatsDenialAsAbsence

func registry() *action.Registry {
	r := action.NewRegistry()
	clinical.Register(r)
	return r
}

func newProxy(t *testing.T) *ptnfake.Proxy {
	t.Helper()
	p, err := ptnfake.New()
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { p.Close() })
	fixtures.Clinical(p)
	return p
}

// THE PERMISSION BEAT (spec §2, acceptance test 4).
//
// Two users, byte-identical requests, different results, and an audit log that
// shows the scope decision. It works because filterCohort does not participate:
// it issues one query with no user predicate and the proxy narrows the result.
func TestSameRequestTwoUsersDifferentCohorts(t *testing.T) {
	r := registry()
	// The identical request object is used for both users. Not a copy -- the
	// same value, so there is no room for the test to differ by accident.
	request := clinical.CohortQuery{Status: "admitted"}

	unrestricted := newProxy(t)
	fixtures.GrantClinicalAll(unrestricted)

	scoped := newProxy(t)
	fixtures.GrantClinicalWard(scoped, "cardiology", "scans/")

	var cohortA, cohortB clinical.Cohort
	if err := unrestricted.Invoke(r, "clinical.filter_cohort", request).Record(&cohortA); err != nil {
		t.Fatal(err)
	}
	if err := scoped.Invoke(r, "clinical.filter_cohort", request).Record(&cohortB); err != nil {
		t.Fatal(err)
	}

	if cohortA.Count <= cohortB.Count {
		t.Fatalf("the scoped user should see fewer patients: unrestricted=%d scoped=%d",
			cohortA.Count, cohortB.Count)
	}
	// Fixture: 5 admitted patients overall, 2 of them in cardiology.
	if cohortA.Count != 5 || cohortB.Count != 2 {
		t.Errorf("expected 5 and 2 patients, got %d and %d", cohortA.Count, cohortB.Count)
	}
	for _, p := range cohortB.Patients {
		if p.Ward != "cardiology" {
			t.Errorf("scoped cohort contains a %s patient: %s", p.Ward, p.PatientID)
		}
	}

	// The governance half: the audit log shows the scope decision, with counts.
	lines := scoped.AuditLines()
	if len(lines) != 1 || !strings.Contains(lines[0], "[scope: 2/5 rows]") {
		t.Errorf("audit log should show the scope decision; got %q", lines)
	}
	if !strings.Contains(unrestricted.AuditLines()[0], "records.query") {
		t.Errorf("unrestricted audit line: %q", unrestricted.AuditLines()[0])
	}
}

// The action must have no way to know who is asking. A requester field would
// be an invitation to filter locally, and a local filter is an authorisation
// decision in a place nobody audits.
func TestCohortQueryCarriesNoIdentity(t *testing.T) {
	forbidden := map[string]bool{
		"requester": true, "user": true, "user_id": true, "userid": true,
		"role": true, "subject": true, "principal": true, "caller": true,
	}
	got := fieldNames(t, clinical.CohortQuery{})
	if len(got) == 0 {
		t.Fatal("fieldNames returned nothing; the assertion below would be vacuous")
	}
	for _, f := range got {
		if forbidden[f] {
			t.Errorf("CohortQuery carries a %q field; scope belongs to the proxy, not the action", f)
		}
	}
}

// The vacuity guard for the test above: fieldNames must actually see fields
// that omitempty hides from a marshalled zero value.
func TestFieldNamesSeesOmitemptyFields(t *testing.T) {
	got := strings.Join(fieldNames(t, clinical.CohortQuery{}), ",")
	if !strings.Contains(got, "ward") || !strings.Contains(got, "max_count") {
		t.Fatalf("fieldNames missed omitempty fields (%q); TestCohortQueryCarriesNoIdentity would pass vacuously", got)
	}
}

func TestCohortDeclaresThatItIsScoped(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalWard(p, "oncology", "scans/")

	var cohort clinical.Cohort
	if err := p.Invoke(r, "clinical.filter_cohort", clinical.CohortQuery{}).Record(&cohort); err != nil {
		t.Fatal(err)
	}
	// Two users get different numbers from the same query. A reader comparing
	// two reports must be told that before concluding patients went missing.
	if cohort.ScopeNote == "" {
		t.Error("a permission-scoped cohort must say so, or it reads as a complete census")
	}
}

func TestScanManifestFindsAndReportsGaps(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalAll(p)

	var manifest clinical.ScanManifest
	if err := p.Invoke(r, "clinical.manifest_scans", clinical.ScanManifestRequest{
		PatientIDs: []string{"p-001", "p-003", "p-004", "p-005"},
		Prefix:     "scans/",
	}).Record(&manifest); err != nil {
		t.Fatal(err)
	}

	// p-003 has two scans; p-004 and p-005 have none.
	if manifest.Found != 3 {
		t.Errorf("found %d scans, want 3 (p-001 x1, p-003 x2)", manifest.Found)
	}
	if strings.Join(manifest.WithoutScans, ",") != "p-004,p-005" {
		t.Errorf("patients without scans: %v", manifest.WithoutScans)
	}
}

// A scoped user's manifest is scoped too. Reporting scans the caller may not
// fetch would leak the existence of documents the key prefix exists to hide.
func TestScanManifestIsScopedToo(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalWard(p, "cardiology", "scans/p-001/")

	var manifest clinical.ScanManifest
	if err := p.Invoke(r, "clinical.manifest_scans", clinical.ScanManifestRequest{
		PatientIDs: []string{"p-001", "p-003"},
		Prefix:     "scans/",
	}).Record(&manifest); err != nil {
		t.Fatal(err)
	}

	if manifest.Found != 1 {
		t.Errorf("found %d scans; only p-001's is inside the granted prefix", manifest.Found)
	}
	for _, s := range manifest.Scans {
		if !strings.HasPrefix(s.Key, "scans/p-001/") {
			t.Errorf("manifest leaks an out-of-scope key: %s", s.Key)
		}
	}
	if strings.Join(manifest.WithoutScans, ",") != "p-003" {
		t.Errorf("p-003 should appear as having no visible scan, got %v", manifest.WithoutScans)
	}
}

func TestScanManifestTreatsDenialAsAbsence(t *testing.T) {
	r := registry()
	p := newProxy(t)
	p.Grant("records", ptnfake.Grant{Verbs: []string{"query"}})
	// No scans grant at all.

	var manifest clinical.ScanManifest
	res := p.Invoke(r, "clinical.manifest_scans", clinical.ScanManifestRequest{
		PatientIDs: []string{"p-001", "p-003"},
		Prefix:     "scans/",
	})
	if err := res.Record(&manifest); err != nil {
		t.Fatalf("no access to the scan store is a legitimate outcome, not a run failure: %v", err)
	}
	if manifest.Found != 0 || len(manifest.WithoutScans) != 2 {
		t.Errorf("expected an empty, honest manifest; got %+v", manifest)
	}
}

// An empty allowlist must permit nothing. An empty allowlist that permits
// everything is the fail-open bug the guard SPEC is explicit about, and this
// check exists precisely to be trusted.
func TestEmptyAllowlistPermitsNothing(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalAll(p)

	var cohort clinical.Cohort
	if err := p.Invoke(r, "clinical.filter_cohort", clinical.CohortQuery{}).Record(&cohort); err != nil {
		t.Fatal(err)
	}

	var report clinical.PHIScopeReport
	if err := p.Invoke(r, "clinical.check_phi_scope", clinical.PHIScopeRequest{
		Cohort:        cohort,
		AllowedFields: nil,
	}).Record(&report); err != nil {
		t.Fatal(err)
	}
	if report.Clean {
		t.Fatal("an empty allowlist must flag every populated field, not permit them all")
	}
	if len(report.Violations) == 0 {
		t.Error("no violations reported for an empty allowlist")
	}
}

func TestPHIScopeAcceptsAnAllowedProjection(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalAll(p)

	var cohort clinical.Cohort
	if err := p.Invoke(r, "clinical.filter_cohort", clinical.CohortQuery{}).Record(&cohort); err != nil {
		t.Fatal(err)
	}

	var report clinical.PHIScopeReport
	if err := p.Invoke(r, "clinical.check_phi_scope", clinical.PHIScopeRequest{
		Cohort:        cohort,
		AllowedFields: []string{"patient_id", "ward", "status", "admitted_on", "diagnosis"},
	}).Record(&report); err != nil {
		t.Fatal(err)
	}
	if !report.Clean {
		t.Errorf("every populated field is on the allowlist, yet %d violations were reported: %+v",
			len(report.Violations), report.Violations)
	}
}

func TestPHIScopeFlagsTheDiagnosisWhenNotAllowed(t *testing.T) {
	r := registry()
	p := newProxy(t)
	fixtures.GrantClinicalAll(p)

	var cohort clinical.Cohort
	if err := p.Invoke(r, "clinical.filter_cohort", clinical.CohortQuery{}).Record(&cohort); err != nil {
		t.Fatal(err)
	}

	var report clinical.PHIScopeReport
	if err := p.Invoke(r, "clinical.check_phi_scope", clinical.PHIScopeRequest{
		Cohort:        cohort,
		AllowedFields: []string{"patient_id", "ward", "status"},
	}).Record(&report); err != nil {
		t.Fatal(err)
	}
	if report.Clean {
		t.Fatal("diagnosis is populated and not allowed; the report should not be clean")
	}
	fields := map[string]bool{}
	for _, v := range report.Violations {
		fields[v.Field] = true
	}
	if !fields["diagnosis"] || !fields["admitted_on"] {
		t.Errorf("expected diagnosis and admitted_on to be flagged, got %v", fields)
	}
	if fields["ward"] {
		t.Error("ward is on the allowlist and must not be flagged")
	}
}

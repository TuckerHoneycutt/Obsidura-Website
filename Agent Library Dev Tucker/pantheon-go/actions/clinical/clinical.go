// Package clinical is the clinical-summary vertical of the deck.
//
// This vertical carries the permission beat (spec §2, acceptance test 4): user
// A and user B issue the SAME request and B's summary contains fewer patients,
// with the audit log showing each scope decision.
//
// The load-bearing property is what these actions do NOT do. Not one of them
// takes a user id, filters by requester, or knows who is asking. Scope is
// applied proxy-side from the run's grants -- SQL row filter for postgres, key
// prefix for s3 (spec §8) -- and the action is none the wiser. An action that
// filtered by user itself would put an authorisation decision somewhere nobody
// audits, and would be indistinguishable from one that forgot to.
package clinical

import (
	"fmt"
	"sort"
	"strings"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/res"
)

// Logical resource names.
const (
	ResRecords = "records" // postgres: patient records
	ResScans   = "scans"   // s3: scan images
)

// CohortQuery selects patients by clinical criteria.
//
// Note what is absent: there is no requester, user_id or role field, and there
// must never be one. Scope is the proxy's job.
type CohortQuery struct {
	Ward     string `json:"ward,omitempty" desc:"Restrict to one ward; empty means every ward the run may see"`
	Status   string `json:"status,omitempty" desc:"Restrict to one admission status"`
	MaxCount int    `json:"max_count,omitempty" desc:"Cap the cohort size; zero means no cap"`
}

// Patient is the vertical patient type.
type Patient struct {
	PatientID  string `json:"patient_id"`
	Ward       string `json:"ward"`
	Status     string `json:"status"`
	AdmittedOn string `json:"admitted_on"`
	Diagnosis  string `json:"diagnosis"`
}

// Cohort is the patients this run was permitted to see.
type Cohort struct {
	Patients []Patient `json:"patients" desc:"Sorted by patient id"`
	Count    int       `json:"count"`
	Criteria string    `json:"criteria" desc:"Human-readable description of what was asked for"`

	// ScopeNote states plainly that the result is permission-scoped. It exists
	// so a rendered report cannot be mistaken for a complete census -- two users
	// running the same query get different numbers, and a reader comparing two
	// reports needs to know that before they conclude patients went missing.
	ScopeNote string `json:"scope_note"`
}

// ScanManifestRequest lists the scan images for a cohort.
type ScanManifestRequest struct {
	PatientIDs []string `json:"patient_ids"`
	Prefix     string   `json:"prefix" desc:"Key prefix under which scans are stored, e.g. scans/"`
}

// Scan is one located image.
type Scan struct {
	PatientID string `json:"patient_id"`
	Key       string `json:"key"`
	Size      int64  `json:"size"`
}

// ScanManifest is what was found, and for whom nothing was.
type ScanManifest struct {
	Scans []Scan `json:"scans" desc:"Sorted by key"`

	// WithoutScans lists cohort members with no image under the prefix. This
	// conflates "no scan exists" with "no scan this run may see", deliberately:
	// distinguishing them would leak the existence of images the caller is not
	// permitted to know about, which is the leak the key-prefix scope exists to
	// prevent.
	WithoutScans []string `json:"without_scans"`

	Found   int `json:"found"`
	Checked int `json:"checked"`
}

// PHIScopeRequest checks a cohort against the fields a report may carry.
type PHIScopeRequest struct {
	Cohort Cohort `json:"cohort"`

	// AllowedFields is an allowlist of patient field names. Empty means nothing
	// is allowed, not everything: an empty allowlist that permits all fields is
	// the fail-open bug the guard SPEC is explicit about, and this check exists
	// precisely to be trusted.
	AllowedFields []string `json:"allowed_fields"`
}

// PHIViolation is one field that would leave scope.
type PHIViolation struct {
	PatientID string `json:"patient_id"`
	Field     string `json:"field"`
	Reason    string `json:"reason"`
}

// PHIScopeReport is the pre-render check.
type PHIScopeReport struct {
	Clean         bool           `json:"clean"`
	Violations    []PHIViolation `json:"violations"`
	FieldsChecked []string       `json:"fields_checked"`
}

const cohortSQL = `select patient_id, ward, status, admitted_on, diagnosis
from patients
where ($1 = '' or ward = $1)
  and ($2 = '' or status = $2)
order by patient_id`

// filterCohort selects the patients this run is permitted to see.
//
// One query, no user predicate. The grant's row filter narrows the result
// proxy-side, so the same action run by two users legitimately returns
// different cohorts -- which is the entire permission beat, and it works
// because this function does not participate in it.
func filterCohort(c *action.Ctx, in CohortQuery) (Cohort, error) {
	rows, err := c.Postgres(ResRecords).Query(cohortSQL, in.Ward, in.Status)
	if err != nil {
		return Cohort{}, fmt.Errorf("querying patient records: %w", err)
	}

	var patients []Patient
	if err := rows.Decode(&patients); err != nil {
		return Cohort{}, fmt.Errorf("decoding patient rows: %w", err)
	}
	sort.Slice(patients, func(i, j int) bool { return patients[i].PatientID < patients[j].PatientID })

	if in.MaxCount > 0 && len(patients) > in.MaxCount {
		patients = patients[:in.MaxCount]
	}
	if patients == nil {
		patients = []Patient{}
	}

	criteria := describeCriteria(in)
	c.Logf("cohort: %d patients matching %s (after permission scoping)", len(patients), criteria)
	c.Emit("clinical.cohort_selected", map[string]any{
		"criteria": criteria, "count": len(patients),
	})

	return Cohort{
		Patients:  patients,
		Count:     len(patients),
		Criteria:  criteria,
		ScopeNote: "This cohort is scoped to the requesting user's permissions; another user may see a different number of patients.",
	}, nil
}

func describeCriteria(in CohortQuery) string {
	parts := []string{}
	if in.Ward != "" {
		parts = append(parts, "ward="+in.Ward)
	}
	if in.Status != "" {
		parts = append(parts, "status="+in.Status)
	}
	if len(parts) == 0 {
		return "all patients"
	}
	return strings.Join(parts, ", ")
}

// manifestScans locates the scan images belonging to a cohort.
//
// Keys outside the run's granted prefix are filtered proxy-side and simply do
// not appear, so a scoped user's manifest is scoped too. A denial on an
// individual key is recorded and treated as absence rather than failing the
// run: a summary that refuses to render because one image is out of scope is
// a summary nobody can use.
func manifestScans(c *action.Ctx, in ScanManifestRequest) (ScanManifest, error) {
	if in.Prefix == "" {
		return ScanManifest{}, fmt.Errorf("prefix is required")
	}

	objects, err := c.S3(ResScans).List(in.Prefix)
	if err != nil {
		if res.Denied(err) {
			// No access to the scan store at all is a legitimate outcome, not a
			// fault: the cohort is simply reported as having no visible images.
			c.Log("warn", "scan store is not in scope for this run", map[string]any{"prefix": in.Prefix})
			return ScanManifest{
				Scans: []Scan{}, WithoutScans: append([]string(nil), in.PatientIDs...),
				Found: 0, Checked: len(in.PatientIDs),
			}, nil
		}
		return ScanManifest{}, fmt.Errorf("listing scans under %s: %w", in.Prefix, err)
	}

	byPatient := map[string][]Scan{}
	for _, o := range objects {
		id := patientIDFromKey(o.Key, in.Prefix)
		if id == "" {
			continue
		}
		byPatient[id] = append(byPatient[id], Scan{PatientID: id, Key: o.Key, Size: o.Size})
	}

	scans := []Scan{}
	without := []string{}
	for _, id := range in.PatientIDs {
		found := byPatient[id]
		if len(found) == 0 {
			without = append(without, id)
			continue
		}
		scans = append(scans, found...)
	}
	sort.Slice(scans, func(i, j int) bool { return scans[i].Key < scans[j].Key })
	sort.Strings(without)

	c.Logf("scan manifest: %d images for %d/%d patients", len(scans), len(in.PatientIDs)-len(without), len(in.PatientIDs))

	return ScanManifest{
		Scans:        scans,
		WithoutScans: without,
		Found:        len(scans),
		Checked:      len(in.PatientIDs),
	}, nil
}

// patientIDFromKey reads the patient id out of a scan key laid out as
// <prefix><patient-id>/<file>.
func patientIDFromKey(key, prefix string) string {
	rest := strings.TrimPrefix(key, prefix)
	if rest == key {
		return "" // not under the prefix at all
	}
	id, _, found := strings.Cut(rest, "/")
	if !found {
		return ""
	}
	return id
}

// patientFields is the full set of fields the vertical Patient type carries.
// Kept beside the check so adding a field to Patient without deciding whether
// it is PHI shows up here as an obvious omission.
var patientFields = []string{"patient_id", "ward", "status", "admitted_on", "diagnosis"}

// checkPHIScope verifies a cohort carries only fields the report may show.
//
// Run before rendering, not after. A report that has already embedded a
// diagnosis cannot un-embed it, and the check exists to stop the render, not to
// annotate the leak.
func checkPHIScope(c *action.Ctx, in PHIScopeRequest) (PHIScopeReport, error) {
	allowed := map[string]bool{}
	for _, f := range in.AllowedFields {
		allowed[f] = true
	}

	violations := []PHIViolation{}
	for _, p := range in.Cohort.Patients {
		for _, field := range patientFields {
			if allowed[field] {
				continue
			}
			if fieldValue(p, field) == "" {
				continue // absent field carries nothing, so nothing leaks
			}
			violations = append(violations, PHIViolation{
				PatientID: p.PatientID,
				Field:     field,
				Reason:    "field is populated but not on the allowlist for this report",
			})
		}
	}
	sort.Slice(violations, func(i, j int) bool {
		if violations[i].PatientID != violations[j].PatientID {
			return violations[i].PatientID < violations[j].PatientID
		}
		return violations[i].Field < violations[j].Field
	})

	clean := len(violations) == 0
	if !clean {
		c.Log("warn", "cohort carries fields outside the report's allowlist", map[string]any{
			"violations": len(violations),
		})
	}
	c.Emit("clinical.phi_scope_checked", map[string]any{
		"clean": clean, "violations": len(violations), "allowed_fields": in.AllowedFields,
	})

	return PHIScopeReport{
		Clean:         clean,
		Violations:    violations,
		FieldsChecked: patientFields,
	}, nil
}

func fieldValue(p Patient, field string) string {
	switch field {
	case "patient_id":
		return p.PatientID
	case "ward":
		return p.Ward
	case "status":
		return p.Status
	case "admitted_on":
		return p.AdmittedOn
	case "diagnosis":
		return p.Diagnosis
	default:
		return ""
	}
}

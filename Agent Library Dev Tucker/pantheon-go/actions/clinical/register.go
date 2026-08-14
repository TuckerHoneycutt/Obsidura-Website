package clinical

import (
	"time"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/kernel"
)

// Register adds the clinical vertical to a registry.
func Register(r *action.Registry) {
	action.Register(r, action.Spec{
		Name:    "clinical.filter_cohort",
		Version: 1,
		Input:   kernel.Ref("clinical.CohortQuery", 1),
		Output:  kernel.Ref("clinical.Cohort", 1),
		Uses:    []action.ResourceUse{{Name: ResRecords, Verbs: []string{"query"}}},
		Policy:  action.Policy{Timeout: 60 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Select the patients matching clinical criteria that the requester may see.",
	}, filterCohort)

	action.Register(r, action.Spec{
		Name:    "clinical.manifest_scans",
		Version: 1,
		Input:   kernel.Ref("clinical.ScanManifestRequest", 1),
		Output:  kernel.Ref("clinical.ScanManifest", 1),
		Uses:    []action.ResourceUse{{Name: ResScans, Verbs: []string{"get", "list"}}},
		Policy:  action.Policy{Timeout: 120 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Locate the scan images belonging to a patient cohort.",
	}, manifestScans)

	action.Register(r, action.Spec{
		Name:    "clinical.check_phi_scope",
		Version: 1,
		Input:   kernel.Ref("clinical.PHIScopeRequest", 1),
		Output:  kernel.Ref("clinical.PHIScopeReport", 1),
		Policy:  action.Policy{Timeout: 30 * time.Second, Retry: 2, Idempotent: true},
		Summary: "Verify a cohort carries only the patient fields this report is allowed to show.",
	}, checkPHIScope)
}

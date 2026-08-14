package clinical_test

import (
	"reflect"
	"strings"
	"testing"
)

// fieldNames lists the JSON field names a TYPE can carry.
//
// Reflection over the type, not marshalling of a value. Every field on
// CohortQuery is omitempty, so json.Marshal of the zero value returns "{}" and
// a test written that way would pass no matter what fields existed -- which is
// exactly the vacuous assertion this helper exists to avoid.
func fieldNames(t *testing.T, v any) []string {
	t.Helper()
	rt := reflect.TypeOf(v)
	for rt.Kind() == reflect.Pointer {
		rt = rt.Elem()
	}
	if rt.Kind() != reflect.Struct {
		t.Fatalf("fieldNames: %T is not a struct", v)
	}
	var out []string
	for i := 0; i < rt.NumField(); i++ {
		f := rt.Field(i)
		if !f.IsExported() {
			continue
		}
		name := f.Name
		if tag := f.Tag.Get("json"); tag != "" && tag != "-" {
			if n, _, _ := strings.Cut(tag, ","); n != "" {
				name = n
			}
		}
		out = append(out, strings.ToLower(name))
	}
	return out
}

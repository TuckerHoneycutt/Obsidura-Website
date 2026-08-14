// Package deck assembles every vertical into one registry and describes it for
// the GUI.
//
// The end-user product is a deck of repeatable actions a non-technical worker
// presses (Discussion Context.md:29). Its labels are generated from the same
// Spec the executor reads, so the button, the definition and the code cannot
// disagree -- which is the whole reason Spec.Summary is a required field and
// not a comment.
package deck

import (
	"sort"

	"github.com/obsidura/pantheon-go/action"
	"github.com/obsidura/pantheon-go/actions/clinical"
	"github.com/obsidura/pantheon-go/actions/finance"
	"github.com/obsidura/pantheon-go/actions/telemetry"
)

// All builds the registry this runner image serves.
//
// One binary, every action. Per-action images are a bonus chunk (spec §11, B4)
// and nothing here assumes them; a Go binary holding fourteen actions costs the
// same to start as one holding one.
func All() *action.Registry {
	r := action.NewRegistry()
	finance.Register(r)
	telemetry.Register(r)
	clinical.Register(r)
	return r
}

// Card is one deck button.
type Card struct {
	Name      string   `json:"name"`
	Version   int      `json:"version"`
	Vertical  string   `json:"vertical"`
	Summary   string   `json:"summary"`
	Input     string   `json:"input"`
	Output    string   `json:"output"`
	Resources []string `json:"resources" desc:"Resources the caller must have grants on"`
}

// Catalog describes every action for the GUI, sorted by name.
func Catalog(r *action.Registry) []Card {
	cards := make([]Card, 0, len(r.Names()))
	for _, e := range r.Entries() {
		resources := make([]string, 0, len(e.Spec.Uses))
		for _, u := range e.Spec.Uses {
			resources = append(resources, u.Name)
		}
		sort.Strings(resources)
		cards = append(cards, Card{
			Name:      e.Spec.Name,
			Version:   e.Spec.Version,
			Vertical:  vertical(e.Spec.Name),
			Summary:   e.Spec.Summary,
			Input:     e.Spec.Input.String(),
			Output:    e.Spec.Output.String(),
			Resources: resources,
		})
	}
	return cards
}

func vertical(name string) string {
	for i := 0; i < len(name); i++ {
		if name[i] == '.' {
			return name[:i]
		}
	}
	return name
}

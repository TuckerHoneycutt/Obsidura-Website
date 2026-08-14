// Package lint holds build-time properties that review cannot be trusted to
// enforce by reading.
package lint

import (
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
)

// allowedInActions is what an action body may import.
//
// An allowlist, not a denylist. A denylist passes on every package nobody
// thought to forbid, and the first cloud SDK someone adds would sail through --
// the same fail-open shape the guard SPEC rejects for destructive verbs. Only
// membership in a known-good set fails closed.
var allowedInActions = map[string]bool{
	// SDK. res is the sole egress, and it is the only package here that
	// touches a socket.
	"github.com/obsidura/pantheon-go/action":       true,
	"github.com/obsidura/pantheon-go/kernel":       true,
	"github.com/obsidura/pantheon-go/res":          true,
	"github.com/obsidura/pantheon-go/table":        true,
	"github.com/obsidura/pantheon-go/actions/core": true,

	// Pure computation and formatting. Nothing here can reach outside the
	// process.
	"context":       true,
	"encoding/csv":  true,
	"encoding/json": true,
	"errors":        true,
	"fmt":           true,
	"io":            true,
	"math":          true,
	"sort":          true,
	"strconv":       true,
	"strings":       true,
	"time":          true,
	"unicode":       true,
	"unicode/utf8":  true,
}

// forbiddenReason explains the packages most likely to be reached for, so the
// failure teaches rather than merely refuses.
var forbiddenReason = map[string]string{
	"net":          "opening a socket bypasses the proxy; use ctx.HTTP or ctx.Postgres",
	"net/http":     "an action must reach HTTP only through ctx.HTTP, so the URL allowlist and audit log apply",
	"database/sql": "an action never holds a database credential; use ctx.Postgres",
	"os":           "an action has no filesystem of its own; data arrives as a payload or through the proxy",
	"os/exec":      "spawning a process escapes every capability check in one line",
	"syscall":      "an action must not touch the host directly",
	"net/url":      "URL construction is fine, but it usually arrives with a client; if genuinely needed, add it to the allowlist deliberately",
}

// TestActionsImportOnlyTheSDK is the property that makes spec §8's promise real:
// credentials live executor-side and never reach the container.
//
// An action that opens its own connection bypasses capability enforcement,
// taint recording, budget metering and the audit log at once -- and does it in
// a single plausible-looking line that review will wave through under deadline.
// This test is why that line cannot land.
func TestActionsImportOnlyTheSDK(t *testing.T) {
	root := repoRoot(t)
	actionsDir := filepath.Join(root, "actions")

	type violation struct{ file, pkg, reason string }
	var found []violation

	err := filepath.Walk(actionsDir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() || !strings.HasSuffix(path, ".go") {
			return nil
		}
		// Test files may import testing and ptnfake; the constraint is on what
		// SHIPS, and a test binary is not the runner image.
		if strings.HasSuffix(path, "_test.go") {
			return nil
		}

		fset := token.NewFileSet()
		f, err := parser.ParseFile(fset, path, nil, parser.ImportsOnly)
		if err != nil {
			return err
		}
		rel, _ := filepath.Rel(root, path)
		for _, imp := range f.Imports {
			pkg, err := strconv.Unquote(imp.Path.Value)
			if err != nil {
				return err
			}
			if allowedInActions[pkg] {
				continue
			}
			reason := forbiddenReason[pkg]
			if reason == "" {
				reason = "not on the action allowlist; add it deliberately in lint/imports_test.go if it is genuinely pure"
			}
			found = append(found, violation{rel, pkg, reason})
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking actions/: %v", err)
	}

	sort.Slice(found, func(i, j int) bool { return found[i].file < found[j].file })
	for _, v := range found {
		t.Errorf("%s imports %q\n    %s", v.file, v.pkg, v.reason)
	}
}

// TestOnlyResPackageDialsTheNetwork keeps the egress surface to one file.
//
// The previous test constrains actions/; this one constrains the SDK itself, so
// a well-meaning helper in table/ or action/ cannot quietly become a second way
// out of the process.
func TestOnlyResPackageDialsTheNetwork(t *testing.T) {
	root := repoRoot(t)

	// Packages legitimately holding a socket: res is the client, ptnfake is the
	// test-only server, serve owns stdio.
	allowedNetworkPkgs := map[string]bool{
		"res":     true,
		"ptnfake": true,
		"serve":   true,
	}
	networkImports := map[string]bool{
		"net": true, "net/http": true, "database/sql": true, "os/exec": true,
	}

	err := filepath.Walk(root, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			if info.Name() == "definitions" || info.Name() == "testdata" || info.Name() == ".git" {
				return filepath.SkipDir
			}
			return nil
		}
		if !strings.HasSuffix(path, ".go") || strings.HasSuffix(path, "_test.go") {
			return nil
		}
		pkgDir := filepath.Base(filepath.Dir(path))
		if allowedNetworkPkgs[pkgDir] {
			return nil
		}

		fset := token.NewFileSet()
		f, perr := parser.ParseFile(fset, path, nil, parser.ImportsOnly)
		if perr != nil {
			return perr
		}
		rel, _ := filepath.Rel(root, path)
		for _, imp := range f.Imports {
			pkg, _ := strconv.Unquote(imp.Path.Value)
			if networkImports[pkg] {
				t.Errorf("%s imports %q, but only res/ (and its test double) may reach the network", rel, pkg)
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("walking repo: %v", err)
	}
}

func repoRoot(t *testing.T) string {
	t.Helper()
	wd, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	// The test runs in lint/; the module root is its parent.
	return filepath.Dir(wd)
}

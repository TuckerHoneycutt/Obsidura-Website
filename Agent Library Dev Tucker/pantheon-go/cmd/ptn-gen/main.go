// Command ptn-gen generates and checks the artifacts derived from the registry.
//
//	ptn-gen emit   [-o dir]   write YAML task definitions and JSON schemas
//	ptn-gen check  [-o dir]   fail if what is on disk differs from what emit would write
//	ptn-gen catalog           print the deck catalog as JSON
//	ptn-gen hello             print the handshake response, for wiring a new executor
//
// `check` is the drift gate. The committed YAML is the artifact of record and
// Go is only how it is produced; without a gate the two diverge and the
// definitions stop describing what actually runs.
package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"os"

	"github.com/obsidura/pantheon-go/deck"
	"github.com/obsidura/pantheon-go/emit"
	"github.com/obsidura/pantheon-go/serve"
)

func main() {
	out := flag.String("o", "definitions", "output directory for emit and check")
	flag.Usage = usage
	flag.Parse()

	args := flag.Args()
	if len(args) == 0 {
		usage()
		os.Exit(2)
	}

	reg := deck.All()

	switch args[0] {
	case "emit":
		files, err := emit.Definitions(reg)
		check(err)
		check(emit.Write(*out, files))
		fmt.Fprintf(os.Stderr, "wrote %d files to %s\n", len(files), *out)

	case "check":
		files, err := emit.Definitions(reg)
		check(err)
		drifted, err := emit.Check(*out, files)
		check(err)
		if len(drifted) > 0 {
			fmt.Fprintf(os.Stderr, "definitions in %s have drifted from the registry:\n", *out)
			for _, d := range drifted {
				fmt.Fprintf(os.Stderr, "  %s\n", d)
			}
			fmt.Fprintf(os.Stderr, "\nrun `ptn-gen emit` and commit the result\n")
			os.Exit(1)
		}
		fmt.Fprintf(os.Stderr, "%s is in sync with the registry (%d files)\n", *out, len(files))

	case "catalog":
		b, err := json.MarshalIndent(deck.Catalog(reg), "", "  ")
		check(err)
		fmt.Println(string(b))

	case "hello":
		descs := []map[string]any{}
		for _, e := range reg.Entries() {
			descs = append(descs, map[string]any{
				"name": e.Spec.Name, "version": e.Spec.Version,
				"input": e.Spec.Input.String(), "output": e.Spec.Output.String(),
				"summary": e.Spec.Summary,
			})
		}
		b, err := json.MarshalIndent(map[string]any{
			"protocol_version": serve.ProtocolVersion,
			"kernel_version":   serve.KernelVersion,
			"runner":           serve.RunnerName,
			"actions":          descs,
		}, "", "  ")
		check(err)
		fmt.Println(string(b))

	default:
		fmt.Fprintf(os.Stderr, "ptn-gen: unknown command %q\n\n", args[0])
		usage()
		os.Exit(2)
	}
}

func usage() {
	fmt.Fprint(os.Stderr, `usage: ptn-gen [-o dir] <command>

  emit      write YAML task definitions and JSON schemas
  check     fail if on-disk definitions differ from the registry (the drift gate)
  catalog   print the deck catalog as JSON
  hello     print the handshake response
`)
}

func check(err error) {
	if err != nil {
		fmt.Fprintf(os.Stderr, "ptn-gen: %v\n", err)
		os.Exit(1)
	}
}

// Command runner is the Go task runner image's entrypoint.
//
// It serves every registered action over stdio and does nothing else. All of
// its behaviour is in the library, so there is no logic here that a test cannot
// reach without spawning a process.
package main

import (
	"fmt"
	"os"

	"github.com/obsidura/pantheon-go/deck"
	"github.com/obsidura/pantheon-go/serve"
)

func main() {
	if err := serve.Run(deck.All()); err != nil {
		// stdout belongs to the protocol; diagnostics go to stderr, which the
		// executor captures as unstructured logs.
		fmt.Fprintf(os.Stderr, "runner: %v\n", err)
		os.Exit(1)
	}
}

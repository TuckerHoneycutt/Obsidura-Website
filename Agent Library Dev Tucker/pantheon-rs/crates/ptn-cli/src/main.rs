//! The `ptn` command.
//!
//!     ptn plan  [--registry FILE] DIR...    show the diff; exit 1 on any diagnostic
//!     ptn apply [--registry FILE] DIR...    plan, then register
//!
//! Exit codes are the interface a CI job uses, so they are stated rather than
//! implied:
//!
//! | code | meaning |
//! |------|---------|
//! | 0    | plan is clean (and, for apply, was applied) |
//! | 1    | one or more definitions were rejected |
//! | 2    | bad usage |
//! | 3    | the registry could not be read or written |

use std::path::PathBuf;
use std::process::ExitCode;

use ptn_registry::{plan, Change, FileStore, Store};

const USAGE: &str = "\
usage: ptn <plan|apply> [--registry FILE] DIR...

  plan    load and validate the given definition directories, and show what
          applying them would change
  apply   the same, then register the result

  --registry FILE   registry location (default: .ptn/registry.json)

Multiple directories are allowed and form one registry: generated definitions
and hand-authored wiring live apart and are validated together.
";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args.is_empty() {
        eprint!("{USAGE}");
        return ExitCode::from(2);
    }

    let command = args[0].clone();

    // `ptn -h` before any command, which is how everyone asks. Handled here
    // rather than only in the flag loop below, because that loop starts after
    // the command and would report help as an unknown command.
    if matches!(command.as_str(), "-h" | "--help" | "help") {
        print!("{USAGE}");
        return ExitCode::SUCCESS;
    }

    let mut registry = PathBuf::from(".ptn/registry.json");
    let mut roots: Vec<PathBuf> = Vec::new();

    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--registry" => {
                i += 1;
                match args.get(i) {
                    Some(v) => registry = PathBuf::from(v),
                    None => {
                        eprintln!("ptn: --registry needs a path");
                        return ExitCode::from(2);
                    }
                }
            }
            "-h" | "--help" => {
                print!("{USAGE}");
                return ExitCode::SUCCESS;
            }
            other if other.starts_with('-') => {
                eprintln!("ptn: unknown flag {other}");
                return ExitCode::from(2);
            }
            other => roots.push(PathBuf::from(other)),
        }
        i += 1;
    }

    if !matches!(command.as_str(), "plan" | "apply") {
        eprintln!("ptn: unknown command {command:?}");
        eprint!("{USAGE}");
        return ExitCode::from(2);
    }
    if roots.is_empty() {
        eprintln!("ptn: at least one definition directory is required");
        return ExitCode::from(2);
    }

    let mut store = FileStore::new(&registry);
    let planned = match plan(&roots, &store) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("ptn: {e}");
            return ExitCode::from(3);
        }
    };

    if !planned.diagnostics.is_empty() {
        eprintln!(
            "ptn {command}: {} definition(s) rejected\n",
            planned.diagnostics.len()
        );
        eprint!("{}", planned.diagnostics);
        eprintln!("\nNothing was applied.");
        return ExitCode::from(1);
    }

    let counts = planned.counts();
    let interesting: Vec<_> = planned.interesting().collect();

    if interesting.is_empty() {
        println!(
            "ptn {command}: no changes ({} registered)",
            planned.changes.len()
        );
    } else {
        println!("ptn {command}:");
        for c in &interesting {
            match &c.file {
                Some(f) => println!(
                    "  {:9} {:9} {}  ({})",
                    c.change,
                    c.kind,
                    c.reference,
                    f.display()
                ),
                None => println!("  {:9} {:9} {}", c.change, c.kind, c.reference),
            }
        }
        println!();
    }

    let summary: Vec<String> = counts.iter().map(|(k, v)| format!("{v} {k}")).collect();
    println!("  {}", summary.join(", "));

    if counts.get(&Change::Orphan).copied().unwrap_or(0) > 0 {
        // Reported, never applied. Removing a definition out from under a
        // mid-flight run is a different operation with different safety
        // questions; folding it into apply would answer them by accident.
        println!("\n  Orphans are reported, not removed. Delete them deliberately.");
    }

    if command == "apply" {
        if let Err(e) = store.apply(&planned.to_apply) {
            eprintln!("ptn apply: {e}");
            return ExitCode::from(3);
        }
        println!("\n  Applied to {}", registry.display());
    }

    ExitCode::SUCCESS
}

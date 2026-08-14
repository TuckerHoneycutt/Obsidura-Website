//! The `ptn` command's exit codes and output.
//!
//! Exit codes are the interface a CI job uses, so they are tested rather than
//! only documented. A `plan` that exits 0 on a rejected definition would let a
//! broken registry through the one gate meant to stop it.
//!
//! | code | meaning |
//! |------|---------|
//! | 0    | plan is clean (and, for apply, was applied) |
//! | 1    | one or more definitions were rejected |
//! | 2    | bad usage |
//! | 3    | the registry could not be read or written |

use std::fs;
use std::path::PathBuf;
use std::process::{Command, Output};

/// A throwaway definition directory plus registry path.
struct Sandbox {
    root: PathBuf,
}

impl Sandbox {
    fn new(name: &str) -> Self {
        let root = std::env::temp_dir().join(format!("ptn-cli-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(root.join("defs")).unwrap();
        Sandbox { root }
    }

    fn write(&self, rel: &str, body: &str) -> &Self {
        let p = self.root.join("defs").join(rel);
        fs::create_dir_all(p.parent().unwrap()).unwrap();
        fs::write(p, body).unwrap();
        self
    }

    fn registry(&self) -> PathBuf {
        self.root.join("registry.json")
    }

    fn run(&self, args: &[&str]) -> Output {
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_ptn"));
        cmd.args(args);
        cmd.output().expect("running ptn")
    }

    fn plan(&self) -> Output {
        self.run(&[
            "plan",
            "--registry",
            self.registry().to_str().unwrap(),
            self.root.join("defs").to_str().unwrap(),
        ])
    }

    fn apply(&self) -> Output {
        self.run(&[
            "apply",
            "--registry",
            self.registry().to_str().unwrap(),
            self.root.join("defs").to_str().unwrap(),
        ])
    }
}

impl Drop for Sandbox {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

fn code(out: &Output) -> i32 {
    out.status.code().unwrap_or(-1)
}

fn stdout(out: &Output) -> String {
    String::from_utf8_lossy(&out.stdout).into_owned()
}

fn stderr(out: &Output) -> String {
    String::from_utf8_lossy(&out.stderr).into_owned()
}

const SCHEMA_IN: &str =
    "kind: schema\nname: demo.In\nversion: 1\ndocument: {\"type\":\"object\"}\n";
const SCHEMA_OUT: &str =
    "kind: schema\nname: demo.Out\nversion: 1\ndocument: {\"type\":\"object\"}\n";
const TASK: &str = r#"
kind: task
name: demo.work
version: 1
summary: Does the thing.
runner: {kind: script, runtime: go, entry: demo.work}
input: demo.In@1
output: demo.Out@1
policy: {timeout: "30s", retry: 0, idempotent: false}
"#;

// ------------------------------------------------------------ exit codes ----

#[test]
fn a_clean_plan_exits_zero() {
    let s = Sandbox::new("clean");
    s.write("in.yaml", SCHEMA_IN)
        .write("out.yaml", SCHEMA_OUT)
        .write("task.yaml", TASK);

    let out = s.plan();
    assert_eq!(code(&out), 0, "stderr:\n{}", stderr(&out));
    assert!(stdout(&out).contains("3 add"), "stdout:\n{}", stdout(&out));
}

#[test]
fn a_rejected_definition_exits_one_and_applies_nothing() {
    let s = Sandbox::new("rejected");
    s.write("in.yaml", SCHEMA_IN).write("task.yaml", TASK); // demo.Out@1 missing

    let out = s.apply();
    assert_eq!(code(&out), 1, "stdout:\n{}", stdout(&out));

    let err = stderr(&out);
    assert!(err.contains("unresolved-ref"), "stderr:\n{err}");
    assert!(err.contains("demo.Out@1"), "stderr:\n{err}");
    assert!(
        err.contains("Nothing was applied"),
        "the CLI must say nothing was applied:\n{err}"
    );
    assert!(
        !s.registry().exists(),
        "a rejected apply must not create a registry"
    );
}

#[test]
fn no_arguments_exits_two_with_usage() {
    let s = Sandbox::new("noargs");
    let out = s.run(&[]);
    assert_eq!(code(&out), 2);
    assert!(stderr(&out).contains("usage: ptn"));
}

#[test]
fn an_unknown_command_exits_two() {
    let s = Sandbox::new("unknowncmd");
    let out = s.run(&["destroy", "defs"]);
    assert_eq!(code(&out), 2);
    assert!(stderr(&out).contains("unknown command"));
}

#[test]
fn an_unknown_flag_exits_two() {
    let s = Sandbox::new("unknownflag");
    let out = s.run(&["plan", "--force", "defs"]);
    assert_eq!(code(&out), 2);
    // There is deliberately no --force. Accepting it silently would be worse
    // than refusing it.
    assert!(stderr(&out).contains("unknown flag"));
}

#[test]
fn a_missing_directory_argument_exits_two() {
    let s = Sandbox::new("nodir");
    let out = s.run(&["plan"]);
    assert_eq!(code(&out), 2);
    assert!(stderr(&out).contains("at least one definition directory"));
}

#[test]
fn registry_flag_without_a_value_exits_two() {
    let s = Sandbox::new("noregval");
    let out = s.run(&["plan", "--registry"]);
    assert_eq!(code(&out), 2);
}

#[test]
fn an_unreadable_registry_exits_three() {
    let s = Sandbox::new("badreg");
    s.write("in.yaml", SCHEMA_IN);
    fs::write(s.registry(), "{ not json").unwrap();

    let out = s.plan();
    assert_eq!(
        code(&out),
        3,
        "a corrupt registry is an infrastructure fault, not a rejected definition"
    );
}

#[test]
fn help_exits_zero() {
    let s = Sandbox::new("help");
    for flag in ["-h", "--help"] {
        let out = s.run(&[flag]);
        assert_eq!(code(&out), 0, "{flag}");
        assert!(stdout(&out).contains("usage: ptn"), "{flag}");
    }
}

// --------------------------------------------------------------- behaviour ----

#[test]
fn apply_is_idempotent() {
    let s = Sandbox::new("idempotent");
    s.write("in.yaml", SCHEMA_IN)
        .write("out.yaml", SCHEMA_OUT)
        .write("task.yaml", TASK);

    assert_eq!(code(&s.apply()), 0);
    let second = s.apply();
    assert_eq!(code(&second), 0);
    assert!(
        stdout(&second).contains("no changes"),
        "a second apply must be a no-op:\n{}",
        stdout(&second)
    );
    assert!(stdout(&second).contains("3 unchanged"));
}

#[test]
fn an_orphan_is_reported_and_the_plan_still_applies() {
    let s = Sandbox::new("orphan");
    s.write("in.yaml", SCHEMA_IN)
        .write("out.yaml", SCHEMA_OUT)
        .write("task.yaml", TASK);
    assert_eq!(code(&s.apply()), 0);

    fs::remove_file(s.root.join("defs").join("task.yaml")).unwrap();
    let out = s.plan();

    assert_eq!(code(&out), 0, "an orphan is a report, not a rejection");
    let text = stdout(&out);
    assert!(text.contains("orphan"), "stdout:\n{text}");
    assert!(
        text.contains("Orphans are reported, not removed"),
        "the CLI must say it did not delete anything:\n{text}"
    );
}

#[test]
fn plan_does_not_write_a_registry() {
    let s = Sandbox::new("planonly");
    s.write("in.yaml", SCHEMA_IN)
        .write("out.yaml", SCHEMA_OUT)
        .write("task.yaml", TASK);

    assert_eq!(code(&s.plan()), 0);
    assert!(
        !s.registry().exists(),
        "plan must be read-only; only apply writes"
    );
}

#[test]
fn multiple_directories_are_validated_as_one_graph() {
    // Generated definitions and hand-authored wiring live apart and must still
    // resolve against each other.
    let s = Sandbox::new("multiroot");
    fs::create_dir_all(s.root.join("wiring")).unwrap();
    s.write("in.yaml", SCHEMA_IN).write("out.yaml", SCHEMA_OUT);
    fs::write(s.root.join("wiring").join("task.yaml"), TASK).unwrap();

    let out = s.run(&[
        "plan",
        "--registry",
        s.registry().to_str().unwrap(),
        s.root.join("defs").to_str().unwrap(),
        s.root.join("wiring").to_str().unwrap(),
    ]);
    assert_eq!(code(&out), 0, "stderr:\n{}", stderr(&out));
    assert!(stdout(&out).contains("3 add"));
}

#[test]
fn every_diagnostic_is_reported_not_just_the_first() {
    let s = Sandbox::new("manyerrors");
    s.write(
        "task.yaml",
        r#"
kind: task
name: demo.broken
version: 1
runner: {kind: script, runtime: go, entry: demo.broken}
input: demo.Missing1@1
output: demo.Missing2@1
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
    );

    let out = s.plan();
    assert_eq!(code(&out), 1);
    let err = stderr(&out);
    assert!(err.contains("demo.Missing1@1"), "stderr:\n{err}");
    assert!(err.contains("demo.Missing2@1"), "stderr:\n{err}");
    assert!(err.contains("2 definition(s) rejected"), "stderr:\n{err}");
}

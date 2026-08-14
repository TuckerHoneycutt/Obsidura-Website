//! Acceptance tests 1 and 2 from the spec, plus the rules they rest on.
//!
//! > 1. `ptn apply` on the demo definition directory succeeds; a deliberately
//! >    invalid definition is rejected with a clear, located error.
//! > 2. ... the inter-task seam validates contracts (and a mismatched pair is
//! >    rejected at plan time).
//!
//! Each definition is written inline rather than committed as a fixture
//! directory, so the input a test rejects sits next to the assertion about why.
//! A reader should not have to open a second file to learn what "invalid" meant.

use std::fs;
use std::path::PathBuf;

use ptn_registry::{plan, Change, FileStore, Rule, Store};

/// A throwaway definition directory. Removed on drop.
struct Dir {
    root: PathBuf,
}

impl Dir {
    fn new(name: &str) -> Self {
        let root = std::env::temp_dir().join(format!("ptn-test-{name}-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        Dir { root }
    }

    fn write(&self, rel: &str, body: &str) -> &Self {
        let path = self.root.join(rel);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, body).unwrap();
        self
    }

    fn roots(&self) -> Vec<PathBuf> {
        vec![self.root.clone()]
    }

    fn registry(&self) -> FileStore {
        FileStore::new(self.root.join(".registry.json"))
    }
}

impl Drop for Dir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}

/// A schema definition, since almost every other rule needs refs that resolve.
fn schema(name: &str) -> String {
    format!("kind: schema\nname: {name}\nversion: 1\ndocument: {{\"type\":\"object\"}}\n")
}

// ---------------------------------------------------------------- test 1 ----

#[test]
fn acceptance_1_a_valid_directory_applies() {
    let d = Dir::new("valid");
    d.write("schemas/in.yaml", &schema("demo.In"))
        .write("schemas/out.yaml", &schema("demo.Out"))
        .write(
            "resources/db.yaml",
            "kind: resource\nname: db\nversion: 1\nconnector: postgres\nverbs: [query]\n",
        )
        .write(
            "tasks/work.yaml",
            r#"
kind: task
name: demo.work
version: 1
summary: Does the thing.
runner: {kind: script, runtime: go, entry: demo.work}
input: demo.In@1
output: demo.Out@1
uses:
  - name: db
    verbs: [query]
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        );

    let mut store = d.registry();
    let planned = plan(&d.roots(), &store).unwrap();

    assert!(
        planned.is_applyable(),
        "a valid directory must plan cleanly, got:\n{}",
        planned.diagnostics
    );
    assert_eq!(planned.changes.len(), 4);
    assert_eq!(planned.counts().get(&Change::Add), Some(&4));

    store.apply(&planned.to_apply).unwrap();

    // Applying twice must be a no-op, or `ptn apply` in CI churns the registry.
    let again = plan(&d.roots(), &store).unwrap();
    assert_eq!(again.counts().get(&Change::Unchanged), Some(&4));
    assert_eq!(again.interesting().count(), 0);
}

#[test]
fn acceptance_1_an_invalid_definition_is_rejected_with_file_field_and_rule() {
    let d = Dir::new("invalid");
    d.write("schemas/in.yaml", &schema("demo.In")).write(
        "tasks/broken.yaml",
        r#"
kind: task
name: demo.broken
version: 1
summary: References a schema nobody declared.
runner: {kind: script, runtime: go, entry: demo.broken}
input: demo.In@1
output: demo.NoSuchThing@3
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
    );

    let planned = plan(&d.roots(), &d.registry()).unwrap();

    assert!(
        !planned.is_applyable(),
        "the invalid definition was accepted"
    );
    assert!(
        planned.to_apply.is_empty(),
        "nothing may be staged from a rejected plan"
    );

    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::UnresolvedRef)
        .expect("expected an unresolved-ref diagnostic");

    // Spec §7 requires all three: file, field, rule.
    assert!(
        diag.file.to_string_lossy().ends_with("tasks/broken.yaml"),
        "diagnostic does not name the file: {diag}"
    );
    assert_eq!(diag.field, "output", "diagnostic does not name the field");
    assert_eq!(diag.rule, Rule::UnresolvedRef);
    assert!(
        diag.message.contains("demo.NoSuchThing@3"),
        "the message should name what could not be resolved: {diag}"
    );
}

#[test]
fn every_problem_is_reported_not_just_the_first() {
    // An author who fixes one error per plan run is an author who stops
    // running plan.
    let d = Dir::new("many");
    d.write("schemas/in.yaml", &schema("demo.In")).write(
        "tasks/a.yaml",
        r#"
kind: task
name: demo.a
version: 1
runner: {kind: script, runtime: go, entry: demo.a}
input: demo.Missing1@1
output: demo.Missing2@1
uses:
  - name: nosuchresource
    verbs: [query]
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
    );

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    assert!(
        planned.diagnostics.len() >= 3,
        "expected input, output and uses to all be reported; got:\n{}",
        planned.diagnostics
    );
}

#[test]
fn an_unparseable_file_names_its_location() {
    let d = Dir::new("unparseable");
    d.write("tasks/bad.yaml", "kind: task\nname: [this is not a name\n");

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::Unparseable)
        .expect("expected an unparseable diagnostic");
    assert!(
        diag.field.contains("line"),
        "a parse failure should carry a line: {diag}"
    );
}

#[test]
fn a_duplicate_name_names_both_files() {
    let d = Dir::new("dupe");
    d.write("schemas/a.yaml", &schema("demo.Thing"))
        .write("schemas/b.yaml", &schema("demo.Thing"));

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::DuplicateName)
        .expect("a name declared twice must be rejected");
    assert!(
        diag.message.contains("a.yaml"),
        "the diagnostic should point at the other declaration: {diag}"
    );
}

#[test]
fn a_verb_the_resource_does_not_expose_is_rejected() {
    // The proxy would refuse this at run time. Catching it at plan time turns
    // a production denial into a build error.
    let d = Dir::new("verb");
    d.write("schemas/in.yaml", &schema("demo.In"))
        .write("schemas/out.yaml", &schema("demo.Out"))
        .write(
            "resources/store.yaml",
            "kind: resource\nname: store\nversion: 1\nconnector: s3\nverbs: [get, list]\n",
        )
        .write(
            "tasks/deleter.yaml",
            r#"
kind: task
name: demo.deleter
version: 1
runner: {kind: script, runtime: go, entry: demo.deleter}
input: demo.In@1
output: demo.Out@1
uses:
  - name: store
    verbs: [get, delete]
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        );

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::UndeclaredVerb)
        .expect("an undeclared verb must be rejected");
    assert_eq!(diag.field, "uses[0].verbs");
    assert!(diag.message.contains("delete"), "{diag}");
}

// ---------------------------------------------------------------- test 2 ----

#[test]
fn acceptance_2_a_mismatched_pair_is_rejected_at_plan_time() {
    let d = Dir::new("mismatch");
    d.write("schemas/a.yaml", &schema("demo.A"))
        .write("schemas/b.yaml", &schema("demo.B"))
        .write("schemas/c.yaml", &schema("demo.C"))
        .write(
            "tasks/first.yaml",
            r#"
kind: task
name: demo.first
version: 1
runner: {kind: script, runtime: go, entry: demo.first}
input: demo.A@1
output: demo.B@1
then: [demo.second@1]
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        )
        .write(
            "tasks/second.yaml",
            r#"
kind: task
name: demo.second
version: 1
runner: {kind: script, runtime: go, entry: demo.second}
input: demo.C@1
output: demo.C@1
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        );

    let planned = plan(&d.roots(), &d.registry()).unwrap();

    assert!(!planned.is_applyable(), "a mismatched seam was accepted");
    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::ContractMismatch)
        .expect("expected a contract-mismatch diagnostic");

    assert_eq!(diag.field, "then[0]");
    assert!(
        diag.message.contains("demo.B@1") && diag.message.contains("demo.C@1"),
        "the message should name both sides of the seam: {diag}"
    );
    // Spec §7 offers exactly two legal ways to bridge differing shapes. Saying
    // so in the error is the difference between a rejection and a lesson.
    assert!(
        diag.message.contains("adapter") || diag.message.contains("mapping"),
        "the message should say how to fix it: {diag}"
    );
}

#[test]
fn a_matching_pair_is_accepted() {
    // The vacuity guard for the test above: the checker must not simply reject
    // every `then:`.
    let d = Dir::new("match");
    d.write("schemas/a.yaml", &schema("demo.A"))
        .write("schemas/b.yaml", &schema("demo.B"))
        .write(
            "tasks/first.yaml",
            r#"
kind: task
name: demo.first
version: 1
runner: {kind: script, runtime: go, entry: demo.first}
input: demo.A@1
output: demo.B@1
then: [demo.second@1]
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        )
        .write(
            "tasks/second.yaml",
            r#"
kind: task
name: demo.second
version: 1
runner: {kind: script, runtime: go, entry: demo.second}
input: demo.B@1
output: demo.A@1
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        );

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    assert!(
        planned.is_applyable(),
        "a matching seam must be accepted:\n{}",
        planned.diagnostics
    );
}

#[test]
fn a_trigger_that_emits_the_wrong_shape_is_rejected() {
    // The trigger seam is a contract like any other.
    let d = Dir::new("trigger");
    d.write("schemas/a.yaml", &schema("demo.A"))
        .write("schemas/b.yaml", &schema("demo.B"))
        .write(
            "triggers/hook.yaml",
            "kind: trigger\nname: demo.hook\nversion: 1\nsource: webhook\npath: /x\nemits: demo.A@1\n",
        )
        .write(
            "tasks/entry.yaml",
            r#"
kind: task
name: demo.entry
version: 1
runner: {kind: script, runtime: go, entry: demo.entry}
input: demo.B@1
output: demo.B@1
on: demo.hook@1
policy: {timeout: "30s", retry: 0, idempotent: false}
"#,
        );

    let planned = plan(&d.roots(), &d.registry()).unwrap();
    let diag = planned
        .diagnostics
        .iter()
        .find(|d| d.rule == Rule::ContractMismatch)
        .expect("a trigger emitting the wrong shape must be rejected");
    assert_eq!(diag.field, "on");
}

// ------------------------------------------------------------- the corpus ----

/// The real definition directories must plan cleanly.
///
/// This is the regression test that matters: everything above uses toy input,
/// and toy input cannot catch a rule that is wrong about the actual corpus.
#[test]
fn the_real_definition_directories_plan_cleanly() {
    let base = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..");
    let roots = vec![
        base.join("pantheon-go/definitions"),
        base.join("pantheon-rs/definitions"),
    ];
    for r in &roots {
        if !r.exists() {
            eprintln!("skipping: {} not present", r.display());
            return;
        }
    }

    let store =
        FileStore::new(std::env::temp_dir().join("ptn-corpus-registry-does-not-exist.json"));
    let planned = plan(&roots, &store).unwrap();

    assert!(
        planned.is_applyable(),
        "the real definitions do not plan cleanly:\n{}",
        planned.diagnostics
    );
    assert!(
        planned.changes.len() >= 40,
        "expected the full corpus, got {} definitions",
        planned.changes.len()
    );
}

/// Orphans are reported and never applied.
#[test]
fn an_orphan_is_reported_but_not_removed() {
    let d = Dir::new("orphan");
    d.write("schemas/a.yaml", &schema("demo.A"));

    let mut store = d.registry();
    let first = plan(&d.roots(), &store).unwrap();
    store.apply(&first.to_apply).unwrap();

    fs::remove_file(d.root.join("schemas/a.yaml")).unwrap();

    let second = plan(&d.roots(), &store).unwrap();
    assert_eq!(second.counts().get(&Change::Orphan), Some(&1));
    assert!(
        second.is_applyable(),
        "an orphan is a report, not a validation failure"
    );

    // And it is still registered afterwards: removing a definition out from
    // under a mid-flight run is a deliberate act, not a side effect of apply.
    assert!(store
        .all()
        .unwrap()
        .contains_key(&"demo.A@1".parse().unwrap()));
}

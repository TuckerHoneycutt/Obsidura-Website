//! The rules a definition directory must satisfy before it can be applied.
//!
//! Every check here runs at PLAN time. That is the point of the plan step: the
//! alternative is discovering that two tasks disagree about the value crossing
//! their seam when the second one receives it, three minutes into a run, in
//! production.

use std::collections::HashMap;
use std::path::PathBuf;

use ptn_vocab::{Definition, Runner, TypeRef};

use crate::diag::{Diagnostic, Diagnostics, Rule};
use crate::load::Located;

/// Everything a directory declares, indexed for resolution.
#[derive(Debug, Default)]
pub struct Index {
    /// Task definitions by ref.
    pub tasks: HashMap<TypeRef, Located>,
    /// Trigger definitions by ref.
    pub triggers: HashMap<TypeRef, Located>,
    /// Resource definitions by ref.
    pub resources: HashMap<TypeRef, Located>,
    /// Agent spec definitions by ref.
    pub agent_specs: HashMap<TypeRef, Located>,
    /// Registered schema definitions by ref.
    pub schemas: HashMap<TypeRef, Located>,
}

impl Index {
    /// Resolves a resource by NAME, ignoring version.
    ///
    /// A task's `uses:` names a resource without pinning a version, because a
    /// resource is a connection to something that already exists rather than a
    /// contract that can be versioned independently. If that turns out to be
    /// wrong, this is the one place it changes.
    fn resource_by_name(&self, name: &str) -> Option<&Located> {
        self.resources
            .iter()
            .find(|(r, _)| r.name == name)
            .map(|(_, l)| l)
    }
}

/// Builds the index, reporting anything declared twice.
pub fn index(defs: &[Located], diags: &mut Diagnostics) -> Index {
    let mut idx = Index::default();

    for located in defs {
        let key = located.def.type_ref();
        let bucket = match &located.def {
            Definition::Task(_) => &mut idx.tasks,
            Definition::Trigger(_) => &mut idx.triggers,
            Definition::Resource(_) => &mut idx.resources,
            Definition::AgentSpec(_) => &mut idx.agent_specs,
            Definition::Schema(_) => &mut idx.schemas,
        };

        if let Some(previous) = bucket.get(&key) {
            diags.push(Diagnostic::new(
                &located.path,
                "name",
                Rule::DuplicateName,
                format!(
                    "{} {} is already declared in {}",
                    located.def.kind(),
                    key,
                    previous.path.display()
                ),
            ));
            continue;
        }
        bucket.insert(key, located.clone());
    }

    idx
}

/// Runs every rule over an indexed directory.
pub fn validate(defs: &[Located], idx: &Index) -> Diagnostics {
    let mut diags = Diagnostics::default();

    for located in defs {
        let path = &located.path;
        match &located.def {
            Definition::Task(task) => {
                check_schema_ref(idx, path, "input", &task.input, &mut diags);
                check_schema_ref(idx, path, "output", &task.output, &mut diags);
                check_uses(idx, path, task, &mut diags);
                check_runner(idx, path, task, &mut diags);
                check_on(idx, path, task, &mut diags);
                check_then(idx, path, task, &mut diags);
            }
            Definition::Trigger(trigger) => {
                check_schema_ref(idx, path, "emits", &trigger.emits, &mut diags);
            }
            Definition::AgentSpec(spec) => {
                check_schema_ref(idx, path, "output", &spec.output, &mut diags);
            }
            Definition::Resource(resource) => {
                if resource.verbs.is_empty() {
                    diags.push(Diagnostic::new(
                        path,
                        "verbs",
                        Rule::InvalidField,
                        "a resource exposing no verbs cannot be used by anything",
                    ));
                }
            }
            Definition::Schema(schema) => {
                if !schema.document.is_object() {
                    diags.push(Diagnostic::new(
                        path,
                        "document",
                        Rule::InvalidField,
                        "schema document must be a JSON Schema object",
                    ));
                }
                if let Some(refines) = &schema.refines {
                    // Refinement CHECKING is deferred (spec §11), but the ref
                    // must still resolve. A dangling pointer is worth catching
                    // even when what it points at is not yet inspected.
                    check_schema_ref(idx, path, "refines", refines, &mut diags);
                }
            }
        }
    }

    diags.sorted()
}

fn check_schema_ref(
    idx: &Index,
    path: &PathBuf,
    field: &str,
    reference: &TypeRef,
    diags: &mut Diagnostics,
) {
    if reference.is_empty() {
        diags.push(Diagnostic::new(
            path,
            field,
            Rule::InvalidField,
            "a schema ref is required; an unvalidatable value is what the contract system exists to prevent",
        ));
        return;
    }
    if !idx.schemas.contains_key(reference) {
        diags.push(Diagnostic::new(
            path,
            field,
            Rule::UnresolvedRef,
            format!("no registered schema {reference}"),
        ));
    }
}

fn check_uses(idx: &Index, path: &PathBuf, task: &ptn_vocab::Task, diags: &mut Diagnostics) {
    for (i, use_) in task.uses.iter().enumerate() {
        let Some(located) = idx.resource_by_name(&use_.name) else {
            diags.push(Diagnostic::new(
                path,
                format!("uses[{i}].name"),
                Rule::UnresolvedRef,
                format!("no resource named {:?} is declared", use_.name),
            ));
            continue;
        };
        let Definition::Resource(resource) = &located.def else {
            continue;
        };

        for verb in &use_.verbs {
            if !resource.verbs.contains(verb) {
                // The proxy would refuse this call at run time. Catching it at
                // plan time turns a production denial into a build error.
                diags.push(Diagnostic::new(
                    path,
                    format!("uses[{i}].verbs"),
                    Rule::UndeclaredVerb,
                    format!(
                        "resource {:?} does not expose verb {:?}; it exposes {:?}",
                        use_.name, verb, resource.verbs
                    ),
                ));
            }
        }
    }
}

fn check_runner(idx: &Index, path: &PathBuf, task: &ptn_vocab::Task, diags: &mut Diagnostics) {
    match &task.runner {
        Runner::Script { runtime, entry } => {
            if runtime.is_empty() {
                diags.push(Diagnostic::new(
                    path,
                    "runner.runtime",
                    Rule::InvalidField,
                    "a script runner must name its runtime",
                ));
            }
            if entry.is_empty() {
                diags.push(Diagnostic::new(
                    path,
                    "runner.entry",
                    Rule::InvalidField,
                    "a script runner must name its entry point",
                ));
            }
        }
        Runner::Agent { spec } => {
            if !idx.agent_specs.contains_key(spec) {
                diags.push(Diagnostic::new(
                    path,
                    "runner.spec",
                    Rule::UnresolvedRef,
                    format!("no agent spec {spec}"),
                ));
            }
        }
    }
}

fn check_on(idx: &Index, path: &PathBuf, task: &ptn_vocab::Task, diags: &mut Diagnostics) {
    let Some(on) = &task.on else { return };

    let Some(located) = idx.triggers.get(on) else {
        diags.push(Diagnostic::new(
            path,
            "on",
            Rule::UnresolvedRef,
            format!("no trigger {on}"),
        ));
        return;
    };
    let Definition::Trigger(trigger) = &located.def else {
        return;
    };

    // The trigger seam is a contract like any other: what the trigger emits is
    // what the task receives.
    if trigger.emits != task.input {
        diags.push(Diagnostic::new(
            path,
            "on",
            Rule::ContractMismatch,
            format!(
                "trigger {on} emits {} but this task declares input {}",
                trigger.emits, task.input
            ),
        ));
    }
}

fn check_then(idx: &Index, path: &PathBuf, task: &ptn_vocab::Task, diags: &mut Diagnostics) {
    for (i, next) in task.then.iter().enumerate() {
        let Some(located) = idx.tasks.get(next) else {
            diags.push(Diagnostic::new(
                path,
                format!("then[{i}]"),
                Rule::UnresolvedRef,
                format!("no task {next}"),
            ));
            continue;
        };
        let Definition::Task(consumer) = &located.def else {
            continue;
        };

        // ACCEPTANCE TEST 2, the plan-time half: a mismatched pair is rejected
        // before anything runs. Spec §7 offers a flat field-path mapping or an
        // adapter task as the two legal ways to bridge differing shapes;
        // neither is "hope they line up".
        if consumer.input != task.output {
            diags.push(Diagnostic::new(
                path,
                format!("then[{i}]"),
                Rule::ContractMismatch,
                format!(
                    "this task outputs {} but {} declares input {}; insert an adapter task or a field-path mapping",
                    task.output, next, consumer.input
                ),
            ));
        }
    }
}

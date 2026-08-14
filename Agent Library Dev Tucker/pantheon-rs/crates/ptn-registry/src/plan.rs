//! The diff `ptn plan` shows and `ptn apply` performs.

use std::collections::BTreeMap;
use std::fmt;
use std::path::PathBuf;

use ptn_vocab::{Definition, TypeRef};

use crate::diag::Diagnostics;
use crate::load;
use crate::store::Store;
use crate::validate;

/// What applying this plan would do to one definition.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Change {
    /// Not in the registry yet.
    Add,
    /// Registered, but the definition differs.
    Update,
    /// Registered already, and byte-identical. Nothing to do.
    Unchanged,
    /// Registered, but no longer present in the definition directories.
    ///
    /// Reported and NOT applied. Removing a definition out from under a run
    /// that is mid-flight is a different operation with different safety
    /// questions, and quietly folding it into apply would answer them by
    /// accident.
    Orphan,
}

impl fmt::Display for Change {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            Change::Add => "add",
            Change::Update => "update",
            Change::Unchanged => "unchanged",
            Change::Orphan => "orphan",
        })
    }
}

#[derive(Debug, Clone)]
/// One definition's fate under this plan.
pub struct PlannedChange {
    /// What would happen to it.
    pub change: Change,
    /// The definition's `kind:` discriminator.
    pub kind: &'static str,
    /// Its `name@version`.
    pub reference: TypeRef,
    /// Where it was authored. `None` for an orphan, which has no file left.
    pub file: Option<PathBuf>,
}

/// The result of planning a set of directories against a registry.
#[derive(Debug, Default)]
pub struct Plan {
    /// Every definition's fate, sorted by change then ref.
    pub changes: Vec<PlannedChange>,
    /// Everything that would prevent applying.
    pub diagnostics: Diagnostics,
    /// The definitions apply would register. Empty when diagnostics are present.
    pub to_apply: Vec<Definition>,
}

impl Plan {
    /// A plan with any diagnostic is not applyable. There is no --force: a
    /// definition that fails validation is a definition the executor cannot
    /// run, so applying it would only move the failure later.
    pub fn is_applyable(&self) -> bool {
        self.diagnostics.is_empty()
    }

    /// How many definitions fall into each change class.
    pub fn counts(&self) -> BTreeMap<Change, usize> {
        let mut out = BTreeMap::new();
        for c in &self.changes {
            *out.entry(c.change).or_insert(0) += 1;
        }
        out
    }

    /// Changes worth showing: everything except unchanged entries.
    pub fn interesting(&self) -> impl Iterator<Item = &PlannedChange> {
        self.changes
            .iter()
            .filter(|c| c.change != Change::Unchanged)
    }
}

/// Loads, validates and diffs.
pub fn plan(roots: &[PathBuf], store: &dyn Store) -> Result<Plan, crate::store::StoreError> {
    let loaded = load::load(roots);

    let mut diags = loaded.diags.clone();
    let idx = validate::index(&loaded.defs, &mut diags);
    for d in validate::validate(&loaded.defs, &idx).0 {
        diags.push(d);
    }

    let registered = store.all()?;
    let mut out = Plan {
        diagnostics: diags.sorted(),
        ..Default::default()
    };

    let mut seen: BTreeMap<TypeRef, ()> = BTreeMap::new();
    for located in &loaded.defs {
        let reference = located.def.type_ref();
        seen.insert(reference.clone(), ());

        let change = match registered.get(&reference) {
            None => Change::Add,
            Some(existing) if existing.def == located.def => Change::Unchanged,
            Some(_) => Change::Update,
        };
        out.changes.push(PlannedChange {
            change,
            kind: located.def.kind(),
            reference,
            file: Some(located.path.clone()),
        });
    }

    for (reference, entry) in &registered {
        if !seen.contains_key(reference) {
            out.changes.push(PlannedChange {
                change: Change::Orphan,
                kind: entry.def.kind(),
                reference: reference.clone(),
                file: None,
            });
        }
    }

    out.changes.sort_by(|a, b| {
        a.change
            .cmp(&b.change)
            .then_with(|| a.reference.cmp(&b.reference))
    });

    if out.is_applyable() {
        out.to_apply = loaded.defs.iter().map(|l| l.def.clone()).collect();
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Changes are grouped by class in the CLI's output, so the ordering is
    /// part of what a reader sees.
    #[test]
    fn change_classes_order_add_update_unchanged_orphan() {
        let mut v = vec![
            Change::Orphan,
            Change::Unchanged,
            Change::Update,
            Change::Add,
        ];
        v.sort();
        assert_eq!(
            v,
            vec![
                Change::Add,
                Change::Update,
                Change::Unchanged,
                Change::Orphan
            ]
        );
    }

    #[test]
    fn change_names_are_stable() {
        for (c, want) in [
            (Change::Add, "add"),
            (Change::Update, "update"),
            (Change::Unchanged, "unchanged"),
            (Change::Orphan, "orphan"),
        ] {
            assert_eq!(c.to_string(), want);
        }
    }

    fn planned(change: Change, name: &str) -> PlannedChange {
        PlannedChange {
            change,
            kind: "schema",
            reference: TypeRef::new(name, 1),
            file: None,
        }
    }

    #[test]
    fn counts_group_by_change_class() {
        let p = Plan {
            changes: vec![
                planned(Change::Add, "a"),
                planned(Change::Add, "b"),
                planned(Change::Unchanged, "c"),
            ],
            ..Default::default()
        };
        let counts = p.counts();
        assert_eq!(counts.get(&Change::Add), Some(&2));
        assert_eq!(counts.get(&Change::Unchanged), Some(&1));
        assert_eq!(counts.get(&Change::Orphan), None);
    }

    /// A plan over an unchanged tree should print nothing but a summary, or the
    /// signal is buried under forty-five unchanged lines.
    #[test]
    fn interesting_hides_unchanged_entries() {
        let p = Plan {
            changes: vec![
                planned(Change::Add, "a"),
                planned(Change::Unchanged, "b"),
                planned(Change::Orphan, "c"),
            ],
            ..Default::default()
        };
        let shown: Vec<_> = p.interesting().map(|c| c.reference.name.clone()).collect();
        assert_eq!(shown, vec!["a", "c"]);
    }

    /// There is no --force: a definition that fails validation is one the
    /// executor cannot run, so applying it would only move the failure later.
    #[test]
    fn a_plan_with_any_diagnostic_is_not_applyable() {
        let mut diagnostics = Diagnostics::default();
        assert!(Plan {
            diagnostics: diagnostics.clone(),
            ..Default::default()
        }
        .is_applyable());

        diagnostics.push(crate::Diagnostic::new(
            "x.yaml",
            "input",
            crate::Rule::UnresolvedRef,
            "nope",
        ));
        assert!(!Plan {
            diagnostics,
            ..Default::default()
        }
        .is_applyable());
    }
}

//! Located diagnostics.
//!
//! Spec §7: "Invalid definitions are rejected at plan time with errors naming
//! the file, field, and rule violated." All three, every time — that is the
//! whole requirement, and it is why this is a struct rather than a string.
//!
//! A diagnostic that says "invalid definition" sends the author to read their
//! whole directory. One that says which file, which field, and which rule sends
//! them to a line.

use std::fmt;
use std::path::{Path, PathBuf};

/// A rule identifier. Stable strings, so a diagnostic can be grepped for and a
/// test can assert on the rule rather than on prose that will be reworded.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Rule {
    /// The file is not parseable as a definition.
    Unparseable,
    /// Two definitions claim the same name@version.
    DuplicateName,
    /// A ref points at something no definition declares.
    UnresolvedRef,
    /// A task uses a verb its resource does not expose.
    UndeclaredVerb,
    /// Two wired tasks disagree about the value crossing their seam.
    ContractMismatch,
    /// A field is required and absent, or present and unusable.
    InvalidField,
}

impl Rule {
    /// The stable kebab-case identifier, as printed.
    pub fn as_str(self) -> &'static str {
        match self {
            Rule::Unparseable => "unparseable",
            Rule::DuplicateName => "duplicate-name",
            Rule::UnresolvedRef => "unresolved-ref",
            Rule::UndeclaredVerb => "undeclared-verb",
            Rule::ContractMismatch => "contract-mismatch",
            Rule::InvalidField => "invalid-field",
        }
    }
}

impl fmt::Display for Rule {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// One located problem.
#[derive(Debug, Clone, PartialEq)]
pub struct Diagnostic {
    /// The file the problem is in.
    pub file: PathBuf,
    /// Dotted path to the offending field, e.g. `uses[0].verbs`. Empty only
    /// when the whole file is the problem.
    pub field: String,
    /// Which rule was violated.
    pub rule: Rule,
    /// What went wrong, in a sentence an author can act on.
    pub message: String,
}

impl Diagnostic {
    /// Builds a diagnostic.
    pub fn new(
        file: impl AsRef<Path>,
        field: impl Into<String>,
        rule: Rule,
        message: impl Into<String>,
    ) -> Self {
        Self {
            file: file.as_ref().to_path_buf(),
            field: field.into(),
            rule,
            message: message.into(),
        }
    }
}

impl fmt::Display for Diagnostic {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.field.is_empty() {
            write!(
                f,
                "{}: {}: {}",
                self.file.display(),
                self.rule,
                self.message
            )
        } else {
            write!(
                f,
                "{}: {}: {}: {}",
                self.file.display(),
                self.field,
                self.rule,
                self.message
            )
        }
    }
}

/// Diagnostics collected over a whole directory.
///
/// Every problem is reported, not just the first. An author fixing one error
/// per plan run is an author who stops running plan.
#[derive(Debug, Default, Clone)]
pub struct Diagnostics(pub Vec<Diagnostic>);

impl Diagnostics {
    /// Records one more problem.
    pub fn push(&mut self, d: Diagnostic) {
        self.0.push(d);
    }

    /// True when nothing was found wrong.
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// How many problems were found.
    pub fn len(&self) -> usize {
        self.0.len()
    }

    /// Iterates the problems in report order.
    pub fn iter(&self) -> std::slice::Iter<'_, Diagnostic> {
        self.0.iter()
    }

    /// Sorted by file then field, so two runs over the same directory produce
    /// the same report and a diff of plan output means something.
    pub fn sorted(mut self) -> Self {
        self.0.sort_by(|a, b| {
            a.file
                .cmp(&b.file)
                .then_with(|| a.field.cmp(&b.field))
                .then_with(|| a.message.cmp(&b.message))
        });
        self
    }

    /// True when any diagnostic reports the given rule.
    pub fn has_rule(&self, rule: Rule) -> bool {
        self.0.iter().any(|d| d.rule == rule)
    }
}

impl fmt::Display for Diagnostics {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        for d in &self.0 {
            writeln!(f, "  {d}")?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Spec §7 requires file, field and rule in every rejection. The format is
    /// what an author actually reads, so it is pinned rather than left to drift.
    #[test]
    fn display_names_file_field_and_rule() {
        let d = Diagnostic::new(
            "tasks/x.yaml",
            "uses[0].verbs",
            Rule::UndeclaredVerb,
            "nope",
        );
        assert_eq!(
            d.to_string(),
            "tasks/x.yaml: uses[0].verbs: undeclared-verb: nope"
        );
    }

    #[test]
    fn a_whole_file_problem_omits_the_field_slot() {
        let d = Diagnostic::new("tasks/x.yaml", "", Rule::Unparseable, "bad yaml");
        assert_eq!(d.to_string(), "tasks/x.yaml: unparseable: bad yaml");
    }

    #[test]
    fn rule_identifiers_are_stable_kebab_case() {
        // Tests and greps depend on these strings; renaming one is a breaking
        // change to anything parsing plan output.
        for (rule, want) in [
            (Rule::Unparseable, "unparseable"),
            (Rule::DuplicateName, "duplicate-name"),
            (Rule::UnresolvedRef, "unresolved-ref"),
            (Rule::UndeclaredVerb, "undeclared-verb"),
            (Rule::ContractMismatch, "contract-mismatch"),
            (Rule::InvalidField, "invalid-field"),
        ] {
            assert_eq!(rule.as_str(), want);
            assert_eq!(rule.to_string(), want);
        }
    }

    #[test]
    fn sorting_is_by_file_then_field_then_message() {
        let mut d = Diagnostics::default();
        d.push(Diagnostic::new(
            "b.yaml",
            "output",
            Rule::UnresolvedRef,
            "z",
        ));
        d.push(Diagnostic::new(
            "a.yaml",
            "output",
            Rule::UnresolvedRef,
            "y",
        ));
        d.push(Diagnostic::new("a.yaml", "input", Rule::UnresolvedRef, "x"));

        let sorted = d.sorted();
        let order: Vec<String> = sorted
            .iter()
            .map(|d| format!("{}:{}", d.file.display(), d.field))
            .collect();
        // Two runs over one directory must report in the same order, or a diff
        // of plan output is noise.
        assert_eq!(
            order,
            vec!["a.yaml:input", "a.yaml:output", "b.yaml:output"]
        );
    }

    #[test]
    fn empty_and_len_track_contents() {
        let mut d = Diagnostics::default();
        assert!(d.is_empty());
        assert_eq!(d.len(), 0);
        d.push(Diagnostic::new("a", "b", Rule::InvalidField, "c"));
        assert!(!d.is_empty());
        assert_eq!(d.len(), 1);
        assert!(d.has_rule(Rule::InvalidField));
        assert!(!d.has_rule(Rule::DuplicateName));
    }

    #[test]
    fn display_indents_each_line_for_the_cli() {
        let mut d = Diagnostics::default();
        d.push(Diagnostic::new("a.yaml", "input", Rule::UnresolvedRef, "x"));
        d.push(Diagnostic::new("b.yaml", "input", Rule::UnresolvedRef, "y"));
        let out = d.to_string();
        assert_eq!(out.lines().count(), 2);
        assert!(out.lines().all(|l| l.starts_with("  ")));
    }
}

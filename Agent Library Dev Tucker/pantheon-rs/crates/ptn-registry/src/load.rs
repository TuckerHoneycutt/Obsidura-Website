//! Walking a definition directory and parsing what is in it.

use std::fs;
use std::path::{Path, PathBuf};

use ptn_vocab::Definition;

use crate::diag::{Diagnostic, Diagnostics, Rule};

/// One definition and where it came from.
///
/// The path travels with the definition all the way to the diagnostic. A
/// validation error that cannot name its file is a validation error the author
/// has to hunt for.
#[derive(Debug, Clone)]
pub struct Located {
    /// Where it was read from. Travels all the way to the diagnostic.
    pub path: PathBuf,
    /// The parsed definition.
    pub def: Definition,
}

/// Everything a directory contained, plus everything wrong with it.
#[derive(Debug, Default)]
pub struct Loaded {
    /// Successfully parsed definitions, sorted by path.
    pub defs: Vec<Located>,
    /// Problems found while reading and parsing.
    pub diags: Diagnostics,
}

/// Loads every `.yaml` / `.yml` file under the given roots.
///
/// Multiple roots on purpose: generated definitions and hand-authored wiring
/// live in different directories with different rules about who may edit them,
/// and they still form one registry. Go owns what an action *is*; YAML owns how
/// actions are *wired*.
pub fn load(roots: &[PathBuf]) -> Loaded {
    let mut out = Loaded::default();
    for root in roots {
        if !root.exists() {
            out.diags.push(Diagnostic::new(
                root,
                "",
                Rule::InvalidField,
                "definition directory does not exist",
            ));
            continue;
        }
        walk(root, &mut out);
    }
    // Sorted so a plan over the same tree reports the same order every run.
    out.defs.sort_by(|a, b| a.path.cmp(&b.path));
    out
}

fn walk(dir: &Path, out: &mut Loaded) {
    let entries = match fs::read_dir(dir) {
        Ok(e) => e,
        Err(e) => {
            out.diags.push(Diagnostic::new(
                dir,
                "",
                Rule::InvalidField,
                format!("cannot read directory: {e}"),
            ));
            return;
        }
    };

    let mut paths: Vec<PathBuf> = entries.filter_map(|e| e.ok()).map(|e| e.path()).collect();
    paths.sort();

    for path in paths {
        if path.is_dir() {
            walk(&path, out);
            continue;
        }
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        if ext != "yaml" && ext != "yml" {
            continue;
        }
        load_file(&path, out);
    }
}

fn load_file(path: &Path, out: &mut Loaded) {
    let body = match fs::read_to_string(path) {
        Ok(b) => b,
        Err(e) => {
            out.diags.push(Diagnostic::new(
                path,
                "",
                Rule::Unparseable,
                format!("cannot read file: {e}"),
            ));
            return;
        }
    };

    match serde_norway::from_str::<Definition>(&body) {
        Ok(def) => out.defs.push(Located {
            path: path.to_path_buf(),
            def,
        }),
        Err(e) => {
            // serde_norway reports a location for most failures. Carrying it
            // into the field slot is the difference between "this file is
            // wrong" and "line 12 is wrong".
            let field = match e.location() {
                Some(loc) => format!("line {}, column {}", loc.line(), loc.column()),
                None => String::new(),
            };
            out.diags.push(Diagnostic::new(
                path,
                field,
                Rule::Unparseable,
                e.to_string(),
            ));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diag::Rule;

    struct Dir(PathBuf);

    impl Dir {
        fn new(name: &str) -> Self {
            let root = std::env::temp_dir().join(format!("ptn-load-{name}-{}", std::process::id()));
            let _ = fs::remove_dir_all(&root);
            fs::create_dir_all(&root).unwrap();
            Dir(root)
        }
        fn write(&self, rel: &str, body: &str) -> &Self {
            let p = self.0.join(rel);
            fs::create_dir_all(p.parent().unwrap()).unwrap();
            fs::write(p, body).unwrap();
            self
        }
    }

    impl Drop for Dir {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    const SCHEMA: &str =
        "kind: schema\nname: demo.A\nversion: 1\ndocument: {\"type\":\"object\"}\n";

    #[test]
    fn walks_nested_directories() {
        let d = Dir::new("nested");
        d.write("a/b/c/one.yaml", SCHEMA);
        let loaded = load(std::slice::from_ref(&d.0));
        assert_eq!(loaded.defs.len(), 1);
        assert!(loaded.diags.is_empty());
    }

    #[test]
    fn accepts_both_yaml_extensions_and_ignores_everything_else() {
        let d = Dir::new("exts");
        d.write("one.yaml", SCHEMA)
            .write(
                "two.yml",
                "kind: schema\nname: demo.B\nversion: 1\ndocument: {}\n",
            )
            .write("notes.md", "# not a definition")
            .write("old.json", "{\"kind\":\"schema\"}");

        let loaded = load(std::slice::from_ref(&d.0));
        assert_eq!(
            loaded.defs.len(),
            2,
            "only .yaml and .yml are definitions; other files are documentation"
        );
        assert!(loaded.diags.is_empty(), "{}", loaded.diags);
    }

    /// A plan over the same tree must report the same order every run, or a
    /// diff of plan output is noise.
    #[test]
    fn results_are_sorted_by_path() {
        let d = Dir::new("sorted");
        d.write("z.yaml", SCHEMA)
            .write(
                "a.yaml",
                "kind: schema\nname: demo.B\nversion: 1\ndocument: {}\n",
            )
            .write(
                "m.yaml",
                "kind: schema\nname: demo.C\nversion: 1\ndocument: {}\n",
            );

        let paths: Vec<String> = load(std::slice::from_ref(&d.0))
            .defs
            .iter()
            .map(|l| l.path.file_name().unwrap().to_string_lossy().into_owned())
            .collect();
        assert_eq!(paths, vec!["a.yaml", "m.yaml", "z.yaml"]);
    }

    #[test]
    fn multiple_roots_form_one_set() {
        let a = Dir::new("root-a");
        let b = Dir::new("root-b");
        a.write("one.yaml", SCHEMA);
        b.write(
            "two.yaml",
            "kind: schema\nname: demo.B\nversion: 1\ndocument: {}\n",
        );

        let loaded = load(&[a.0.clone(), b.0.clone()]);
        assert_eq!(loaded.defs.len(), 2);
    }

    /// A typo'd path must not silently plan zero definitions and report
    /// "no changes".
    #[test]
    fn a_missing_directory_is_reported() {
        let loaded = load(&[PathBuf::from("/definitely/not/here")]);
        assert!(loaded.defs.is_empty());
        assert_eq!(loaded.diags.len(), 1);
        assert!(loaded.diags.has_rule(Rule::InvalidField));
    }

    #[test]
    fn a_parse_failure_carries_a_line_and_does_not_stop_the_walk() {
        let d = Dir::new("parse");
        d.write("aaa-bad.yaml", "kind: task\nname: [unclosed\n")
            .write("zzz-good.yaml", SCHEMA);

        let loaded = load(std::slice::from_ref(&d.0));
        assert_eq!(
            loaded.defs.len(),
            1,
            "one bad file must not stop the others being read"
        );
        let diag = loaded
            .diags
            .iter()
            .find(|x| x.rule == Rule::Unparseable)
            .expect("expected an unparseable diagnostic");
        assert!(diag.field.contains("line"), "{diag}");
    }

    #[test]
    fn an_empty_directory_yields_nothing_and_no_complaint() {
        let d = Dir::new("empty");
        let loaded = load(std::slice::from_ref(&d.0));
        assert!(loaded.defs.is_empty());
        assert!(loaded.diags.is_empty());
    }
}
